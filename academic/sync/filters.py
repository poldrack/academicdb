"""Discovery filters: exclusions, cutoff, version collapse, known-work dedupe."""
import re
from datetime import date

from academic.sync.candidates import Candidate
from academic.sync.known import KnownWorks
from academic.tombstones import doi_key

EXCLUDED_OPENALEX_TYPES = frozenset({
    'peer-review', 'paratext', 'erratum', 'dataset', 'other', 'retraction',
    'editorial', 'letter', 'supplementary-materials',
})
CORRECTION_TITLE = re.compile(
    r'^\s*(corrigendum|correction|erratum|author correction)', re.IGNORECASE
)
VERSION_SUFFIX = re.compile(r'_v(\d+)\s*$', re.IGNORECASE)


def is_excluded(c: Candidate) -> bool:
    return (
        c.openalex_type in EXCLUDED_OPENALEX_TYPES
        or c.is_supplement
        or bool(CORRECTION_TITLE.match(c.title or ''))
    )


def before_cutoff(c: Candidate, cutoff: date) -> bool:
    if c.publication_date:
        return c.publication_date < cutoff
    if c.year:
        return date(c.year, 1, 1) < cutoff
    return True


def _version(c: Candidate) -> int:
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
