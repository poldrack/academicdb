# Cloud Database + Weekly Bibliography Pipeline — Design

Date: 2026-10-18
Branch: `dev/newdbmodel`

## Intent

Today the bibliography lives in a local SQLite database, and updating the two
websites' publication lists is a manual chain (`make export` → copy
`publications.json` into each site → render/commit). The goal is for the
bibliography to regenerate **weekly, unattended**, and for both sites to update
from it, with the owner's attention needed only when there is a genuine
decision to make.

The database moves to the cloud primarily so an unattended job (GitHub Actions)
can read and write it. Cost must stay as close to zero as possible.

Sites:
- Personal: https://github.com/poldrack/poldrack.github.io (Quarto, rendered locally today, `docs/` committed, no CI)
- Lab: https://github.com/poldracklab/poldracklab.github.io (Quarto, `.github/workflows/render.yml` renders + deploys to Pages on push to `main`)

## Goals

1. Hosted PostgreSQL on **Neon (free tier)** as the single source of truth.
2. A weekly scheduled job that:
   1. discovers new publications,
   2. enriches existing ones (PMID, PMCID, open-access link),
   3. detects preprints that have since been published and proposes hiding them,
   4. exports a YAML reference list and updates both sites.
3. Risk-split review:
   - **Routine changes publish automatically**: enrichment of already-visible
     publications (PMID, PMCID, OA URL, metadata corrections on fields that are
     not manually edited).
   - **New publications and proposed preprint hides require approval** via a
     pull request on the personal site.
4. One approval updates both sites.
5. The local Django web app keeps working (hand edits, CV generation including
   talks/teaching/etc. from CSVs), now pointed at the Neon database.

## Non-goals (for this project)

- Deploying the web app to the cloud. It stays local; revisit later.
- Scopus. It is dropped from the weekly pipeline. Its main use was finding
  unique collaborators for the NSF collaborators list; that feature is
  deferred and may return later as a separate function.
- ORCID sync in the weekly pipeline. (Funding/professional activities from
  ORCID remain available as manual commands in the local app.)
- Editing entry contents through the PR. Content edits happen in the local app.

## Anti-goals (ranked by the owner)

Things that would make this a failure even if every step technically runs:

1. **Very bad — a wrong paper appears on the sites** (another author with a
   similar name, a conference abstract, an erratum, peer-review report, etc.).
2. **Very bad — a hand edit is silently undone** (a corrected field reverts, or a
   manually hidden item reappears) by a sync.
3. **Pretty bad — the pipeline silently stops** (expired token/key, disabled
   schedule) and nobody notices for months.
4. **Pretty bad — a real paper gets hidden** because a preprint was wrongly
   matched to an unrelated published paper.

Not concerns: the two sites drifting apart (they are generated from the same
export), and page appearance changing (easy to fix later).

## Decided by the owner

- Neon free-tier PostgreSQL (chosen over Stanford hosted MySQL, which is likely
  unreachable from GitHub Actions, and over Supabase, whose free tier pauses
  after a week idle).
- Local web interface only, for now.
- Drop Scopus and the collaborators feature for now.
- Option "split by risk": routine updates auto-publish; new papers and preprint
  hides go through review.
- Review happens via a PR on the **personal site** repo; merging it triggers
  publishing to the lab site as well.
- Output format pushed to the sites is **YAML** (sites currently read JSON and
  must be switched).

## Data sources (from recon on 2026-10-18)

Recon compared the local DB against OpenAlex for ORCID 0000-0001-6755-0259:

- OpenAlex matched 95% (396/415) of non-ignored local publications. Of the 19
  misses, 10 have no DOI (old books/chapters); 9 exist in OpenAlex but with
  truncated author lists that omit the owner.
- OpenAlex returned 274 works not in the local DB, mostly noise: peer-review
  reports (43), paratext (14), datasets (21), "other"/posters (16), errata (8),
  conference-abstract supplements, sub-chapters of the owner's own books, and
  OSF versioned DOIs (`_v1`…`_v4`). A handful are genuine new 2025–26 items.
- OpenAlex `ids.pmcid` is empty for all works; PMCIDs can be parsed from PMC
  location URLs and agreed with the NCBI ID converter in a 50-DOI sample.
- OpenAlex has no explicit preprint→published field. Preprints are sometimes
  merged as locations of the published work, sometimes separate works.
- Since Feb 2026 OpenAlex requires a (free) API key for cursor paging and a
  usable budget. The list endpoint caps authorships at 100; single-work fetches
  return full lists and are free.

Sources in the weekly pipeline:

