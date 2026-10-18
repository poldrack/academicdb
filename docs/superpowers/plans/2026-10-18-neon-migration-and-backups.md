# Neon Migration and Backups Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all data from the local SQLite database to Neon PostgreSQL with verified row counts, import the resource links, add local and Neon-object-storage backups with a tested restore path, and make Neon the app's default.

**Architecture:** One small module, `academic/db_transfer.py`, owns counting rows and copying data between two Django database aliases, using `dumpdata`/`loaddata` with natural keys. The migration command, the backup command and the restore command are thin wrappers around it. Backups are gzipped Django JSON fixtures. That format restores into any engine (Neon, another Postgres, SQLite) regardless of server version. Note that the local `pg_dump` is 14.23 and Neon runs PostgreSQL 18.6, so `pg_dump` can't dump Neon without an upgrade. Remote backups go to Neon object storage through boto3.

**Tech Stack:** Django 4.2, PostgreSQL 18 (Neon), SQLite, dj-database-url, boto3 (new), pytest + pytest-django, botocore `Stubber` for S3 tests.

**Spec:** `docs/superpowers/specs/2026-10-18-cloud-db-weekly-bibliography-design.md` (sections "Migration", "Backups", "Constraints")

## Roadmap (later plans, written after this one ships)

1. **This plan:** migration, link import, backups, cutover.
2. **Weekly sync core:**
   - pending, rejected and proposed-hide state, plus delete tombstones;
   - OpenAlex discovery (with the fixed one-year cutoff and type filters) and the PubMed backstop;
   - fill-only enrichment from the NCBI ID converter, OpenAlex and CrossRef;
   - preprint→published proposals;
   - tests proving no writer undoes a manual edit or hide.
3. **Export and publishing:**
   - trimmed deterministic YAML export;
   - personal-site Actions render workflow;
   - YAML reading in both sites' `.qmd` files;
   - weekly-sync, publish and heartbeat workflows;
   - review-PR open/merge/close handling;
   - failure issues;
   - weekly remote backup in CI.
4. **Phase 2:** data/code link discovery.

## Global Constraints

- Use uv for everything: `uv add` for dependencies, `uv run` for every command.
- Tests use pytest functions (not classes) and fixtures. They are written and committed before the implementation (RED → commit → GREEN). Don't change a test just to make it pass.
- No code or imports in any `__init__.py`.
- Keep functions short and modules focused.
- Run tests with `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest …`.
- Migration source is `academicdb_web/db.sqlite3`. `~/.cache/academicdb/db.sqlite3` is never read or written.
- Neon is selected with `USE_NEON=true`. Add `NEON_UNPOOLED=true` for anything that bulk-loads, migrates or dumps (direct connection). See `academicdb_web/database.py`.
- No credentials in code, tests, logs or committed files. The S3 variables are `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`, plus the new `BACKUP_BUCKET`.
- Existing manual edits, ignored flags and ignore reasons must survive migration.
- `.env` is the owner's file. Claude cannot read or edit it, so any `.env` change is an owner step.

## Review Focus

1. **Non-empty target.** Copying or restoring into a database that already has data must refuse and change nothing, rather than merging or duplicating. Tested in Task 1 (`test_copy_refuses_nonempty_target_and_leaves_it_unchanged`).
2. **Primary-key sequences after load.** After a bulk load into Postgres, the next insert must not collide with loaded IDs. Tested on SQLite in Task 1 (`test_new_rows_after_copy_get_fresh_ids`), and verified on Neon in Task 5 Step 4.
3. **DOI case and prefix mismatch between links and publications.** `Link.get_links_for_publication` uses exact `doi=` matching, and links are stored lowercased. A publication whose DOI has uppercase letters would silently lose its links on the site. Tested in Task 2 (`test_links_found_for_mixed_case_publication_doi`).
4. **JSON fields and flags round-trip.** `authors`, `identifiers`, `manual_edits`, `edit_history`, `is_ignored` and `ignore_reason` must survive the copy. Tested in Task 1 (`test_copy_preserves_json_fields_and_flags`).
5. **Backup pruning touches only backups.** Pruning must never delete objects outside the backup prefix, or newer backups than the newest 26. Tested in Task 4 (`test_prune_only_touches_backup_prefix`).

