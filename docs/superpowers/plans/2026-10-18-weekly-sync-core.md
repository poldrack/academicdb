# Weekly Sync Core Implementation Plan (Plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `weekly_sync` management command that finds new publications (OpenAlex primary, PubMed backstop), fills in missing identifiers and open-access links, and proposes hiding published preprints. New items and hides wait for review, nothing the owner edited or hid is ever changed, and the run writes a JSON report that Plan 3 turns into the review PR.

**Architecture:** A new `academic/sync/` package. There is one small module per source (`openalex`, `pubmed`, `idconv`, `crossref`), all of which return plain `Candidate` records through a shared HTTP helper. The other modules are:
- `filters` and `known` decide what counts as new;
- `enrich` applies fill-only updates;
- `preprints` builds hide proposals;
- `review` holds the approve/reject state transitions;
- `run` orchestrates the whole job.

Each run has two phases. The fetch phase makes all the network calls. The write phase does all the database writes inside one transaction, so a failure of the primary source writes nothing. Review state lives in a new `Publication.review_status` field and two new models, `RejectedWork` (tombstones) and `PreprintHideProposal`.

**Tech Stack:** Django 4.2, PostgreSQL (Neon), `requests`, Biopython `Entrez.read` (XML parsing only), pytest + `responses` for HTTP mocking, freezegun.

**Spec:** `docs/superpowers/specs/2026-10-18-cloud-db-weekly-bibliography-design.md`. The relevant sections are "Data sources", "Weekly run" steps 2–5, "Discovery cutoff", "Protecting against the anti-goals", and "Calls made by Claude".

## Roadmap position

- Plan 1 is done: Neon, backups and links.
- **This plan** produces the sync command and its report.
- Plan 3 covers the YAML export, the site and PR workflows, and running this command on a schedule.
- Plan 4 covers data/code link discovery.

## Global Constraints

- Use uv for everything. Tests run with `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest …`. There are 2 known failures on `main` (`test_homepage_accessible`, `test_comprehensive_sync_with_data_directory`); leave them.
- Use pytest functions and fixtures, not classes. Write and commit the tests before the implementation, and don't change a test just to make it pass.
- `academic/sync/__init__.py` must exist and be **empty**.
- Keep functions short and modules focused.
- **No network in tests.** Mock HTTP with `responses`.
- The pipeline runs for a single owner, selected with `--orcid-id`. The models stay multi-user.
- Environment variables are read at the point of use, following the existing pattern:
  - `OPENALEX_KEY` (required; sent as the `api_key` query parameter)
  - `PUBMED_EMAIL` (sent to NCBI as `email`, with `tool=academicdb`)
  - `NCBI_API_KEY` (optional)
  - `DISCOVERY_CUTOFF` (required, `YYYY-MM-DD`)
- **Discovery cutoff:** a *fixed* date from config, not a rolling window. Works published before it are never proposed as new. Enrichment and preprint detection still cover every existing publication.
- **Fill-only rule:** without review, a run may only fill *empty* fields and set PMID, PMCID and the OA URL. It never overwrites a non-empty title, author list, venue, date, volume or pages. Such differences are recorded as `discrepancies` in the report, and the field is left alone.
- **Hand edits:**
  - Never change a field flagged in `manual_edits`, except to add a *missing* identifier key. `lookup_pmc_ids` sets `manual_edits['identifiers']` on 236 rows as protection, not as a hand edit, so filling an absent `pmid`/`pmcid`/`openalex` key is allowed. An existing value is never changed.
  - Never change `is_ignored` or `ignore_reason`.
  - Never re-add a rejected or deleted work.
- **No automatic hides.** Every preprint→published match becomes a `PreprintHideProposal(status='pending')`.
- Excluded OpenAlex types: `peer-review`, `paratext`, `erratum`, `dataset`, `other`, `retraction`, `editorial`, `letter`, `supplementary-materials`. Conference-abstract supplements are excluded too (Task 4 rule).
- OSF versioned DOIs (`…/osf.io/<id>_v<N>`) collapse to one work.
- Pending publications must not appear in the CV.

## Review Focus

1. **The same work arriving through two sources in one run** (OpenAlex DOI and a PubMed PMID, or DOI case differences) must create one pending publication, not two. Tested in Task 8 (`test_same_work_from_openalex_and_pubmed_creates_one_pending`).
2. **A rejected work coming back with a different OSF version suffix or DOI case** must still be recognised as rejected. Tested in Task 4 (`test_rejected_osf_version_not_reproposed`).
3. **A failure of the primary source** (OpenAlex 5xx or 401) must leave the database untouched and exit non-zero, rather than half-writing. Tested in Task 8 (`test_openalex_failure_writes_nothing`).
4. **A preprint matched to an ignored, pending-rejected or other-owner publication** must not produce a proposal. A proposal already decided as rejected must not be raised again. Tested in Task 6 (`test_no_reproposal_after_rejected_hide`, `test_ignored_published_version_not_used`).
5. **Running twice in a row with no upstream changes** must produce no new pending items, no new proposals and no enrichment changes. Tested in Task 8 (`test_second_run_is_noop`).

---

### Task 1: Review state, tombstones and CV exclusion

