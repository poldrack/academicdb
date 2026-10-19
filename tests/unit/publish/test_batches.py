import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from academic.admin import ReviewBatchAdmin

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


def test_reviewable_items_excludes_keyless_items(academic_user):
    keyed = make_pub(academic_user, review_status='pending')
    make_pub(academic_user, review_status='pending', doi=None,
             identifiers={})
    pmid_only = make_pub(academic_user, review_status='pending', doi=None,
                         identifiers={'pmid': '42'})
    good = make_proposal(academic_user)
    keyless_pp = make_pub(academic_user, is_preprint=True, doi=None,
                          identifiers={})
    keyless = PreprintHideProposal.objects.create(
        owner=academic_user, preprint=keyless_pp,
        published=make_pub(academic_user), method='crossref_relation')
    pubs, proposals = reviewable_items(academic_user)
    assert keyed in pubs and pmid_only in pubs
    assert all(p.doi or p.identifiers for p in pubs)
    assert proposals == [good]
    assert PreprintHideProposal.objects.get(pk=keyless.pk).status == 'pending'


def test_admin_can_close_batch_by_status_alone(academic_user):
    """The README recovery sets status only; the form must accept that."""
    pre = PublicationFactory(owner=academic_user, is_preprint=True,
                             publication_type='preprint', doi='10.1101/p')
    target = PublicationFactory(owner=academic_user, doi='10.1000/t')
    prop = PreprintHideProposal.objects.create(
        owner=academic_user, preprint=pre, published=target,
        method='crossref_relation', evidence={})
    batch = ReviewBatch.objects.create(
        owner=academic_user, pr_number=3, branch='b', path='p',
        opened_at=timezone.now())
    batch.proposals.set([prop])
    model_admin = ReviewBatchAdmin(ReviewBatch, admin.site)
    request = RequestFactory().get('/')
    academic_user.is_staff = academic_user.is_superuser = True
    request.user = academic_user
    form_class = model_admin.get_form(request, batch, change=True)
    form = form_class(data={'status': 'closed'}, instance=batch)
    assert form.is_valid(), form.errors
    form.save()
    batch.refresh_from_db()
    assert batch.status == 'closed'
    assert list(batch.proposals.all()) == [prop]
