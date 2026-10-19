# Export and Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weekly, unattended:
- export a trimmed, deterministic YAML reference list from Neon;
- publish routine changes to both sites;
- open one review PR on the personal site for new papers and proposed preprint hides;
- apply the owner's decisions when that PR is merged or closed;
- raise a GitHub issue whenever anything fails or stalls.

**Architecture:**
- **Code layout:** a new `academic/publish/` package (YAML export, GitHub REST client, review batches, decisions, publishing) is driven by management commands.
- **Workflows:** three GitHub Actions workflows in the `poldrack/academicdb` repo (`weekly-sync`, `publish`, `heartbeat`) run those commands. Two GitHub App installation tokens give access to the personal site and the lab site.
- **Site-side files:** these are versioned in this repo under `deploy/sites/`, tested here, and copied into the site repos in the owner-present rollout task.

**Tech Stack:** Django 4.2, PostgreSQL 18 on Neon, PyYAML, requests, pytest + pytest-django + `responses` + freezegun, GitHub REST API, GitHub Actions, `actions/create-github-app-token`, Quarto.

**Spec:** `docs/superpowers/specs/2026-10-18-cloud-db-weekly-bibliography-design.md`. Plans 1 and 2 are complete: `docs/superpowers/plans/2026-10-18-neon-migration-and-backups.md` and `docs/superpowers/plans/2026-10-18-weekly-sync-core.md`.

## Calls made by Claude in this plan (owner to check)

1. **Review file instead of editing the full list.** The review PR adds `review/<YYYY-MM-DD>.yml` with two sections:
   - `new:` lists the pending papers. Delete an entry to reject it.
   - `hide:` lists the preprints proposed for hiding. Delete an entry to keep that preprint visible.

   The spec's version had the PR edit the full `publications.yml`, while routine pushes keep changing that same file on `main`. That would often conflict, and "restoring" a preprint would mean re-typing its YAML. The meaning of merge and close is unchanged: what remains in the file is what gets approved. After processing, the review file is deleted from `main`.
2. **GitHub App, two installation tokens.** An App installation is per account, so the workflows mint one token for `poldrack` (personal site, plus `academicdb` for dispatch) and one for `poldracklab` (lab site). The built-in `GITHUB_TOKEN` handles issues and workflow keep-alive in `academicdb`.
3. **Fallback for a lost dispatch.** Every weekly run first checks whether the open review PR was merged or closed and processes it, so a failed `repository_dispatch` only delays decisions by up to a week.
4. **Keep-alive.** Both scheduled workflows call `gh workflow enable` on both scheduled workflows each run. That keeps GitHub from disabling them after 60 days without repository activity. The daily heartbeat opens an issue when the last successful weekly run is more than 14 days old.
5. **Schedule.** `weekly-sync` runs Mondays at 13:00 UTC (06:00 Pacific); `heartbeat` runs daily at 14:00 UTC.
6. **Workflows run from `main` only.** Scheduled and `repository_dispatch` workflows only run from the default branch, so automation starts only after `dev/newdbmodel` is merged into `main` and pushed. That merge is the owner's decision in Task 11.

## Global Constraints

- **uv:** use it for everything; `uv add` for dependencies, `uv run` for every command.
- **Tests:** pytest functions (not classes) and fixtures. They are written and committed before the implementation (RED → commit → GREEN). Never change a test just to make it pass; a test change must reflect a requirement change or a test error.
- **`__init__.py`:** no code or imports in any of them (`academic/publish/__init__.py` is empty).
- **Size:** keep functions short and modules focused.
- **Test command:** `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest …`. The suite has exactly 2 known failures to leave alone: `test_homepage_accessible` and `test_comprehensive_sync_with_data_directory`.
- **No network in tests:** HTTP is mocked with `responses`.
- **Secrets:**
  - No secret ever appears in code, logs, commit messages, exception messages or test fixtures.
  - Never read `.env` or `neon-storage.env`.
  - No database credentials in either site repo.
- **Never run `migrate` or any write against Neon** outside Task 11's owner-present steps.
- **Commit trailer:** use the Co-Authored-By line your own system context gives you.
- **Single owner:** the pipeline runs for ORCID `0000-0001-6755-0259`; models stay multi-user.
- **Public export:**
  - It contains only approved, non-ignored publications.
  - Pending items appear only in the review file.
  - Preprints with a pending hide proposal stay visible until the hide is confirmed.