**Files:**
- Modify: `academic/models.py`. Add to `Publication`: `review_status`, and `'openalex'` in `SOURCE_CHOICES`. Add the models `RejectedWork` and `PreprintHideProposal`.
- Create: `academic/migrations/0028_review_state.py` (via `makemigrations`)
- Create: `academic/tombstones.py`
- Modify: `academic/signals.py` (a `post_delete` receiver for `Publication`)
- Modify: `academic/cv_renderer.py` (`get_publications` and `get_preprints` filter on `review_status='approved'`)
- Test: `tests/unit/test_review_state.py`

**Interfaces:**
- Produces:
  - **`Publication.review_status`:** `CharField(max_length=20, choices=[('approved','Approved'),('pending','Pending review')], default='approved', db_index=True)`. Existing rows become `approved`.
  - **`RejectedWork`:**
    - fields: `owner` FK→AcademicUser (CASCADE, related_name `rejected_works`); `doi` CharField(255, blank); `openalex_id` CharField(32, blank); `pmid` CharField(20, blank); `title_key` CharField(500, blank); `reason` CharField(20, choices `rejected`/`deleted`); `created_at` auto_now_add
    - index on (owner, doi)
  - **`PreprintHideProposal`:**
    - fields: `owner` FK; `preprint` FK→Publication (CASCADE, related_name `hide_proposals`); `published` FK→Publication (CASCADE, related_name `+`); `method` CharField(30, choices `crossref_relation`/`openalex_location`/`title_author`); `evidence` JSONField(default=dict); `status` CharField(20, choices `pending`/`confirmed`/`rejected`, default `pending`); `created_at`; `decided_at` (DateTime, null)
    - `unique_together = ('preprint', 'published')`
  - **`academic/tombstones.py`:**
    - `doi_key(doi: str | None) -> str`: lowercases, strips the `https://doi.org/` style prefixes (reuse `academic.link_import.normalize_doi`), collapses `/+`, and strips a trailing `_v\d+` **only when the DOI contains `osf.io/`**. Other DOIs that happen to end in `_vN` are left alone. Returns `''` for None or empty.
    - `title_key(title: str | None) -> str`: lowercases, keeps only `[a-z0-9 ]`, collapses whitespace, takes the first 200 characters.
    - `record_tombstone(pub: Publication, reason: str) -> RejectedWork`: a `get_or_create` on `owner` + (`doi_key` when present, otherwise `title_key`). It fills `openalex_id` from `pub.identifiers.get('openalex', '')` and `pmid` from `pub.identifiers.get('pmid', '')`. An existing row keeps its original `reason`.
  - **Signal:** `post_delete` on `Publication` calls `record_tombstone(instance, 'deleted')`. This covers instance deletes, queryset deletes (the views, admin, commands, API) and cascades from the delete paths.

- [ ] **Step 1: Write the failing tests** (`django_db`; use the `academic_user` fixture and create publications with `Publication.objects.create`)

```python
def test_existing_and_new_publications_default_to_approved(academic_user):
    assert Publication.objects.create(owner=academic_user, doi='10.1/a', title='Title long enough', year=2024).review_status == 'approved'

@pytest.mark.parametrize('raw,key', [
    ('https://doi.org/10.31234/OSF.IO/ABCDE_V3', '10.31234/osf.io/abcde'),
    ('10.1101//2024.01.01.123', '10.1101/2024.01.01.123'),
    (None, ''),
])
def test_doi_key(raw, key):
    assert doi_key(raw) == key

def test_title_key_normalizes():
    assert title_key('  The Brain: A (Very) Short Intro! ') == 'the brain a very short intro'

def test_instance_delete_records_tombstone(academic_user):
    pub = Publication.objects.create(owner=academic_user, doi='10.1/a', title='Title long enough', year=2024,
                                     identifiers={'openalex': 'W1', 'pmid': '9'})
    pub.delete()
    t = RejectedWork.objects.get(owner=academic_user)
    assert (t.doi, t.openalex_id, t.pmid, t.reason) == ('10.1/a', 'W1', '9', 'deleted')

def test_queryset_delete_records_tombstones(academic_user):
    # create 3 pubs; academic_user.publications.all().delete()
    assert RejectedWork.objects.filter(owner=academic_user).count() == 3

def test_no_doi_publication_tombstoned_by_title(academic_user):
    # pub with doi=None, title='Statistical Thinking for the 21st Century'; delete
    assert RejectedWork.objects.get().title_key == 'statistical thinking for the 21st century'

def test_rejected_reason_preserved_when_later_deleted(academic_user):
    pub = ...  # doi '10.1/a'
    record_tombstone(pub, 'rejected'); pub.delete()
    assert list(RejectedWork.objects.values_list('reason', flat=True)) == ['rejected']

def test_cv_excludes_pending_publications(academic_user):
    # one approved article titled 'Approved paper title', one pending titled 'Pending paper title'
    tex = generate_cv_latex(academic_user)
    assert 'Approved paper title' in tex and 'Pending paper title' not in tex

def test_cv_excludes_pending_preprints(academic_user):
    # pending preprint doi 10.1101/2026.01.01.000001 titled 'Pending preprint title'
    assert 'Pending preprint title' not in generate_cv_latex(academic_user)
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_review_state.py -v`
Expected: collection error, `ImportError` for `academic.tombstones` / `RejectedWork`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/test_review_state.py
git commit -m "test: add failing tests for review state, tombstones, CV exclusion"
```

- [ ] **Step 4: Implement** the fields, models, `academic/tombstones.py`, the signal and the CV filters. Then run `uv run python manage.py makemigrations academic --name review_state`.

- [ ] **Step 5: Run to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_review_state.py tests/unit/test_cv_formatting.py tests/unit/test_cv_query_count.py -v`
Expected: all pass. Then run the full suite: only the 2 known failures should remain. A test elsewhere that deletes publications and counts rows of other tables is a real finding; fix the code, not the test.

