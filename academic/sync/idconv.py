from academic.link_import import normalize_doi
from academic.sync.http import get_json

IDCONV = 'https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/'
BATCH = 200


def _key(requested):
    return normalize_doi(requested) if '/' in requested else requested


def _convert_batch(ids, email):
    params = {'ids': ','.join(ids), 'format': 'json',
              'tool': 'academicdb', 'email': email}
    return get_json(IDCONV, params).get('records', [])


def _usable(record):
    return record.get('status') != 'error' and record.get('pmcid')


def lookup_pmcids(ids: list[str], email: str) -> dict[str, dict]:
    out = {}
    for start in range(0, len(ids), BATCH):
        for record in _convert_batch(ids[start:start + BATCH], email):
            if _usable(record):
                out[_key(record['requested-id'])] = {
                    'pmid': str(record.get('pmid', '')), 'pmcid': record['pmcid']}
    return out
