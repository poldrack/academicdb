"""Build the publication YAML consumed by the static sites."""
from collections import defaultdict

import yaml

from academic.models import Link, Publication
from academic.tombstones import doi_key


def _author_name(author):
    name = (author.get('name') or '').strip()
    if name:
        return name
    return ' '.join(p for p in (author.get('given'), author.get('family')) if p).strip()


def _authors(pub):
    names = (_author_name(a) for a in (pub.authors or []) if isinstance(a, dict))
    return [{'name': n} for n in names if n]


def _identifiers(pub):
    ids = pub.identifiers or {}
    pairs = ((k, str(ids.get(k) or '')) for k in ('pmid', 'pmcid'))
    return {k: v for k, v in pairs if v}


def _links(pub, resources):
    links = {k: v for k, v in (pub.links or {}).items() if v}
    if resources:
        links['resources'] = list(resources)
    return links


def site_record(pub, resources=()):
    date = pub.publication_date
    return {
        'doi': pub.doi,
        'title': pub.title,
        'year': pub.year,
        'publication_date': date.isoformat() if date else None,
        'publication_name': pub.publication_name,
        'publication_type': pub.publication_type,
        'is_preprint': pub.is_preprint,
        'volume': pub.volume,
        'page_range': pub.page_range,
        'authors': _authors(pub),
        'identifiers': _identifiers(pub),
        'links': _links(pub, resources),
        'oa_url': (pub.metadata or {}).get('oa_url'),
    }


def _resources_by_doi(user):
    grouped = defaultdict(list)
    for link in Link.objects.filter(owner=user).order_by('type', 'url'):
        grouped[link.doi.lower()].append(
            {'type': link.type, 'url': link.url, 'title': link.title}
        )
    return grouped


def _sort_key(pub):
    date = pub.publication_date
    return (
        -(pub.year or 0),
        date is None,
        -date.toordinal() if date else 0,
        (pub.title or '').lower(),
        pub.id,
    )


def _publications(user, include_pending):
    pubs = Publication.objects.filter(owner=user, is_ignored=False)
    if not include_pending:
        pubs = pubs.filter(review_status='approved')
    return sorted(pubs, key=_sort_key)


def site_records(user, include_pending=False):
    pubs = _publications(user, include_pending)
    resources = _resources_by_doi(user)
    return [site_record(p, resources.get((p.doi or '').lower(), ())) for p in pubs]


def render_site_yaml(records):
    return yaml.safe_dump(
        {'publications': records}, sort_keys=False, allow_unicode=True, width=10000
    )


def record_key(record):
    key = doi_key(record.get('doi'))
    if key:
        return key
    pmid = (record.get('identifiers') or {}).get('pmid')
    return f'pmid:{pmid}' if pmid else ''
