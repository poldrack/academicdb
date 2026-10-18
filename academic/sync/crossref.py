from academic.link_import import normalize_doi
from academic.sync.http import SourceError, get

CROSSREF = 'https://api.crossref.org/works/'


def _relation(doi):
    resp = get(CROSSREF + doi, ok_statuses=(404,))
    if resp.status_code == 404:
        return {}
    try:
        return resp.json().get('message', {}).get('relation', {})
    except (ValueError, AttributeError) as exc:
        raise SourceError(f'{CROSSREF}{doi}: invalid body') from exc


def published_dois_for_preprint(doi: str) -> list[str]:
    related = _relation(doi).get('is-preprint-of', [])
    return [normalize_doi(r['id']) for r in related if r.get('id-type') == 'doi']
