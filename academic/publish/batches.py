"""Review batch state: which pending items are out for review."""
from django.db import transaction

from academic.models import Publication, PreprintHideProposal, ReviewBatch
from academic.publish.site_yaml import record_key, site_record


def open_batch(user):
    """Return the user's open batch, or None."""
    return (
        ReviewBatch.objects.filter(owner=user, status='open')
        .order_by('-opened_at', '-id')
        .first()
    )


def _has_key(pub):
    return bool(record_key(site_record(pub)))


def reviewable_items(user):
    """Return (pending publications, pending hide proposals), ordered by id.

    Items with no record key (no DOI and no PMID) cannot be matched back
    from the review file, so they are left out and stay pending.
    """
    pubs = Publication.objects.filter(
        owner=user, review_status='pending', is_ignored=False
    ).order_by('id')
    proposals = PreprintHideProposal.objects.filter(
        owner=user, status='pending'
    ).select_related('preprint').order_by('id')
    return ([p for p in pubs if _has_key(p)],
            [p for p in proposals if _has_key(p.preprint)])


def create_batch(user, pr_number, branch, path, pubs, proposals, now):
    """Record a new open batch linking the given items."""
    with transaction.atomic():
        batch = ReviewBatch.objects.create(
            owner=user, status='open', pr_number=pr_number,
            branch=branch, path=path, opened_at=now,
        )
        batch.publications.set(pubs)
        batch.proposals.set(proposals)
    return batch
