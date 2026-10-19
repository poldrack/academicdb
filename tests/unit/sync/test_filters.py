from datetime import date

import pytest

from academic.models import RejectedWork
from academic.sync.candidates import Candidate
from academic.sync.filters import (
    before_cutoff,
    collapse_versions,
    is_excluded,
    select_new,
)
from academic.sync.known import KnownWorks
from tests.factories import PublicationFactory

CUTOFF = date(2025, 10, 18)


def preprint(user, **kw):
    return PublicationFactory(owner=user, is_preprint=True,
                              publication_type='preprint', **kw)


def make(**kw):
    base = dict(
        source='openalex', title='A Title', year=2026, publication_date=None,
        publication_name='J', publication_type='journal-article', authors=[],
    )
    base.update(kw)
    return Candidate(**base)


def test_excluded_types_and_supplements():
    assert is_excluded(make(doi='10.1/a', openalex_type='peer-review'))
    assert is_excluded(make(doi='10.1/a', openalex_type='dataset'))
    assert is_excluded(make(doi='10.1/a', openalex_type='journal-article', is_supplement=True))
    assert is_excluded(make(doi='10.1/a', title='Erratum: X'))
    assert is_excluded(make(doi='10.1/a', title='author correction: Y'))
    assert is_excluded(make(doi='10.1/a', title='CORRIGENDUM to Z'))
    assert not is_excluded(make(doi='10.1/a', openalex_type='article'))
    assert not is_excluded(make(doi='10.1/a', title='Correlates of success'))


def test_before_cutoff_uses_date_then_year():
    assert before_cutoff(make(publication_date=date(2025, 10, 17)), CUTOFF)
    assert not before_cutoff(make(publication_date=None, year=2026), CUTOFF)
    assert before_cutoff(make(publication_date=None, year=None), CUTOFF)
    assert not before_cutoff(make(publication_date=date(2025, 10, 18)), CUTOFF)
    assert before_cutoff(make(publication_date=None, year=2025), CUTOFF)


def test_date_wins_over_year():
    c = make(publication_date=date(2026, 3, 1), year=2020)
    assert not before_cutoff(c, CUTOFF)


def test_collapse_osf_versions_keeps_highest():
    cands = [make(doi=f'10.31234/osf.io/abcde_v{v}') for v in (1, 3, 2)]
    out = collapse_versions(cands)
    assert [c.doi for c in out] == ['10.31234/osf.io/abcde_v3']


def test_collapse_unversioned_counts_as_zero_and_keeps_order():
    a = make(doi='10.31234/osf.io/abcde', title='a')
    b = make(doi='10.1/other', title='b')
    c = make(doi='10.31234/OSF.IO/abcde_v2', title='c')
    d = make(doi='', title='d')
    out = collapse_versions([a, b, c, d])
    assert [x.title for x in out] == ['c', 'b', 'd']


def test_collapse_non_versioned_keeps_first_seen():
    first = make(doi='10.1/x', source='openalex')
    second = make(doi='https://doi.org/10.1/X', source='pubmed')
    assert collapse_versions([first, second]) == [first]


def test_known_includes_ignored_pending_and_tombstones(academic_user):
    PublicationFactory(owner=academic_user, doi='10.1/a', is_ignored=True)
    PublicationFactory(owner=academic_user, doi='10.1/b', review_status='pending')
    RejectedWork.objects.create(owner=academic_user, doi='10.1/c', reason='rejected')
    known = KnownWorks.from_db(academic_user)
    for doi in ('10.1/a', '10.1/b', 'https://doi.org/10.1/C'):
        assert known.contains(make(doi=doi, title='unrelated'))
    assert not known.contains(make(doi='10.1/d', title='unrelated'))


def test_known_is_user_scoped(academic_user, django_user_model):
    other = django_user_model.objects.create_user(
        username='other', email='o@example.com', password='x'
    )
    PublicationFactory(owner=other, doi='10.1/theirs')
    RejectedWork.objects.create(owner=other, doi='10.1/theirs2', reason='rejected')
    known = KnownWorks.from_db(academic_user)
    assert not known.contains(make(doi='10.1/theirs'))
    assert not known.contains(make(doi='10.1/theirs2'))


