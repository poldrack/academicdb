"""Everything the user already has or has rejected, for discovery dedupe."""
from dataclasses import dataclass, field

from academic.models import Publication, RejectedWork
from academic.sync.candidates import Candidate
from academic.tombstones import doi_key, title_key


def _clean(values):
    return {v for v in values if v}


@dataclass
class KnownWorks:
    doi_keys: set[str] = field(default_factory=set)
    openalex_ids: set[str] = field(default_factory=set)
    pmids: set[str] = field(default_factory=set)
    title_keys: set[str] = field(default_factory=set)

    @classmethod
    def from_db(cls, user) -> 'KnownWorks':
        known = cls()
        pubs = Publication.objects.filter(owner=user).values_list(
            'doi', 'title', 'identifiers'
        )
        for doi, title, identifiers in pubs:
            ids = identifiers or {}
            known._absorb(doi_key(doi), ids.get('openalex'), ids.get('pmid'),
                          title_key(title))
        rejected = RejectedWork.objects.filter(owner=user).values_list(
            'doi', 'openalex_id', 'pmid', 'title_key'
        )
        for doi, openalex_id, pmid, tkey in rejected:
            known._absorb(doi_key(doi), openalex_id, pmid, tkey)
        return known

    def _absorb(self, doi, openalex_id, pmid, tkey):
        self.doi_keys |= _clean([doi])
        self.openalex_ids |= _clean([openalex_id])
        self.pmids |= _clean([str(pmid) if pmid else ''])
        self.title_keys |= _clean([tkey])

    def contains(self, c: Candidate) -> bool:
        doi = doi_key(c.doi)
        if doi and doi in self.doi_keys:
            return True
        if c.openalex_id and c.openalex_id in self.openalex_ids:
            return True
        if c.pmid and c.pmid in self.pmids:
            return True
        tkey = title_key(c.title)
        return not doi and bool(tkey) and tkey in self.title_keys

    def add(self, c: Candidate) -> None:
        self._absorb(doi_key(c.doi), c.openalex_id, c.pmid, title_key(c.title))
