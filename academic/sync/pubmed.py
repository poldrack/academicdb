import io
import re
from datetime import date

from Bio import Entrez

from academic.sync.candidates import Candidate
from academic.sync.http import SourceError, get, get_json

EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
BATCH = 200


def _base_params(email, api_key):
    params = {'tool': 'academicdb', 'email': email}
    if api_key:
        params['api_key'] = api_key
    return params


def _search_ids(query, mindate, email, api_key):
    params = {
        'db': 'pubmed', 'term': query, 'datetype': 'pdat',
        'mindate': mindate.strftime('%Y/%m/%d'), 'maxdate': '3000',
        'retmax': 1000, 'retmode': 'json', **_base_params(email, api_key),
    }
    data = get_json(f'{EUTILS}/esearch.fcgi', params)
    return data.get('esearchresult', {}).get('idlist', [])


def _fetch_batch(ids, email, api_key):
    params = {'db': 'pubmed', 'id': ','.join(ids), 'retmode': 'xml',
              **_base_params(email, api_key)}
    resp = get(f'{EUTILS}/efetch.fcgi', params)
    try:
        return Entrez.read(io.BytesIO(resp.content))['PubmedArticle']
    except Exception as exc:
        raise SourceError('efetch: unparseable XML') from exc


def search_pubmed(query: str, mindate: date, email: str,
                  api_key: str | None = None) -> list[Candidate]:
    ids = _search_ids(query, mindate, email, api_key)
    candidates = []
    for start in range(0, len(ids), BATCH):
        for article in _fetch_batch(ids[start:start + BATCH], email, api_key):
            candidates.append(parse_pubmed_article(article))
    return candidates


def _article_id(article, id_type):
    ids = article.get('PubmedData', {}).get('ArticleIdList', [])
    for item in ids:
        if getattr(item, 'attributes', {}).get('IdType') == id_type:
            return str(item)
    return ''


def _year(pub_date):
    if 'Year' in pub_date:
        return int(str(pub_date['Year']))
    match = re.search(r'\d{4}', str(pub_date.get('MedlineDate', '')))
    return int(match.group()) if match else None


def _author_name(author):
    if 'CollectiveName' in author:
        return str(author['CollectiveName'])
    return f"{author.get('LastName', '')}, {author.get('ForeName', '')}".strip(', ')


def parse_pubmed_article(article: dict) -> Candidate:
    citation = article['MedlineCitation']
    art = citation['Article']
    journal = art['Journal']
    authors = [{'name': _author_name(a)} for a in art.get('AuthorList', [])]
    return Candidate(
        source='pubmed',
        title=str(art['ArticleTitle']).rstrip('.'),
        year=_year(journal['JournalIssue']['PubDate']),
        publication_date=None,
        publication_name=str(journal.get('Title', '')),
        publication_type='journal-article',
        authors=authors,
        doi=_article_id(article, 'doi'),
        pmid=str(citation['PMID']),
        pmcid=_article_id(article, 'pmc'),
    )
