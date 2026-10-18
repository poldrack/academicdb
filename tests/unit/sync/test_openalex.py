import pytest
import requests
import responses

from academic.sync import http, openalex
from academic.sync.http import SourceError

ORCID = '0000-0001-6755-0259'
WORKS_URL = 'https://api.openalex.org/works'


def make_work(**overrides):
    work = {
        'id': 'https://openalex.org/W4414790363',
        'doi': 'https://doi.org/10.1038/X',
        'title': 'A title',
        'publication_year': 2025,
        'publication_date': '2025-03-04',
        'type': 'article',
        'ids': {'pmid': 'https://pubmed.ncbi.nlm.nih.gov/41143079'},
        'authorships': [{'raw_author_name': 'Russell A. Poldrack'}],
        'biblio': {'issue': '3', 'first_page': '10'},
        'primary_location': {'source': {'display_name': 'Nature'}},
        'best_oa_location': {'landing_page_url': 'https://oa.example/x'},
        'open_access': {'oa_status': 'green', 'oa_url': 'https://oa.example/y'},
        'locations': [],
    }
    work.update(overrides)
    return work


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(http.time, 'sleep', calls.append)
    return calls


@responses.activate
def test_get_retries_then_succeeds(sleeps):
    for status in (503, 503, 200):
        responses.add(responses.GET, 'https://x.test/a', status=status)
    resp = http.get('https://x.test/a')
    assert resp.status_code == 200
    assert len(sleeps) == 2
    ua = responses.calls[0].request.headers['User-Agent']
    assert ua == 'academicdb (+https://github.com/poldrack/academicdb)'


@responses.activate
def test_get_raises_on_401(sleeps):
    responses.add(responses.GET, 'https://x.test/a', status=401)
    with pytest.raises(SourceError, match='HTTP 401'):
        http.get('https://x.test/a')
    assert len(responses.calls) == 1
    assert sleeps == []


@responses.activate
def test_get_raises_after_retries_exhausted(sleeps):
    responses.add(responses.GET, 'https://x.test/a', status=500)
    with pytest.raises(SourceError, match='HTTP 500'):
        http.get('https://x.test/a')
    assert len(responses.calls) == 4


@responses.activate
def test_fetch_works_follows_cursor():
    responses.add(responses.GET, WORKS_URL, json={
        'results': [make_work(), make_work()], 'meta': {'next_cursor': 'abc'}})
    responses.add(responses.GET, WORKS_URL, json={
        'results': [make_work()], 'meta': {'next_cursor': None}})
    works = openalex.fetch_works_by_orcid(ORCID, 'KEY')
    assert len(works) == 3
    for call in responses.calls:
        assert 'api_key=KEY' in call.request.url
        assert f'author.orcid%3A{ORCID}' in call.request.url or \
            f'author.orcid:{ORCID}' in call.request.url
    assert 'cursor=abc' in responses.calls[1].request.url


def test_parse_work_ids_and_pmc():
    work = make_work(locations=[{
        'landing_page_url': 'https://www.ncbi.nlm.nih.gov/pmc/articles/12550278'}])
    cand = openalex.parse_work(work)
    assert cand.openalex_id == 'W4414790363'
    assert cand.pmid == '41143079'
    assert cand.pmcid == 'PMC12550278'
    assert cand.pmc_url.endswith('/pmc/articles/12550278')
    assert cand.source == 'openalex'
    assert cand.oa_url == 'https://oa.example/x'
    assert cand.oa_status == 'green'
    assert cand.publication_name == 'Nature'
    assert cand.year == 2025


def test_parse_work_doi_normalized():
    cand = openalex.parse_work(make_work(doi='https://doi.org/10.1162/IMAG.A.958'))
    assert cand.doi == '10.1162/imag.a.958'


def test_parse_work_authors_family_given():
    cand = openalex.parse_work(make_work())
    assert cand.authors == [{'name': 'Poldrack, Russell A.'}]


