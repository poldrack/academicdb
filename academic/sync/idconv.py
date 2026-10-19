from academic.link_import import normalize_doi
from academic.sync.http import SourceError, get_json

IDCONV = 'https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/'
BATCH = 200


def _key(requested):
    return normalize_doi(requested) if '/' in requested else requested


def _convert_batch(ids, idtype, email):
    params = {'ids': ','.join(ids), 'idtype': idtype, 'format': 'json',
              'tool': 'academicdb', 'email': email}
    data = get_json(IDCONV, params)
    if data.get('status') == 'error':
        raise SourceError(f'{IDCONV}: error response')
    return data.get('records', [])


def _usable(record):
    return (record.get('requested-id') and record.get('pmcid')
            and record.get('status') != 'error')


def _by_type(ids):
    groups = {'doi': [], 'pmid': []}
    for value in ids:
        groups['doi' if '/' in value else 'pmid'].append(value)
    return groups


def lookup_pmcids(ids: list[str], email: str) -> dict[str, dict]:
    out = {}
    for idtype, group in _by_type(ids).items():
        for start in range(0, len(group), BATCH):
            for record in _convert_batch(group[start:start + BATCH], idtype, email):
                if _usable(record):
                    out[_key(record['requested-id'])] = {
                        'pmid': str(record.get('pmid', '')), 'pmcid': record['pmcid']}
    return out
