"""End-to-end tests for the weekly sync orchestrator and command."""
import json
import re
from datetime import date, datetime, timezone

import pytest
import responses
from django.core.management import CommandError, call_command
from django.forms.models import model_to_dict
from freezegun import freeze_time

from academic.models import PreprintHideProposal, Publication, RejectedWork
from academic.sync import http, idconv, pubmed
from academic.sync.run import SyncConfig, run_weekly_sync
from tests.factories import PublicationFactory
from tests.unit.sync.test_ncbi_crossref import XML_HEAD
from tests.unit.sync.test_openalex import make_work

pytestmark = pytest.mark.django_db

WORKS_URL = 'https://api.openalex.org/works'
ESEARCH = f'{pubmed.EUTILS}/esearch.fcgi'
EFETCH = f'{pubmed.EUTILS}/efetch.fcgi'
IDCONV_RE = re.compile(re.escape(idconv.IDCONV) + '.*')
CROSSREF_RE = re.compile(r'https://api\.crossref\.org/works/.*')

KNOWN_DOI = '10.1000/known.2024'
KNOWN_TITLE = 'Known paper about cognitive control networks'
NEW_DOI = '10.1000/new.2026'
NEW_TITLE = 'A brand new study of attention networks'
OLD_DOI = '10.1000/old.2024'
REVIEW_DOI = '10.1000/review.2026'
PREPRINT_DOI = '10.1101/2024.05.05.000001'
PUBLISHED_DOI = '10.1016/j.pub.2025.00001'
PUBLISHED_TITLE = 'Published version of the memory consolidation study'
FULL_AUTHORS = ['Ann Alpha', 'Bob Beta', 'Cat Gamma', 'Dan Delta']
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def oa_work(wid, doi, title, year, pub_date, **kw):
    kw.setdefault('ids', {})
    return make_work(id=f'https://openalex.org/{wid}', doi=f'https://doi.org/{doi}',
                     title=title, publication_year=year, publication_date=pub_date,
                     **kw)


def known_work():
    return oa_work(
        'W1', KNOWN_DOI, KNOWN_TITLE, 2024, '2024-03-01',
        primary_location={'source': {'display_name': 'Journal K'}},
        best_oa_location={'landing_page_url': 'https://oa.example/known'},
        locations=[{'landing_page_url':
                    'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC999'}])


def new_work(truncated=True):
    names = FULL_AUTHORS[:1] if truncated else FULL_AUTHORS
    return oa_work('W2', NEW_DOI, NEW_TITLE, 2026, '2026-05-01',
                   ids={'pmid': 'https://pubmed.ncbi.nlm.nih.gov/222'},
                   authorships=[{'raw_author_name': n} for n in names],
                   is_authors_truncated=truncated)


def published_work():
    return oa_work(
        'W5', PUBLISHED_DOI, PUBLISHED_TITLE, 2025, '2025-02-01',
        locations=[{'landing_page_url': f'https://doi.org/{PREPRINT_DOI}'}])


def base_works():
    return [
        known_work(),
        new_work(),
        oa_work('W3', OLD_DOI, 'An old study from before the cutoff', 2024,
                '2024-01-01'),
        oa_work('W4', REVIEW_DOI, 'Review of a manuscript on attention', 2026,
                '2026-06-01', type='peer-review'),
        published_work(),
    ]


def pubmed_article(pmid, doi, title):
    return (
        '<PubmedArticle><MedlineCitation Status="MEDLINE" Owner="NLM">'
        f'<PMID Version="1">{pmid}</PMID><Article PubModel="Print"><Journal>'
        '<JournalIssue CitedMedium="Print"><PubDate><Year>2026</Year></PubDate>'
        '</JournalIssue><Title>Nature</Title></Journal>'
        f'<ArticleTitle>{title}.</ArticleTitle>'
        '<AuthorList CompleteYN="Y"><Author ValidYN="Y"><LastName>Alpha</LastName>'
        '<ForeName>Ann</ForeName></Author></AuthorList></Article></MedlineCitation>'
        f'<PubmedData><ArticleIdList><ArticleId IdType="doi">{doi}</ArticleId>'
        '</ArticleIdList></PubmedData></PubmedArticle>'
    )


def efetch_body(*articles):
    return f'{XML_HEAD}<PubmedArticleSet>{"".join(articles)}</PubmedArticleSet>'