- [ ] **Step 6: Commit**

```bash
git add academic/models.py academic/migrations/0028_review_state.py academic/tombstones.py academic/signals.py academic/cv_renderer.py
git commit -m "feat: add review state, delete tombstones, hide proposals; CV skips pending"
```

---

### Task 2: HTTP helper and OpenAlex client

**Files:**
- Create: `academic/sync/__init__.py` (empty)
- Create: `academic/sync/http.py`, `academic/sync/candidates.py`, `academic/sync/openalex.py`
- Test: `tests/unit/sync/test_openalex.py` (create `tests/unit/sync/__init__.py`, empty)

**Interfaces:**
- Produces:
  - **`class SourceError(Exception)`** in `http.py`.
  - **`get(url: str, params: dict | None = None, *, timeout: int = 30, retries: int = 3, backoff: float = 2.0) -> requests.Response`** in `http.py`:
    - sends the header `User-Agent: academicdb (+https://github.com/poldrack/academicdb)`;
    - retries on 429 and 5xx, sleeping `backoff ** attempt` seconds via `time.sleep`, so tests can monkeypatch it;
    - raises `SourceError(f'{url}: HTTP {status}')` once retries run out, or immediately on any other 4xx.
  - **`@dataclass class Candidate`** in `candidates.py`:
    - `source: str` (`'openalex'` or `'pubmed'`)
    - `title: str`, `year: int | None`, `publication_date: date | None`, `publication_name: str`, `publication_type: str` (a model `TYPE_CHOICES` value)
    - `authors: list[dict]` (`[{'name': 'Family, Given'}]`)
    - `doi: str = ''` (normalized with `normalize_doi`), `pmid: str = ''`, `pmcid: str = ''` (`'PMC123'` form), `openalex_id: str = ''` (`'W123'` form)
    - `oa_url: str = ''`, `oa_status: str = ''`
    - `openalex_type: str = ''`
    - `location_dois: list[str]` (DOIs of the other locations, normalized)
    - `pmc_url: str = ''`
    - `is_supplement: bool = False`
    - `authors_truncated: bool = False`
  - **`openalex.py`:**
    - `OPENALEX = 'https://api.openalex.org'`
    - `fetch_works_by_orcid(orcid: str, api_key: str) -> list[dict]`: `GET /works` with `filter=author.orcid:{orcid}`, `per-page=200` and `cursor=*`. It follows `meta.next_cursor` until it is null and always sends `api_key`.
    - `fetch_work(openalex_id: str, api_key: str) -> dict`: `GET /works/{id}`.
    - `parse_work(work: dict) -> Candidate`:
      - **IDs:** `openalex_id` is the last path segment of `work['id']`. `doi` comes from `work['doi']`. `pmid` comes from `ids.pmid`, taking the trailing digits.
      - **PMC:** `pmcid` is parsed from any location `landing_page_url` matching `ncbi.nlm.nih.gov/pmc/articles/(PMC)?(\d+)`, normalized to `PMC<digits>`. `pmc_url` is that URL.
      - **Open access:** `oa_url` is `best_oa_location.landing_page_url`, falling back to `open_access.oa_url`. `oa_status` is `open_access.oa_status`.
      - **Authors:** `authors` comes from `authorships[].raw_author_name` (falling back to `author.display_name`), converted to `'Family, Given'` by splitting at the last space. `authors_truncated` is `work.get('is_authors_truncated') or len(authorships) >= 100`.
      - **Supplement:** `is_supplement` is true if `biblio.issue` contains `suppl` (case-insensitive) or `biblio.first_page` matches `^S\d+`.
      - **Location DOIs:** `location_dois` are the DOIs found in other locations' `landing_page_url` (`doi.org/…`), excluding the work's own DOI.
      - **Type mapping:** `article`→`journal-article`, `preprint`→`preprint`, `book-chapter`→`book-chapter`, `book`→`book`, `dissertation`→`thesis`, `report`→`report`, and anything else → `other`, keeping `openalex_type` raw.
    - `full_authors(candidate: Candidate, api_key: str) -> Candidate`: if `authors_truncated`, re-parses from `fetch_work`; otherwise returns the candidate unchanged.

- [ ] **Step 1: Write the failing tests.** Use `responses`. Put JSON fixtures inline as small dicts modelled on real OpenAlex records, for example `{'id': 'https://openalex.org/W4414790363', 'doi': 'https://doi.org/10.1038/X', 'type': 'article', ...}`.

