from dataclasses import dataclass, field
from datetime import date


@dataclass
class Candidate:
    source: str
    title: str
    year: int | None
    publication_date: date | None
    publication_name: str
    publication_type: str
    authors: list[dict]
    doi: str = ''
    pmid: str = ''
    pmcid: str = ''
    openalex_id: str = ''
    oa_url: str = ''
    oa_status: str = ''
    openalex_type: str = ''
    location_dois: list[str] = field(default_factory=list)
    pmc_url: str = ''
    is_supplement: bool = False
    authors_truncated: bool = False
    volume: str = ''
    page_range: str = ''
    excluded_type: str = ''  # source-specific notice type (e.g. PubMed erratum)
    repository_only: bool = False  # every sourced location is a repository
