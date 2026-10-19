import io
import re
from datetime import date

import pytest
import responses
from Bio import Entrez

from academic.sync import crossref, idconv, pubmed
from academic.sync.http import SourceError

ESEARCH = f'{pubmed.EUTILS}/esearch.fcgi'
EFETCH = f'{pubmed.EUTILS}/efetch.fcgi'

XML_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" '
    '"https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">\n'
)


def article_xml(pubdate='<Year>2025</Year>'):
    return (
        '<PubmedArticle><MedlineCitation Status="MEDLINE" Owner="NLM">'
        '<PMID Version="1">123</PMID><Article PubModel="Print"><Journal>'
        f'<JournalIssue CitedMedium="Print"><PubDate>{pubdate}</PubDate></JournalIssue>'
        '<Title>Nature</Title></Journal><ArticleTitle>A title.</ArticleTitle>'
        '<AuthorList CompleteYN="Y"><Author ValidYN="Y"><LastName>Poldrack</LastName>'
        '<ForeName>Russell A</ForeName></Author></AuthorList></Article></MedlineCitation>'
        '<PubmedData><ArticleIdList><ArticleId IdType="doi">10.1/abc</ArticleId>'
        '<ArticleId IdType="pmc">PMC456</ArticleId></ArticleIdList></PubmedData>'
        '</PubmedArticle>'
    )


def efetch_body(pubdate='<Year>2025</Year>'):
    return f'{XML_HEAD}<PubmedArticleSet>{article_xml(pubdate)}</PubmedArticleSet>'


def parsed_article(pubdate='<Year>2025</Year>'):
    data = Entrez.read(io.BytesIO(efetch_body(pubdate).encode()))
    return data['PubmedArticle'][0]


def esearch_json(ids):
    return {'esearchresult': {'idlist': ids}}


@responses.activate
def test_search_pubmed_sends_mindate_and_tool():
    responses.add(responses.GET, ESEARCH, json=esearch_json(['123']))
    responses.add(responses.GET, EFETCH, body=efetch_body())
    result = pubmed.search_pubmed('poldrack[au]', date(2025, 10, 18), 'me@x.org')
    query = responses.calls[0].request.params
    assert query['mindate'] == '2025/10/18'
    assert query['maxdate'] == '3000'
    assert query['datetype'] == 'pdat'
    assert query['tool'] == 'academicdb'
    assert query['email'] == 'me@x.org'
    assert query['db'] == 'pubmed'
    assert query['term'] == 'poldrack[au]'
    assert query['retmax'] == '1000'
    assert query['retmode'] == 'json'
    assert 'api_key' not in query
    assert [c.pmid for c in result] == ['123']


@responses.activate
def test_search_pubmed_sends_api_key():
    responses.add(responses.GET, ESEARCH, json=esearch_json([]))
    pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org', api_key='KEY')
    assert responses.calls[0].request.params['api_key'] == 'KEY'


@responses.activate
def test_search_pubmed_no_ids_skips_efetch():
    responses.add(responses.GET, ESEARCH, json=esearch_json([]))
    assert pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org') == []
    assert len(responses.calls) == 1


@responses.activate
def test_search_pubmed_batches_efetch():
    ids = [str(i) for i in range(450)]
    responses.add(responses.GET, ESEARCH, json=esearch_json(ids))
    responses.add(responses.GET, EFETCH, body=efetch_body())
    pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org')
    fetches = [c for c in responses.calls if c.request.url.startswith(EFETCH)]
    assert len(fetches) == 3
    sizes = [len(c.request.params['id'].split(',')) for c in fetches]
    assert sizes == [200, 200, 50]
    assert fetches[0].request.params['retmode'] == 'xml'


@responses.activate
def test_search_pubmed_malformed_xml_raises_source_error():
    responses.add(responses.GET, ESEARCH, json=esearch_json(['1']))
    responses.add(responses.GET, EFETCH, body='not xml at all')
    with pytest.raises(SourceError):
        pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org')


def test_parse_pubmed_article_fields():
    c = pubmed.parse_pubmed_article(parsed_article())
    assert c.source == 'pubmed'
    assert c.doi == '10.1/abc'
    assert c.pmid == '123'
    assert c.pmcid == 'PMC456'
    assert c.title == 'A title'
    assert c.authors == [{'name': 'Poldrack, Russell A'}]
    assert c.year == 2025
    assert c.publication_name == 'Nature'
    assert c.publication_type == 'journal-article'


def test_parse_pubmed_medline_date_year():
    c = pubmed.parse_pubmed_article(
        parsed_article('<MedlineDate>2025 Jan-Feb</MedlineDate>')
    )
    assert c.year == 2025


def lookup_url():
    return re.compile(re.escape(idconv.IDCONV) + '.*')