- **Fields:** the YAML has exactly these, in this order: `doi, title, year, publication_date, publication_name, publication_type, is_preprint, volume, page_range, authors[].name, identifiers (pmid, pmcid), links (incl. links.resources), oa_url`.
- **Order:** year desc, then publication_date desc (missing dates last), then title (case-insensitive), then id.
- **Decisions:**
  - Merge approves what remains in the review file.
  - Close rejects everything in the batch.
  - Rejections leave tombstones (existing `reject_pending`).
  - Hides are recorded by the existing `confirm_hide`.
  - After decisions, the sites are regenerated from the database, never from the PR file.
- **One review PR at a time:** never rewritten. Reminder comment once, after the PR has been open 14 days.
- **Repositories:**
  - `PIPELINE_REPO=poldrack/academicdb`
  - `PERSONAL_SITE_REPO=poldrack/poldrack.github.io`
  - `LAB_SITE_REPO=poldracklab/poldracklab.github.io`
  - site file `publications.yml`
  - review branch prefix `academicdb/review-`
  - dispatch event type `review-pr-closed`

## Review Focus

1. **Broken review file.** If the owner leaves the review file invalid (bad YAML, a missing section, or the file deleted in the PR), the pipeline must decide nothing, leave the batch open and fail loudly. → Task 6 `test_invalid_review_file_decides_nothing`, `test_missing_review_file_decides_nothing`.
2. **Rejected published version.** A pending paper the owner rejects, whose hide proposal points at it as the published version, must leave the preprint visible. → Task 6 `test_rejecting_published_target_keeps_preprint_visible`.
3. **Routine publish during review.** A routine publish while a review PR is open must not leak pending items and must keep proposed-hide preprints visible. → Task 7 `test_public_publish_during_open_review`.
4. **Partial publish failure.** If the personal site updates but the lab push fails, the next run must finish the lab update and must not re-commit the personal site. → Task 7 `test_publish_is_idempotent_after_partial_failure`.
5. **Dispatch for a non-bot PR, or a lost dispatch.** A non-bot PR number is a no-op. A lost dispatch is caught up by the next weekly run. → Task 7 `test_process_review_unknown_pr_is_noop`, `test_publish_sites_processes_decided_pr_first`.

---

### Task 1: Plan 2 carry-overs in the sync

**Files:**
- Modify: `academic/sync/run.py` (fetch phase, `_crossref_lookup`)
- Modify: `academic/sync/idconv.py`
- Modify: `academic/tombstones.py` (`doi_key`)
- Modify: `academic/sync/filters.py` (`_version`)
- Modify: `README.md` (Weekly sync section)
- Test: `tests/unit/sync/test_run.py`, `tests/unit/sync/test_ncbi_crossref.py`, `tests/unit/sync/test_filters.py`

**Interfaces:**
- Consumes: `published_dois_for_preprint(doi) -> list[str]`, `visible_preprints(user)`, `propose_hides(user, crossref_lookup, location_index)`.
- Produces: `_Fetched.crossref: dict[str, list[str]]` (preprint DOI key → published DOIs). `lookup_pmcids(ids, email)` keeps its signature.

- [ ] **Step 1: Write the failing tests**
  - `test_crossref_fetched_before_any_write` (test_run.py): monkeypatch `academic.sync.run.published_dois_for_preprint` and `academic.sync.run._write` with wrappers that append `'crossref'`/`'write'` to a shared log. Run the sync. Assert every `'crossref'` entry comes before `'write'`, and that a library preprint's DOI was looked up.
  - `test_crossref_failure_recorded_once_and_sync_continues`: CrossRef returns 500 for one preprint. `report.errors` contains exactly one `crossref:` entry and the run completes.
  - `test_idconv_uses_new_endpoint_and_one_id_type_per_request`: `IDCONV == 'https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/'`. `lookup_pmcids(['10.1/a', '123', '10.1/b'], 'e@x')` makes two requests, one with `idtype=doi` and ids `10.1/a,10.1/b`, one with `idtype=pmid` and ids `123`. The results merge.
  - `test_research_square_versions_collapse`: `doi_key('10.21203/rs.3.rs-1234567/v2') == '10.21203/rs.3.rs-1234567'`. `collapse_versions` over `/v1`, `/v3`, `/v2` keeps `/v3`. A non-Research-Square DOI ending `/v2` is unchanged by `doi_key`.