```python
def test_get_retries_then_succeeds(monkeypatch):  # 503, 503, 200 → returns 200; sleep called twice
def test_get_raises_on_401():                      # 401 → SourceError('... HTTP 401'), single call
def test_fetch_works_follows_cursor():             # page1 next_cursor='abc', page2 next_cursor=None → 3 works; every request has api_key and filter=author.orcid:0000-0001-6755-0259
def test_parse_work_ids_and_pmc():                 # ids.pmid 'https://pubmed.ncbi.nlm.nih.gov/41143079' → '41143079'; location url .../pmc/articles/12550278 → 'PMC12550278'
def test_parse_work_doi_normalized():              # 'https://doi.org/10.1162/IMAG.A.958' → '10.1162/imag.a.958'
def test_parse_work_authors_family_given():        # raw_author_name 'Russell A. Poldrack' → {'name': 'Poldrack, Russell A.'}
def test_parse_work_type_mapping():                # 'dissertation' → 'thesis'; 'peer-review' → 'other' with openalex_type 'peer-review'
def test_parse_work_supplement_flag():             # biblio first_page 'S123' → is_supplement True
def test_parse_work_location_dois():               # location landing_page_url 'https://doi.org/10.1101/2025.01.14.633053' → in location_dois
def test_full_authors_refetches_truncated():       # 100 authorships in list result → fetch_work called, 120 authors returned
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_openalex.py -v`
Expected: `ModuleNotFoundError: academic.sync`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/
git commit -m "test: add failing tests for HTTP helper and OpenAlex client"
```

- [ ] **Step 4: Implement** the three modules.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/
git commit -m "feat: add HTTP helper and OpenAlex client"
```

---

### Task 3: PubMed, NCBI ID converter and CrossRef relation clients

**Files:**
- Create: `academic/sync/pubmed.py`, `academic/sync/idconv.py`, `academic/sync/crossref.py`
- Test: `tests/unit/sync/test_ncbi_crossref.py`

**Interfaces:**
- Consumes: `get` and `SourceError` from `http.py`; `Candidate` (Task 2).
- Produces:
  - **`pubmed.py`:**
    - `EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'`
    - `search_pubmed(query: str, mindate: date, email: str, api_key: str | None = None) -> list[Candidate]`:
      - calls `esearch.fcgi` with `db=pubmed`, `term=query`, `datetype=pdat`, `mindate=YYYY/MM/DD`, `maxdate=3000`, `retmax=1000`, `retmode=json`, `tool=academicdb`, `email` and the optional `api_key`;
      - then makes `efetch.fcgi` calls in batches of 200 IDs (`retmode=xml`), parsed with `Bio.Entrez.read(io.BytesIO(resp.content))`;
      - returns `[]` without calling efetch if there are no IDs.
    - `parse_pubmed_article(article: dict) -> Candidate`:
      - `source='pubmed'`;
      - `doi` and `pmcid` come from `PubmedData.ArticleIdList` (attributes `IdType` `doi`/`pmc`), and `pmid` from `MedlineCitation.PMID`;
      - `title` is the `ArticleTitle` text with a trailing period removed;
      - `publication_name` is `Journal.Title`, and `year` is `JournalIssue.PubDate.Year`, falling back to the first 4 digits of `MedlineDate`;
      - `authors` are `'LastName, ForeName'` (or `CollectiveName`);
      - `publication_type='journal-article'`.
  - **`idconv.py`:**
    - `IDCONV = 'https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/'`
    - `lookup_pmcids(ids: list[str], email: str) -> dict[str, dict]`:
      - accepts DOIs or PMIDs, in batches of 200, with `format=json`, `tool=academicdb` and `email`;
      - maps each *requested* id (DOI lowercased) to `{'pmid': str, 'pmcid': str}`;
      - drops records with `status == 'error'` or no `pmcid`.
  - **`crossref.py`:**
    - `CROSSREF = 'https://api.crossref.org/works/'`
    - `published_dois_for_preprint(doi: str) -> list[str]`: `GET CROSSREF + doi`, then reads `message.relation['is-preprint-of']`, returning each `id` where `id-type == 'doi'`, normalized. Returns `[]` on 404.

- [ ] **Step 1: Write the failing tests** (`responses`; minimal fixture payloads; for PubMed, an efetch XML string with one `PubmedArticle`)

```python
def test_search_pubmed_sends_mindate_and_tool():   # esearch params mindate='2025/10/18', datetype='pdat', tool='academicdb', email='me@x.org'
def test_search_pubmed_no_ids_skips_efetch():       # esearch idlist [] → [] and exactly 1 request
def test_search_pubmed_batches_efetch():            # 450 ids → 3 efetch calls
def test_parse_pubmed_article_fields():             # doi '10.1/abc', pmid '123', pmcid 'PMC456', title without trailing '.', authors [{'name': 'Poldrack, Russell A'}], year 2025
def test_parse_pubmed_medline_date_year():          # MedlineDate '2025 Jan-Feb' → 2025
def test_lookup_pmcids_maps_requested_ids():        # request ['10.1/ABC', '999']; response records for both → keys '10.1/abc' and '999'
def test_lookup_pmcids_drops_errors():              # status 'error' record → absent
def test_lookup_pmcids_batches_200():               # 250 ids → 2 requests
def test_published_dois_for_preprint():             # relation is-preprint-of [{'id-type':'doi','id':'10.1038/S41593-025-1'}] → ['10.1038/s41593-025-1']
def test_published_dois_404_is_empty():             # 404 → []
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_ncbi_crossref.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_ncbi_crossref.py
git commit -m "test: add failing tests for PubMed, ID converter and CrossRef clients"
```

