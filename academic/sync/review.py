"""State transitions applied when the owner decides a review PR.

Each transition re-fetches (and row-locks) its target inside the
transaction, so decisions are made against current database state. The
caller's in-memory objects may therefore be stale after a call.
"""
from datetime import datetime

from django.db import transaction

from academic.models import PreprintHideProposal, Publication
from academic.tombstones import record_tombstone


def _fresh_pending_pub(pub: Publication) -> Publication:
    fresh = Publication.objects.select_for_update().get(pk=pub.pk)
    if fresh.review_status != 'pending':
        raise ValueError(f'Publication {pub.pk} is not pending review')
    return fresh


def _fresh_pending_proposal(proposal: PreprintHideProposal) -> PreprintHideProposal:
    fresh = (
        PreprintHideProposal.objects.select_for_update()
        .select_related('preprint', 'published')
        .get(pk=proposal.pk)
    )
    if fresh.status != 'pending':
        raise ValueError(f'Proposal {proposal.pk} is not pending')
    return fresh


@transaction.atomic
def approve_pending(pub: Publication) -> None:
    fresh = _fresh_pending_pub(pub)
    fresh.review_status = 'approved'
    fresh.save(update_fields=['review_status'])
    pub.review_status = 'approved'


@transaction.atomic
def reject_pending(pub: Publication) -> None:
    fresh = _fresh_pending_pub(pub)
    record_tombstone(fresh, 'rejected')
    fresh.delete()


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
    fresh = _fresh_pending_proposal(proposal)
    _hide_preprint(fresh, now)
    _decide(fresh, 'confirmed', now)
    PreprintHideProposal.objects.filter(
        preprint_id=fresh.preprint_id, status='pending'
    ).exclude(pk=fresh.pk).update(status='rejected', decided_at=now)


@transaction.atomic
def reject_hide(proposal: PreprintHideProposal, now: datetime) -> None:
    _decide(_fresh_pending_proposal(proposal), 'rejected', now)