- [ ] **Step 2: Run them to verify they fail**

  Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/sync -q`
  Expected: the 4 new tests FAIL (CrossRef called inside `_write`, old endpoint, no version collapse).

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement**
  - **CrossRef prefetch:** `_fetch` builds `crossref` by calling `published_dois_for_preprint` for each `visible_preprints(user)` row with a DOI. A `SourceError` is appended once to `report.errors` and yields `[]`. `_crossref_lookup` becomes a dict lookup on `doi_key`.
  - **ID converter:** group IDs by type (`'/' in id` → `doi`, else `pmid`), batch ≤200 per type, and pass `idtype`.
  - **Research Square versions:** `doi_key` strips `/v\d+$` only when the key starts with `10.21203/rs.`. `filters._version` reads that suffix too, so the highest version wins.
  - **README:** add one paragraph under "Weekly sync". Deleting publications, including the bulk "delete all", records each one as rejected so the sync never re-adds it. To allow a deleted paper back, delete its row in `RejectedWork` via the admin.

- [ ] **Step 5: Run the sync tests, then the full suite**

  Expected: sync tests pass; full suite has only the 2 known failures.

- [ ] **Step 6: Commit**

---

### Task 2: Site YAML export

**Files:**
- Create: `academic/publish/__init__.py` (empty), `academic/publish/site_yaml.py`
- Create: `academic/management/commands/export_site_yaml.py`
- Modify: `pyproject.toml` (`uv add pyyaml`), `Makefile` (`export-yaml` target)
- Test: `tests/unit/publish/__init__.py` (empty), `tests/unit/publish/test_site_yaml.py`

**Interfaces:**
- Produces:
  - `site_record(pub: Publication, resources: list[dict]) -> dict`
  - `site_records(user, include_pending: bool = False) -> list[dict]` (public by default)
  - `render_site_yaml(records: list[dict]) -> str`, which emits `{'publications': records}`
  - `record_key(record: dict) -> str`: `doi_key(doi)`, else `'pmid:<pmid>'`, else `''`
  - Command `export_site_yaml --orcid-id ID --output PATH [--include-pending]`.

- [ ] **Step 1: Write the failing tests**
  - `test_record_has_exactly_the_site_fields_in_order`: keys equal the Global Constraints list, in order. No `id`, `source`, timestamps, `metadata` or `manual_edits`.
  - `test_identifiers_keep_only_nonempty_pmid_and_pmcid`: `{'pmid': '1', 'pmcid': '', 'scopus': 'x'}` → `{'pmid': '1'}`; all empty → `{}`.
  - `test_links_include_resources_from_link_table`: a `Link` with the pub's DOI (case-insensitive) appears as `links.resources: [{'type','url','title'}]`, ordered by type then URL. With no links, `links == {}`.
  - `test_author_name_falls_back_to_given_family`: `{'given': 'Ann', 'family': 'Lee'}` → `{'name': 'Ann Lee'}`. An author with neither name nor given/family is dropped.
  - `test_oa_url_from_metadata`: `metadata={'oa_url': 'u'}` → `oa_url: 'u'`; absent → `None`.
  - `test_public_records_exclude_ignored_and_pending`.
  - `test_include_pending_adds_pending`.
  - `test_order_year_date_title`: records sort by year desc, then date desc with `None` last, then case-insensitive title, then id.
  - `test_render_is_deterministic_and_round_trips`:
    - two renders are byte-identical;
    - `yaml.safe_load` round-trips;
    - dates are ISO strings;
    - non-ASCII author names are kept unescaped;
    - no line wrapping inside titles.
  - `test_export_site_yaml_command_writes_file`.

- [ ] **Step 2: Run them; expect FAIL** (module missing)

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement**
  - **Queries:** use one query for publications and one for links, grouped by `doi.lower()`. No N+1 queries: test with `django_assert_num_queries(2)`, and add that test in Step 1.
  - **Dump:** `yaml.safe_dump(…, sort_keys=False, allow_unicode=True, width=10000)`.
  - **Makefile:** `export-yaml` writes `backups/publications.yml` for ORCID `0000-0001-6755-0259` with `USE_NEON=true`.

- [ ] **Step 5: Run tests and the full suite; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 3: Review batch state

**Files:**
- Modify: `academic/models.py` (add `ReviewBatch`), new migration `academic/migrations/0029_reviewbatch.py`
- Create: `academic/publish/batches.py`
- Test: `tests/unit/publish/test_batches.py`

**Interfaces:**
- Produces:
  - **The model:** `ReviewBatch(owner FK AcademicUser CASCADE, status CharField choices open/merged/closed default 'open', pr_number PositiveIntegerField null unique, branch CharField(100), path CharField(200), opened_at DateTimeField, decided_at DateTimeField null, reminded_at DateTimeField null, publications M2M Publication related_name='review_batches', proposals M2M PreprintHideProposal related_name='review_batches')`.
  - **Helpers in `batches.py`:**
    - `open_batch(user) -> ReviewBatch | None`
    - `reviewable_items(user) -> tuple[list[Publication], list[PreprintHideProposal]]` returns pending publications (`review_status='pending'`, not ignored) and pending proposals, both ordered by id.
    - `create_batch(user, pr_number, branch, path, pubs, proposals, now) -> ReviewBatch`

- [ ] **Step 1: Write the failing tests**
  - `test_open_batch_none_when_all_decided`
  - `test_reviewable_items_lists_pending_only`: approved pubs, ignored pending pubs, and confirmed or rejected proposals are excluded.
  - `test_create_batch_links_items`
  - `test_pr_number_unique`
  - `test_deleting_rejected_pub_removes_it_from_batch`: M2M rows go away, the batch survives.

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement the model, `makemigrations academic --name reviewbatch`, then the helpers.** Register `ReviewBatch` in `academic/admin.py` (list display: pr_number, status, opened_at).

- [ ] **Step 5: Run tests and the full suite; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 4: GitHub REST client

**Files:**
- Create: `academic/publish/github.py`
- Test: `tests/unit/publish/test_github.py`

**Interfaces:**
- Produces:
  - `class GitHubError(Exception)`: its message contains method, path and status only, never the token or the response headers.
  - `@dataclass RepoFile(text: str, sha: str)`.
  - `class GitHub`, constructed as `__init__(self, token: str | None, api: str = 'https://api.github.com')`. It sends `Authorization: Bearer <token>` when the token is set, plus `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`, with a timeout of 30 s.
    - **Files:**
      - `get_file(repo, path, ref='main') -> RepoFile | None` (404 → `None`; decodes base64 UTF-8)
      - `put_file(repo, path, text, message, branch='main', sha=None) -> str` (returns the commit sha)
      - `delete_file(repo, path, message, sha, branch='main') -> None`
    - **Branches and pull requests:**
      - `create_branch(repo, branch, from_branch='main') -> None` (a 422 "Reference already exists" is not an error)
      - `open_pr(repo, head, title, body, base='main') -> int`
      - `get_pr(repo, number) -> dict` (keys used: `state`, `merged`, `merge_commit_sha`, `head.ref`)
      - `comment(repo, number, body) -> None`
    - **Issues:**
      - `find_open_issue(repo, title) -> int | None` (searches open issues with label `pipeline`)
      - `open_issue(repo, title, body) -> int` (label `pipeline`)
      - `close_issue(repo, number, body) -> None` (comment, then close)
    - **Runs:** `latest_success(repo, workflow_file) -> datetime | None`, from `GET /repos/{repo}/actions/workflows/{file}/runs?status=success&per_page=1`.

- [ ] **Step 1: Write the failing tests**, one per method, with `responses`. Assert:
  - URL and method;
  - JSON body (base64 content, `sha` present only when given, `branch`);
  - the auth header present when a token is given and absent without one;
  - 404 → `None` for `get_file`;
  - 422 tolerated for `create_branch`;
  - a 500 raises `GitHubError` whose `str()` does not contain the token (`'secret-token-xyz'`).

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement with a `requests.Session`.** One private `_request(method, path, **kw)` raises `GitHubError` for any status ≥400 the caller didn't allow. No retries: a failure fails the run, which raises an issue (Task 8).

- [ ] **Step 5: Run tests; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 5: Opening the review PR

**Files:**
- Create: `academic/publish/review_pr.py`
- Test: `tests/unit/publish/test_review_pr.py`

**Interfaces:**
- Consumes: `site_record`, `record_key` (Task 2), `open_batch`, `reviewable_items`, `create_batch` (Task 3), `GitHub` (Task 4).
- Produces:
  - `REVIEW_HEADER: str`, the comment block at the top of the review file.
  - `review_yaml(pubs, proposals) -> str`, which emits `{'new': [site_record…], 'hide': [{**site_record(preprint), 'published_as': {'doi', 'title'}, 'evidence': {'method': …, **evidence}}]}`.
  - `pr_title(pubs, proposals) -> str` and `pr_body(pubs, proposals) -> str`.
  - `open_review_pr(user, gh: GitHub, repo: str, now: datetime) -> ReviewBatch | None`
  - `remind_if_stale(batch, gh, repo, now) -> bool`

- [ ] **Step 1: Write the failing tests**
  - `test_review_yaml_sections_and_header`:
    - The file starts with `REVIEW_HEADER`.
    - The header says, verbatim: `# Delete an entry under "new" to reject that paper.`, `# Delete an entry under "hide" to keep that preprint visible.` and `# Edits to fields are ignored; make content edits in the local app.`
    - `new` holds the pending records; `hide` holds the preprint records with `published_as` and `evidence`.
  - `test_pr_title_counts`: 3 papers and 1 hide → `'Review: 3 new papers, 1 preprint to hide'`, singular/plural correct. Zero hides → `'Review: 1 new paper'`.
  - `test_pr_body_lists_items_with_links_and_evidence`:
    - each new paper shows title, venue, year and authors (first 3 plus `et al.`);
    - each shows a `https://doi.org/<doi>` link;
    - it shows `https://openalex.org/<id>` and `https://pubmed.ncbi.nlm.nih.gov/<pmid>/` only when those values are non-empty (`''` counts as missing);
    - each hide line reads `"<preprint title>" hidden because it was published as "<published title>" (<doi link>)`, followed by the method and evidence values.
  - `test_open_review_pr_creates_branch_file_pr_and_batch` (mocked GitHub): branch `academicdb/review-2026-10-19`, file `review/2026-10-19.yml` on that branch, PR opened against `main`, batch saved with `pr_number` and both item sets.
  - `test_open_review_pr_noop_when_batch_open` and `test_open_review_pr_noop_when_nothing_pending`: no HTTP calls are made.
  - `test_failed_pr_creation_saves_no_batch`: `open_pr` raises `GitHubError` → no `ReviewBatch` row, error propagates.
  - `test_remind_once_after_14_days`: at day 13 no comment; at day 14 one comment and `reminded_at` set; day 20 no second comment.

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement.** The batch is created only after `open_pr` returns. A reminder comment reads: `This review has been open for 14 days. New discoveries wait until it is merged or closed.`

