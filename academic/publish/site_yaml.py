"""Build the publication YAML consumed by the static sites."""
import re
import unicodedata
from collections import defaultdict

import yaml

from academic.models import Link, Publication
from academic.publish.citations import format_publication
from academic.tombstones import doi_key

INITIALS = re.compile(r'[A-Z]{1,4}')


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
    return {'resources': list(resources)} if resources else {}


def site_record(pub, resources=()):
    date = pub.publication_date
    record = {
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
    record['citation'] = format_publication(record)
    return record


def _resources_by_doi(user):
    grouped = defaultdict(list)
    for link in Link.objects.filter(owner=user).order_by('type', 'url'):
        key = doi_key(link.doi)
        if key:
            grouped[key].append(
                {'type': link.type, 'url': link.url, 'title': link.title}
            )
    return grouped


def _fold(text):
    """Lowercase and strip accents so "Öztürk" sorts with "Oz"."""
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _initials_of(given):
    tokens = given.replace('.', ' ').split()
    return ''.join(part[0] for token in tokens if not token.islower()
                   for part in token.split('-') if part)


def _surname_and_initials(name):
    """Split "Family, Given", "Family INITIALS" or "Given Family"."""
    if ',' in name:
        surname, given = name.split(',', 1)
        return surname.strip(), _initials_of(given)
    tokens = name.split()
    if len(tokens) < 2:
        return name, ''
    if INITIALS.fullmatch(tokens[-1]):
        return ' '.join(tokens[:-1]), tokens[-1]
    return tokens[-1], _initials_of(' '.join(tokens[:-1]))


def _first_author_key(pub):
    """Sort key from the first author's surname, then initials."""
    names = [a['name'] for a in _authors(pub)]
    if not names:
        return (True, '', '')
    surname, initials = _surname_and_initials(names[0])
    return (False, _fold(surname), _fold(initials))


def _sort_key(pub):
    date = pub.publication_date
    return (
        -(pub.year or 0),
        _first_author_key(pub),
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
    return [site_record(p, resources.get(doi_key(p.doi), ())) for p in pubs]


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