def register_openalex(works):
    responses.add(responses.GET, WORKS_URL, json={
        'results': works, 'meta': {'next_cursor': None}})
    responses.add(responses.GET, f'{WORKS_URL}/W2', json=new_work(truncated=False))


def register_ncbi(pubmed_ok=True, crossref_status=404):
    if pubmed_ok:
        responses.add(responses.GET, ESEARCH, json={'esearchresult': {'idlist': ['222']}})
        responses.add(responses.GET, EFETCH, body=efetch_body(
            pubmed_article('222', NEW_DOI.upper(), NEW_TITLE)))
    else:
        responses.add(responses.GET, ESEARCH, status=500)
    responses.add(responses.GET, IDCONV_RE, json={'records': [
        {'requested-id': KNOWN_DOI, 'pmid': '111', 'pmcid': 'PMC999'}]})
    responses.add(responses.GET, CROSSREF_RE, status=crossref_status)


def register_all(works=None, pubmed_ok=True):
    register_openalex(base_works() if works is None else works)
    register_ncbi(pubmed_ok)


@pytest.fixture(autouse=True)
def frozen():
    with freeze_time('2026-10-18'):
        yield


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(http.time, 'sleep', calls.append)
    return calls


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('OPENALEX_KEY', 'OAKEY')
    monkeypatch.setenv('PUBMED_EMAIL', 'me@x.org')
    monkeypatch.setenv('DISCOVERY_CUTOFF', '2025-10-18')
    monkeypatch.delenv('NCBI_API_KEY', raising=False)


@pytest.fixture
def user(academic_user):
    academic_user.pubmed_query = 'poldrack[au]'
    academic_user.save()
    return academic_user


@pytest.fixture
def config(user):
    return SyncConfig(orcid=user.orcid_id, cutoff=date(2025, 10, 18),
                      openalex_key='OAKEY', ncbi_email='me@x.org', ncbi_api_key=None)


def approved(user, **kw):
    base = dict(owner=user, review_status='approved', is_ignored=False,
                metadata={}, identifiers={}, manual_edits={})
    base.update(kw)
    return PublicationFactory(**base)


@pytest.fixture
def library(user):
    return {
        'known': approved(user, doi=KNOWN_DOI, title=KNOWN_TITLE, year=2024,
                          publication_name='Journal K', identifiers={'pmid': '111'}),
        'preprint': approved(user, doi=PREPRINT_DOI, year=2024,
                             title='Preprint on memory consolidation in sleep'),
        'published': approved(user, doi=PUBLISHED_DOI, title=PUBLISHED_TITLE,
                              year=2025),
    }


def run(user, config):
    return run_weekly_sync(user, config, NOW)


def pending(user):
    return Publication.objects.filter(owner=user, review_status='pending')


def run_command(user, tmp_path, *extra):
    report = tmp_path / 'report.json'
    call_command('weekly_sync', '--orcid-id', user.orcid_id,
                 '--report', str(report), *extra)
    return json.loads(report.read_text())


# --- SyncConfig -----------------------------------------------------------

def test_config_from_env_reads_values():
    cfg = SyncConfig.from_env('0000-0000-0000-0001', {
        'OPENALEX_KEY': 'K', 'PUBMED_EMAIL': 'e@x', 'DISCOVERY_CUTOFF': '2025-10-18',
        'NCBI_API_KEY': 'N'})
    assert cfg == SyncConfig('0000-0000-0000-0001', date(2025, 10, 18), 'K', 'e@x', 'N')


@pytest.mark.parametrize('missing', ['OPENALEX_KEY', 'PUBMED_EMAIL', 'DISCOVERY_CUTOFF'])
def test_config_missing_var_names_it(missing):
    env = {'OPENALEX_KEY': 'K', 'PUBMED_EMAIL': 'e@x', 'DISCOVERY_CUTOFF': '2025-10-18'}
    del env[missing]
    with pytest.raises(ValueError, match=missing):
        SyncConfig.from_env('x', env)


def test_config_bad_cutoff_format():
    env = {'OPENALEX_KEY': 'K', 'PUBMED_EMAIL': 'e@x', 'DISCOVERY_CUTOFF': '18/10/2025'}
    with pytest.raises(ValueError, match='DISCOVERY_CUTOFF'):
        SyncConfig.from_env('x', env)


