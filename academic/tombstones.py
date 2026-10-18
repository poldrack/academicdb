"""Permanent tombstones for deleted or rejected works."""
import re

from academic.link_import import normalize_doi
from academic.models import Publication, RejectedWork

OSF_VERSION_SUFFIX = re.compile(r'_v\d+$')


def doi_key(doi):
    if not doi:
        return ''
    key = re.sub(r'/+', '/', normalize_doi(doi))
    if 'osf.io/' in key:
        key = OSF_VERSION_SUFFIX.sub('', key)
    return key


def title_key(title):
    text = re.sub(r'[^a-z0-9 ]', '', (title or '').lower())
    return ' '.join(text.split())[:200]


def _identity(pub):
    doi = doi_key(pub.doi)
    return {'doi': doi} if doi else {'title_key': title_key(pub.title)}


def record_tombstone(pub: Publication, reason: str) -> RejectedWork:
    identifiers = pub.identifiers or {}
    defaults = {
        'reason': reason,
        'openalex_id': identifiers.get('openalex', ''),
        'pmid': identifiers.get('pmid', ''),
        'title_key': title_key(pub.title),
    }
    work, _ = RejectedWork.objects.get_or_create(
        owner_id=pub.owner_id, defaults=defaults, **_identity(pub)
    )
    return work
