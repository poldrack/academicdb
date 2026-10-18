from datetime import datetime, timezone

import pytest

from academic.models import Publication, PreprintHideProposal, RejectedWork
from academic.sync.review import (
    approve_pending,
    confirm_hide,
    reject_hide,
    reject_pending,
)
from tests.factories import PublicationFactory

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def make_pub(user, status='pending', **kw):
    base = dict(owner=user, title='A Title', year=2026, review_status=status,
                doi='10.1016/j.example.2026.01')
    base.update(kw)
    return PublicationFactory(**base)


@pytest.fixture
def preprint(academic_user):
    return make_pub(academic_user, 'approved', title='Preprint',
                    doi='10.1101/2026.01.01.123456', metadata={'k': 'v'})


@pytest.fixture
def published(academic_user):
    return make_pub(academic_user, 'approved', title='Published',
                    doi='10.1038/x')


def make_proposal(user, preprint, published, **kw):
    return PreprintHideProposal.objects.create(
        owner=user, preprint=preprint, published=published,
        method='crossref_relation', **kw)


def test_approve_pending(academic_user):
    pub = make_pub(academic_user)
    approve_pending(pub)
    pub.refresh_from_db()
    assert pub.review_status == 'approved'


def test_approve_non_pending_raises(academic_user):
    pub = make_pub(academic_user, 'approved')
    with pytest.raises(ValueError):
        approve_pending(pub)


def test_reject_non_pending_raises(academic_user):
    pub = make_pub(academic_user, 'approved')
    with pytest.raises(ValueError):
        reject_pending(pub)
    assert Publication.objects.filter(pk=pub.pk).exists()


def test_reject_pending_tombstones_and_deletes(academic_user):
    pub = make_pub(academic_user)
    reject_pending(pub)
    assert not Publication.objects.filter(owner=academic_user).exists()
    rows = RejectedWork.objects.filter(owner=academic_user)
    assert rows.count() == 1
    assert rows.get().reason == 'rejected'


def test_confirm_hide_sets_ignore_and_origin(academic_user, preprint, published):
    proposal = make_proposal(academic_user, preprint, published)
    confirm_hide(proposal, NOW)
    preprint.refresh_from_db()
    proposal.refresh_from_db()
    assert preprint.is_ignored is True
    assert preprint.ignore_reason == 'Published as 10.1038/x'
    assert preprint.metadata['k'] == 'v'
    assert preprint.metadata['hidden_by'] == {
        'method': 'pipeline_review', 'proposal_id': proposal.id,
        'confirmed_at': NOW.isoformat(), 'published_doi': '10.1038/x'}
    assert proposal.status == 'confirmed'
    assert proposal.decided_at == NOW


def test_confirm_hide_rejects_sibling_proposals(academic_user, preprint, published):
    other = make_pub(academic_user, 'approved', title='Other', doi='10.1000/o')
    proposal = make_proposal(academic_user, preprint, published)
    sibling = make_proposal(academic_user, preprint, other)
    confirm_hide(proposal, NOW)
    sibling.refresh_from_db()
    assert sibling.status == 'rejected'
    assert sibling.decided_at == NOW


def test_reject_hide_leaves_preprint_visible(academic_user, preprint, published):
    proposal = make_proposal(academic_user, preprint, published)
    reject_hide(proposal, NOW)
    preprint.refresh_from_db()
    proposal.refresh_from_db()
    assert preprint.is_ignored is False
    assert 'hidden_by' not in preprint.metadata
    assert proposal.status == 'rejected'
    assert proposal.decided_at == NOW


def test_decided_proposals_cannot_be_decided_again(academic_user, preprint, published):
    proposal = make_proposal(academic_user, preprint, published)
    reject_hide(proposal, NOW)
    with pytest.raises(ValueError):
        confirm_hide(proposal, NOW)
    with pytest.raises(ValueError):
        reject_hide(proposal, NOW)