- [ ] **Step 5: Run tests; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 6: Applying review decisions

**Files:**
- Create: `academic/publish/decisions.py`
- Test: `tests/unit/publish/test_decisions.py`

**Interfaces:**
- Consumes: `approve_pending`, `reject_pending`, `confirm_hide`, `reject_hide` (`academic/sync/review.py`), `record_key` (Task 2), `GitHub` (Task 4), `ReviewBatch` (Task 3).
- Produces:
  - `class ReviewFileError(Exception)`
  - `parse_review_file(text: str) -> tuple[set[str], set[str]]` returns the record keys of `new` and `hide`. It raises `ReviewFileError` on invalid YAML, a non-mapping top level, or a missing or non-list `new`/`hide`. An empty list is valid.
  - `@dataclass Decisions(approved: list[int], rejected: list[int], hidden: list[int], kept: list[int])`, holding publication ids; `hidden`/`kept` are preprint ids.
  - `apply_merged(batch, text, now) -> Decisions`, atomic.
  - `apply_closed(batch, now) -> Decisions`, atomic.
  - `process_pr(batch, gh, repo, now) -> Decisions | None`: `None` while the PR is open or the batch is not open.

- [ ] **Step 1: Write the failing tests**
  - `test_merge_approves_present_and_rejects_deleted`: the rejected pub is gone, with a `RejectedWork` tombstone.
  - `test_merge_hides_present_and_keeps_deleted`:
    - a confirmed preprint is `is_ignored=True` with `metadata['hidden_by']`;
    - a deleted entry → proposal `rejected`, preprint still visible.
  - `test_rejecting_published_target_keeps_preprint_visible`: the published side is a pending pub in the same batch that the owner deleted from `new`, while the preprint is still under `hide` → proposal `rejected`, preprint visible, pending pub rejected.
  - `test_close_rejects_everything`.
  - `test_invalid_review_file_decides_nothing`: cases are `'new: [unclosed'`, `'[]'` and `'new: []'` (no `hide`). Each raises `ReviewFileError`; no publication or proposal changes; the batch stays `open`.
  - `test_missing_review_file_decides_nothing`: `get_file` returns `None` at the merge commit → `ReviewFileError`; nothing changes.
  - `test_process_pr_reads_file_at_merge_commit_and_deletes_it`: `get_file(repo, batch.path, ref=<merge_commit_sha>)`; after deciding, `delete_file` on `main` (the sha comes from a fresh `get_file` on `main`). The batch becomes `merged` with `decided_at`.
  - `test_process_pr_open_is_noop` and `test_process_pr_already_decided_is_noop`.
  - `test_item_already_decided_elsewhere_is_skipped`: a proposal confirmed by hand before the merge raises no error, and the other items are decided.

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement `apply_merged` in this order:**
  1. Parse the file.
  2. For each batch proposal still `pending`:
     - its `published` pub is in this batch and its key is absent from `new` → `reject_hide`;
     - otherwise, the preprint key is in `hide` → `confirm_hide`;
     - otherwise → `reject_hide`.
  3. For each batch pub still `pending`:
     - key in `new` → `approve_pending`;
     - otherwise → `reject_pending`.
  4. Mark the batch `merged`.

  Hides go first because rejecting a pub cascades and deletes its proposals. An item that is no longer pending is skipped. `process_pr` deletes the review file only after the database transaction commits.

