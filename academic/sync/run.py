"""Weekly sync orchestrator: fetch everything first, then write in one transaction."""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Mapping

from django.db import transaction

from academic.link_import import normalize_doi
from academic.models import Publication
from academic.sync.candidates import Candidate
from academic.sync.crossref import published_dois_for_preprint
from academic.sync.enrich import apply_enrichment
from academic.sync.filters import select_new
from academic.sync.http import SourceError
from academic.sync.idconv import lookup_pmcids
from academic.sync.known import KnownWorks
from academic.sync.openalex import fetch_works_by_orcid, full_authors, parse_work
from academic.sync.preprints import propose_hides
from academic.sync.pubmed import search_pubmed
from academic.sync.text import fit_field
from academic.tombstones import doi_key

REQUIRED_ENV = ('OPENALEX_KEY', 'PUBMED_EMAIL', 'DISCOVERY_CUTOFF')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _parse_cutoff(value: str) -> date:
    try:
        if DATE_RE.match(value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise ValueError(f'DISCOVERY_CUTOFF must be YYYY-MM-DD, got {value!r}')


@dataclass
class SyncConfig:
    orcid: str
    cutoff: date
    openalex_key: str
    ncbi_email: str
    ncbi_api_key: str | None

    @classmethod
    def from_env(cls, orcid: str, env: Mapping[str, str]) -> 'SyncConfig':
        missing = [name for name in REQUIRED_ENV if not env.get(name)]
        if missing:
            raise ValueError(f'Missing environment variable(s): {", ".join(missing)}')
        return cls(orcid=orcid, cutoff=_parse_cutoff(env['DISCOVERY_CUTOFF']),
                   openalex_key=env['OPENALEX_KEY'], ncbi_email=env['PUBMED_EMAIL'],
                   ncbi_api_key=env.get('NCBI_API_KEY') or None)


@dataclass
class SyncReport:
    run_at: str
    cutoff: str
    new_pending: list[dict] = field(default_factory=list)
    enriched: list[dict] = field(default_factory=list)
    proposed_hides: list[dict] = field(default_factory=list)
    discrepancies: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def summary(self) -> str:
        return (f'new: {len(self.new_pending)}  enriched: {len(self.enriched)}  '
                f'proposed hides: {len(self.proposed_hides)}  '
                f'discrepancies: {len(self.discrepancies)}  errors: {len(self.errors)}')


@dataclass
class _Fetched:
    openalex: list[Candidate]
    new: list[Candidate]
    pmc: dict


class _DryRunRollback(Exception):
    pass


def run_weekly_sync(user, config: SyncConfig, now: datetime,
                    dry_run: bool = False) -> SyncReport:
    report = SyncReport(run_at=now.isoformat(), cutoff=config.cutoff.isoformat())
    fetched = _fetch(user, config, report)
    try:
        with transaction.atomic():
            _write(user, fetched, report)
            if dry_run:
                raise _DryRunRollback
    except _DryRunRollback:
        pass
    return report


# --- Fetch phase (network + reads only) -----------------------------------

def _fetch(user, config, report) -> _Fetched:
    works = fetch_works_by_orcid(config.orcid, config.openalex_key)
    if not works:
        raise SourceError(f'OpenAlex returned no works for {config.orcid}')
    openalex = [parse_work(w) for w in works]
    pubmed = _fetch_pubmed(user, config, report)
    new = select_new(openalex + pubmed, KnownWorks.from_db(user), config.cutoff)
    new = [_full_authors(c, config, report) for c in new]
    return _Fetched(openalex=openalex, new=new, pmc=_fetch_pmc(user, config, report))


def _fetch_pubmed(user, config, report) -> list[Candidate]:
    if not user.has_pubmed_query:
        return []
    try:
        return search_pubmed(user.pubmed_query, config.cutoff, config.ncbi_email,
                             config.ncbi_api_key)
    except SourceError as exc:
        report.errors.append(f'pubmed: {exc}')
        return []


def _full_authors(c, config, report) -> Candidate:
    try:
        return full_authors(c, config.openalex_key)
    except SourceError as exc:
        report.errors.append(f'openalex authors {c.openalex_id}: {exc}')
        return c


def visible_approved(user):
    return Publication.objects.filter(owner=user, review_status='approved',
                                      is_ignored=False)


def _idconv_ids(user) -> list[str]:
    ids = []
    for doi, identifiers in visible_approved(user).values_list('doi', 'identifiers'):
        identifiers = identifiers or {}
        if identifiers.get('pmcid'):
            continue
        if doi:
            ids.append(normalize_doi(doi))
        elif identifiers.get('pmid'):
            ids.append(str(identifiers['pmid']))
    return ids


def _fetch_pmc(user, config, report) -> dict:
    ids = _idconv_ids(user)
    if not ids:
        return {}
    try:
        return lookup_pmcids(ids, config.ncbi_email)
    except SourceError as exc:
        report.errors.append(f'idconv: {exc}')
        return {}


# --- Write phase (inside one transaction) ---------------------------------

def _write(user, fetched: _Fetched, report: SyncReport) -> None:
    for c in fetched.new:
        report.new_pending.append(_pending_item(_create_pending(user, c), c))
    _enrich_all(user, fetched, report)
    _propose(user, fetched, report)


def _identifiers(c) -> dict:
    ids = {'pmid': c.pmid, 'pmcid': c.pmcid, 'openalex': c.openalex_id}
    return {k: v for k, v in ids.items() if v}


def _oa_metadata(c) -> dict:
    meta = {'oa_url': c.oa_url, 'oa_status': c.oa_status}
    return {k: v for k, v in meta.items() if v}


def _create_pending(user, c) -> Publication:
    return Publication.objects.create(
        owner=user, review_status='pending', source=c.source,
        doi=c.doi or None, title=c.title, year=c.year,
        publication_date=c.publication_date,
        publication_name=fit_field('publication_name', c.publication_name) or None,
        publication_type=c.publication_type, authors=list(c.authors),
        volume=fit_field('volume', c.volume) or None,
        page_range=fit_field('page_range', c.page_range) or None,
        identifiers=_identifiers(c), metadata=_oa_metadata(c))


def _author_summary(authors) -> str:
    names = [a.get('name', '') for a in authors]
    summary = '; '.join(names[:3])
    return f'{summary}; …' if len(names) > 3 else summary


def _pending_item(pub, c) -> dict:
    return {'id': pub.id, 'doi': pub.doi or '', 'title': pub.title, 'year': pub.year,
            'publication_name': c.publication_name,
            'authors': _author_summary(c.authors), 'source': c.source,
            'openalex_id': c.openalex_id, 'pmid': c.pmid}


def _index(candidates):
    by_doi, by_openalex = {}, {}
    for c in candidates:
        if doi_key(c.doi):
            by_doi.setdefault(doi_key(c.doi), c)
        if c.openalex_id:
            by_openalex.setdefault(c.openalex_id, c)
    return by_doi, by_openalex


def _match(pub, by_doi, by_openalex):
    c = by_doi.get(doi_key(pub.doi)) if doi_key(pub.doi) else None
    return c or by_openalex.get((pub.identifiers or {}).get('openalex') or '')


def _pmc_entry(pub, pmc):
    if pub.doi and normalize_doi(pub.doi) in pmc:
        return pmc[normalize_doi(pub.doi)]
    pmid = (pub.identifiers or {}).get('pmid')
    return pmc.get(str(pmid)) if pmid else None


def _blank_candidate() -> Candidate:
    return Candidate(source='idconv', title='', year=None, publication_date=None,
                     publication_name='', publication_type='', authors=[])


def _enrich_all(user, fetched, report) -> None:
    by_doi, by_openalex = _index(fetched.openalex)
    for pub in visible_approved(user):
        c = _match(pub, by_doi, by_openalex)
        pmc = _pmc_entry(pub, fetched.pmc)
        if c is None and pmc is None:
            continue
        c = c or _blank_candidate()
        _record_enrichment(report, pub, c, apply_enrichment(pub, c, pmc))


def _record_enrichment(report, pub, c, result) -> None:
    doi = pub.doi or ''
    if result.changed:
        report.enriched.append({'id': pub.id, 'doi': doi, 'fields': result.changed})
    for d in result.discrepancies:
        report.discrepancies.append({'id': pub.id, 'doi': doi, **d, 'source': c.source})


def _is_preprint(c) -> bool:
    return c.publication_type == 'preprint'


def _location_index(candidates) -> dict:
    """Map each location DOI to a candidate DOI, preferring non-preprints."""
    chosen = {}
    for c in candidates:
        for key in filter(None, (doi_key(loc) for loc in c.location_dois)):
            if not c.doi:
                continue
            current = chosen.get(key)
            if current is None or (_is_preprint(current) and not _is_preprint(c)):
                chosen[key] = c
    return {key: c.doi for key, c in chosen.items()}


def _crossref_lookup(report):
    def lookup(doi):
        try:
            return published_dois_for_preprint(doi)
        except SourceError as exc:
            report.errors.append(f'crossref: {exc}')
            return []
    return lookup


def _pub_ref(pub) -> dict:
    return {'id': pub.id, 'doi': pub.doi or '', 'title': pub.title}


def _propose(user, fetched, report) -> None:
    proposals = propose_hides(user, _crossref_lookup(report),
                              _location_index(fetched.openalex))
    for p in proposals:
        report.proposed_hides.append({
            'proposal_id': p.id, 'method': p.method, 'evidence': p.evidence,
            'preprint': _pub_ref(p.preprint), 'published': _pub_ref(p.published)})
