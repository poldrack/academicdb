"""Permanent tombstones for deleted or rejected works."""
import re

from academic.link_import import normalize_doi
from academic.models import Publication, RejectedWork

OSF_VERSION_SUFFIX = re.compile(r'_v\d+$')
ELIFE_VERSION_SUFFIX = re.compile(r'^(10\.7554/elife\.\d+)\.\d+$')


def doi_key(doi):
    if not doi:
        return ''
    key = re.sub(r'/+', '/', normalize_doi(doi))
    if 'osf.io/' in key:
        key = OSF_VERSION_SUFFIX.sub('', key)
    return ELIFE_VERSION_SUFFIX.sub(r'\1', key)


def title_key(title):
    text = re.sub(r'[^a-z0-9 ]', '', (title or '').lower())
    return ' '.join(text.split())[:200]


def _identity(pub):
    doi = doi_key(pub.doi)
    return {'doi': doi} if doi else {'doi': '', 'title_key': title_key(pub.title)}


def _defaults(pub, reason):
    identifiers = pub.identifiers or {}
    return {
        'reason': reason,
        'openalex_id': identifiers.get('openalex') or '',
        'pmid': str(identifiers.get('pmid') or ''),
        'title_key': title_key(pub.title),
    }


def record_tombstone(pub: Publication, reason: str) -> RejectedWork:
    identity = _identity(pub)
    existing = RejectedWork.objects.filter(
        owner_id=pub.owner_id, **identity).order_by('id').first()
    if existing:
        return existing
    return RejectedWork.objects.create(
        owner_id=pub.owner_id, **{**_defaults(pub, reason), **identity})