def test_known_matches_by_openalex_id_and_pmid(academic_user):
    PublicationFactory(
        owner=academic_user, doi='10.1/a', identifiers={'openalex': 'W9', 'pmid': '77'}
    )
    known = KnownWorks.from_db(academic_user)
    assert known.contains(make(doi='10.9/zzz', title='x', openalex_id='W9'))
    assert known.contains(make(doi='10.9/zzz', title='x', pmid='77'))
    assert not known.contains(make(doi='10.9/zzz', title='x', openalex_id='W10'))


def test_known_matches_tombstone_openalex_and_pmid(academic_user):
    RejectedWork.objects.create(
        owner=academic_user, openalex_id='W5', pmid='55', reason='deleted'
    )
    known = KnownWorks.from_db(academic_user)
    assert known.contains(make(doi='10.9/q', openalex_id='W5'))
    assert known.contains(make(doi='10.9/q', pmid='55'))


def test_known_title_only_for_no_doi(academic_user):
    title = 'Statistical Thinking for the 21st Century'
    preprint(academic_user, doi=None, title=title)
    known = KnownWorks.from_db(academic_user)
    assert known.contains(make(title=title.upper() + '.', doi=''))
    assert not known.contains(make(title=title, doi='10.9/new'))


def test_known_ignores_empty_keys(academic_user):
    PublicationFactory(owner=academic_user, doi=None, title='', identifiers={})
    RejectedWork.objects.create(owner=academic_user, doi='10.1/x', reason='rejected')
    known = KnownWorks.from_db(academic_user)
    assert '' not in known.doi_keys | known.title_keys
    assert '' not in known.openalex_ids | known.pmids
    assert not known.contains(make(title='', doi='', openalex_id='', pmid=''))


def test_known_from_db_uses_fixed_queries(academic_user, django_assert_num_queries):
    for i in range(5):
        PublicationFactory(owner=academic_user, doi=f'10.1/q{i}')
    with django_assert_num_queries(2):
        KnownWorks.from_db(academic_user)


def test_rejected_osf_version_not_reproposed(academic_user):
    RejectedWork.objects.create(
        owner=academic_user, doi='10.31234/osf.io/abcde', reason='rejected'
    )
    known = KnownWorks.from_db(academic_user)
    cand = make(doi='10.31234/OSF.IO/ABCDE_v4')
    assert select_new([cand], known, CUTOFF) == []


def test_select_new_dedupes_within_run(academic_user):
    known = KnownWorks.from_db(academic_user)
    a = make(source='openalex', doi='10.1/dup', title='One')
    b = make(source='pubmed', doi='10.1/dup', title='One')
    assert select_new([a, b], known, CUTOFF) == [a]


def test_select_new_dedupes_by_pmid_across_sources(academic_user):
    known = KnownWorks.from_db(academic_user)
    a = make(doi='10.1/a', pmid='5', title='One')
    b = make(source='pubmed', doi='', pmid='5', title='Other')
    assert select_new([a, b], known, CUTOFF) == [a]


def test_select_new_filters_and_keeps_order(academic_user):
    PublicationFactory(owner=academic_user, doi='10.1/have')
    known = KnownWorks.from_db(academic_user)
    keep1 = make(doi='10.1/k1', title='K1')
    old = make(doi='10.1/old', year=2024, title='Old')
    have = make(doi='10.1/have', title='Have')
    erratum = make(doi='10.1/err', title='Erratum: foo')
    peer = make(doi='10.1/pr', openalex_type='peer-review', title='PR')
    keep2 = make(doi='', pmid='9', title='K2')
    out = select_new([keep1, old, have, erratum, peer, keep2], known, CUTOFF)
    assert out == [keep1, keep2]


def test_select_new_adds_kept_to_known(academic_user):
    known = KnownWorks.from_db(academic_user)
    select_new([make(doi='10.1/z', openalex_id='W1', pmid='1')], known, CUTOFF)
    assert known.contains(make(doi='10.1/z'))
    assert known.contains(make(doi='10.2/other', openalex_id='W1'))
    assert known.contains(make(doi='10.2/other', pmid='1'))


@pytest.mark.parametrize('title', [
    'Correction: Title here', 'Correction to: Title', 'Erratum: X', 'Errata: X',
    'Corrigendum to Brain imaging of x', 'Author Correction: X',
    'Publisher Correction: X', 'Retraction Note: X', 'Expression of Concern: X',
    '  correction - X',
])
def test_notice_titles_excluded(title):
    assert is_excluded(make(doi='10.1/a', title=title))


