"""Review batch state: which pending items are out for review."""
from academic.models import Publication, PreprintHideProposal, ReviewBatch


def open_batch(user):
    """Return the user's open batch, or None."""
    return (
        ReviewBatch.objects.filter(owner=user, status='open')
        .order_by('-opened_at', '-id')
        .first()
    )


def reviewable_items(user):
    """Return (pending publications, pending hide proposals), ordered by id."""
    pubs = Publication.objects.filter(
        owner=user, review_status='pending', is_ignored=False
    ).order_by('id')
    proposals = PreprintHideProposal.objects.filter(
        owner=user, status='pending'
    ).order_by('id')
    return list(pubs), list(proposals)


def create_batch(user, pr_number, branch, path, pubs, proposals, now):
    """Record a new open batch linking the given items."""
    batch = ReviewBatch.objects.create(
        owner=user, status='open', pr_number=pr_number,
        branch=branch, path=path, opened_at=now,
    )
    batch.publications.set(pubs)
    batch.proposals.set(proposals)
    return batch