# --- Orchestrator ---------------------------------------------------------

@responses.activate
def test_new_work_created_pending_and_reported(user, config, library):
    register_all()
    report = run(user, config)
    pubs = list(pending(user))
    assert len(pubs) == 1
    pub = pubs[0]
    assert pub.doi == NEW_DOI and pub.title == NEW_TITLE and pub.year == 2026
    assert pub.source == 'openalex'
    assert pub.identifiers == {'pmid': '222', 'openalex': 'W2'}
    assert pub.metadata == {'oa_url': 'https://oa.example/x', 'oa_status': 'green'}
    assert [a['name'] for a in pub.authors] == [
        'Alpha, Ann', 'Beta, Bob', 'Gamma, Cat', 'Delta, Dan']
    item = report.new_pending[0]
    assert item == {
        'id': pub.id, 'doi': NEW_DOI, 'title': NEW_TITLE, 'year': 2026,
        'publication_name': 'Nature',
        'authors': 'Alpha, Ann; Beta, Bob; Gamma, Cat; …',
        'source': 'openalex', 'openalex_id': 'W2', 'pmid': '222'}
    assert report.run_at == NOW.isoformat()
    assert report.cutoff == '2025-10-18'
    assert report.errors == []


@responses.activate
def test_same_work_from_openalex_and_pubmed_creates_one_pending(user, config, library):
    register_all()
    run(user, config)
    assert pending(user).count() == 1


@responses.activate
def test_pubmed_only_work_created_with_pubmed_source(user, config, library):
    register_openalex([known_work()])
    register_ncbi()
    report = run(user, config)
    pub = pending(user).get()
    assert pub.source == 'pubmed' and pub.doi == NEW_DOI
    assert pub.identifiers == {'pmid': '222'}
    assert pub.metadata == {}
    assert report.new_pending[0]['authors'] == 'Alpha, Ann'


@responses.activate
def test_pre_cutoff_and_excluded_types_not_created(user, config, library):
    register_all()
    run(user, config)
    dois = set(Publication.objects.filter(owner=user).values_list('doi', flat=True))
    assert OLD_DOI not in dois
    assert REVIEW_DOI not in dois


@responses.activate
def test_known_paper_enriched_fill_only(user, config, library):
    register_all()
    report = run(user, config)
    known = Publication.objects.get(pk=library['known'].pk)
    assert known.identifiers['pmcid'] == 'PMC999'
    assert known.identifiers['pmid'] == '111'
    assert known.metadata['oa_url'] == 'https://oa.example/known'
    assert known.title == KNOWN_TITLE
    entry = next(e for e in report.enriched if e['id'] == known.pk)
    assert entry['doi'] == KNOWN_DOI
    assert 'identifiers.pmcid' in entry['fields']
    assert 'metadata.oa_url' in entry['fields']


@responses.activate
def test_enrichment_matches_by_openalex_id(user, config, library):
    library['known'].doi = None
    library['known'].identifiers = {'pmid': '111', 'openalex': 'W1'}
    library['known'].save()
    register_all()
    run(user, config)
    known = Publication.objects.get(pk=library['known'].pk)
    assert known.identifiers['pmcid'] == 'PMC999'


@responses.activate
def test_idconv_fills_pmcid_without_openalex_match(user, config, library):
    # Final-review finding 5: an empty OpenAlex list is now an error, so use
    # a single work that matches nothing in the library.
    register_openalex([oa_work('W3', OLD_DOI, 'An old study from before the cutoff',
                               2024, '2024-01-01')])
    register_ncbi()
    report = run(user, config)
    known = Publication.objects.get(pk=library['known'].pk)
    assert known.identifiers == {'pmid': '111', 'pmcid': 'PMC999'}
    assert any(e['id'] == known.pk for e in report.enriched)
    assert report.discrepancies == []
    lookups = [c for c in responses.calls if c.request.url.startswith(idconv.IDCONV)]
    requested = lookups[0].request.params['ids'].split(',')
    assert set(requested) == {KNOWN_DOI, PREPRINT_DOI, PUBLISHED_DOI}


@responses.activate
def test_discrepancies_reported(user, config, library):
    library['known'].publication_name = 'Journal Q'
    library['known'].save()
    register_all()
    report = run(user, config)
    assert {'id': library['known'].pk, 'doi': KNOWN_DOI, 'field': 'publication_name',
            'ours': 'Journal Q', 'theirs': 'Journal K',
            'source': 'openalex'} in report.discrepancies
    known = Publication.objects.get(pk=library['known'].pk)
    assert known.publication_name == 'Journal Q'