- [ ] **Step 4: Implement** the three modules.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/pubmed.py academic/sync/idconv.py academic/sync/crossref.py
git commit -m "feat: add PubMed, NCBI ID converter and CrossRef relation clients"
```

---

### Task 4: Known works and discovery filters

**Files:**
- Create: `academic/sync/known.py`, `academic/sync/filters.py`
- Test: `tests/unit/sync/test_filters.py`

**Interfaces:**
- Consumes: `Candidate`; `doi_key`, `title_key`, `RejectedWork` (Task 1).
- Produces:
  - **`known.py`:**
    - `@dataclass class KnownWorks`: `doi_keys: set[str]`, `openalex_ids: set[str]`, `pmids: set[str]`, `title_keys: set[str]`
    - `KnownWorks.from_db(user) -> KnownWorks`: built from **all** of the user's publications (approved, pending and ignored) plus all of their `RejectedWork` rows.
    - `KnownWorks.contains(c: Candidate) -> bool`: true if any of the candidate's `doi_key(c.doi)`, `c.openalex_id`, `c.pmid` or `title_key(c.title)` is in the matching set. The title is used only when the candidate has no DOI.
    - `KnownWorks.add(c: Candidate) -> None`: lets one run dedupe across sources.
  - **`filters.py`:**
    - `EXCLUDED_OPENALEX_TYPES = frozenset({'peer-review','paratext','erratum','dataset','other','retraction','editorial','letter','supplementary-materials'})`
    - `is_excluded(c: Candidate) -> bool`: true if the type is excluded, or `c.is_supplement`, or the title starts with `Corrigendum`/`Correction`/`Erratum`/`Author Correction` (case-insensitive).
    - `before_cutoff(c: Candidate, cutoff: date) -> bool`: compares `publication_date` when present, otherwise `date(year, 1, 1)`. A candidate with no year counts as before the cutoff.
    - `collapse_versions(cands: list[Candidate]) -> list[Candidate]`: groups by `doi_key`, keeping the highest `_vN` version and the first-seen record for non-versioned DOIs. Candidates without a DOI pass through.
    - `select_new(cands: list[Candidate], known: KnownWorks, cutoff: date) -> list[Candidate]`: runs `collapse_versions`, then drops anything excluded, before the cutoff, or already known. It calls `known.add` for each kept candidate so a later duplicate is dropped too, and keeps the input order.

- [ ] **Step 1: Write the failing tests** (`django_db` where `from_db` is used)

```python
def test_excluded_types_and_supplements():           # peer-review, dataset → excluded; journal-article with is_supplement → excluded; 'Erratum: X' → excluded
def test_before_cutoff_uses_date_then_year():         # date 2025-10-17 → True; date None year 2026 → False; year None → True
def test_collapse_osf_versions_keeps_highest():       # osf.io/abcde_v1, _v3, _v2 → one candidate with _v3
def test_known_includes_ignored_pending_and_tombstones(academic_user):  # ignored pub doi A, pending pub doi B, RejectedWork doi C → all contains() True
def test_known_matches_by_openalex_id_and_pmid(academic_user):          # pub identifiers {'openalex':'W9','pmid':'77'}; candidate with other DOI but W9 → True
def test_known_title_only_for_no_doi(academic_user):                    # no-DOI pub 'Statistical Thinking for the 21st Century'; candidate same title, doi '' → True; same title with a DOI → False
def test_rejected_osf_version_not_reproposed(academic_user):            # RejectedWork doi '10.31234/osf.io/abcde'; candidate '10.31234/OSF.IO/ABCDE_v4' → select_new returns []
def test_select_new_dedupes_within_run(academic_user):                  # same DOI from openalex and pubmed → one candidate (the first)
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_filters.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_filters.py
git commit -m "test: add failing tests for discovery filters and known works"
```

- [ ] **Step 4: Implement** `known.py` and `filters.py`.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/known.py academic/sync/filters.py
git commit -m "feat: add discovery filters, version collapse and known-work matching"
```

---

### Task 5: Fill-only enrichment

**Files:**
- Create: `academic/sync/enrich.py`
- Test: `tests/unit/sync/test_enrich.py`

**Interfaces:**
- Consumes: `Candidate`.
- Produces:
  - `FILL_FIELDS = ('publication_date', 'publication_name', 'volume', 'page_range')`
  - `COMPARE_FIELDS = ('title', 'publication_name', 'year')`
  - `IDENTIFIER_KEYS = ('pmid', 'pmcid', 'openalex')`
  - `@dataclass class EnrichResult`: `changed: list[str]` (field names, with identifier keys as `identifiers.<key>`); `discrepancies: list[dict]` (`{'field', 'ours', 'theirs'}`)
  - `plan_enrichment(pub: Publication, c: Candidate, pmc: dict | None = None) -> EnrichResult`. Pure: it computes but does not save.
    - **Fields:** fills each `FILL_FIELDS` field only when it is empty on `pub` and not flagged in `pub.manual_edits`. Fills `authors` only when `pub.authors` is empty and it isn't flagged.
    - **Identifiers:** adds an identifier key only when it is absent (falsy) in `pub.identifiers`, using the candidate's values or the `pmc` dict's `pmid`/`pmcid`. An existing value is never changed, even if different.
    - **OA URL:** sets `metadata['oa_url']`/`metadata['oa_status']` when the candidate has an `oa_url` that differs from the current one and `manual_edits` has no `oa_url`.
    - **Discrepancies:** records a discrepancy for each `COMPARE_FIELDS` field where both sides are non-empty and differ (case- and whitespace-insensitive for strings). It also records one when an existing identifier differs from the candidate's.
  - `apply_enrichment(pub: Publication, c: Candidate, pmc: dict | None = None) -> EnrichResult`: runs `plan_enrichment`, writes the changes to `pub`, sets `last_api_sync`, and calls `pub.save(update_fields=[...])` only if something changed. It never touches `is_ignored`, `ignore_reason`, `review_status`, `title`, `year`, `publication_type`, `manual_edits` or `edit_history`.