---

### Task 1: Row counting and database copy (`academic/db_transfer.py`)

**Files:**
- Create: `academic/db_transfer.py`
- Modify: `academicdb_web/settings/test.py` (add a `source` in-memory SQLite alias)
- Test: `tests/unit/test_db_transfer.py`

**Interfaces:**
- Produces:
  - `EXCLUDED_MODELS: frozenset[str]`, which is exactly `{'contenttypes.contenttype', 'auth.permission', 'sessions.session'}`. `migrate` recreates the first two; sessions aren't worth moving.
  - `MIGRATE_SEEDED_MODELS: frozenset[str]`, which is exactly `{'sites.site'}`. `migrate` and `flush` create the default `example.com` site (pk 1), so this model is ignored by the emptiness check. `loaddata` overwrites that row by pk, so its counts still match.
  - `class TargetNotEmptyError(Exception)`
  - `model_counts(using: str) -> dict[str, int]`: keys are lowercase `app_label.modelname` for every concrete, managed model not in `EXCLUDED_MODELS`.
  - `count_mismatches(source: dict[str, int], target: dict[str, int]) -> list[tuple[str, int, int]]`: `(label, source_count, target_count)` for every label whose counts differ, with missing labels treated as 0. Sorted by label.
  - `dump_fixture(using: str, path: Path) -> None`: `dumpdata` with `natural_foreign=True`, `natural_primary=True`, excluding `EXCLUDED_MODELS`. Writes gzip if `path` ends in `.gz`.
  - `load_fixture(path: Path, using: str) -> None`: raises `TargetNotEmptyError` (naming the non-empty models) if any count in `model_counts(using)`, outside `MIGRATE_SEEDED_MODELS`, is above 0. Otherwise runs `loaddata` inside `transaction.atomic(using=using)`, then resets sequences when the target vendor is `postgresql`. To reset, run the SQL from `connection.ops.sequence_reset_sql(no_style(), models)`.
  - `copy_all_data(source: str, target: str, tmp_dir: Path) -> list[tuple[str, int, int]]`: `dump_fixture` → `load_fixture` → returns `count_mismatches(model_counts(source), model_counts(target))`.

- [ ] **Step 1: Add the `source` alias to the test settings**

In `academicdb_web/settings/test.py`, add `'source': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}` to `DATABASES`.

- [ ] **Step 2: Write the failing tests**