- [ ] **Step 5: Run tests and the full suite; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 7: Publishing commands

**Files:**
- Create: `academic/publish/publish.py`
- Create: `academic/management/commands/publish_sites.py`, `academic/management/commands/process_review.py`
- Modify: `Makefile` (`publish-dry-run` target)
- Test: `tests/unit/publish/test_publish.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces:
  - `PublishConfig`, built by `from_env(env: Mapping) -> PublishConfig`:
    - `personal_repo`, `lab_repo`, `pipeline_repo`, read from `PERSONAL_SITE_REPO`, `LAB_SITE_REPO` and `PIPELINE_REPO` with the Global Constraints defaults;
    - `site_path='publications.yml'`;
    - `personal_token` from `PERSONAL_GITHUB_TOKEN` and `lab_token` from `LAB_GITHUB_TOKEN`. Both are required unless `dry_run`; a missing one raises `CommandError` naming the variable.
  - `publish_public(user, targets: list[tuple[GitHub, str]], site_path: str, dry_run: bool = False) -> list[str]` returns the repos updated.
  - `class DryRunGitHub(GitHub)`: reads go through, while writes are logged to `self.writes` and return placeholders.
  - Command `publish_sites --orcid-id ID [--dry-run]` runs in order:
    1. If there is an open batch, `process_pr`.
    2. `publish_public` to both sites.
    3. If a batch is still open, `remind_if_stale`; otherwise `open_review_pr`.

    With `--dry-run`, all database writes roll back and it prints the planned writes.
  - Command `process_review --orcid-id ID --pr N`: the batch with that `pr_number` → `process_pr`, then `publish_public`. An unknown PR number prints `No review batch for PR N` and exits 0.

- [ ] **Step 1: Write the failing tests**
  - `test_publish_commits_only_when_content_differs`: identical remote text → no PUT. Different text → one PUT per site, message `Update publications (academicdb)`, with the remote `sha`. A missing remote file → PUT without a sha.
  - `test_public_publish_during_open_review`: with a pending pub and a pending hide proposal in an open batch, the pushed YAML has no pending pub and still contains the preprint.
  - `test_publish_is_idempotent_after_partial_failure`:
    - the lab PUT fails → `GitHubError` propagates after the personal PUT;
    - on the second run, the personal file equals the new text → no personal PUT, and the lab PUT happens.
  - `test_publish_sites_processes_decided_pr_first`: an open batch whose PR is merged gets decided, then the published YAML includes the newly approved pub, and a new review PR opens if items remain (none here → no PR).
  - `test_publish_sites_opens_review_pr_when_pending`.
  - `test_process_review_unknown_pr_is_noop`.
  - `test_dry_run_makes_no_writes`: there are no POST, PUT or DELETE requests to `responses`; DB counts are unchanged; planned writes are printed; it works with no tokens set.
  - `test_missing_token_names_variable`.

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement.** In the Makefile, `publish-dry-run` runs `USE_NEON=true uv run python manage.py publish_sites --orcid-id 0000-0001-6755-0259 --dry-run`.

- [ ] **Step 5: Run tests and the full suite; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 8: Failure issues and heartbeat

**Files:**
- Create: `academic/publish/alerts.py`
- Create: `academic/management/commands/pipeline_alert.py`
- Test: `tests/unit/publish/test_alerts.py`

**Interfaces:**
- Consumes: `GitHub` (Task 4).
- Produces:
  - `report_failure(gh, repo, workflow: str, run_url: str) -> int`: opens the issue `Pipeline failing: <workflow>`, or comments on it if it is already open. The body includes the run URL and the line `Check the run log; the next scheduled run will retry.`
  - `resolve_failure(gh, repo, workflow, run_url) -> bool`: closes that issue with `Recovered in <run_url>.` if it is open.
  - `check_heartbeat(gh, repo, workflow_file: str, now: datetime, max_age_days: int = 14) -> bool`, which returns `True` when healthy:
    - if the last success is older than `max_age_days` (or there is none), it opens or comments on `Pipeline stalled: <workflow_file>`, giving the last success date or `never`;
    - when healthy, it closes that issue if open.
  - Command `pipeline_alert {failure,recovered,heartbeat} --workflow NAME [--run-url URL] [--max-age-days N]`. It uses `GITHUB_TOKEN` and `GITHUB_REPOSITORY` from the environment and needs no database access. It exits non-zero only on a GitHub error.

- [ ] **Step 1: Write the failing tests:**
  - `test_failure_opens_issue_once_then_comments`
  - `test_recovered_closes_open_issue`
  - `test_recovered_without_issue_is_noop`
  - `test_heartbeat_stale_opens_issue` (15 days old)
  - `test_heartbeat_never_succeeded_opens_issue`
  - `test_heartbeat_fresh_closes_issue` (13 days old)

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Implement**

- [ ] **Step 5: Run tests; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 9: Pipeline workflows

**Files:**
- Create: `.github/workflows/weekly-sync.yml`, `.github/workflows/publish.yml`, `.github/workflows/heartbeat.yml`
- Modify: `README.md` (new "Automation" section)
- Test: `tests/unit/test_workflows.py`

**Interfaces:**
- Consumes: commands `backup_database --upload`, `weekly_sync`, `publish_sites`, `process_review`, `pipeline_alert`.
- Produces: the secret names below. Task 11 sets them.
  - **Secrets:** `NEON_DATABASE_URL`, `NEON_DATABASE_URL_UNPOOLED`, `SECRET_KEY`, `OPENALEX_KEY`, `PUBMED_EMAIL`, `NCBI_API_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BACKUP_BUCKET`, `APP_ID`, `APP_PRIVATE_KEY`.
  - **Repository variable:** `DISCOVERY_CUTOFF`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_workflows.py`. Load each file with `yaml.safe_load`; note that PyYAML parses the key `on` as `True`.
  - `test_weekly_sync_schedule_and_dispatch`: cron `'0 13 * * 1'` plus `workflow_dispatch`.
  - `test_heartbeat_schedule`: cron `'0 14 * * *'`.
  - `test_publish_triggers`: `repository_dispatch.types == ['review-pr-closed']`, and `workflow_dispatch` has a required input `pr`.
  - `test_pipeline_workflows_share_concurrency_group`: weekly-sync and publish use `academicdb-pipeline` with `cancel-in-progress: false`.
  - `test_weekly_sync_step_order`: the step `run:` commands contain, in order, `backup_database --upload`, `weekly_sync`, `publish_sites` and `gh workflow enable`. A step with `if: failure()` runs `pipeline_alert failure`, and a step with `if: success()` runs `pipeline_alert recovered`.
  - `test_every_secret_documented`: every `secrets.X` referenced in any workflow appears in the README "Automation" section, and none of the workflows `echo` a secret.
  - `test_app_tokens_per_owner`: two `actions/create-github-app-token@v2` steps, `owner: poldrack` (repositories `poldrack.github.io,academicdb`) and `owner: poldracklab` (repositories `poldracklab.github.io`). Their outputs feed `PERSONAL_GITHUB_TOKEN` and `LAB_GITHUB_TOKEN`.
  - `test_keepalive_permissions`: weekly-sync and heartbeat have `permissions` `actions: write`, `issues: write` and `contents: read`.