| Source | Role |
|---|---|
| OpenAlex (free API key) | Primary discovery by ORCID; PMID; OA URL/status; PMC location; merged preprint locations |
| PubMed E-utilities (existing `pubmed_query`) | Backstop discovery (catches OpenAlex author-list errors); full author lists |
| NCBI ID converter | Authoritative PMCID lookup (batch ≤200 IDs) |
| CrossRef | `relation` data (is-preprint-of / has-preprint) for preprint→published detection; metadata by DOI |

Removed from the weekly pipeline: Scopus, ORCID. Existing code for them may
remain as manual commands; whether to delete it is left to the builder.

## How it works

### Components

- **Neon PostgreSQL**: connection via the existing `DATABASE_URL` setting path
  (`academicdb_web/settings/base.py`). Used by both the local app and the job.
- **academicdb2 repo GitHub Actions**: holds the database credentials and runs
  all pipeline logic. Workflows:
  - `weekly-sync` — cron weekly, plus `workflow_dispatch` for manual runs.
  - `publish` — triggered by `repository_dispatch` from the personal site after
    a review PR is merged or closed, plus `workflow_dispatch`.
- **Personal site repo**: receives the YAML and review PRs; gets a new Actions
  workflow that renders Quarto and deploys to Pages (Pages source switches to
  GitHub Actions). A small workflow fires `repository_dispatch` to academicdb2
  when a bot review PR is merged or closed. No database credentials live in
  either site repo.
- **Lab site repo**: receives YAML pushes; its existing render workflow rebuilds
  the site.
- **Cross-repo credential**: a GitHub App (preferred, no expiry) or
  fine-grained PAT, with write access to both site repos. The owner creates it;
  the poldracklab org may need an admin to approve it.

### Weekly run

1. Back up the database (see Backups).
2. Discover: query OpenAlex by ORCID and PubMed by the user's query. Normalize
   DOIs; collapse OSF `_vN` versions; drop types peer-review, paratext,
   erratum, dataset, other, and conference-abstract supplements; drop anything
   previously **rejected** or **manually ignored**; drop anything published
   before the **discovery cutoff** (below). Fetch single OpenAlex works
   for full author lists where the list response hit the 100-author cap.
3. Every newly discovered work becomes a publication in **pending** state. Pending
   items never appear in the public export until approved.
4. Enrich visible publications: PMID, PMCID (NCBI ID converter), OA URL. These
   are routine and do not need review.
5. Detect published preprints. Candidate evidence, in order of strength:
   CrossRef relation; preprint DOI appearing as a location of the published work
   in OpenAlex; title + author similarity. Every match becomes a **proposed
   hide**, recorded with its evidence and the matched published paper.
6. Export YAML from the DB.
   - If there are pending items or proposed hides: push the export to a bot
     branch on the personal site and open (or update) a review PR. The YAML in
     the PR includes approved items plus the pending ones, and excludes the
     preprints proposed for hiding. The PR body is a plain-language summary,
     e.g. "3 new papers; 1 preprint hidden because it was published as X",
     with links and match evidence for each item.
   - Routine changes publish immediately: the job commits the export to both
     sites' `main`, built **without** pending items and with proposed-hide
     preprints still visible.
   - If nothing changed, nothing is committed.
7. On any failure, open or update a GitHub issue in academicdb2 (which emails
   the owner) in addition to the failed-run notification.

### Discovery cutoff (decided by the owner)

The backlog of ~274 unmatched OpenAlex works (plus PubMed) is handled with a
one-year date cutoff instead of a triage step. Works published before the
cutoff are never proposed as new publications. The owner then curates the
first review PR by editing its YAML directly, deleting unwanted entries before
merging.

Claude's call: the cutoff is a **fixed date**, one year before the first
production run, stored in configuration (not a rolling window). Older papers
missing from the database are added by hand in the local app. The cutoff
applies to discovery only; enrichment and preprint detection still cover all
existing publications.

### Approval (PR merge / close)

- **Merge** = approve what remains in the PR's YAML:
  - a pending item still present → approved (becomes visible);
  - a pending item the owner deleted from the YAML before merging → rejected;
  - a proposed-hide preprint still absent → hide confirmed (`is_ignored=True`,
    reason and published DOI recorded);
  - a proposed-hide preprint the owner restored to the YAML → hide rejected.
- **Close without merge** = reject everything proposed in that PR.
- Rejections are persisted by stable identifier (DOI and/or OpenAlex ID) so the
  same item is never proposed again.
- After recording decisions, `publish` regenerates YAML **from the database**
  (not from the PR file) and pushes it to both sites, so the database stays the
  single source of truth.
