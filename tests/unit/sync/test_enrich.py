import pytest

from academic.sync.candidates import Candidate
from academic.sync.enrich import apply_enrichment, plan_enrichment
from tests.factories import PublicationFactory

pytestmark = pytest.mark.django_db


def make(**kw):
    extra = {k: kw.pop(k) for k in ('volume', 'page_range') if k in kw}
    base = dict(
        source='openalex', title='A Title', year=2026, publication_date=None,
        publication_name='J', publication_type='journal-article', authors=[],
    )
    base.update(kw)
    c = Candidate(**base)
    for key, value in extra.items():
        setattr(c, key, value)  # Candidate has no volume/page_range fields
    return c


def make_pub(academic_user, **kw):
    base = dict(owner=academic_user, title='A Title', year=2026,
                publication_name='J', volume='1', identifiers={},
                manual_edits={}, authors=[{'name': 'X, Y'}])
    base.update(kw)
    return PublicationFactory(**base)


def test_fills_only_empty_fields(academic_user):
    pub = make_pub(academic_user, publication_name='Neuron', volume=None)
    c = make(publication_name='NEURON (Cambridge)', volume='12')
    result = apply_enrichment(pub, c)
    pub.refresh_from_db()
    assert result.changed == ['volume']
    assert pub.volume == '12'
    assert pub.publication_name == 'Neuron'


def test_never_overwrites_manually_edited(academic_user):
    pub = make_pub(academic_user, volume=None, manual_edits={'volume': True})
    result = apply_enrichment(pub, make(volume='12'))
    pub.refresh_from_db()
    assert pub.volume is None
    assert 'volume' not in result.changed


def test_adds_missing_identifier_despite_identifiers_flag(academic_user):
    pub = make_pub(academic_user, identifiers={'pmid': '1'},
                   manual_edits={'identifiers': True})
    result = apply_enrichment(pub, make(pmcid='PMC9'))
    pub.refresh_from_db()
    assert pub.identifiers == {'pmid': '1', 'pmcid': 'PMC9'}
    assert result.changed == ['identifiers.pmcid']


def test_never_changes_existing_identifier(academic_user):
    pub = make_pub(academic_user, identifiers={'pmcid': 'PMC1'})
    result = apply_enrichment(pub, make(pmcid='PMC2'))
    pub.refresh_from_db()
    assert pub.identifiers == {'pmcid': 'PMC1'}
    assert {'field': 'identifiers.pmcid', 'ours': 'PMC1',
            'theirs': 'PMC2'} in result.discrepancies


def test_title_difference_is_discrepancy_not_change(academic_user):
    pub = make_pub(academic_user, title='A study of X')
    result = apply_enrichment(pub, make(title='A Study of Y'))
    pub.refresh_from_db()
    assert pub.title == 'A study of X'
    assert {'field': 'title', 'ours': 'A study of X',
            'theirs': 'A Study of Y'} in result.discrepancies


def test_case_and_whitespace_difference_is_not_discrepancy(academic_user):
    pub = make_pub(academic_user, title='A  study of X')
    result = plan_enrichment(pub, make(title='a study of x'))
    assert not [d for d in result.discrepancies if d['field'] == 'title']


def test_sets_oa_url(academic_user):
    pub = make_pub(academic_user)
    c = make(oa_url='https://europepmc.org/x', oa_status='green')
    result = apply_enrichment(pub, c)
    pub.refresh_from_db()
    assert pub.metadata['oa_url'] == 'https://europepmc.org/x'
    assert pub.metadata['oa_status'] == 'green'
    assert 'metadata.oa_url' in result.changed


def test_oa_url_respects_manual_edit(academic_user):
    pub = make_pub(academic_user, manual_edits={'oa_url': True})
    result = plan_enrichment(pub, make(oa_url='https://x.org', oa_status='gold'))
    assert 'metadata.oa_url' not in result.changed


def test_fills_empty_authors_unless_flagged(academic_user):
    pub = make_pub(academic_user, authors=[])
    flagged = make_pub(academic_user, authors=[], doi='10.1/b',
                       manual_edits={'authors': True})
    c = make(authors=[{'name': 'A, B'}])
    assert 'authors' in plan_enrichment(pub, c).changed
    assert 'authors' not in plan_enrichment(flagged, c).changed


def test_never_touches_ignore_or_review(academic_user):
    pub = make_pub(academic_user, is_ignored=True, ignore_reason='dup',
                   review_status='approved', volume=None)
    apply_enrichment(pub, make(volume='3'))
    pub.refresh_from_db()
    assert pub.is_ignored is True
    assert pub.ignore_reason == 'dup'
    assert pub.review_status == 'approved'


def test_no_save_when_nothing_changes(academic_user, django_assert_num_queries):
    pub = make_pub(academic_user)
    with django_assert_num_queries(0):
        result = apply_enrichment(pub, make())
    assert result.changed == []