@responses.activate
def test_hand_edited_and_hidden_publications_untouched(user, config, library):
    hand = approved(
        user, doi='10.1000/hand.2023', title='Hand edited title by the owner',
        year=2023, publication_date=None, publication_name='Journal H',
        volume='5', page_range='1-9',
        manual_edits={'title': True, 'volume': True, 'publication_date': True},
        identifiers={'pmid': '333', 'pmcid': 'PMC333', 'openalex': 'W6'},
        metadata={'oa_url': 'https://oa.example/hand', 'oa_status': 'gold'})
    hidden = approved(user, doi='10.1000/hidden.2023', year=2023,
                      title='Hidden publication the owner ignored', is_ignored=True,
                      publication_name=None, volume=None, page_range=None,
                      ignore_reason='misattributed')
    works = base_works() + [
        oa_work('W6', hand.doi, 'Different title from openalex', 2023, '2023-04-01',
                ids={'pmid': 'https://pubmed.ncbi.nlm.nih.gov/333'},
                primary_location={'source': {'display_name': 'Journal H'}},
                biblio={'volume': '99', 'first_page': '1', 'last_page': '9'},
                best_oa_location={'landing_page_url': 'https://oa.example/hand'},
                open_access={'oa_status': 'gold'},
                locations=[{'landing_page_url':
                            'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC333'}]),
        oa_work('W7', hidden.doi, hidden.title, 2023, '2023-02-02',
                ids={'pmid': 'https://pubmed.ncbi.nlm.nih.gov/444'},
                biblio={'volume': '7', 'first_page': '3', 'last_page': '4'},
                locations=[{'landing_page_url':
                            'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC444'}]),
    ]
    register_all(works)
    before = [model_to_dict(Publication.objects.get(pk=p.pk)) for p in (hand, hidden)]
    report = run(user, config)
    after = [model_to_dict(Publication.objects.get(pk=p.pk)) for p in (hand, hidden)]
    assert after == before
    assert after[0]['publication_date'] is None
    # Ruling (fix round 1): owner-decided fields no longer produce discrepancies.
    assert not [d for d in report.discrepancies if d['id'] == hand.pk]


@responses.activate
def test_rejected_work_not_recreated(user, config, library):
    RejectedWork.objects.create(owner=user, doi=NEW_DOI, reason='rejected')
    register_all()
    report = run(user, config)
    assert pending(user).count() == 0
    assert report.new_pending == []


@responses.activate
def test_preprint_hide_proposed_not_applied(user, config, library):
    register_all()
    report = run(user, config)
    proposal = PreprintHideProposal.objects.get(owner=user)
    assert proposal.method == 'openalex_location'
    assert proposal.status == 'pending'
    assert proposal.preprint_id == library['preprint'].pk
    assert proposal.published_id == library['published'].pk
    preprint = Publication.objects.get(pk=library['preprint'].pk)
    assert preprint.is_ignored is False
    assert report.proposed_hides == [{
        'proposal_id': proposal.pk, 'method': 'openalex_location',
        'evidence': proposal.evidence,
        'preprint': {'id': preprint.pk, 'doi': PREPRINT_DOI, 'title': preprint.title},
        'published': {'id': library['published'].pk, 'doi': PUBLISHED_DOI,
                      'title': PUBLISHED_TITLE}}]


@responses.activate
def test_location_index_prefers_published_candidate(user, config, library):
    preprint_copy = oa_work(
        'W8', '10.31234/osf.io/abcde', 'Preprint copy of the memory study', 2024,
        '2024-06-01', type='preprint',
        locations=[{'landing_page_url': f'https://doi.org/{PREPRINT_DOI}'}])
    register_all(base_works() + [preprint_copy])
    run(user, config)
    proposal = PreprintHideProposal.objects.get(owner=user)
    assert proposal.method == 'openalex_location'
    assert proposal.published_id == library['published'].pk


@responses.activate
def test_crossref_failure_reported(user, config, library):
    register_openalex(base_works())
    register_ncbi(crossref_status=500)
    report = run(user, config)
    assert any('crossref' in e for e in report.errors)
    assert PreprintHideProposal.objects.filter(owner=user).count() == 1