@pytest.mark.parametrize('raw,expected', [
    ('dissertation', 'thesis'), ('peer-review', 'other'),
    ('article', 'journal-article'), ('book-chapter', 'book-chapter')])
def test_parse_work_type_mapping(raw, expected):
    cand = openalex.parse_work(make_work(type=raw))
    assert cand.publication_type == expected
    assert cand.openalex_type == raw


def test_parse_work_supplement_flag():
    cand = openalex.parse_work(make_work(biblio={'first_page': 'S123'}))
    assert cand.is_supplement is True
    assert openalex.parse_work(make_work()).is_supplement is False


def test_parse_work_location_dois():
    work = make_work(locations=[
        {'landing_page_url': 'https://doi.org/10.1101/2025.01.14.633053'},
        {'landing_page_url': 'https://doi.org/10.1038/X'}])
    cand = openalex.parse_work(work)
    assert cand.location_dois == ['10.1101/2025.01.14.633053']


def test_full_authors_refetches_truncated(monkeypatch):
    short = make_work(authorships=[{'raw_author_name': f'A B{i}'} for i in range(100)])
    full = make_work(authorships=[{'raw_author_name': f'A B{i}'} for i in range(120)])
    fetched = []
    monkeypatch.setattr(openalex, 'fetch_work',
                        lambda wid, key: fetched.append(wid) or full)
    cand = openalex.full_authors(openalex.parse_work(short), 'KEY')
    assert fetched == ['W4414790363']
    assert len(cand.authors) == 120


def test_full_authors_returns_untruncated_unchanged():
    cand = openalex.parse_work(make_work())
    assert openalex.full_authors(cand, 'KEY') is cand


@responses.activate
def test_get_retries_connection_error_then_raises_source_error(sleeps):
    for _ in range(4):
        responses.add(responses.GET, 'https://x.test/a',
                      body=requests.ConnectionError('boom'))
    with pytest.raises(SourceError, match='ConnectionError') as exc_info:
        http.get('https://x.test/a', params={'api_key': 'SECRET'})
    assert len(responses.calls) == 4
    assert len(sleeps) == 3
    assert 'SECRET' not in str(exc_info.value)
    assert exc_info.value.__cause__ is None  # chained exception text would hold URL params


@responses.activate
def test_get_connection_error_then_success(sleeps):
    responses.add(responses.GET, 'https://x.test/a',
                  body=requests.Timeout('slow'))
    responses.add(responses.GET, 'https://x.test/a', json={'ok': 1})
    assert http.get('https://x.test/a').json() == {'ok': 1}
    assert len(sleeps) == 1


@responses.activate
def test_fetch_works_invalid_json_is_source_error():
    responses.add(responses.GET, WORKS_URL, body='<html>not json</html>')
    with pytest.raises(SourceError, match='invalid JSON'):
        openalex.fetch_works_by_orcid(ORCID, 'KEY')


@responses.activate
def test_fetch_works_missing_keys_is_source_error():
    responses.add(responses.GET, WORKS_URL, json={'unexpected': 1})
    with pytest.raises(SourceError):
        openalex.fetch_works_by_orcid(ORCID, 'KEY')


def test_parse_work_authors_collapses_whitespace():
    work = make_work(authorships=[{'raw_author_name': ' Russell  A.   Poldrack '}])
    assert openalex.parse_work(work).authors == [{'name': 'Poldrack, Russell A.'}]


@responses.activate
def test_get_json_non_object_is_source_error():
    responses.add(responses.GET, 'https://x.test/a', body='[]')
    with pytest.raises(SourceError, match='unexpected JSON body'):
        http.get_json('https://x.test/a')


@responses.activate
def test_fetch_work_null_body_is_source_error():
    responses.add(responses.GET, 'https://api.openalex.org/works/W1', body='null')
    with pytest.raises(SourceError, match='unexpected JSON body'):
        openalex.fetch_work('W1', 'KEY')