- [ ] **Step 1: Write the failing tests** (`django_db`)

```python
def test_fills_only_empty_fields(academic_user):          # pub publication_name 'Neuron', volume None; candidate name 'NEURON (Cambridge)', volume '12' → changed == ['volume']; name unchanged
def test_never_overwrites_manually_edited(academic_user):  # manual_edits {'volume': True}, volume None → volume stays None
def test_adds_missing_identifier_despite_identifiers_flag(academic_user):  # manual_edits {'identifiers': True}, identifiers {'pmid':'1'}; candidate pmcid 'PMC9' → identifiers == {'pmid':'1','pmcid':'PMC9'}
def test_never_changes_existing_identifier(academic_user):  # identifiers {'pmcid':'PMC1'}; candidate pmcid 'PMC2' → unchanged; discrepancy {'field':'identifiers.pmcid','ours':'PMC1','theirs':'PMC2'}
def test_title_difference_is_discrepancy_not_change(academic_user):  # title 'A study of X' vs candidate 'A Study of Y' → title unchanged, discrepancy recorded
def test_sets_oa_url(academic_user):                       # candidate oa_url 'https://europepmc.org/x', oa_status 'green' → metadata has both, 'metadata.oa_url' in changed
def test_never_touches_ignore_or_review(academic_user):    # pub is_ignored True, ignore_reason 'dup', review_status 'approved' → unchanged after apply
def test_no_save_when_nothing_changes(academic_user, django_assert_num_queries):  # identical candidate → apply makes 0 queries
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_enrich.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_enrich.py
git commit -m "test: add failing tests for fill-only enrichment"
```

- [ ] **Step 4: Implement** `enrich.py`.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/enrich.py
git commit -m "feat: add fill-only enrichment with discrepancy reporting"
```

---

### Task 6: Preprint → published hide proposals

**Files:**
- Create: `academic/sync/preprints.py`
- Test: `tests/unit/sync/test_preprints.py`

**Interfaces:**
- Consumes: `PreprintHideProposal` (Task 1); `doi_key`; `Candidate.location_dois`; `Publication._is_likely_published_version(preprint, published)` (models.py:638) and the title/author helpers it uses.
- Produces:
  - `visible_preprints(user) -> QuerySet[Publication]`: `is_preprint=True`, `is_ignored=False`, `review_status='approved'`.
  - `published_candidates(user) -> list[Publication]`: non-preprint and not ignored, any `review_status`.
  - `find_match(preprint: Publication, published: list[Publication], crossref_dois: list[str], location_index: dict[str, str]) -> tuple[Publication, str, dict] | None`. Tries, in order:
    1. `crossref_relation`, when a `crossref_dois` entry matches a published pub's `doi_key`. Evidence: `{'relation': 'is-preprint-of', 'doi': <doi>}`.
    2. `openalex_location`, when `location_index[doi_key(preprint.doi)]` (preprint DOI → published DOI, built from candidates' `location_dois`) matches. Evidence: `{'openalex_id': ..., 'published_doi': ...}`.
    3. `title_author`, the first pub where `_is_likely_published_version` is true. Evidence: `{'title_similarity': float, 'author_similarity': float}`, computed with the same helpers that method uses.
  - `propose_hides(user, crossref_lookup: Callable[[str], list[str]], location_index: dict[str, str]) -> list[PreprintHideProposal]`:
    - skips a preprint that already has any proposal with status `pending` or `confirmed`;
    - skips a (preprint, published) pair that already has a `rejected` proposal;
    - creates `PreprintHideProposal(status='pending')` and returns the new ones;
    - calls `crossref_lookup` once per visible preprint.

- [ ] **Step 1: Write the failing tests** (`django_db`; build the preprint/published pairs by hand; `crossref_lookup` is a plain lambda)

```python
def test_crossref_relation_match(academic_user):        # lookup returns [published.doi] → proposal method 'crossref_relation'
def test_openalex_location_match(academic_user):        # location_index {preprint.doi: published.doi} → method 'openalex_location'
def test_title_author_match(academic_user):             # same title, overlapping authors, later year → method 'title_author', evidence has both similarities
def test_unrelated_paper_not_matched(academic_user):    # different title → no proposal
def test_ignored_published_version_not_used(academic_user):  # only match is is_ignored=True → no proposal
def test_hidden_preprint_skipped(academic_user):        # preprint is_ignored=True → no proposal, crossref_lookup not called
def test_no_duplicate_pending_proposal(academic_user):  # run twice → 1 proposal
def test_no_reproposal_after_rejected_hide(academic_user):  # existing rejected proposal for the pair → none created
def test_propose_never_hides(academic_user):            # after propose_hides, preprint.is_ignored still False
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_preprints.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_preprints.py
git commit -m "test: add failing tests for preprint hide proposals"
```

- [ ] **Step 4: Implement** `preprints.py`.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/preprints.py
git commit -m "feat: propose hiding preprints that have been published"
```