@pytest.mark.parametrize('title', [
    'Correction for multiple comparisons in fMRI',
    'Correctional facilities and mental health',
    'Erratic behavior in models',
])
def test_genuine_titles_not_excluded(title):
    assert not is_excluded(make(doi='10.1/a', title=title))


def test_doiless_candidate_matches_known_doi_bearing_title(academic_user):
    title = 'A Known Paper With A DOI'
    preprint(academic_user, doi='10.1101/known', title=title)
    known = KnownWorks.from_db(academic_user)
    assert known.contains(make(title=title, doi=''))
    assert not known.contains(make(title=title, doi='10.9/different'))


def test_select_new_dedupes_doi_and_doiless_same_title(academic_user):
    known = KnownWorks.from_db(academic_user)
    a = make(source='openalex', doi='10.1/a', pmid='', title='Same Title')
    b = make(source='pubmed', doi='', pmid='42', title='Same Title')
    assert select_new([a, b], known, CUTOFF) == [a]


@pytest.mark.django_db
def test_select_new_drops_pubmed_erratum(academic_user):
    from tests.unit.sync.test_ncbi_crossref import typed_article
    from academic.sync import pubmed
    c = pubmed.parse_pubmed_article(typed_article('Published Erratum'))
    c.year = 2026
    assert select_new([c], KnownWorks.from_db(academic_user), CUTOFF) == []


@pytest.mark.parametrize('kind', ['software', 'dissertation'])
def test_software_and_dissertations_excluded(kind):
    assert is_excluded(make(doi='10.5281/zenodo.1', openalex_type=kind))


@pytest.mark.parametrize('kind', ['article', 'conference-paper'])
def test_repository_only_non_preprint_excluded(kind):
    assert is_excluded(make(doi='10.17863/cam.1', openalex_type=kind,
                            repository_only=True))


def test_repository_only_preprint_or_pubmed_indexed_kept():
    assert not is_excluded(make(doi='10.48550/arxiv.1', openalex_type='preprint',
                                repository_only=True))
    assert not is_excluded(make(doi='10.1/x', pmid='5', openalex_type='article',
                                repository_only=True))


def test_work_without_doi_or_pmid_excluded():
    assert is_excluded(make(doi='', pmid='', openalex_type='preprint'))
    assert not is_excluded(make(doi='', pmid='42'))


def test_osf_project_doi_excluded():
    assert is_excluded(make(doi='10.17605/osf.io/a6mpc', openalex_type='preprint'))
    assert not is_excluded(make(doi='10.31234/osf.io/cn59h_v2',
                                openalex_type='preprint'))


def test_collapse_elife_versions_prefers_concept_doi():
    dois = ['10.7554/elife.112683.1', '10.7554/elife.112683',
            '10.7554/elife.112683.2']
    out = collapse_versions([make(doi=d) for d in dois])
    assert [c.doi for c in out] == ['10.7554/elife.112683']


def test_collapse_elife_versions_without_concept_keeps_latest():
    dois = ['10.7554/elife.5.2', '10.7554/elife.5.3', '10.7554/elife.5.1']
    out = collapse_versions([make(doi=d) for d in dois])
    assert [c.doi for c in out] == ['10.7554/elife.5.3']


def test_known_matches_elife_version_of_existing(academic_user):
    PublicationFactory(owner=academic_user, doi='10.7554/eLife.112683')
    known = KnownWorks.from_db(academic_user)
    assert known.contains(make(doi='10.7554/elife.112683.2', title='other'))


def test_copy_of_published_paper_with_own_doi_skipped(academic_user):
    PublicationFactory(owner=academic_user, doi='10.1038/s41586-025-1',
                       title='Investigating the analytical robustness of X.')
    known = KnownWorks.from_db(academic_user)
    copy = make(doi='10.17863/cam.122939', openalex_type='article',
                title='Investigating the analytical robustness of X')
    preprint = make(doi='10.31222/osf.io/twqsv_v1', openalex_type='preprint',
                    title='Investigating the Analytical Robustness of X')
    assert select_new([copy, preprint], known, CUTOFF) == []


def test_published_version_of_existing_preprint_kept(academic_user):
    preprint(academic_user, doi='10.1101/2024.1', title='Deep models of rest')
    known = KnownWorks.from_db(academic_user)
    journal = make(doi='10.1002/hbm.1', title='Deep Models of Rest')
    assert select_new([journal], known, CUTOFF) == [journal]
