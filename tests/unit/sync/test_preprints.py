import pytest

from academic.models import PreprintHideProposal
from academic.sync.preprints import propose_hides
from tests.factories import PublicationFactory

pytestmark = pytest.mark.django_db

TITLE = 'Neural correlates of adaptive decision making under uncertainty'
AUTHORS = [{'name': 'Smith, Jane'}, {'name': 'Jones, Bob'}, {'name': 'Lee, Kim'}]


def make_pair(user, published_title=TITLE, published_authors=None, **pub_kw):
    preprint = PublicationFactory(
        owner=user, title=TITLE, year=2024, is_preprint=True,
        authors=AUTHORS, review_status='approved', is_ignored=False,
        identifiers={'openalex': 'W111'}, manual_edits={'publication_type': True},
    )
    published = PublicationFactory(
        owner=user, title=published_title, year=2025, is_preprint=False,
        authors=published_authors or AUTHORS,
        is_ignored=False, **{'review_status': 'approved', **pub_kw},
    )
    return preprint, published


def no_lookup(doi):
    return []


def test_crossref_relation_match(academic_user):
    preprint, published = make_pair(
        academic_user, published_title='Totally different words here now')
    result = propose_hides(academic_user, lambda d: [published.doi], {})
    assert len(result) == 1
    assert result[0].method == 'crossref_relation'
    assert result[0].preprint == preprint and result[0].published == published
    assert result[0].status == 'pending'
    assert result[0].evidence == {'relation': 'is-preprint-of', 'doi': published.doi}


def test_openalex_location_match(academic_user):
    preprint, published = make_pair(
        academic_user, published_title='Totally different words here now')
    index = {preprint.doi.lower(): published.doi}
    result = propose_hides(academic_user, no_lookup, index)
    assert [p.method for p in result] == ['openalex_location']
    assert result[0].evidence == {
        'openalex_id': 'W111', 'published_doi': published.doi}


def test_title_author_match(academic_user):
    make_pair(academic_user)
    result = propose_hides(academic_user, no_lookup, {})
    assert [p.method for p in result] == ['title_author']
    evidence = result[0].evidence
    assert evidence['title_similarity'] == 1.0
    assert evidence['author_similarity'] > 0.9


def test_unrelated_paper_not_matched(academic_user):
    make_pair(academic_user, published_title='Quantum chromodynamics lattice gauge')
    assert propose_hides(academic_user, no_lookup, {}) == []


def test_ignored_published_version_not_used(academic_user):
    _, published = make_pair(academic_user)
    published.is_ignored = True
    published.save()
    assert propose_hides(academic_user, lambda d: [published.doi], {}) == []


def test_hidden_preprint_skipped(academic_user):
    preprint, _ = make_pair(academic_user)
    preprint.is_ignored = True
    preprint.save()
    calls = []
    result = propose_hides(academic_user, lambda d: calls.append(d) or [], {})
    assert result == [] and calls == []


def test_no_duplicate_pending_proposal(academic_user):
    make_pair(academic_user)
    propose_hides(academic_user, no_lookup, {})
    assert propose_hides(academic_user, no_lookup, {}) == []
    assert PreprintHideProposal.objects.count() == 1


def test_no_reproposal_after_rejected_hide(academic_user):
    preprint, published = make_pair(academic_user)
    PreprintHideProposal.objects.create(
        owner=academic_user, preprint=preprint, published=published,
        method='title_author', status='rejected')
    assert propose_hides(academic_user, no_lookup, {}) == []
    assert PreprintHideProposal.objects.count() == 1


def test_rejected_pair_does_not_block_other_published(academic_user):
    preprint, published = make_pair(academic_user)
    PreprintHideProposal.objects.create(
        owner=academic_user, preprint=preprint, published=published,
        method='title_author', status='rejected')
    other = PublicationFactory(
        owner=academic_user, title=TITLE, year=2025, is_preprint=False,
        authors=AUTHORS)
    result = propose_hides(academic_user, no_lookup, {})
    assert [p.published for p in result] == [other]


def test_propose_never_hides(academic_user):
    preprint, _ = make_pair(academic_user)
    propose_hides(academic_user, no_lookup, {})
    preprint.refresh_from_db()
    assert preprint.is_ignored is False


def test_pending_published_is_candidate(academic_user):
    make_pair(academic_user, review_status='pending')
    assert len(propose_hides(academic_user, no_lookup, {})) == 1


def test_other_owners_published_not_used(academic_user, django_user_model):
    make_pair(academic_user)
    PublicationFactory(owner=academic_user).delete()
    other_user = django_user_model.objects.create_user(
        username='other', password='x', orcid_id='0000-0000-0000-0002')
    other_pub = PublicationFactory(
        owner=other_user, title=TITLE, year=2025, is_preprint=False,
        authors=AUTHORS)
    result = propose_hides(academic_user, lambda d: [other_pub.doi], {})
    assert all(p.published.owner == academic_user for p in result)