---

### Task 7: Review transitions

**Files:**
- Create: `academic/sync/review.py`
- Test: `tests/unit/sync/test_review.py`

**Interfaces:**
- Consumes: Task 1 models and `record_tombstone`.
- Produces. Plan 3 calls these when a review PR is merged or closed:
  - `approve_pending(pub: Publication) -> None`: sets `review_status='approved'`. Raises `ValueError` if the publication is not pending.
  - `reject_pending(pub: Publication) -> None`: calls `record_tombstone(pub, 'rejected')`, then `pub.delete()`. Raises `ValueError` if not pending.
  - `confirm_hide(proposal: PreprintHideProposal, now: datetime) -> None`:
    - sets `preprint.is_ignored=True` and `preprint.ignore_reason=f'Published as {published.doi}'`;
    - sets `preprint.metadata['hidden_by'] = {'method': 'pipeline_review', 'proposal_id': id, 'confirmed_at': iso, 'published_doi': ...}`;
    - sets `proposal.status='confirmed'` and `decided_at=now`;
    - sets the other pending proposals for the same preprint to `rejected`.
  - `reject_hide(proposal: PreprintHideProposal, now: datetime) -> None`: `status='rejected'`, `decided_at=now`. The preprint is unchanged.
  - All four run inside `transaction.atomic()`.

- [ ] **Step 1: Write the failing tests** (`django_db`)

```python
def test_approve_pending():                    # → review_status 'approved'
def test_approve_non_pending_raises():         # approved pub → ValueError
def test_reject_pending_tombstones_and_deletes():  # → no Publication, RejectedWork reason 'rejected'
def test_confirm_hide_sets_ignore_and_origin():    # preprint is_ignored True, ignore_reason 'Published as 10.1038/x', metadata['hidden_by']['method'] == 'pipeline_review'
def test_confirm_hide_rejects_sibling_proposals(): # second pending proposal for same preprint → 'rejected'
def test_reject_hide_leaves_preprint_visible():    # is_ignored False, status 'rejected'
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_review.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_review.py
git commit -m "test: add failing tests for review transitions"
```

- [ ] **Step 4: Implement** `review.py`.

- [ ] **Step 5: Run to verify they pass**

Run: same command as Step 2.
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/review.py
git commit -m "feat: add approve/reject transitions for pending works and hides"
```

---

### Task 8: Orchestrator and `weekly_sync` command

**Files:**
- Create: `academic/sync/run.py`
- Create: `academic/management/commands/weekly_sync.py`
- Test: `tests/unit/sync/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - **`@dataclass class SyncConfig`:** `orcid: str`, `cutoff: date`, `openalex_key: str`, `ncbi_email: str`, `ncbi_api_key: str | None`
  - **`SyncConfig.from_env(orcid: str, env: Mapping[str, str]) -> SyncConfig`:** raises `ValueError` naming `OPENALEX_KEY`, `PUBMED_EMAIL` or `DISCOVERY_CUTOFF` when one is missing, or when `DISCOVERY_CUTOFF` is not `YYYY-MM-DD`.
  - **`@dataclass class SyncReport`:** `run_at: str`, `cutoff: str`, `new_pending: list[dict]`, `enriched: list[dict]`, `proposed_hides: list[dict]`, `discrepancies: list[dict]`, `errors: list[str]`, plus a `to_json() -> str`. Plan 3 consumes this, so the item shapes are fixed:
    - `new_pending`: `{'id', 'doi', 'title', 'year', 'publication_name', 'authors': '<first 3 names>; …', 'source', 'openalex_id', 'pmid'}`
    - `enriched`: `{'id', 'doi', 'fields': [...]}`
    - `proposed_hides`: `{'proposal_id', 'method', 'evidence', 'preprint': {'id','doi','title'}, 'published': {'id','doi','title'}}`
    - `discrepancies`: `{'id', 'doi', 'field', 'ours', 'theirs', 'source'}`
  - **`run_weekly_sync(user, config: SyncConfig, now: datetime) -> SyncReport`.** It runs in two phases.
    1. **Fetch** (no database writes):
       - OpenAlex works by ORCID, parsed, with `full_authors` applied to the *new* candidates only. A `SourceError` here is re-raised, and nothing gets written.
       - PubMed `search_pubmed(user.pubmed_query, cutoff, …)`, skipped when the user has no `pubmed_query`.
       - `lookup_pmcids` for visible approved publications missing a `pmcid` that have a DOI or PMID.
       - A failure of PubMed or the ID converter is appended to `errors`, and the run continues.
    2. **Write** (one `transaction.atomic()`):
       - `select_new(openalex + pubmed candidates, KnownWorks.from_db(user), cutoff)` creates one `Publication(review_status='pending', source=c.source, identifiers={pmid, pmcid, openalex}, metadata={'oa_url','oa_status'}, …)` per candidate.
       - `apply_enrichment` runs for each approved, non-ignored publication. Match OpenAlex candidates by `doi_key` first, then by `identifiers.openalex`, and pass that publication's idconv entry.
       - `propose_hides(user, crossref_lookup, location_index)`. Here `crossref_lookup` wraps `published_dois_for_preprint` and appends to `errors` on `SourceError` (returning `[]`). `location_index` maps each `location_dois` entry to its candidate's DOI, for every OpenAlex candidate.
       - Fills the report.
  - **Command `weekly_sync --orcid-id ID [--report PATH] [--dry-run]`:**
    - builds `SyncConfig.from_env(..., os.environ)`, a `ValueError` becoming a `CommandError`;
    - runs the sync; `--dry-run` runs the write phase and then rolls it back, but still produces the full report;
    - writes the report JSON to `--report` (default `sync_report.json`);
    - prints a one-line summary: `new: N  enriched: N  proposed hides: N  discrepancies: N  errors: N`;
    - raises `CommandError` (exit 1) if `errors` is non-empty, after the writes have committed;
    - if OpenAlex fails, raises `CommandError` and writes nothing.