- [ ] **Step 2: Run them; expect FAIL** (files missing)

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Write the workflows**
  - **Setup steps:** all three use `actions/checkout@v4`, `astral-sh/setup-uv@v6` and `uv sync --frozen`.
  - **Job env:** `USE_NEON: 'true'`; the backup step adds `NEON_UNPOOLED: 'true'`.
  - **Keep-alive:** `gh workflow enable weekly-sync.yml && gh workflow enable heartbeat.yml` with `GH_TOKEN: ${{ github.token }}`.
  - **weekly-sync** uploads `sync_report.json` as an artifact.
  - **publish** runs `process_review --pr ${{ github.event.client_payload.pr || inputs.pr }}`.
  - **README "Automation" section:** list each secret and what it is for, the App permissions (Contents read/write, Pull requests read/write, Metadata read), and where the App is installed. It notes that schedules only run from `main`.

- [ ] **Step 5: Run tests; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 10: Site-side files

**Files:**
- Create: `deploy/sites/personal/publications.qmd`, `deploy/sites/personal/.github/workflows/render.yml`, `deploy/sites/personal/.github/workflows/review-dispatch.yml`
- Create: `deploy/sites/lab/publications.qmd`, `deploy/sites/lab/software.qmd`, `deploy/sites/lab/.github/workflows/render.yml`
- Test: `tests/unit/test_site_pages.py`