- Field-level edits to entries inside the PR are not honored; the PR body says
  so. Make content edits in the local app.

### Protecting against the anti-goals

- **Wrong paper**: nothing new reaches the sites without approval; the
  OpenAlex type filters and the persisted rejection list keep repeat noise out of
  PRs; the summary shows the evidence for each new item.
- **Hand edits undone**: every weekly writer goes through the existing
  edit-protection path (`save_with_edit_protection`, `manual_edits`). A sync must
  never un-hide something hidden manually, and never re-add a deleted or rejected
  item. Tests must prove this for every writer in the pipeline.
- **Silent stop**: failure issue + email (above). GitHub disables scheduled
  workflows after 60 days of repository inactivity, and the design must prevent
  that. A heartbeat must make a missed run visible, e.g. an issue when the last
  success is older than 14 days, checked by a separate trigger. Prefer
  non-expiring credentials (GitHub App); if a PAT is used, surface its expiry
  ahead of time.
- **Real paper hidden**: all hides go through review with evidence shown; no
  automatic hide in the weekly job.

## YAML export

- Built on `academic/management/commands/export_publications.py`.
- Contains only fields the sites use: `doi, title, year, publication_date,
  publication_name, publication_type, is_preprint, volume, page_range,
  authors[].name, identifiers (pmid, pmcid), links (incl. links.resources),
  oa_url`. Drop timestamps, `source`, `id`, Scopus author/affiliation IDs, and
  anything else that changes every sync, so weekly diffs show only real changes.
- Excludes ignored items and pending items (except in the review-PR branch, as
  described above).
- Deterministic order: year desc, then publication_date desc, then title.
- Every author entry must have `name`, falling back to given + family name.
- Both sites switch `publications.qmd` (and the lab site's `software.qmd`) from
  `json.load` to reading the YAML; add PyYAML to the lab CI install. Page
  appearance may change in the process.

## Migration

- One-time copy from the current local database into Neon. Recon got
  inconsistent counts (412 vs 457 publications, 0 vs 32 ignored), so there may
  be more than one database file. Before migrating, the builder confirms which
  DB the local app actually uses and shows the owner the row counts per table.
  After migrating, those counts must match in Neon.
- The Link table is currently empty. Resource links live only in
  `data/examples/links.csv` and the lab site's `publications.json`
  (`links.resources`). Migration imports them into the Link table: about 41
  papers and 50 resources after URL normalization. The lab site's software
  page must show the same links as today.
- Keep the local SQLite file untouched as a fallback.
- Neon is opt-in until the migration is verified. This is already implemented
  in `academicdb_web/database.py`:
  - `USE_NEON=true` selects `NEON_DATABASE_URL` (pooled; server-side cursors
    disabled);
  - adding `NEON_UNPOOLED=true` selects `NEON_DATABASE_URL_UNPOOLED` (direct;
    use it for migrations and dumps);
  - otherwise the existing `DATABASE_URL`, `USE_POSTGRES` and SQLite order
    applies.

  The Neon schema has been created (all migrations applied, 2026-10-18), but
  it holds no data. After migration, Neon becomes the default. Editing then
  requires an internet connection.
- There are two local SQLite files: `academicdb_web/db.sqlite3` (the
  settings default) and `~/.cache/academicdb/db.sqlite3` (the Makefile's
  `DBDIR`). This likely explains the inconsistent counts.
- Existing manual edits, ignored flags and ignore reasons must survive migration.

## Phase 2: data/code link discovery (after the core pipeline works)

Goal: suggest data/code links for papers automatically, instead of relying
only on the hand-maintained spreadsheet. The spreadsheet, once imported into
the Link table, stays the place for corrections and older papers.

Recon on 2026-10-18 tested sources against the existing links (41 papers, 50
resources). Raw results and collector scripts are in the session scratchpad,
not the repo.

- No source comes close to complete. All useful sources together found 29/50.
- The broad citation-graph sources mostly return things a paper *used*, not
  things it *shared*: ScholeXplorer/Scholix, DataCite related-ID search,
  Europe PMC data links, and unfiltered full text. Examples are fMRIPrep, MRIQC,
  datalad, reused OpenNeuro datasets, and other authors' figshare supplements.

Sources to use (high precision):

| Source | Recon result |
|---|---|
| OpenNeuro: `advancedSearch` by author, matched to papers via DOI/PMID/title in free-text references | 9/16 OpenNeuro links; 3 new candidates, all correct |
| OSF: nodes of the owner's OSF accounts (jrh7c, 93vb4, wqtkq), matched by title | 9/14 OSF links; 17 new, ~3/5 correct |
| CrossRef `relation` `is-supplemented-by` | rare but near-certain; repository DOIs under `references` are suggestions only |
| Europe PMC full text (PMC papers): data/code availability section and body only, never reference-list-only hits | the only source that finds GitHub links |

Sources not to use: unfiltered Scholix, DataCite related-ID search, and
DataCite records by ORCID unless they are Dataset type and link to or
title-match a paper. Of those ORCID records, 622/686 are software releases.

Rules:
- A candidate requires an author/ORCID overlap with the paper, or a GitHub
  owner that is a co-author or lab org.
- A blocklist of common tools applies (fMRIPrep, MRIQC, FSL, nipype, pydeface,
  datalad, TemplateFlow, HCP, …), except on the paper describing that tool.
- Candidates are proposed links in the weekly review PR, with the same
  approve/reject-by-editing-YAML semantics. Rejections persist. Nothing is
  written automatically, and manual links are never altered.
- Caveat: the OSF/OpenNeuro title matchers were tuned on the same ground
  truth, so expect lower recall on new papers.

## Backups

- Weekly `pg_dump` (or the existing `backup_data` JSON) from the weekly job,
  stored in **Neon object storage** (decided by the owner; S3-compatible,
  private). Credentials are `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` and `AWS_REGION` (in `.env` locally; GitHub secrets
  for the job). Retention policy is the builder's call.
- **Local backups** (owner request): a make target dumps the Neon database to
  a timestamped file on the owner's machine, and a matching restore path
  exists. This guards against losing both the database and the backups at
  Neon.
- Restore must be documented and tested once.
- Neon's free tier keeps only ~6 hours of point-in-time history, so it is not
  a backup.

## Constraints

- Cost: free tiers only (Neon free, GitHub Actions free minutes, OpenAlex free
  key, NCBI/CrossRef/PubMed free).
- No database credentials in either site repo.
- Project rules (CLAUDE.md): uv for everything; pytest with TDD
  (tests committed before implementation); no code in `__init__.py`; short
  functions; external APIs mocked in tests (`responses`).
- Secrets: `DATABASE_URL`, OpenAlex API key, NCBI/Entrez email, cross-repo
  credential. All stored as GitHub Actions secrets; none in code.

## Calls made by Claude (owner to check)

- **Single owner.** The pipeline runs only for the owner's account (ORCID
  0000-0001-6755-0259), configured via secrets/settings. It is not a multi-user
  feature. The app's models stay multi-user.