@responses.activate
def test_lookup_pmcids_maps_requested_ids():
    records = [
        {'requested-id': '10.1/ABC', 'pmid': '1', 'pmcid': 'PMC1'},
        {'requested-id': '999', 'pmid': '999', 'pmcid': 'PMC9'},
    ]
    responses.add(responses.GET, lookup_url(), json={'records': records})
    out = idconv.lookup_pmcids(['10.1/ABC', '999'], 'me@x.org')
    assert out == {
        '10.1/abc': {'pmid': '1', 'pmcid': 'PMC1'},
        '999': {'pmid': '999', 'pmcid': 'PMC9'},
    }
    query = responses.calls[0].request.params
    assert query['format'] == 'json'
    assert query['tool'] == 'academicdb'
    assert query['email'] == 'me@x.org'


@responses.activate
def test_lookup_pmcids_drops_errors_and_missing_pmcid():
    records = [
        {'requested-id': '10.1/bad', 'status': 'error', 'pmcid': 'PMC2'},
        {'requested-id': '10.1/none', 'pmid': '5'},
    ]
    responses.add(responses.GET, lookup_url(), json={'records': records})
    assert idconv.lookup_pmcids(['10.1/bad', '10.1/none'], 'me@x.org') == {}


@responses.activate
def test_lookup_pmcids_batches_200():
    responses.add(responses.GET, lookup_url(), json={'records': []})
    idconv.lookup_pmcids([str(i) for i in range(250)], 'me@x.org')
    assert len(responses.calls) == 2


@responses.activate
def test_published_dois_for_preprint():
    relation = {'is-preprint-of': [
        {'id-type': 'doi', 'id': '10.1038/S41593-025-1'},
        {'id-type': 'uri', 'id': 'http://x'},
    ]}
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc',
                  json={'message': {'relation': relation}})
    assert crossref.published_dois_for_preprint('10.1101/abc') == ['10.1038/s41593-025-1']


@responses.activate
def test_published_dois_no_relation_is_empty():
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc',
                  json={'message': {}})
    assert crossref.published_dois_for_preprint('10.1101/abc') == []


@responses.activate
def test_published_dois_404_is_empty():
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc', status=404)
    assert crossref.published_dois_for_preprint('10.1101/abc') == []


@responses.activate
def test_published_dois_other_4xx_raises():
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc', status=400)
    with pytest.raises(SourceError):
        crossref.published_dois_for_preprint('10.1101/abc')


@responses.activate
def test_published_dois_5xx_raises(monkeypatch):
    monkeypatch.setattr('academic.sync.http.time.sleep', lambda s: None)
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc', status=500)
    with pytest.raises(SourceError):
        crossref.published_dois_for_preprint('10.1101/abc')


@responses.activate
def test_search_pubmed_book_only_is_empty():
    body = f'{XML_HEAD}<PubmedArticleSet></PubmedArticleSet>'
    responses.add(responses.GET, ESEARCH, json=esearch_json(['1']))
    responses.add(responses.GET, EFETCH, body=body)
    assert pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org') == []


def test_parse_pubmed_article_missing_journal():
    article = {'MedlineCitation': {'PMID': '7', 'Article': {'ArticleTitle': 'T.'}}}
    c = pubmed.parse_pubmed_article(article)
    assert (c.pmid, c.title, c.year, c.publication_name) == ('7', 'T', None, '')


@responses.activate
def test_search_pubmed_skips_record_without_pmid():
    responses.add(responses.GET, ESEARCH, json=esearch_json(['1']))
    responses.add(responses.GET, EFETCH, body=efetch_body())
    good = pubmed.parse_pubmed_article(parsed_article())
    assert pubmed.parse_pubmed_article({'MedlineCitation': {}}) is None
    assert good is not None
    result = pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org')
    assert len(result) == 1


def test_parse_pubmed_title_strips_markup():
    article = {'MedlineCitation': {'PMID': '7', 'Article': {
        'ArticleTitle': 'Effect of <i>Foo</i> on  <sup>2</sup>H\n mice.'}}}
    assert pubmed.parse_pubmed_article(article).title == 'Effect of Foo on 2H mice'


def test_parse_pubmed_author_initials_and_empty():
    authors = [{'LastName': 'Poldrack', 'Initials': 'RA'}, {}]
    article = {'MedlineCitation': {'PMID': '7', 'Article': {
        'ArticleTitle': 'T', 'AuthorList': authors}}}
    assert pubmed.parse_pubmed_article(article).authors == [{'name': 'Poldrack, RA'}]


@responses.activate
@pytest.mark.parametrize('payload', [
    {'esearchresult': {'ERROR': 'bad', 'idlist': []}},
    {'error': 'rate limited'},
])
def test_search_pubmed_error_payload_raises(payload):
    responses.add(responses.GET, ESEARCH, json=payload)
    with pytest.raises(SourceError) as err:
        pubmed.search_pubmed('q', date(2025, 1, 1), 'me@x.org')
    assert str(err.value) == f'{ESEARCH}: error response'