**Interfaces:**
- Consumes: `render_site_yaml`, `site_records` (Task 2).
- Produces: files that are copied verbatim into the site repos in Task 11.

The current site files are in the public repos. Fetch them read-only into a temp dir with `git clone --depth 1`:
- **Personal site:** `publications.qmd`, which reads `publications.json` with `json.load`. There is no CI; `docs/` is committed.
- **Lab site:** `publications.qmd`, `software.qmd` (the "Data/code/OSF pages" block reads `links.resources`), and `.github/workflows/render.yml`.

- [ ] **Step 1: Write the failing tests.** A helper extracts every ```` ```{python} ```` block from a `.qmd`, writes `publications.yml` (from `render_site_yaml` over factory pubs) to `tmp_path`, `chdir`s there, and `exec`s the blocks, capturing stdout.
  - `test_personal_publications_page_renders_from_yaml`: the output has `## 2026` before `## 2025`. A DOI pub renders as `[Title](https://doi.org/10.1/x)`, a preprint venue gets ` (preprint)`, and a volume renders italic.
  - `test_lab_publications_page_renders_from_yaml`: same assertions.
  - `test_lab_software_page_lists_resource_links`: a pub with Data and Code links renders `[Data](url)` and `[Code](url)`; a pub without links is absent.
  - `test_pages_read_yaml_not_json`: no `.qmd` mentions `publications.json` or `json.load`.
  - `test_personal_render_workflow`:
    - triggers on push to `main` and on `pull_request`;
    - installs `pyyaml`;
    - uploads `docs` with `actions/upload-pages-artifact@v3`;
    - deploys with `actions/deploy-pages@v4` only on push.
  - `test_review_dispatch_workflow`:
    - triggers on `pull_request` `closed`;
    - its job `if` requires `startsWith(github.event.pull_request.head.ref, 'academicdb/review-')`;
    - it mints an App token for `owner: poldrack`, `repositories: academicdb`;
    - it posts `event_type=review-pr-closed` with `client_payload[pr]` set to the PR number to `repos/poldrack/academicdb/dispatches`.
  - `test_lab_render_installs_pyyaml`: the lab workflow equals upstream's apart from `pyyaml` added to the "Install quarto deps" pip line. Keep the rest identical.

