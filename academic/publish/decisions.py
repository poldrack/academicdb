"""Apply the owner's review decisions when the review PR is merged or closed.

The batch's items are snapshotted (with their record keys) before any
change, because rejecting a pending publication deletes it and cascades
to proposals that point at it. Hides are decided before publications for
the same reason. An item that is gone or no longer pending was decided
elsewhere and is skipped.
"""
from collections import Counter
from dataclasses import dataclass, field

import yaml
from django.db import transaction

from academic.models import PreprintHideProposal, Publication, ReviewBatch
from academic.publish.site_yaml import record_key, site_record
from academic.sync.review import (
    approve_pending, confirm_hide, reject_hide, reject_pending,
)

DELETE_MESSAGE = 'Remove processed review file'
SECTIONS = ('new', 'hide')


class ReviewFileError(Exception):
    """The review file is missing or not in the expected shape."""


@dataclass
class Decisions:
    approved: list[int] = field(default_factory=list)
    rejected: list[int] = field(default_factory=list)
    hidden: list[int] = field(default_factory=list)
    kept: list[int] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    undecided: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class _ProposalItem:
    id: int
    preprint_id: int
    published_id: int


# Parsing

def _load(text):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ReviewFileError('Review file is not valid YAML') from exc
    if not isinstance(data, dict):
        raise ReviewFileError('Review file must be a mapping')
    return data


def _section_keys(data, name):
    entries = data.get(name)
    if not isinstance(entries, list):
        raise ReviewFileError(f'Review file needs a "{name}" list')
    if not all(isinstance(entry, dict) for entry in entries):
        raise ReviewFileError(f'Non-mapping entry under "{name}"')
    return {record_key(entry) for entry in entries} - {''}


def parse_review_file(text):
    """Return the record keys under "new" and "hide"; keyless entries skip."""
    data = _load(text)
    new, hide = (_section_keys(data, name) for name in SECTIONS)
    return new, hide


# Snapshot

def _pub_key(pub):
    return record_key(site_record(pub))


@dataclass
class _Plan:
    pub_keys: dict
    items: list
    preprint_keys: dict
    new: set = field(default_factory=set)
    hide: set = field(default_factory=set)
    unmatched: list = field(default_factory=list)
    dup_pubs: set = field(default_factory=set)
    dup_preprints: set = field(default_factory=set)

    def kept(self, pub_id):
        return self.pub_keys[pub_id] in self.new

    def reported(self):
        """Keys the owner is told about: edited entries and shared keys."""
        return sorted(set(self.unmatched) | self.dup_pubs
                      | self.dup_preprints)

    def pub_on_hold(self, pub_id):
        if self.pub_keys[pub_id] in self.dup_pubs:
            return True
        return bool(self.unmatched) and not self.kept(pub_id)

    def proposal_on_hold(self, item):
        key = self.preprint_keys[item.preprint_id]
        if key in self.dup_preprints:
            return True
        if (item.published_id in self.pub_keys
                and self.pub_on_hold(item.published_id)):
            return True
        return bool(self.unmatched) and key not in self.hide


def _snapshot(batch):
    pubs = list(batch.publications.order_by('id'))
    proposals = list(batch.proposals.select_related('preprint')
                     .order_by('id'))
    return _Plan(
        pub_keys={p.id: _pub_key(p) for p in pubs},
        items=[_ProposalItem(p.id, p.preprint_id, p.published_id)
               for p in proposals],
        preprint_keys={p.preprint_id: _pub_key(p.preprint)
                       for p in proposals},
    )


def _repeated(keys):
    return {key for key, count in Counter(keys).items() if count > 1}


def _mark_duplicates(plan):
    """Items sharing a key cannot tell which entry was deleted: hold them."""
    plan.dup_pubs = _repeated(plan.pub_keys.values())
    plan.dup_preprints = _repeated(
        plan.preprint_keys[item.preprint_id] for item in plan.items)
    return plan


def _with_file(plan, new, hide):
    plan.new, plan.hide = new, hide
    plan.unmatched = sorted((new - set(plan.pub_keys.values()))
                            | (hide - set(plan.preprint_keys.values())))
    return plan


# Re-fetching (an item gone or no longer pending was decided elsewhere)

def _locked(model, pk):
    return model.objects.select_for_update().filter(pk=pk).first()


