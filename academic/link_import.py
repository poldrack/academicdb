"""
Import resource links (Code/Data/OSF) for publications.

Sources: the links spreadsheet (columns type,DOI,url) and the
`links.resources` entries in a site's exported publications.json.
"""
import csv
import json
from dataclasses import dataclass, field

from academic.models import Link, Publication


DOI_PREFIXES = (
    'https://doi.org/', 'http://doi.org/',
    'https://dx.doi.org/', 'http://dx.doi.org/',
    'doi:',
)
CSV_COLUMNS = ('type', 'DOI', 'url')


@dataclass(frozen=True)
class LinkRecord:
    doi: str
    type: str
    url: str
    title: str = ''


@dataclass
class LinkImportResult:
    created: int = 0
    existing: int = 0
    unmatched_dois: list = field(default_factory=list)


def normalize_doi(value):
    doi = value.strip().lower()
    for prefix in DOI_PREFIXES:
        if doi.startswith(prefix):
            return doi[len(prefix):]
    return doi


def normalize_url(value):
    url = value.strip()
    return url[:-1] if url.endswith('/') else url


def _record(doi, link_type, url, title=''):
    return LinkRecord(normalize_doi(doi), link_type.strip(), normalize_url(url), title.strip())


def read_links_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing column(s): {', '.join(missing)}")
        return [
            _record(row['DOI'], row['type'], row['url'])
            for row in reader
            if all((row.get(c) or '').strip() for c in CSV_COLUMNS)
        ]


def read_links_from_publications_json(path):
    with open(path, encoding='utf-8') as f:
        publications = json.load(f).get('publications', [])
    return [
        _record(pub['doi'], res['type'], res['url'], res.get('title', ''))
        for pub in publications if pub.get('doi')
        for res in (pub.get('links') or {}).get('resources', [])
    ]


def _dedupe(records):
    seen = {}
    for rec in records:
        rec = _record(rec.doi, rec.type, rec.url, rec.title)
        seen.setdefault((rec.doi, rec.type, rec.url), rec)
    return list(seen.values())


def _publication_exists(user, doi):
    return Publication.objects.filter(owner=user, doi__iexact=doi).exists()


def import_link_records(user, records):
    result = LinkImportResult()
    for rec in _dedupe(records):
        if not _publication_exists(user, rec.doi):
            result.unmatched_dois.append(rec.doi)
            continue
        _, created = Link.objects.get_or_create(
            owner=user, doi=rec.doi, type=rec.type, url=rec.url,
            defaults={'title': rec.title, 'source': 'csv_import'},
        )
        if created:
            result.created += 1
        else:
            result.existing += 1
    return result