- [ ] **Step 2: Run them; expect FAIL**

- [ ] **Step 3: Commit the tests**

- [ ] **Step 4: Write the files**
  - **The `.qmd` files:** keep each site's current rendering logic. Change only the loader (`yaml.safe_load` of `publications.yml`) and the footer, which becomes `*Updated: <date> - generated from academicdb*`.
  - **Personal render workflow:** use `quarto-dev/quarto-actions/setup@v2` and Python 3.12, and run `pip install pyyaml jupyter nbformat nbclient ipykernel`.

- [ ] **Step 5: Run tests; expect PASS**

- [ ] **Step 6: Commit**

---

### Task 11: Rollout (owner present)

The controller runs these steps with the owner. Each one that writes outside this repo (to GitHub settings, the site repos, Neon, or the branch merge) needs the owner's explicit go-ahead at that step.

- [ ] **Step 1: Migrate Neon.** `make backup-local`, then `make migrate-neon`. Expected: `Applying academic.0029_reviewbatch... OK`. Note: a backup taken with the new code before the migration fails, as in Plan 2. Take it from the previous commit with a temporary checkout, as before, or take it right after the migration.
- [ ] **Step 2: Local dry run.** `make publish-dry-run`. Show the owner:
  - the diff between the current site files and the new YAML (item count, and which entries differ beyond format);
  - the review file;
  - the PR title and body it would open (7 papers, 2 hides).

  Fix anything wrong test-first.
- [ ] **Step 3: The owner creates the GitHub App** `academicdb-bot`:
  - permissions: Contents read/write, Pull requests read/write, Metadata read;
  - installs: on `poldrack` (repos `academicdb`, `poldrack.github.io`) and on `poldracklab` (repo `poldracklab.github.io`; an org admin may need to approve);
  - generates a private key.

  The owner adds the Task 9 secrets and variable to `poldrack/academicdb`, and `APP_ID` and `APP_PRIVATE_KEY` to `poldrack/poldrack.github.io`.
- [ ] **Step 4: Site PRs.** With the owner's approval, open one PR per site repo. Each copies its `deploy/sites/<site>/` files and adds an initial `publications.yml` from `make export-yaml`. The owner reviews and merges, then switches the personal site's Pages source to "GitHub Actions". Afterwards, confirm both sites render the list. The old `publications.json` and the personal site's committed `docs/` may be deleted in a follow-up commit if the owner wants.
- [ ] **Step 5: Merge to `main`.** The owner decides whether to merge `dev/newdbmodel` into `main` and push. Schedules and dispatch only work from `main`.
- [ ] **Step 6: First run.** Run `weekly-sync` via `workflow_dispatch`. Expected:
  - the remote backup uploads;
  - the sync reports `new: 0` (the 7 are already pending);
  - both sites get one commit, or none if their files are unchanged;
  - the review PR opens with 7 papers and 2 hides.
- [ ] **Step 7: The owner reviews the PR**, deleting unwanted entries in the review file, and merges. Expected:
  - `publish` runs from the dispatch;
  - the decisions match the file;
  - the review file is deleted from `main`;
  - both sites show the approved papers and no longer list the hidden preprints.
- [ ] **Step 8: Alert path.** Dispatch `heartbeat` once. Expected: healthy, no issue. Then `make backup-local`.
