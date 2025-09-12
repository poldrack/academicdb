# Tasks: Academic Database Web Interface & Modernization

**Input**: Design documents from `/specs/001-i-would-like/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/api-schema.yml, quickstart.md

## Execution Flow (main)
```
1. Load plan.md from feature directory
   ✓ Extracted: Django + PostgreSQL + ORCID, web app structure
2. Load optional design documents:
   ✓ data-model.md: 9 entities (AcademicUser, Publication, etc.)
   ✓ contracts/: API schema with 15+ endpoints
   ✓ quickstart.md: 6 integration test scenarios
3. Generate tasks by category:
   ✓ Setup: Django project, PostgreSQL, ORCID OAuth
   ✓ Tests: Contract tests, integration tests (TDD)
   ✓ Core: Models, forms, views, serializers
   ✓ Integration: Authentication, API, sync jobs
   ✓ Polish: Migration, documentation, performance
4. Apply task rules:
   ✓ Different files = mark [P] for parallel
   ✓ Same file = sequential (no [P])
   ✓ Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness
9. Return: SUCCESS (59 tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Web app**: Django project structure at repository root
- **Tests**: `tests/` directory with contract/, integration/, unit/ subdirs
- **Core**: `academicdb_web/` (Django project), `academicdb/` (main app)

## Phase 3.1: Setup & Environment
- [ ] T001 Create Django project structure and configure PostgreSQL connection
- [ ] T002 Initialize Django project with required dependencies (Django 4.2+, psycopg2-binary, django-allauth)
- [ ] T003 [P] Configure linting tools (black, flake8, isort) in pyproject.toml
- [ ] T004 [P] Set up pytest configuration with Django settings in pytest.ini
- [ ] T005 Configure ORCID OAuth settings and django-allauth in academicdb_web/settings.py

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

### Contract Tests [P] - All can run in parallel
- [ ] T006 [P] Contract test POST /auth/login/ in tests/contract/test_auth_login.py
- [ ] T007 [P] Contract test GET /auth/callback/ in tests/contract/test_auth_callback.py
- [ ] T008 [P] Contract test GET /publications/ in tests/contract/test_publications_list.py
- [ ] T009 [P] Contract test POST /publications/ in tests/contract/test_publications_create.py
- [ ] T010 [P] Contract test GET /publications/{id}/ in tests/contract/test_publications_detail.py
- [ ] T011 [P] Contract test PUT /publications/{id}/ in tests/contract/test_publications_update.py
- [ ] T012 [P] Contract test DELETE /publications/{id}/ in tests/contract/test_publications_delete.py
- [ ] T013 [P] Contract test POST /publications/sync/ in tests/contract/test_publications_sync.py
- [ ] T014 [P] Contract test GET /coauthors/ in tests/contract/test_coauthors_list.py
- [ ] T015 [P] Contract test PUT /coauthors/{id}/ in tests/contract/test_coauthors_update.py
- [ ] T016 [P] Contract test POST /cv/export/ in tests/contract/test_cv_export.py

### Integration Tests [P] - Based on quickstart scenarios
- [ ] T017 [P] Integration test researcher registration flow in tests/integration/test_user_registration.py
- [ ] T018 [P] Integration test publication import and edit preservation in tests/integration/test_publication_sync.py
- [ ] T019 [P] Integration test collaboration network analysis in tests/integration/test_collaboration_analysis.py
- [ ] T020 [P] Integration test multi-collection CRUD operations in tests/integration/test_collection_management.py
- [ ] T021 [P] Integration test CV generation and export in tests/integration/test_cv_generation.py
- [ ] T022 [P] Integration test data isolation and security in tests/integration/test_data_security.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)

### Django Models [P] - One file each, can run in parallel
- [ ] T023 [P] AcademicUser model with ORCID integration in academicdb/models/user.py
- [ ] T024 [P] Publication model with JSONB fields in academicdb/models/publication.py
- [ ] T025 [P] Coauthor model with affiliation tracking in academicdb/models/coauthor.py
- [ ] T026 [P] Funding model in academicdb/models/funding.py
- [ ] T027 [P] Talk model in academicdb/models/talk.py
- [ ] T028 [P] Education model in academicdb/models/education.py
- [ ] T029 [P] Employment model in academicdb/models/employment.py
- [ ] T030 [P] Supporting models (Distinction, Membership, Service) in academicdb/models/supporting.py

### Django Forms [P] - After models exist
- [ ] T031 [P] Publication forms with validation in academicdb/forms/publication.py
- [ ] T032 [P] User profile forms in academicdb/forms/user.py
- [ ] T033 [P] Coauthor forms in academicdb/forms/coauthor.py

### DRF Serializers [P] - After models exist
- [ ] T034 [P] Publication serializers in academicdb/serializers/publication.py
- [ ] T035 [P] User serializers in academicdb/serializers/user.py
- [ ] T036 [P] Coauthor serializers in academicdb/serializers/coauthor.py

