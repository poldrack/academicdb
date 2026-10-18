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
