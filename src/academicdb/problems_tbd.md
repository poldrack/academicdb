## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.  

[x] ~~I would like to add a feature that allows the user to enter a list of DOIs that should be skipped during the ingestion of publications.  These could be specified via a text field within the user profile.~~ **FIXED**:

**Root cause**: Users needed a way to prevent specific DOIs from being imported during publication synchronization from external sources (ORCID, Scopus, PubMed).

**Solution implemented**:
1. **Database field**: Added `skip_dois` TextField to AcademicUser model to store list of DOIs to skip
2. **Helper method**: Added `get_skip_dois_list()` method to parse and normalize DOI list (handles various formats)
3. **Profile UI**: Added textarea field in user profile for entering DOIs to skip (one per line)
4. **Form handling**: Updated ProfileView to save skip_dois field
5. **Sync integration**: Updated all sync commands (ORCID, Scopus, PubMed, Scopus Enhanced) to check skip list before creating publications
6. **DOI normalization**: Skip list supports multiple formats (plain DOI, doi: prefix, full URLs)

**Files modified**: `academic/models.py`, `academic/templates/academic/profile.html`, `academic/views.py`, `academic/management/commands/sync_orcid.py`, `academic/management/commands/sync_scopus.py`, `academic/management/commands/sync_pubmed.py`, `academic/management/commands/sync_scopus_enhanced.py`, plus new migration `academic/migrations/0012_add_skip_dois_field.py`  