def _pending_pub(pk):
    pub = _locked(Publication, pk)
    return pub if pub and pub.review_status == 'pending' else None


def _pending_proposal(pk):
    proposal = _locked(PreprintHideProposal, pk)
    return proposal if proposal and proposal.status == 'pending' else None


# Individual decisions

def _target_ok(item, plan):
    """The published target will be visible once this batch is decided."""
    target = Publication.objects.filter(pk=item.published_id).first()
    if target is None or target.is_ignored:
        return False
    if item.published_id in plan.pub_keys:
        return plan.kept(item.published_id) and target.review_status in (
            'approved', 'pending')
    return target.review_status == 'approved'


def _decide_hide(item, plan, now, decisions):
    proposal = _pending_proposal(item.id)
    if proposal is None:
        return
    wanted = plan.preprint_keys[item.preprint_id] in plan.hide
    if wanted and _target_ok(item, plan):
        confirm_hide(proposal, now)
        decisions.hidden.append(item.preprint_id)
    else:
        reject_hide(proposal, now)
        decisions.kept.append(item.preprint_id)


def _decide_pub(pub_id, plan, decisions):
    pub = _pending_pub(pub_id)
    if pub is None:
        return
    if plan.kept(pub_id):
        approve_pending(pub)
        decisions.approved.append(pub_id)
    else:
        reject_pending(pub)
        decisions.rejected.append(pub_id)


def _hold_hide(item, decisions):
    if _pending_proposal(item.id) is not None:
        decisions.undecided.append(item.preprint_id)


def _hold_pub(pub_id, decisions):
    if _pending_pub(pub_id) is not None:
        decisions.undecided.append(pub_id)


def _decide_merged(plan, now):
    decisions = Decisions(unmatched=plan.reported())
    for item in plan.items:
        if plan.proposal_on_hold(item):
            _hold_hide(item, decisions)
        else:
            _decide_hide(item, plan, now, decisions)
    for pub_id in plan.pub_keys:
        if plan.pub_on_hold(pub_id):
            _hold_pub(pub_id, decisions)
        else:
            _decide_pub(pub_id, plan, decisions)
    return decisions


def _decide_closed(plan, now):
    """Closing rejects everything: an empty file with nothing unmatched."""
    return _decide_merged(_with_file(plan, set(), set()), now)


# Batch-level application

def _lock_open(batch):
    fresh = ReviewBatch.objects.select_for_update().get(pk=batch.pk)
    if fresh.status != 'open':
        raise ValueError(f'Review batch {batch.pk} is already {fresh.status}')
    return fresh


def _finish(batch, fresh, status, now):
    fresh.status, fresh.decided_at = status, now
    fresh.save(update_fields=['status', 'decided_at'])
    batch.status, batch.decided_at = status, now


def apply_merged(batch, text, now):
    new, hide = parse_review_file(text)
    with transaction.atomic():
        fresh = _lock_open(batch)
        plan = _mark_duplicates(_with_file(_snapshot(fresh), new, hide))
        decisions = _decide_merged(plan, now)
        _finish(batch, fresh, 'merged', now)
    return decisions


def apply_closed(batch, now):
    with transaction.atomic():
        fresh = _lock_open(batch)
        decisions = _decide_closed(_snapshot(fresh), now)
        _finish(batch, fresh, 'closed', now)
    return decisions


# Pull request driver

def _merged_text(batch, gh, repo, pr):
    found = gh.get_file(repo, batch.path, ref=pr['merge_commit_sha'])
    if found is None:
        raise ReviewFileError(
            f'Review file {batch.path} is missing at the merge commit')
    return found.text


def _delete_review_file(batch, gh, repo):
    current = gh.get_file(repo, batch.path, ref='main')
    if current is not None:
        gh.delete_file(repo, batch.path, DELETE_MESSAGE, current.sha,
                       branch='main')


def process_pr(batch, gh, repo, now):
    if batch.status != 'open':
        return None
    pr = gh.get_pr(repo, batch.pr_number)
    if pr.get('state') == 'open':
        return None
    if not pr.get('merged'):
        return apply_closed(batch, now)
    decisions = apply_merged(batch, _merged_text(batch, gh, repo, pr), now)
    _delete_review_file(batch, gh, repo)
    return decisions
