import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from academic.models import PreprintHideProposal, ReviewBatch
from academic.publish.batches import create_batch, open_batch, reviewable_items
from tests.factories import PublicationFactory


def make_pub(user, **kw):
    return PublicationFactory(owner=user, **kw)


def make_proposal(user, status='pending'):
    return PreprintHideProposal.objects.create(
        owner=user,
        preprint=make_pub(user, is_preprint=True),
        published=make_pub(user),
        method='crossref_relation',
        status=status,
    )


def new_batch(user, pr_number=1, pubs=(), proposals=()):
    return create_batch(
        user, pr_number, f'review/{pr_number}', 'site/x.yaml',
        list(pubs), list(proposals), timezone.now(),
    )


def test_open_batch_none_when_all_decided(academic_user):
    batch = new_batch(academic_user)
    batch.status = 'merged'
    batch.save()
    assert open_batch(academic_user) is None


def test_reviewable_items_lists_pending_only(academic_user, second_academic_user):
    p2 = make_pub(academic_user, review_status='pending')
    p1 = make_pub(academic_user, review_status='pending')
    make_pub(academic_user, review_status='approved')
    make_pub(academic_user, review_status='pending', is_ignored=True)
    make_pub(second_academic_user, review_status='pending')
    q1 = make_proposal(academic_user)
    make_proposal(academic_user, status='confirmed')
    make_proposal(academic_user, status='rejected')
    make_proposal(second_academic_user)
    pubs, proposals = reviewable_items(academic_user)
    assert pubs == sorted([p1, p2], key=lambda p: p.id)
    assert proposals == [q1]


def test_create_batch_links_items(academic_user, second_academic_user):
    pub = make_pub(academic_user, review_status='pending')
    prop = make_proposal(academic_user)
    now = timezone.now()
    batch = create_batch(academic_user, 7, 'br', 'p.yaml', [pub], [prop], now)
    assert batch.status == 'open'
    assert batch.opened_at == now
    assert batch.pr_number == 7
    assert list(batch.publications.all()) == [pub]
    assert list(batch.proposals.all()) == [prop]
    assert open_batch(academic_user) == batch
    assert open_batch(second_academic_user) is None


def test_pr_number_unique(academic_user):
    new_batch(academic_user, pr_number=5)
    with pytest.raises(IntegrityError), transaction.atomic():
        new_batch(academic_user, pr_number=5)


def test_deleting_rejected_pub_removes_it_from_batch(academic_user):
    keep = make_pub(academic_user, review_status='pending')
    gone = make_pub(academic_user, review_status='pending')
    batch = new_batch(academic_user, pubs=[keep, gone])
    gone.delete()
    assert ReviewBatch.objects.filter(pk=batch.pk).exists()
    assert list(batch.publications.all()) == [keep]