@responses.activate
def test_second_run_is_noop(user, config, library):
    register_all()
    run(user, config)
    proposals = PreprintHideProposal.objects.count()
    second = run(user, config)
    assert PreprintHideProposal.objects.count() == proposals
    assert second.new_pending == []
    assert second.enriched == []
    assert second.proposed_hides == []
    assert pending(user).count() == 1


@responses.activate
def test_full_authors_failure_keeps_truncated_candidate(user, config, library):
    responses.add(responses.GET, WORKS_URL, json={
        'results': base_works(), 'meta': {'next_cursor': None}})
    responses.add(responses.GET, f'{WORKS_URL}/W2', status=500)
    register_ncbi()
    report = run(user, config)
    pub = pending(user).get()
    assert [a['name'] for a in pub.authors] == ['Alpha, Ann']
    assert len(report.errors) == 1
    assert 'OAKEY' not in report.errors[0]


@responses.activate
def test_report_to_json_round_trips(user, config, library):
    register_all()
    report = run(user, config)
    data = json.loads(report.to_json())
    assert set(data) == {'run_at', 'cutoff', 'new_pending', 'enriched',
                         'proposed_hides', 'discrepancies', 'errors'}
    assert data['new_pending'][0]['doi'] == NEW_DOI


@responses.activate
def test_user_without_pubmed_query_skips_pubmed(user, config, library):
    user.pubmed_query = ''
    user.save()
    register_all()
    report = run(user, config)
    assert not [c for c in responses.calls if c.request.url.startswith(ESEARCH)]
    assert report.errors == []


# --- Command --------------------------------------------------------------

@responses.activate
def test_openalex_failure_writes_nothing(user, library, tmp_path):
    responses.add(responses.GET, WORKS_URL, status=500)
    register_ncbi()
    pubs, rejected = Publication.objects.count(), RejectedWork.objects.count()
    with pytest.raises(CommandError):
        run_command(user, tmp_path)
    assert len([c for c in responses.calls if c.request.url.startswith(WORKS_URL)]) == 4
    assert Publication.objects.count() == pubs
    assert RejectedWork.objects.count() == rejected
    assert PreprintHideProposal.objects.count() == 0
    known = Publication.objects.get(pk=library['known'].pk)
    assert 'pmcid' not in known.identifiers
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['errors'] and report['new_pending'] == []


@responses.activate
def test_pubmed_failure_reported_but_run_completes(user, library, tmp_path):
    register_all(pubmed_ok=False)
    with pytest.raises(CommandError, match='error'):
        run_command(user, tmp_path)
    assert pending(user).count() == 1
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['errors']
    assert all('me@x.org' not in e for e in report['errors'])


@responses.activate
def test_command_success_prints_summary(user, library, tmp_path, capsys):
    register_all()
    report = run_command(user, tmp_path)
    out = capsys.readouterr().out
    assert 'new: 1  enriched: ' in out
    assert f'proposed hides: 1  discrepancies: {len(report["discrepancies"])}  errors: 0' in out
    assert len(report['new_pending']) == 1


@responses.activate
def test_dry_run_rolls_back(user, library, tmp_path):
    register_all()
    report = run_command(user, tmp_path, '--dry-run')
    assert len(report['new_pending']) == 1
    assert len(report['proposed_hides']) == 1
    assert pending(user).count() == 0
    assert PreprintHideProposal.objects.count() == 0
    known = Publication.objects.get(pk=library['known'].pk)
    assert 'pmcid' not in known.identifiers


def test_missing_cutoff_is_command_error(monkeypatch, user, tmp_path):
    monkeypatch.delenv('DISCOVERY_CUTOFF')
    with pytest.raises(CommandError, match='DISCOVERY_CUTOFF'):
        run_command(user, tmp_path)


def test_unknown_orcid_is_command_error(user, tmp_path):
    with pytest.raises(CommandError, match='9999'):
        call_command('weekly_sync', '--orcid-id', '9999-9999-9999-9999',
                     '--report', str(tmp_path / 'r.json'))