- [ ] **Step 1: Write the failing tests.** Use `responses` for every endpoint, with a small OpenAlex payload that has:
  - 1 known paper, with a new PMC location and OA URL;
  - 1 new 2026 paper;
  - 1 pre-cutoff paper;
  - 1 peer-review;
  - 1 published version whose location holds a known preprint DOI.

  The PubMed payload returns the same new paper by PMID. Cutoff is `2025-10-18`, with `freeze_time('2026-10-18')`.

```python
def test_new_work_created_pending_and_reported():       # exactly 1 pending pub; report.new_pending[0]['doi'] == new DOI
def test_same_work_from_openalex_and_pubmed_creates_one_pending():
def test_pre_cutoff_and_excluded_types_not_created():
def test_known_paper_enriched_fill_only():               # pmcid + oa_url added; title unchanged; report.enriched lists fields
def test_hand_edited_and_hidden_publications_untouched():
    # pub A manual_edits {'title': True, 'volume': True} with candidate values differing; pub B is_ignored True
    # snapshot every field of A and B before; after run → identical (compare model_to_dict)
def test_rejected_work_not_recreated():                  # RejectedWork for the new DOI → 0 pending
def test_preprint_hide_proposed_not_applied():           # 1 proposal method 'openalex_location'; preprint.is_ignored False
def test_second_run_is_noop():                           # run twice → second report has empty new_pending, enriched, proposed_hides
def test_openalex_failure_writes_nothing():              # OpenAlex 500 x4 → CommandError; Publication count and RejectedWork count unchanged
def test_pubmed_failure_reported_but_run_completes():    # esearch 500 x4 → pending from OpenAlex still created; CommandError mentions errors; report.errors non-empty
def test_dry_run_rolls_back(tmp_path):                   # --dry-run → report has 1 new_pending but Publication pending count 0
def test_missing_cutoff_is_command_error(monkeypatch):   # DISCOVERY_CUTOFF unset → CommandError naming it
```

- [ ] **Step 2: Run to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync/test_run.py -v`
Expected: `ModuleNotFoundError: academic.sync.run`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/sync/test_run.py
git commit -m "test: add failing end-to-end tests for weekly sync"
```

- [ ] **Step 4: Implement** `run.py` and the command.

- [ ] **Step 5: Run to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync -v`
Expected: all pass. Then run the full suite: only the 2 known failures remain.

- [ ] **Step 6: Commit**

```bash
git add academic/sync/run.py academic/management/commands/weekly_sync.py
git commit -m "feat: add weekly_sync orchestrator and command with JSON report"
```

---

### Task 9: First live dry run (owner present)

**Files:**
- Modify: `README.md` (a "Weekly sync" subsection: env vars, `make sync-dry-run`, `make sync`, report location)
- Modify: `Makefile` (`sync-dry-run` and `sync` targets)

- [ ] **Step 1: Migrate Neon.**

Run: `make migrate-neon`
Expected: `Applying academic.0028_review_state... OK`. Then run `make backup-local` first, as a safety net.

- [ ] **Step 2: The owner adds `DISCOVERY_CUTOFF=2025-10-18` to `.env`.** That is one year before the first production run (2026-10-18). `OPENALEX_KEY` and `PUBMED_EMAIL` are already present.

- [ ] **Step 3: Add the Makefile targets.**
  - `sync-dry-run`: `USE_NEON=true uv run python manage.py weekly_sync --orcid-id 0000-0001-6755-0259 --dry-run --report backups/sync_report_dry.json`
  - `sync`: the same without `--dry-run`, writing `backups/sync_report.json`.

- [ ] **Step 4: Live dry run**

Run: `make sync-dry-run`
Expected: a summary line and a report. Show the owner the new candidates (titles, venues and sources), the proposed hides with their evidence, and the discrepancy count. The owner judges whether the filters let junk through. Each problem becomes a new failing test in Task 4 or Task 6 plus a fix, never a hand-edit of data.

- [ ] **Step 5: Owner decides on a real run.** If approved, run `make sync`, then `make backup-local`. Pending items stay invisible on the CV until Plan 3's review PR approves them.

- [ ] **Step 6: Commit**

```bash
git add Makefile README.md
git commit -m "chore: add weekly sync make targets and docs"
```