@responses.activate
@pytest.mark.parametrize('relation', [
    {'is-preprint-of': [{'id-type': 'doi'}, 'junk', None]},
    ['x'],
    {'is-preprint-of': 'x'},
    'x',
])
def test_published_dois_malformed_relation_is_empty(relation):
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc',
                  json={'message': {'relation': relation}})
    assert crossref.published_dois_for_preprint('10.1101/abc') == []


@responses.activate
def test_published_dois_entry_without_id():
    relation = {'is-preprint-of': [
        {'id-type': 'doi'}, {'id-type': 'doi', 'id': '10.1/X'}]}
    responses.add(responses.GET, crossref.CROSSREF + '10.1101/abc',
                  json={'message': {'relation': relation}})
    assert crossref.published_dois_for_preprint('10.1101/abc') == ['10.1/x']


@responses.activate
def test_lookup_pmcids_error_status_raises():
    responses.add(responses.GET, lookup_url(),
                  json={'status': 'error', 'message': 'bad'})
    with pytest.raises(SourceError) as err:
        idconv.lookup_pmcids(['1'], 'me@x.org')
    assert str(err.value) == f'{idconv.IDCONV}: error response'
    assert 'me@x.org' not in str(err.value)


@responses.activate
def test_lookup_pmcids_record_without_requested_id_skipped():
    records = [{'pmcid': 'PMC1'}, {'requested-id': '9', 'pmcid': 'PMC9'}]
    responses.add(responses.GET, lookup_url(), json={'records': records})
    assert idconv.lookup_pmcids(['9'], 'me@x.org') == {'9': {'pmid': '', 'pmcid': 'PMC9'}}


@responses.activate
def test_source_error_does_not_chain_url_with_params(monkeypatch):
    from academic.sync import http
    monkeypatch.setattr(http.time, 'sleep', lambda s: None)
    url = 'https://example.org/x'
    responses.add(responses.GET, url, body=http.requests.ConnectionError('boom'))
    with pytest.raises(SourceError) as err:
        http.get(url, {'api_key': 'SECRET'})
    assert err.value.__cause__ is None
    assert err.value.__suppress_context__ is True
    assert 'api_key' not in str(err.value)


def test_parse_pubmed_volume_and_pages():
    article = {'MedlineCitation': {'PMID': '7', 'Article': {
        'ArticleTitle': 'T.',
        'Journal': {'JournalIssue': {'Volume': '12'}},
        'Pagination': {'MedlinePgn': '100-110'}}}}
    c = pubmed.parse_pubmed_article(article)
    assert (c.volume, c.page_range) == ('12', '100-110')
    bare = pubmed.parse_pubmed_article(
        {'MedlineCitation': {'PMID': '7', 'Article': {'ArticleTitle': 'T.'}}})
    assert (bare.volume, bare.page_range) == ('', '')


def typed_article(*types):
    type_xml = ''.join(f'<PublicationType UI="D0">{t}</PublicationType>' for t in types)
    xml = article_xml().replace(
        '</AuthorList>', f'</AuthorList><PublicationTypeList>{type_xml}'
        '</PublicationTypeList>')
    body = f'{XML_HEAD}<PubmedArticleSet>{xml}</PubmedArticleSet>'
    return Entrez.read(io.BytesIO(body.encode()))['PubmedArticle'][0]


@pytest.mark.parametrize('notice', [
    'Published Erratum', 'Editorial', 'Letter', 'Comment',
    'Retraction of Publication', 'Retracted Publication', 'Expression of Concern',
])
def test_pubmed_notice_types_are_excluded(notice):
    from academic.sync.filters import is_excluded
    c = pubmed.parse_pubmed_article(typed_article('Journal Article', notice))
    assert is_excluded(c)


def test_pubmed_journal_article_not_excluded():
    from academic.sync.filters import is_excluded
    c = pubmed.parse_pubmed_article(typed_article('Journal Article', 'Review'))
    assert not is_excluded(c)
    assert c.publication_type == 'journal-article'


@responses.activate
def test_idconv_uses_new_endpoint_and_one_id_type_per_request():
    assert idconv.IDCONV == 'https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/'
    responses.add(responses.GET, lookup_url(), json={'records': [
        {'requested-id': '10.1/a', 'pmid': '1', 'pmcid': 'PMC1'},
        {'requested-id': '123', 'pmid': '123', 'pmcid': 'PMC123'}]})
    out = idconv.lookup_pmcids(['10.1/a', '123', '10.1/b'], 'e@x')
    assert len(responses.calls) == 2
    params = {c.request.params['idtype']: c.request.params['ids']
              for c in responses.calls}
    assert params == {'doi': '10.1/a,10.1/b', 'pmid': '123'}
    assert set(out) == {'10.1/a', '123'}
