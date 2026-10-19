"""Discovery filters: exclusions, cutoff, version collapse, known-work dedupe."""
import math
import re
from datetime import date

from academic.sync.candidates import Candidate
from academic.sync.known import KnownWorks
from academic.tombstones import doi_key

EXCLUDED_OPENALEX_TYPES = frozenset({
    'peer-review', 'paratext', 'erratum', 'dataset', 'other', 'retraction',
    'editorial', 'letter', 'supplementary-materials', 'software', 'dissertation',
})
OSF_PROJECT_PREFIX = '10.17605/'  # OSF project pages, not OSF preprints
CORRECTION_TITLE = re.compile(
    r'^\s*((author |publisher )?(correction|erratum|errata|corrigendum|addendum)'
    r'( to| for)?\s*[:\-\u2013]'
    r'|corrigendum\b'
    r'|retraction( note| notice)?\s*[:\-\u2013]'
    r'|expression of concern\b)',
    re.IGNORECASE,
)
VERSION_SUFFIX = re.compile(r'_v(\d+)\s*$', re.IGNORECASE)
ELIFE_VERSION = re.compile(r'^10\.7554/elife\.\d+(?:\.(\d+))?$', re.IGNORECASE)


def _repository_copy(c: Candidate) -> bool:
    """A non-preprint known only from institutional repositories."""
    return c.repository_only and c.openalex_type != 'preprint' and not c.pmid


def is_excluded(c: Candidate) -> bool:
    return (
        c.openalex_type in EXCLUDED_OPENALEX_TYPES
        or c.is_supplement
        or bool(c.excluded_type)
        or bool(CORRECTION_TITLE.match(c.title or ''))
        or not (c.doi or c.pmid)
        or (c.doi or '').lower().startswith(OSF_PROJECT_PREFIX)
        or _repository_copy(c)
    )


def before_cutoff(c: Candidate, cutoff: date) -> bool:
    if c.publication_date:
        return c.publication_date < cutoff
    if c.year:
        return date(c.year, 1, 1) < cutoff
    return True


def _version(c: Candidate) -> float:
    elife = ELIFE_VERSION.match(c.doi or '')
    if elife:  # the unversioned eLife DOI always resolves to the latest version
        return int(elife.group(1)) if elife.group(1) else math.inf
    match = VERSION_SUFFIX.search(c.doi or '')
    return int(match.group(1)) if match else 0


def collapse_versions(cands: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    out: list = []
    for c in cands:
        key = doi_key(c.doi)
        if not key:
            out.append(c)
        elif key not in best:
            best[key] = c
            out.append(key)
        elif _version(c) > _version(best[key]):
            best[key] = c
    return [best[x] if isinstance(x, str) else x for x in out]


def select_new(cands, known: KnownWorks, cutoff: date) -> list[Candidate]:
    kept = []
    for c in collapse_versions(cands):
        if is_excluded(c) or before_cutoff(c, cutoff) or known.contains(c):
            continue
        known.add(c)
        kept.append(c)
    return kept
