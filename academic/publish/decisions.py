"""Apply the owner's review decisions when the review PR is merged or closed.

The batch's items are snapshotted (with their record keys) before any
change, because rejecting a pending publication deletes it and cascades
to proposals that point at it. Hides are decided before publications for
the same reason. An item that is gone or no longer pending was decided
elsewhere and is skipped.
"""
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
    keys = set()
    for entry in entries:
        key = record_key(entry) if isinstance(entry, dict) else ''
        if not key:
            raise ReviewFileError(f'Unidentifiable entry under "{name}"')
        keys.add(key)
    return keys


def parse_review_file(text):
    data = _load(text)
    new, hide = (_section_keys(data, name) for name in SECTIONS)
    return new, hide


# Snapshot

def _pub_key(pub):
    return record_key(site_record(pub))


def _snapshot(batch):
    pubs = list(batch.publications.order_by('id'))
    proposals = list(batch.proposals.select_related('preprint')
                     .order_by('id'))
    pub_keys = {p.id: _pub_key(p) for p in pubs}
    items = [_ProposalItem(p.id, p.preprint_id, p.published_id)
             for p in proposals]
    preprint_keys = {p.preprint_id: _pub_key(p.preprint) for p in proposals}
    return pub_keys, items, preprint_keys


# Individual decisions (skip what was decided elsewhere)

def _try(transition, model, pk, *args):
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return False
    try:
        transition(obj, *args)
    except ValueError:
        return False
    return True


def _hide(item, now, decisions):
    if _try(confirm_hide, PreprintHideProposal, item.id, now):
        decisions.hidden.append(item.preprint_id)


def _keep(item, now, decisions):
    if _try(reject_hide, PreprintHideProposal, item.id, now):
        decisions.kept.append(item.preprint_id)


def _approve(pub_id, decisions):
    if _try(approve_pending, Publication, pub_id):
        decisions.approved.append(pub_id)


def _reject(pub_id, decisions):
    if _try(reject_pending, Publication, pub_id):
        decisions.rejected.append(pub_id)


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


def _hide_wanted(item, pub_keys, preprint_keys, new, hide):
    if item.published_id in pub_keys and pub_keys[item.published_id] not in new:
        return False
    return preprint_keys[item.preprint_id] in hide


def _decide_merged(snapshot, new, hide, now):
    pub_keys, items, preprint_keys = snapshot
    decisions = Decisions()
    for item in items:
        if _hide_wanted(item, pub_keys, preprint_keys, new, hide):
            _hide(item, now, decisions)
        else:
            _keep(item, now, decisions)
    for pub_id, key in pub_keys.items():
        if key in new:
            _approve(pub_id, decisions)
        else:
            _reject(pub_id, decisions)
    return decisions


def _decide_closed(snapshot, now):
    pub_keys, items, _ = snapshot
    decisions = Decisions()
    for item in items:
        _keep(item, now, decisions)
    for pub_id in pub_keys:
        _reject(pub_id, decisions)
    return decisions


def apply_merged(batch, text, now):
    new, hide = parse_review_file(text)
    with transaction.atomic():
        fresh = _lock_open(batch)
        decisions = _decide_merged(_snapshot(fresh), new, hide, now)
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