@responses.activate
def test_openalex_failure_hides_secrets(user, library, tmp_path, capsys):
    responses.add(responses.GET, WORKS_URL, status=500)
    register_ncbi()
    with pytest.raises(CommandError) as excinfo:
        run_command(user, tmp_path)
    texts = [str(excinfo.value), capsys.readouterr().out,
             (tmp_path / 'report.json').read_text()]
    for text in texts:
        assert 'OAKEY' not in text
        assert 'me@x.org' not in text


def test_crash_removes_stale_report(user, tmp_path, monkeypatch):
    report = tmp_path / 'report.json'
    report.write_text('{"stale": true}')

    def boom(*args, **kwargs):
        raise RuntimeError('parse bug')
    monkeypatch.setattr('academic.management.commands.weekly_sync.run_weekly_sync', boom)
    with pytest.raises(RuntimeError):
        call_command('weekly_sync', '--orcid-id', user.orcid_id, '--report', str(report))
    assert not report.exists()


# --- Final review fixes ---------------------------------------------------

@responses.activate
def test_empty_openalex_results_is_command_error(user, library, tmp_path):
    register_openalex([])
    register_ncbi()
    pubs = Publication.objects.count()
    with pytest.raises(CommandError):
        run_command(user, tmp_path)
    assert Publication.objects.count() == pubs
    known = Publication.objects.get(pk=library['known'].pk)
    assert 'pmcid' not in known.identifiers
    report = json.loads((tmp_path / 'report.json').read_text())
    assert any('no works' in e for e in report['errors'])


@responses.activate
def test_empty_openalex_results_raises_source_error(user, config, library):
    register_openalex([])
    register_ncbi()
    with pytest.raises(http.SourceError, match=f'no works for {user.orcid_id}'):
        run(user, config)


@responses.activate
@pytest.mark.parametrize('name,limit', [
    ('volume', 50), ('page_range', 100), ('publication_name', 500)])
def test_pending_fields_truncated_to_max_length(user, config, library, name, limit):
    long = 'x' * (limit + 10)
    biblio = {'volume': long} if name == 'volume' else {}
    if name == 'page_range':
        biblio = {'first_page': '1', 'last_page': long}
    work = new_work(truncated=False)
    work['biblio'] = biblio
    if name == 'publication_name':
        work['primary_location'] = {'source': {'display_name': long}}
    register_openalex([work])
    register_ncbi()
    run(user, config)
    full = f'1-{long}' if name == 'page_range' else long
    assert getattr(pending(user).get(), name) == full[:limit]


@responses.activate
def test_doi_matching_an_erratum_reported_not_enriched(user, config, library):
    erratum = known_work()
    erratum.update(type='erratum', title=f'Erratum: {KNOWN_TITLE}')
    register_all(works=[w for w in base_works() if w['id'] != erratum['id']]
                 + [erratum])
    report = run(user, config)
    known = Publication.objects.get(pk=library['known'].pk)
    assert known.identifiers == {'pmid': '111'}
    assert 'oa_url' not in known.metadata
    assert not any(e['id'] == known.pk for e in report.enriched)
    assert {'id': known.pk, 'doi': KNOWN_DOI, 'field': 'doi', 'ours': KNOWN_DOI,
            'theirs': f'erratum: Erratum: {KNOWN_TITLE}',
            'source': 'openalex'} in report.discrepancies


# --- Plan 3 task 1: CrossRef prefetch --------------------------------------

@responses.activate
def test_crossref_fetched_before_any_write(user, config, library, monkeypatch):
    import academic.sync.run as run_module
    log, looked_up = [], []
    real_lookup, real_write = run_module.published_dois_for_preprint, run_module._write

    def lookup(doi):
        log.append('crossref')
        looked_up.append(doi)
        return real_lookup(doi)

    def write(*args, **kwargs):
        log.append('write')
        return real_write(*args, **kwargs)

    monkeypatch.setattr(run_module, 'published_dois_for_preprint', lookup)
    monkeypatch.setattr(run_module, '_write', write)
    register_all()
    run(user, config)
    assert 'crossref' in log and 'write' in log
    assert log.index('write') > max(i for i, x in enumerate(log) if x == 'crossref')
    assert PREPRINT_DOI in looked_up


@responses.activate
def test_crossref_failure_recorded_once_and_sync_continues(user, config, library):
    register_openalex(base_works())
    register_ncbi(crossref_status=500)
    report = run(user, config)
    assert len([e for e in report.errors if e.startswith('crossref:')]) == 1
    assert pending(user).count() == 1
