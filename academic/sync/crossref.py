from academic.link_import import normalize_doi
from academic.sync.http import SourceError, get

CROSSREF = 'https://api.crossref.org/works/'


def _relation(doi):
    resp = get(CROSSREF + doi, ok_statuses=(404,))
    if resp.status_code == 404:
        return {}
    try:
        body = resp.json()
    except ValueError:
        raise SourceError(f'{CROSSREF}{doi}: invalid body') from None
    message = body.get('message') if isinstance(body, dict) else None
    return message.get('relation') if isinstance(message, dict) else None


def _entries(doi):
    relation = _relation(doi)
    entries = relation.get('is-preprint-of', []) if isinstance(relation, dict) else []
    return entries if isinstance(entries, list) else []


def _entry_doi(entry):
    if isinstance(entry, dict) and entry.get('id-type') == 'doi' and entry.get('id'):
        return normalize_doi(entry['id'])
    return None


def published_dois_for_preprint(doi: str) -> list[str]:
    found = (_entry_doi(e) for e in _entries(doi))
    return [d for d in found if d]
