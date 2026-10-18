"""State transitions applied when the owner decides a review PR."""
from datetime import datetime

from django.db import transaction

from academic.models import PreprintHideProposal, Publication
from academic.tombstones import record_tombstone


def _require_pending_pub(pub: Publication) -> None:
    if pub.review_status != 'pending':
        raise ValueError(f'Publication {pub.pk} is not pending review')


def _require_pending_proposal(proposal: PreprintHideProposal) -> None:
    if proposal.status != 'pending':
        raise ValueError(f'Proposal {proposal.pk} is not pending')


@transaction.atomic
def approve_pending(pub: Publication) -> None:
    _require_pending_pub(pub)
    pub.review_status = 'approved'
    pub.save(update_fields=['review_status'])


@transaction.atomic
def reject_pending(pub: Publication) -> None:
    _require_pending_pub(pub)
    record_tombstone(pub, 'rejected')
    pub.delete()


def _hide_preprint(proposal: PreprintHideProposal, now: datetime) -> None:
    preprint, published = proposal.preprint, proposal.published
    metadata = dict(preprint.metadata or {})
    metadata['hidden_by'] = {
        'method': 'pipeline_review',
        'proposal_id': proposal.id,
        'confirmed_at': now.isoformat(),
        'published_doi': published.doi,
    }
    preprint.is_ignored = True
    preprint.ignore_reason = f'Published as {published.doi}'
    preprint.metadata = metadata
    preprint.save(update_fields=['is_ignored', 'ignore_reason', 'metadata'])


def _decide(proposal: PreprintHideProposal, status: str, now: datetime) -> None:
    proposal.status = status
    proposal.decided_at = now
    proposal.save(update_fields=['status', 'decided_at'])


@transaction.atomic
def confirm_hide(proposal: PreprintHideProposal, now: datetime) -> None:
    _require_pending_proposal(proposal)
    _hide_preprint(proposal, now)
    _decide(proposal, 'confirmed', now)
    PreprintHideProposal.objects.filter(
        preprint_id=proposal.preprint_id, status='pending'
    ).exclude(pk=proposal.pk).update(status='rejected', decided_at=now)


@transaction.atomic
def reject_hide(proposal: PreprintHideProposal, now: datetime) -> None:
    _require_pending_proposal(proposal)
    _decide(proposal, 'rejected', now)
