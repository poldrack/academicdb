import re
from datetime import date

from academic.link_import import normalize_doi
from academic.sync.candidates import Candidate
from academic.sync.http import SourceError, get_json
from academic.sync.text import clean_markup

OPENALEX = 'https://api.openalex.org'
TYPE_MAP = {
    'article': 'journal-article',
    'preprint': 'preprint',
    'book-chapter': 'book-chapter',
    'book': 'book',
    'dissertation': 'thesis',
    'report': 'report',
}
PMC_RE = re.compile(r'ncbi\.nlm\.nih\.gov/pmc/articles/(?:PMC)?(\d+)', re.I)
DOI_URL_RE = re.compile(r'doi\.org/(.+)$', re.I)


def fetch_works_by_orcid(orcid, api_key):
    works, cursor = [], '*'
    while cursor:
        params = {'filter': f'author.orcid:{orcid}', 'per-page': 200,
                  'cursor': cursor, 'api_key': api_key}
        data = get_json(f'{OPENALEX}/works', params)
        results, meta = data.get('results'), data.get('meta')
        if results is None or meta is None:
            raise SourceError(f'{OPENALEX}/works: unexpected response')
        works.extend(results)
        cursor = meta.get('next_cursor')
    return works


def fetch_work(openalex_id, api_key):
    return get_json(f'{OPENALEX}/works/{openalex_id}', {'api_key': api_key})


def _family_given(name):
    name = ' '.join(name.split())
    if ' ' not in name:
        return name
    given, family = name.rsplit(' ', 1)
    return f'{family}, {given}'


def _parse_authors(authorships):
    names = (a.get('raw_author_name') or (a.get('author') or {}).get('display_name')
             for a in authorships)
    return [{'name': _family_given(n)} for n in names if n]


def _parse_pmc(locations):
    for loc in locations:
        url = loc.get('landing_page_url') or ''
        match = PMC_RE.search(url)
        if match:
            return f'PMC{match.group(1)}', url
    return '', ''


def _parse_location_dois(locations, own_doi):
    dois = []
    for loc in locations:
        match = DOI_URL_RE.search(loc.get('landing_page_url') or '')
        doi = normalize_doi(match.group(1)) if match else ''
        if doi and doi != own_doi and doi not in dois:
            dois.append(doi)
    return dois


def _repository_only(locations):
    kinds = [(loc.get('source') or {}).get('type') for loc in locations]
    kinds = [k for k in kinds if k]
    return bool(kinds) and all(k == 'repository' for k in kinds)


def _is_supplement(biblio):
    issue = biblio.get('issue') or ''
    first_page = biblio.get('first_page') or ''
    return 'suppl' in issue.lower() or bool(re.match(r'S\d+', first_page))


def _page_range(biblio):
    first, last = biblio.get('first_page'), biblio.get('last_page')
    if first and last and first != last:
        return f'{first}-{last}'
    return first or ''


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _pmid(work):
    match = re.search(r'(\d+)$', (work.get('ids') or {}).get('pmid') or '')
    return match.group(1) if match else ''


def parse_work(work):
    locations = work.get('locations') or []
    authorships = work.get('authorships') or []
    oa = work.get('open_access') or {}
    best = work.get('best_oa_location') or {}
    doi = normalize_doi(work.get('doi') or '')
    pmcid, pmc_url = _parse_pmc(locations)
    raw_type = work.get('type') or ''
    source = (work.get('primary_location') or {}).get('source') or {}
    return Candidate(
        source='openalex',
        title=clean_markup(work.get('title')),
        year=work.get('publication_year'),
        publication_date=_parse_date(work.get('publication_date')),
        publication_name=source.get('display_name') or '',
        publication_type=TYPE_MAP.get(raw_type, 'other'),
        authors=_parse_authors(authorships),
        doi=doi,
        pmid=_pmid(work),
        pmcid=pmcid,
        openalex_id=work['id'].rstrip('/').rsplit('/', 1)[-1],
        oa_url=best.get('landing_page_url') or oa.get('oa_url') or '',
        oa_status=oa.get('oa_status') or '',
        openalex_type=raw_type,
        location_dois=_parse_location_dois(locations, doi),
        pmc_url=pmc_url,
        is_supplement=_is_supplement(work.get('biblio') or {}),
        repository_only=_repository_only(locations),
        volume=(work.get('biblio') or {}).get('volume') or '',
        page_range=_page_range(work.get('biblio') or {}),
        authors_truncated=bool(work.get('is_authors_truncated')
                               or len(authorships) >= 100),
    )


def full_authors(candidate, api_key):
    if not candidate.authors_truncated:
        return candidate
    full = parse_work(fetch_work(candidate.openalex_id, api_key))
    return full