- **Routine changes are fill-only.** Without review, the job may only fill
  *empty* fields and set PMID, PMCID and OA URL. It never overwrites a non-empty
  title, author list, venue, date, volume or pages. Differences in those fields
  are not applied automatically; the builder may log them for the owner.
- **Deletes leave tombstones.** From now on, every delete path in the local app
  (single delete, the duplicates page, bulk "delete all", the API delete) records
  a permanent rejection keyed by DOI/OpenAlex ID, so the item is never proposed
  again. Items deleted before this project left no record, which is handled by
  the first-run triage (below).
- **Hides are never undone by the pipeline.** All hides, manual or confirmed
  through a PR, are respected by every sync. A PR-confirmed hide records where it
  came from (pipeline-proposed, confirmed on date X, evidence) in structured
  form, so it is easy to find and reverse by hand in the local app.
- **One open review PR at a time, never rewritten.** While a review PR is open,
  weekly runs do not add items to it or rewrite its branch. New discoveries wait
  for the next PR after the current one is merged or closed. Routine pushes to
  `main` continue meanwhile. A merge therefore decides only what that PR showed.
  After the PR has been open for 14 days, a reminder comment is added.

## Left to the builder

- Data model for pending/rejected/proposed-hide state (new fields vs. a separate
  table), and the migrations.
- How the pipeline is packaged (management commands vs. a module) and how the
  workflows invoke it.
- OpenAlex query details, rate handling, and the title/author similarity
  threshold for preprint matching (it may reuse
  `Publication.find_published_version_of_preprint`).
- Whether to keep or delete the Scopus/ORCID sync code and the
  collaborator-extraction code.
- Fixes for bugs found in recon that touch the pipeline:
  - `sync_preprint_relations` reads a `metadata['relation']` key that nothing
    writes, so it does nothing;
  - CrossRef `page` is never saved;
  - Scopus replaces whole JSON fields on update (moot if Scopus is out of the
    pipeline).
- GitHub App vs. fine-grained PAT, and the exact Pages/workflow setup on the
  personal site.
- How full-text search behaves on Postgres (it is already Postgres-aware), and
  whether to enable the GIN indexes that are commented out.
