import io
import re
from datetime import date

from Bio import Entrez

from academic.sync.candidates import Candidate
from academic.sync.http import SourceError, get, get_json
from academic.sync.text import clean_markup

EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
BATCH = 200
EXCLUDED_PUBMED_TYPES = frozenset({
    'Published Erratum', 'Editorial', 'Letter', 'Comment',
    'Retraction of Publication', 'Retracted Publication', 'Expression of Concern',
})


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
    url = f'{EUTILS}/esearch.fcgi'
    data = get_json(url, params)
    result = data.get('esearchresult', {})
    if 'error' in data or 'ERROR' in result:
        raise SourceError(f'{url}: error response')
    return result.get('idlist', [])


def _fetch_batch(ids, email, api_key):
    params = {'db': 'pubmed', 'id': ','.join(ids), 'retmode': 'xml',
              **_base_params(email, api_key)}
    resp = get(f'{EUTILS}/efetch.fcgi', params)
    try:
        return Entrez.read(io.BytesIO(resp.content)).get('PubmedArticle', [])
    except Exception as exc:
        raise SourceError('efetch: unparseable XML') from exc


def search_pubmed(query: str, mindate: date, email: str,
                  api_key: str | None = None) -> list[Candidate]:
    ids = _search_ids(query, mindate, email, api_key)
    candidates = []
    for start in range(0, len(ids), BATCH):
        for article in _fetch_batch(ids[start:start + BATCH], email, api_key):
            candidate = parse_pubmed_article(article)
            if candidate is not None:
                candidates.append(candidate)
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
    last = str(author.get('LastName', ''))
    first = str(author.get('ForeName') or author.get('Initials') or '')
    return f'{last}, {first}' if last and first else last or first


def _authors(art):
    names = (_author_name(a) for a in art.get('AuthorList', []))
    return [{'name': n} for n in names if n]


def _clean_title(raw):
    return clean_markup(raw).rstrip('.')


def _excluded_type(art) -> str:
    types = [str(t) for t in art.get('PublicationTypeList', [])]
    return next((t for t in types if t in EXCLUDED_PUBMED_TYPES), '')


def parse_pubmed_article(article: dict) -> Candidate | None:
    citation = article.get('MedlineCitation', {})
    art = citation.get('Article', {})
    journal = art.get('Journal', {})
    pmid = str(citation.get('PMID', ''))
    title = _clean_title(art.get('ArticleTitle', ''))
    if not pmid or not title:
        return None
    pub_date = journal.get('JournalIssue', {}).get('PubDate', {})
    return Candidate(
        source='pubmed',
        title=title,
        year=_year(pub_date),
        publication_date=None,
        publication_name=str(journal.get('Title', '')),
        publication_type='journal-article',
        authors=_authors(art),
        doi=_article_id(article, 'doi'),
        pmid=pmid,
        pmcid=_article_id(article, 'pmc'),
        volume=str(journal.get('JournalIssue', {}).get('Volume') or ''),
        page_range=str(art.get('Pagination', {}).get('MedlinePgn') or ''),
        excluded_type=_excluded_type(art),
    )