### API Views - Sequential due to URL dependencies
- [ ] T037 Authentication views (login, callback) in academicdb/views/auth.py
- [ ] T038 Publication ViewSet (CRUD operations) in academicdb/views/publications.py
- [ ] T039 Coauthor views in academicdb/views/coauthors.py
- [ ] T040 CV export views in academicdb/views/cv.py
- [ ] T041 URL configuration in academicdb/urls.py

### Web Interface Views [P] - After API views
- [ ] T042 [P] Dashboard view in academicdb/views/dashboard.py
- [ ] T043 [P] Publication list/detail views in academicdb/views/web_publications.py
- [ ] T044 [P] User profile views in academicdb/views/profile.py

## Phase 3.4: Integration & Middleware

### Authentication & Permissions
- [ ] T045 ORCID OAuth integration with django-allauth in academicdb/auth.py
- [ ] T046 User-scoped permissions and data isolation in academicdb/permissions.py
- [ ] T047 Custom user manager for AcademicUser in academicdb/models/user.py

### External API Integration
- [ ] T048 [P] External API sync service (preserve manual edits) in academicdb/services/sync_service.py
- [ ] T049 [P] Publication import utilities in academicdb/services/import_service.py
- [ ] T050 [P] Coauthor analysis service in academicdb/services/collaboration_service.py

### Background Tasks & Management
- [ ] T051 Django management command for MongoDB migration in academicdb/management/commands/migrate_from_mongo.py
- [ ] T052 Django management command for external API sync in academicdb/management/commands/sync_external_apis.py
- [ ] T053 Django management command for NSF collaborator export in academicdb/management/commands/export_nsf_collaborators.py

## Phase 3.5: Polish & Deployment

### Database & Migration
- [ ] T054 Create Django migrations for all models in migrations/
- [ ] T055 [P] Database indexes and performance optimization
- [ ] T056 [P] MongoDB to PostgreSQL migration scripts in scripts/migration/

### Templates & Static Files [P]
- [ ] T057 [P] Django templates for web interface in academicdb/templates/
- [ ] T058 [P] CSS/JS assets with Bootstrap 5 in academicdb/static/

### Final Integration & Testing
- [ ] T059 End-to-end testing with real ORCID sandbox and performance validation

## Dependencies

### Critical Path
```
Setup (T001-T005) → Tests (T006-T022) → Models (T023-T030) → Serializers/Forms → Views → Integration
```

### Specific Dependencies
- **Models first**: T023-T030 must complete before T031-T036 (forms/serializers)
- **Views depend on serializers**: T037-T044 blocked by T034-T036
- **Integration depends on views**: T045-T053 blocked by T037-T044
- **Migration scripts need models**: T051, T054, T056 blocked by T023-T030

### Parallel Opportunities
```
# All contract tests can run simultaneously (T006-T016)
Task: "Contract test POST /auth/login/ in tests/contract/test_auth_login.py"
Task: "Contract test GET /publications/ in tests/contract/test_publications_list.py" 
Task: "Contract test POST /publications/ in tests/contract/test_publications_create.py"
[...all contract tests...]

# All integration tests can run simultaneously (T017-T022)
Task: "Integration test researcher registration in tests/integration/test_user_registration.py"
Task: "Integration test publication sync in tests/integration/test_publication_sync.py"
[...all integration tests...]

# All model creation can run simultaneously (T023-T030)
Task: "AcademicUser model with ORCID integration in academicdb/models/user.py"
Task: "Publication model with JSONB fields in academicdb/models/publication.py"
[...all model files...]
```

## Task Generation Rules Applied

1. **From Contracts (api-schema.yml)**:
   - 15 endpoints → 11 contract test tasks [P] (T006-T016)
   - Auth, Publications, Coauthors, CV endpoints → 4 view implementation tasks (T037-T040)

2. **From Data Model**:
   - 9 entities → 8 model creation tasks [P] (T023-T030) 
   - Relationships → 3 service layer tasks [P] (T048-T050)

3. **From Quickstart Scenarios**:
   - 6 scenarios → 6 integration test tasks [P] (T017-T022)
   - End-to-end validation → 1 comprehensive test task (T059)

4. **From Technical Context**:
   - Django + PostgreSQL + ORCID → 5 setup tasks (T001-T005)
   - MongoDB migration → 3 migration tasks (T051, T054, T056)

## Validation Checklist
*GATE: Checked before task execution*

- [x] All 11 API contracts have corresponding test tasks (T006-T016)
- [x] All 9 entities have model creation tasks (T023-T030)  
- [x] All 22 tests come before implementation (T006-T022 before T023+)
- [x] All [P] tasks operate on different files
- [x] Each task specifies exact file path
- [x] TDD enforced: tests must fail before implementation
- [x] Dependencies clearly mapped in critical path
- [x] Integration scenarios cover all user flows from quickstart.md

**Total Tasks**: 59
**Parallel Tasks**: 34 (marked with [P])
**Sequential Tasks**: 25 (due to file or dependency conflicts)

---

*Tasks ready for execution. Follow TDD: ensure all tests fail before implementing.*