All tests use `@pytest.mark.django_db(databases=['default', 'source'], transaction=True)`. A fixture `source_data` creates, with `.using('source')`:
- an `AcademicUser` with `orcid_id='0000-0001-6755-0259'`;
- two `Publication`s, one of them with `authors=[{'name': 'Poldrack, R. A.'}]`, `identifiers={'pmcid': 'PMC123', 'pmid': '456'}`, `manual_edits={'title': True}`, `edit_history=[{'field': 'title'}]`, `is_ignored=True` and `ignore_reason='Published as journal article'`;
- one `Link` (`type='Code'`, `doi` equal to that publication's DOI, `url='https://github.com/x/y'`).

```python
def test_model_counts_reports_source_rows(source_data):
    counts = model_counts('source')
    assert counts['academic.publication'] == 2
    assert counts['academic.link'] == 1
    assert 'contenttypes.contenttype' not in counts

def test_count_mismatches_lists_only_differences():
    assert count_mismatches({'a.x': 2, 'a.y': 1}, {'a.x': 2}) == [('a.y', 1, 0)]

def test_copy_all_data_produces_matching_counts(source_data, tmp_path):
    assert copy_all_data('source', 'default', tmp_path) == []
    assert Publication.objects.using('default').count() == 2

def test_copy_preserves_json_fields_and_flags(source_data, tmp_path):
    copy_all_data('source', 'default', tmp_path)
    pub = Publication.objects.using('default').get(is_ignored=True)
    assert pub.authors == [{'name': 'Poldrack, R. A.'}]
    assert pub.identifiers == {'pmcid': 'PMC123', 'pmid': '456'}
    assert pub.manual_edits == {'title': True}
    assert pub.edit_history == [{'field': 'title'}]
    assert pub.ignore_reason == 'Published as journal article'

def test_copy_refuses_nonempty_target_and_leaves_it_unchanged(source_data, tmp_path):
    # create one AcademicUser in 'default' first
    with pytest.raises(TargetNotEmptyError, match='academic.academicuser'):
        copy_all_data('source', 'default', tmp_path)
    assert Publication.objects.using('default').count() == 0
    assert AcademicUser.objects.using('default').count() == 1

def test_new_rows_after_copy_get_fresh_ids(source_data, tmp_path):
    copy_all_data('source', 'default', tmp_path)
    max_id = max(Publication.objects.using('default').values_list('id', flat=True))
    new = Publication.objects.using('default').create(owner=..., doi='10.1/new', title='t', year=2026)
    assert new.id > max_id

def test_dump_fixture_gzip_roundtrip(source_data, tmp_path):
    path = tmp_path / 'b.json.gz'
    dump_fixture('source', path)
    assert gzip.open(path).read(1) == b'['
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_db_transfer.py -v`
Expected: collection error, `ModuleNotFoundError: academic.db_transfer`.

- [ ] **Step 4: Commit the tests**

```bash
git add academicdb_web/settings/test.py tests/unit/test_db_transfer.py
git commit -m "test: add failing tests for database transfer"
```

- [ ] **Step 5: Implement `academic/db_transfer.py`** with the interfaces above. Use `django.apps.apps.get_models()` and filter on `_meta.managed and not _meta.proxy`. Use `call_command('dumpdata', …, database=using, output=str(path))` and `call_command('loaddata', str(path), database=using)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_db_transfer.py -v`
Expected: 7 passed. Then run the full suite: the only failures should be the 2 existing ones (`test_homepage_accessible`, `test_comprehensive_sync_with_data_directory`).

- [ ] **Step 7: Commit**

```bash
git add academic/db_transfer.py
git commit -m "feat: add row counting and fixture-based database copy"
```

---

### Task 2: Migration command and link import

**Files:**
- Create: `academic/management/commands/copy_database.py`
- Create: `academic/link_import.py`
- Create: `academic/management/commands/import_links.py`
- Modify: `academic/models.py:2782-2787` (`Link.get_links_for_publication` → `doi__iexact`)
- Modify: `academic/views.py:2181-2194` (`LinkUploadView` uses `normalize_doi`)
- Modify: `academic/data_ingestion.py:89-145` (`ingest_links` reads the `type,DOI,url` format through `read_links_csv`)
- Test: `tests/unit/test_copy_database_command.py`, `tests/unit/test_link_import.py`

**Interfaces:**
- Consumes: `model_counts`, `copy_all_data`, `TargetNotEmptyError` from Task 1.
- Produces:
  - Command `copy_database`, with `--source-sqlite PATH` or `--source-alias ALIAS` (exactly one is required). It copies the source into `default`. It prints a table of `label  source  target` for every model, then either `All counts match.` or raises `CommandError('Count mismatch: …')`. It raises `CommandError` if the source file doesn't exist, or if the source path equals the `default` database's `NAME`. `--source-sqlite` registers alias `source` in `django.db.connections.databases` with SQLite settings (copy the full default-filled dict from `connections.databases['default']` and override `ENGINE`/`NAME`).
  - `academic/link_import.py`:
    - `@dataclass(frozen=True) class LinkRecord: doi: str; type: str; url: str; title: str = ''`
    - `normalize_doi(value: str) -> str`: strips whitespace and any `https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/` or `doi:` prefix, then lowercases.
    - `normalize_url(value: str) -> str`: strips whitespace and one trailing `/`.
    - `read_links_csv(path: Path) -> list[LinkRecord]`: needs the columns `type,DOI,url` and raises `ValueError` naming any missing column. Skips rows with an empty field.
    - `read_links_from_publications_json(path: Path) -> list[LinkRecord]`: reads `publications[].links.resources[]` with `{type, url, title}`, taking the DOI from the publication's `doi`.
    - `@dataclass class LinkImportResult: created: int; existing: int; unmatched_dois: list[str]`
    - `import_link_records(user, records: list[LinkRecord]) -> LinkImportResult`: dedupes on `(doi, type, url)` after normalization. Skips and reports records whose DOI matches no publication of `user` (case-insensitive). Sets `source='csv_import'`. Is idempotent.
  - Command `import_links --orcid-id ID [--csv PATH] [--publications-json PATH]` (at least one source required). Prints the created, existing and unmatched counts, and lists the unmatched DOIs.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_copy_database_command.py` uses `django_db(databases=['default','source'], transaction=True)` and a source fixture like Task 1's.

```python
def test_copy_database_reports_match(source_data):
    out = StringIO()
    call_command('copy_database', source_alias='source', stdout=out)
    assert 'All counts match.' in out.getvalue()
    assert 'academic.publication' in out.getvalue()

def test_copy_database_requires_exactly_one_source():
    with pytest.raises(CommandError):
        call_command('copy_database')

def test_copy_database_missing_sqlite_file(tmp_path):
    with pytest.raises(CommandError, match='does not exist'):
        call_command('copy_database', source_sqlite=str(tmp_path / 'nope.sqlite3'))

def test_copy_database_nonempty_target_is_command_error(source_data):
    # create one AcademicUser in 'default' first
    with pytest.raises(CommandError, match='not empty'):
        call_command('copy_database', source_alias='source')
```

`tests/unit/test_link_import.py` uses `django_db`, a `user` fixture, and publications with DOIs `10.1038/S41562-024-01942-4` (mixed case) and `10.1/abc`.

```python
@pytest.mark.parametrize('raw', ['https://doi.org/10.1/ABC', 'doi:10.1/abc', ' 10.1/abc ', 'http://dx.doi.org/10.1/abc'])
def test_normalize_doi(raw):
    assert normalize_doi(raw) == '10.1/abc'

def test_read_links_csv_example_format(tmp_path):
    # file with header 'type,DOI,url' and 2 rows (one with empty url)
    assert read_links_csv(path) == [LinkRecord('10.1/abc', 'Code', 'https://github.com/x/y')]

def test_read_links_csv_missing_column(tmp_path):
    with pytest.raises(ValueError, match='DOI'):
        read_links_csv(path_with_header_type_url)

def test_read_links_from_publications_json(tmp_path):
    # {"publications": [{"doi": "10.1/abc", "links": {"resources": [{"type": "OSF", "url": "https://osf.io/a6t8k/", "title": "OSF"}]}}]}
    assert read_links_from_publications_json(path) == [LinkRecord('10.1/abc', 'OSF', 'https://osf.io/a6t8k', 'OSF')]

def test_import_dedupes_across_sources_and_is_idempotent(user, pubs):
    recs = [LinkRecord('10.1/abc', 'Code', 'https://github.com/x/y'),
            LinkRecord('10.1/ABC', 'Code', 'https://github.com/x/y/')]
    assert import_link_records(user, recs).created == 1
    assert import_link_records(user, recs).existing == 1   # second run creates nothing
    assert Link.objects.count() == 1

def test_import_reports_unmatched_dois(user, pubs):
    result = import_link_records(user, [LinkRecord('10.9/none', 'Data', 'https://openneuro.org/datasets/ds000001')])
    assert result.unmatched_dois == ['10.9/none'] and Link.objects.count() == 0

def test_links_found_for_mixed_case_publication_doi(user, pubs):
    import_link_records(user, [LinkRecord('10.1038/s41562-024-01942-4', 'Code', 'https://zenodo.org/records/5748130')])
    pub = Publication.objects.get(doi='10.1038/S41562-024-01942-4')
    assert Link.get_links_for_publication(pub).count() == 1

def test_ingest_links_reads_example_csv_format(user, pubs, tmp_path):
    # data dir containing links.csv in 'type,DOI,url' format
    assert ingest_links(user, str(tmp_path)) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_copy_database_command.py tests/unit/test_link_import.py -v`
Expected: FAIL. Command `copy_database` is unknown, `academic.link_import` doesn't exist, and the mixed-case and `ingest_links` tests fail against the current code.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/test_copy_database_command.py tests/unit/test_link_import.py
git commit -m "test: add failing tests for copy_database and link import"
```

- [ ] **Step 4: Implement** `copy_database`, `academic/link_import.py` and `import_links`. Change `get_links_for_publication` to `doi__iexact`. Make `LinkUploadView` call `normalize_doi`, and make `ingest_links` call `read_links_csv` + `import_link_records`, keeping the return value as the created count.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_copy_database_command.py tests/unit/test_link_import.py tests/unit/test_links.py -v`
Expected: all pass, including the existing `test_links.py`. Run the full suite: only the 2 existing failures remain.

- [ ] **Step 6: Commit**

```bash
git add academic/management/commands/copy_database.py academic/link_import.py academic/management/commands/import_links.py academic/models.py academic/views.py academic/data_ingestion.py
git commit -m "feat: add copy_database and import_links commands; case-insensitive link lookup"
```

---

### Task 3: Local backup and restore commands

**Files:**
- Create: `academic/management/commands/backup_database.py`
- Create: `academic/management/commands/restore_database.py`
- Modify: `Makefile` (targets `backup-local`, `restore-local`, `backup-check`)
- Test: `tests/unit/test_backup_commands.py`

**Interfaces:**
- Consumes: `dump_fixture`, `load_fixture`, `model_counts`, `count_mismatches` and `TargetNotEmptyError` from Task 1.
- Produces:
  - `backup_database --output-dir DIR [--upload]` (`--upload` is wired up in Task 4). It writes `DIR/academicdb_YYYYMMDD_HHMMSS.json.gz` and a sidecar `DIR/academicdb_YYYYMMDD_HHMMSS.counts.json`, containing `model_counts('default')`, using UTC time. It prints the fixture path on the last line.
  - `restore_database PATH`: loads into `default` through `load_fixture`. If a sidecar `.counts.json` exists, it compares counts and raises `CommandError('Count mismatch: …')` on any difference. A non-empty target raises `CommandError` containing `not empty`.
  - Make targets:
    - `backup-local`: runs `USE_NEON=true NEON_UNPOOLED=true uv run python manage.py backup_database --output-dir $(LOCAL_BACKUP_DIR)` with `LOCAL_BACKUP_DIR ?= backups`. `backups/` is already gitignored and lives inside the Dropbox-synced repo.
    - `restore-local FILE=…`: restores into whatever `.env` selects.
    - `backup-check FILE=…`: restores into a throwaway SQLite at `$(LOCAL_BACKUP_DIR)/restore_check.sqlite3`. It deletes that file first, then runs `migrate` and `restore_database` with `DATABASE_URL=sqlite:///…` and `USE_NEON` unset.

- [ ] **Step 1: Write the failing tests** (`django_db(transaction=True)`; freeze time with `freezegun` at `2026-10-18 12:00:00`)

```python
def test_backup_writes_fixture_and_counts(user_with_pubs, tmp_path):
    out = StringIO()
    call_command('backup_database', output_dir=str(tmp_path), stdout=out)
    fixture = tmp_path / 'academicdb_20261018_120000.json.gz'
    counts = json.loads((tmp_path / 'academicdb_20261018_120000.counts.json').read_text())
    assert fixture.exists() and counts['academic.publication'] == 2
    assert out.getvalue().strip().splitlines()[-1] == str(fixture)

def test_restore_roundtrip_into_empty_db(user_with_pubs, tmp_path):
    call_command('backup_database', output_dir=str(tmp_path))
    # flush 'default' (call_command('flush', interactive=False)), then:
    call_command('restore_database', str(tmp_path / 'academicdb_20261018_120000.json.gz'))
    assert Publication.objects.count() == 2

def test_restore_refuses_nonempty_db(user_with_pubs, tmp_path):
    call_command('backup_database', output_dir=str(tmp_path))
    with pytest.raises(CommandError, match='not empty'):
        call_command('restore_database', str(tmp_path / 'academicdb_20261018_120000.json.gz'))

def test_restore_detects_count_mismatch(user_with_pubs, tmp_path):
    # back up, edit the counts.json to say publication: 3, flush, restore
    with pytest.raises(CommandError, match='Count mismatch'):
        call_command('restore_database', str(fixture))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_backup_commands.py -v`
Expected: FAIL with `Unknown command: 'backup_database'`.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/unit/test_backup_commands.py
git commit -m "test: add failing tests for backup/restore commands"
```

- [ ] **Step 4: Implement** both commands and the three Makefile targets.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_backup_commands.py -v`
Expected: 4 passed. Run the full suite: only the 2 existing failures remain.

- [ ] **Step 6: Commit**

```bash
git add academic/management/commands/backup_database.py academic/management/commands/restore_database.py Makefile
git commit -m "feat: add portable JSON backup/restore commands and make targets"
```

---

### Task 4: Upload backups to Neon object storage

**Files:**
- Create: `academic/remote_backup.py`
- Modify: `academic/management/commands/backup_database.py` (`--upload`)
- Modify: `pyproject.toml` / `uv.lock` via `uv add boto3`
- Test: `tests/unit/test_remote_backup.py`

**Interfaces:**
- Consumes: the files written by `backup_database` (Task 3).
- Produces:
  - `BACKUP_PREFIX = 'academicdb-backups/'`, `KEEP_BACKUPS = 26` (about six months of weekly backups; Claude's call).
  - `s3_client_from_env(env: Mapping[str, str])` returns a boto3 S3 client built from `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`. It raises `ValueError` naming the first missing variable.
  - `upload_backup(client, bucket: str, fixture: Path) -> list[str]` uploads the fixture and its sidecar `.counts.json` under `BACKUP_PREFIX`, returning the keys.
  - `prune_backups(client, bucket: str, keep: int = KEEP_BACKUPS) -> list[str]` lists keys under `BACKUP_PREFIX` matching `academicdb_\d{8}_\d{6}\.(json\.gz|counts\.json)`. It groups them by timestamp, deletes all but the newest `keep` timestamps, and returns the deleted keys.
  - `backup_database --upload` reads `BACKUP_BUCKET` from the environment (a `CommandError` if it's unset), then uploads and prunes after writing locally, and prints each uploaded key.

- [ ] **Step 1: Add the dependency**

Run: `uv add boto3`
Expected: `pyproject.toml` lists `boto3`, and `uv.lock` is updated.

- [ ] **Step 2: Write the failing tests** (use `botocore.stub.Stubber` on `boto3.client('s3', region_name='us-east-1', aws_access_key_id='x', aws_secret_access_key='x')`; no network)

```python
def test_s3_client_from_env_requires_endpoint():
    with pytest.raises(ValueError, match='AWS_ENDPOINT_URL_S3'):
        s3_client_from_env({'AWS_ACCESS_KEY_ID': 'a', 'AWS_SECRET_ACCESS_KEY': 'b', 'AWS_REGION': 'us-east-2'})

def test_upload_backup_puts_fixture_and_counts(stubbed_client, tmp_path):
    # expect put_object for academicdb-backups/academicdb_20261018_120000.json.gz and .counts.json
    assert upload_backup(client, 'bkt', fixture) == [
        'academicdb-backups/academicdb_20261018_120000.json.gz',
        'academicdb-backups/academicdb_20261018_120000.counts.json']

def test_prune_keeps_newest_timestamps(stubbed_client):
    # list_objects_v2 returns 28 timestamps x 2 files; expect delete_objects for the oldest 2 timestamps (4 keys)
    assert len(prune_backups(client, 'bkt', keep=26)) == 4

def test_prune_only_touches_backup_prefix(stubbed_client):
    # list returns academicdb-backups/notes.txt and 3 valid timestamps; keep=2
    deleted = prune_backups(client, 'bkt', keep=2)
    assert 'academicdb-backups/notes.txt' not in deleted and len(deleted) == 2

def test_backup_upload_requires_bucket(monkeypatch, tmp_path):
    monkeypatch.delenv('BACKUP_BUCKET', raising=False)
    with pytest.raises(CommandError, match='BACKUP_BUCKET'):
        call_command('backup_database', output_dir=str(tmp_path), upload=True)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_remote_backup.py -v`
Expected: FAIL, `ModuleNotFoundError: academic.remote_backup`.

- [ ] **Step 4: Commit the tests**

```bash
git add pyproject.toml uv.lock tests/unit/test_remote_backup.py
git commit -m "test: add failing tests for remote backup upload and pruning"
```

- [ ] **Step 5: Implement** `academic/remote_backup.py` and the `--upload` flag. Pass `endpoint_url=env['AWS_ENDPOINT_URL_S3']` to `boto3.client('s3', …)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit/test_remote_backup.py tests/unit/test_backup_commands.py -v`
Expected: all pass. Run the full suite: only the 2 existing failures remain.

- [ ] **Step 7: Commit**

```bash
git add academic/remote_backup.py academic/management/commands/backup_database.py
git commit -m "feat: upload backups to Neon object storage with pruning"
```

---

### Task 5: Run the migration and cut over (runbook, owner present)

Each step's output is shown to the owner before the next step. Stop at any failure.

**Files:**
- Modify: `Makefile`. Remove the `DATABASE_URL=sqlite:////${DBDIR}/db.sqlite3` prefix from `export`, and add a `migrate-data` target running `USE_NEON=true NEON_UNPOOLED=true uv run python manage.py copy_database --source-sqlite academicdb_web/db.sqlite3`.
- Modify: `README.md` (a short "Database" section: Neon default, `make backup-local`, `make backup-check`, `make restore-local`, and where remote backups live).

- [ ] **Step 1: Owner sets `BACKUP_BUCKET`** in `.env`, naming the bucket created in Neon object storage. Neon is still opt-in at this point.

- [ ] **Step 2: Take a safety copy of the source file**

Run: `cp academicdb_web/db.sqlite3 backups/pre_neon_db.sqlite3`
Expected: the file exists, 13M.

- [ ] **Step 3: Copy the data**

Run: `make migrate-data`
Expected: the counts table, ending in `All counts match.`, with `academic.publication` 457 and `socialaccount.socialapp` 1.

- [ ] **Step 4: Check sequences on Neon**

Run a `manage.py shell -c` with `USE_NEON=true`. Inside `transaction.atomic()`, create one `Publication` for the owner, print whether its id is greater than the previous max id, then roll back.
Expected: `True`, and the publication count afterwards is still 457.

- [ ] **Step 5: Import links**

Run: `USE_NEON=true uv run python manage.py import_links --orcid-id 0000-0001-6755-0259 --csv data/examples/links.csv --publications-json <path to poldracklab.github.io checkout>/publications.json`
Expected: about 50 links created (recon counted 50 unique resources across 41 papers, after merging Zenodo versions, which this import does not do). Show the owner the unmatched DOIs and the created count.

- [ ] **Step 6: First backup, local and remote**

Run: `make backup-local`, then the same command with `--upload`.
Expected: a fixture path and two uploaded keys under `academicdb-backups/`.

- [ ] **Step 7: Prove the restore works**

Run: `make backup-check FILE=<fixture from step 6>`
Expected: `restore_database` completes without a count mismatch.

- [ ] **Step 8: App check on Neon**

Run: `make run-neon`, and have the owner log in through ORCID, open the dashboard, the publications list, the links list and the CV download.
Expected: the same data as on SQLite.

- [ ] **Step 9: Cut over.** The owner adds `USE_NEON=true` to `.env`.

Verify: `uv run python manage.py shell -c "from django.db import connection; print(connection.settings_dict['HOST'])"` prints the `-pooler` Neon host.

- [ ] **Step 10: Commit** the Makefile and README changes

```bash
git add Makefile README.md
git commit -m "chore: make Neon the default database; document backups"
```
