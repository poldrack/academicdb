"""Fill-only enrichment: never overwrites existing or hand-edited data."""
from dataclasses import dataclass, field

from django.utils import timezone

from academic.sync.candidates import Candidate

FILL_FIELDS = ('publication_date', 'publication_name', 'volume', 'page_range')
COMPARE_FIELDS = ('title', 'publication_name', 'year')
IDENTIFIER_KEYS = ('pmid', 'pmcid', 'openalex')


@dataclass
class EnrichResult:
    changed: list[str] = field(default_factory=list)
    discrepancies: list[dict] = field(default_factory=list)
    updates: dict = field(default_factory=dict)


def _empty(value) -> bool:
    return value is None or value == '' or value == []


def _norm(value):
    if isinstance(value, str):
        return ' '.join(value.lower().split())
    return int(value) if isinstance(value, (int, float)) else value


def _plan_fill(pub, c, result):
    for name in FILL_FIELDS:
        theirs = getattr(c, name, None)
        flagged = pub.manual_edits.get(name)
        if _empty(getattr(pub, name)) and not _empty(theirs) and not flagged:
            result.changed.append(name)
            result.updates[name] = theirs
    if _empty(pub.authors) and c.authors and not pub.manual_edits.get('authors'):
        result.changed.append('authors')
        result.updates['authors'] = c.authors


def _candidate_ids(c, pmc) -> dict:
    pmc = pmc or {}
    return {
        'pmid': c.pmid or pmc.get('pmid') or '',
        'pmcid': c.pmcid or pmc.get('pmcid') or '',
        'openalex': c.openalex_id,
    }


def _plan_identifiers(pub, c, pmc, result):
    ours = dict(pub.identifiers or {})
    merged = dict(ours)
    for key, theirs in _candidate_ids(c, pmc).items():
        if not theirs:
            continue
        if not ours.get(key):
            merged[key] = theirs
            result.changed.append(f'identifiers.{key}')
        elif str(ours[key]) != str(theirs):
            result.discrepancies.append(
                {'field': f'identifiers.{key}', 'ours': ours[key], 'theirs': theirs})
    if merged != ours:
        result.updates['identifiers'] = merged


def _plan_oa(pub, c, result):
    metadata = pub.metadata or {}
    if not c.oa_url or pub.manual_edits.get('oa_url') or pub.manual_edits.get('metadata'):
        return
    if metadata.get('oa_url') == c.oa_url:
        return
    result.updates['metadata'] = {
        **metadata, 'oa_url': c.oa_url, 'oa_status': c.oa_status}
    result.changed.append('metadata.oa_url')


def _plan_discrepancies(pub, c, result):
    for name in COMPARE_FIELDS:
        ours, theirs = getattr(pub, name), getattr(c, name, None)
        if _empty(ours) or _empty(theirs):
            continue
        if _norm(ours) != _norm(theirs):
            result.discrepancies.append(
                {'field': name, 'ours': ours, 'theirs': theirs})


def plan_enrichment(pub, c: Candidate, pmc: dict | None = None) -> EnrichResult:
    result = EnrichResult()
    _plan_fill(pub, c, result)
    _plan_identifiers(pub, c, pmc, result)
    _plan_oa(pub, c, result)
    _plan_discrepancies(pub, c, result)
    return result


def apply_enrichment(pub, c: Candidate, pmc: dict | None = None) -> EnrichResult:
    result = plan_enrichment(pub, c, pmc)
    if not result.updates:
        return result
    for name, value in result.updates.items():
        setattr(pub, name, value)
    pub.last_api_sync = timezone.now()
    pub.save(update_fields=[*result.updates, 'last_api_sync'])
    return result
