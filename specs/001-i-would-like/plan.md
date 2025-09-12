# Implementation Plan: Academic Database Web Interface & Modernization

**Branch**: `001-i-would-like` | **Date**: 2025-09-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-i-would-like/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   ✓ Loaded feature specification successfully
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   ✓ Detected Django web application, updated to PostgreSQL backend
   ✓ Set Structure Decision based on project type
3. Evaluate Constitution Check section below
   ✓ No major violations identified for this plan scope
   ✓ Update Progress Tracking: Initial Constitution Check
4. Execute Phase 0 → research.md
   ✓ Research completed: PostgreSQL, ORCID auth, migration strategy
5. Execute Phase 1 → contracts, data-model.md, quickstart.md, CLAUDE.md
   ✓ All Phase 1 deliverables created successfully
6. Re-evaluate Constitution Check section
   ✓ Design maintains constitutional compliance
   ✓ Update Progress Tracking: Post-Design Constitution Check
7. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
   ✓ Task generation strategy documented below
8. STOP - Ready for /tasks command
   ✓ Planning phase complete
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Migrate existing Flask-based academic database web interface to Django, providing comprehensive CRUD operations for all database collections (publications, collaborators, funding, etc.) while preserving manual edits during external data source updates. The system will use PostgreSQL with JSONB fields as the backend, with ORCID authentication for academic researchers.

## Technical Context
**Language/Version**: Python 3.12+ (matches existing pyproject.toml)  
**Primary Dependencies**: Django, psycopg2-binary, django-extensions  
**Storage**: PostgreSQL with JSONB fields (migrating from MongoDB)  
**Testing**: pytest + Django TestCase  
**Target Platform**: Web application (Django server)
**Project Type**: web - determines source structure  
**Performance Goals**: Handle concurrent access by multiple researchers, <2s page load, efficient full-text search  
**Constraints**: Minimal additional libraries, data migration from MongoDB, maintain backward compatibility with CLI tools  
**Scale/Scope**: Small to medium academic departments (10-50 researchers), 12 collection types migrating to relational+JSONB hybrid

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Simplicity**:
- Projects: 2 (django-web, cli-tools) (acceptable for web app)
- Using framework directly? YES (Django without wrapper classes)
- Single data model? YES (MongoDB documents, no DTOs)
- Avoiding patterns? YES (Django ORM + MongoDB, no Repository pattern)

**Architecture**:
- EVERY feature as library? N/A (Django web app follows MVC pattern)
- Libraries listed: academicdb-web (Django app), academicdb-core (existing CLI tools)
- CLI per library: manage.py (Django standard), existing academicdb CLI tools
- Library docs: llms.txt format planned? YES (for Django app structure)

**Testing (NON-NEGOTIABLE)**:
- RED-GREEN-Refactor cycle enforced? YES (Django TestCase + pytest)
- Git commits show tests before implementation? YES (will enforce)
- Order: Contract→Integration→E2E→Unit strictly followed? YES
- Real dependencies used? YES (test with actual MongoDB instance)
- Integration tests for: new Django views, API endpoints, data integrity
- FORBIDDEN: Implementation before test, skipping RED phase

**Observability**:
- Structured logging included? YES (Django logging + Python logging)
- Frontend logs → backend? YES (Django handles this)
- Error context sufficient? YES (Django error handling + custom logging)

**Versioning**:
- Version number assigned? 1.0.0 (Django web interface version)
- BUILD increments on every change? YES
- Breaking changes handled? YES (migration scripts, backward compatibility)

## Project Structure

### Documentation (this feature)
```
specs/001-i-would-like/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 2: Web application (Django + MongoDB)
academicdb_web/              # Django project
├── settings.py
├── urls.py
├── wsgi.py
└── asgi.py

academicdb/                  # Django app within project
├── models.py               # MongoDB document models via djongo
├── views.py                # Django views for CRUD operations
├── forms.py                # Django forms for data input
├── urls.py                 # URL routing
├── templates/              # Django HTML templates
├── static/                 # CSS, JS, images
└── management/             # Django management commands
    └── commands/
        ├── sync_external.py    # Preserve edits during sync
        └── backup_data.py      # Data backup before updates

src/academicdb/             # Existing CLI tools (preserve)
└── [existing structure]

tests/
├── test_models.py          # Django model tests
├── test_views.py           # Django view tests
├── test_forms.py           # Form validation tests
├── test_sync.py            # Data sync integrity tests
└── integration/            # End-to-end web interface tests
```

**Structure Decision**: Option 2 - Web application (Django backend serves HTML + handles API)

## Phase 0: Outline & Research

### Research Tasks Identified
1. **Django + MongoDB Integration**: Research djongo vs mongoengine vs direct pymongo
2. **Data Migration Strategy**: How to preserve existing MongoDB schema in Django
3. **Authentication Method**: Django built-in vs ORCID OAuth vs institutional SSO
4. **Edit Tracking**: How to implement field-level edit history in Django + MongoDB
5. **Concurrent Access**: Django session handling for multiple researchers
6. **External API Sync**: Django management commands vs Celery for background tasks

### Research Execution
*Delegating research tasks...*

**Output**: research.md with all technical decisions and rationale

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

**Design Tasks**:
1. **Extract entities from feature spec** → `data-model.md`
2. **Generate Django URL patterns and view contracts** → `/contracts/`
3. **Generate failing Django tests** for all views and models
4. **Extract integration scenarios** → `quickstart.md`
5. **Update CLAUDE.md** with Django + MongoDB context

**Output**: data-model.md, /contracts/*, failing Django tests, quickstart.md, CLAUDE.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `/templates/tasks-template.md` as base
- Generate tasks from Django app structure
- Each model → model creation + tests [P]
- Each view → view implementation + tests [P]
- Each form → form creation + validation tests [P]
- Integration tests for complete user workflows
- External sync preservation logic
- Database migration and setup tasks

**Ordering Strategy**:
- TDD order: Tests before implementation
- Django dependency order: Models → Forms → Views → Templates → URLs
- Mark [P] for parallel execution (independent Django apps/components)

**Estimated Output**: 20-25 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (Django development following TDD)  
**Phase 5**: Validation (Django tests, manual testing, performance validation)

## Complexity Tracking
*No constitutional violations requiring justification identified*

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)  
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*