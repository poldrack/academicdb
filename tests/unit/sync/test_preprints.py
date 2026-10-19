import itertools

import pytest

from academic.models import PreprintHideProposal
from academic.sync.preprints import find_match, propose_hides
from tests.factories import PublicationFactory

pytestmark = pytest.mark.django_db

TITLE = 'Neural correlates of adaptive decision making under uncertainty'
AUTHORS = [{'name': 'Smith, Jane'}, {'name': 'Jones, Bob'}, {'name': 'Lee, Kim'}]


_counter = itertools.count(1)


def make_preprint(user, **kw):
    base = dict(
        owner=user, title=TITLE, year=2024, authors=AUTHORS,
        doi=f'10.1101/2024.01.01.{next(_counter):06d}',
        review_status='approved', is_ignored=False,
        identifiers={'openalex': 'W111'},
    )
    base.update(kw)
    return PublicationFactory(**base)


def make_published(user, **kw):
    base = dict(
        owner=user, title=TITLE, year=2025, authors=AUTHORS,
        doi=f'10.1016/j.neuron.2025.{next(_counter):05d}',
        review_status='approved', is_ignored=False,
    )
    base.update(kw)
    return PublicationFactory(**base)


def make_pair(user, published_title=TITLE, **pub_kw):
    preprint = make_preprint(user)
    published = make_published(user, title=published_title, **pub_kw)
    assert preprint.is_preprint and not published.is_preprint
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
    other = make_published(academic_user)
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


def other_owner(django_user_model):
    return django_user_model.objects.create_user(
        username='other', password='x', orcid_id='0000-0000-0000-0002')


def test_other_owners_published_not_used(academic_user, django_user_model):
    _, mine = make_pair(academic_user)
    theirs = make_published(other_owner(django_user_model))
    result = propose_hides(academic_user, lambda d: [theirs.doi], {})
    assert len(result) == 1
    assert result[0].published == mine


def test_no_crossref_lookup_for_preprint_without_doi(academic_user):
    make_preprint(academic_user, doi='', manual_edits={'publication_type': True}, is_preprint=True)
    calls = []
    propose_hides(academic_user, lambda d: calls.append(d) or [], {})
    assert calls == []


@pytest.mark.parametrize('best_first', [True, False])
def test_title_author_match_picks_best(academic_user, best_first):
    make_preprint(academic_user)
    pubs = [make_published(academic_user),
            make_published(academic_user, title=TITLE + ' revisited again')]
    best = pubs[0]
    if not best_first:
        best.delete()
        best = make_published(academic_user)
    result = propose_hides(academic_user, no_lookup, {})
    assert [p.published for p in result] == [best]


def test_confirmed_proposal_blocks_new(academic_user):
    preprint, published = make_pair(academic_user)
    PreprintHideProposal.objects.create(
        owner=academic_user, preprint=preprint, published=published,
        method='title_author', status='confirmed')
    assert propose_hides(academic_user, no_lookup, {}) == []


def test_pending_proposal_blocks_other_published(academic_user):
    preprint, published = make_pair(academic_user)
    PreprintHideProposal.objects.create(
        owner=academic_user, preprint=preprint, published=published,
        method='title_author', status='pending')
    make_published(academic_user)
    assert propose_hides(academic_user, no_lookup, {}) == []


def test_pending_review_preprint_skipped(academic_user):
    make_preprint(academic_user, review_status='pending')
    make_published(academic_user)
    assert propose_hides(academic_user, no_lookup, {}) == []


def test_other_owners_preprint_not_processed(academic_user, django_user_model):
    make_published(academic_user)
    make_preprint(other_owner(django_user_model))
    assert propose_hides(academic_user, no_lookup, {}) == []


def test_preprint_never_matched_to_preprint(academic_user):
    first = make_preprint(academic_user)
    second = make_preprint(academic_user)
    result = propose_hides(academic_user, lambda d: [second.doi], {})
    assert result == [] and first.is_preprint


def test_find_match_prefers_closest_title_regardless_of_list_order(academic_user):
    preprint = make_preprint(academic_user)
    worse = make_published(academic_user, title=TITLE + ' revisited again')
    best = make_published(academic_user)
    pub, method, _ = find_match(preprint, [worse, best], [], {})
    assert (pub, method) == (best, 'title_author')


# --- Final review fixes ---------------------------------------------------

def test_preprint_typed_row_without_flag_is_visible_not_published(academic_user):
    from academic.models import Publication
    from academic.sync.preprints import published_candidates, visible_preprints
    row = make_published(academic_user, doi='10.9999/server.0001',
                         publication_type='preprint')
    Publication.objects.filter(pk=row.pk).update(is_preprint=False)
    assert row.pk in {p.pk for p in visible_preprints(academic_user)}
    assert row.pk not in {p.pk for p in published_candidates(academic_user)}
