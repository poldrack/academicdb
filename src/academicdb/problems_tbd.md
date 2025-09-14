## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.  

[x] ~~The position matching tests for author similarity seem to brittle. for example, I see this warning message: "    ⚠️  Position 5: Names seem very different - J He vs He J."  It seems obvious that "J He" and "He J." would refer to the same person.  Improve the logic so that it is more robust to these kinds of differences.~~ **FIXED**:

**Root cause**: The `names_reasonably_similar` function was too strict for cases like "J He" vs "He J." which are clearly the same author with different formatting.

**Solution implemented**:
1. **Enhanced name normalization**: Added removal of periods and better whitespace handling
2. **Reversed order matching**: Added specific logic to detect "initial+surname vs surname+initial" patterns (e.g., "J He" vs "He J.")
3. **Flexible initial matching**: Improved handling of single-letter names and initials
4. **Better surname matching**: Relaxed surname length requirements to allow single-letter surnames
5. **Initial+surname cross-validation**: Added logic to match initials against given names across different formats

**Files modified**: `academic/management/commands/enrich_scopus_authors.py:names_reasonably_similar()`

[x] ~~We need a way to mark publications as "ignored". This could refer to cases where there has been a corrigendum (which appears as a separate publication) or in cases where the publication doesn't actually belong to the author.~~ **FIXED**:

**Root cause**: No existing mechanism to mark publications as ignored for exclusion from reports, CVs, or analysis.

**Solution implemented**:
1. **Database schema changes**: Added `is_ignored` boolean field and `ignore_reason` text field to Publication model
2. **Migration created**: Database migration to add the new fields to existing publications
3. **API updates**: Updated PublicationSerializer to include ignore fields in REST API
4. **View filtering**: Modified PublicationListView to filter out ignored publications by default (with option to show them via `?show_ignored=true`)
5. **Form integration**: Added ignore fields to both create and update publication forms
6. **UI support**: Forms now allow users to mark publications as ignored and provide reasons

**Files modified**: `academic/models.py`, `academic/serializers.py`, `academic/views.py`, plus database migration

[x] ~~Some publications (e.g. 10.1093/braincomms/fcae120, 10.7554/eLife.79277 ) show both a "PMC Full Text" link and a "Pmc" link, both of which refer to the same PMC link. Please ensure that the PMC Full Text link is only stored and referred to once for all publications.~~ **FIXED**:

**Root cause**: The PMC lookup command was adding PMC links to the `links` dictionary while the template was already displaying PMC links from the `identifiers.pmcid` field, resulting in duplicate links in the UI.

**Solution implemented**:
1. **Prevented future duplicates**: Modified `lookup_pmc_ids.py` to only store PMC ID in identifiers, not add redundant links
2. **Created cleanup command**: Added `deduplicate_pmc_links.py` management command to identify and remove existing duplicate PMC links
3. **Bulk cleanup performed**: Ran deduplication command and successfully cleaned 141+ publications with duplicate PMC links
4. **Consistent display logic**: PMC links now only appear once via the identifiers display, eliminating redundancy

**Files modified**: `academic/management/commands/lookup_pmc_ids.py`, `academic/management/commands/deduplicate_pmc_links.py`



[x] ~~The progress window is not fully tracking the onging processing when a full database sync is performed.  In particular, it never says that Scopus ID matching is happening - it stops at PMC matching.  Please ensure that all steps in the process are reflected in the progress window.~~ **FIXED**:

**Root cause**: Progress tracking in the comprehensive sync function was not properly updating progress percentages for postprocessing tasks, causing the progress bar to appear stuck after PMC matching while Scopus ID enrichment was running in the background.

**Solution implemented**:
1. **Improved progress granularity**: Split total progress calculation into distinct phases with proper step allocation (sync sources: 30 steps each, enrichment: 20 steps, postprocessing: 15 steps)
2. **Per-task progress updates**: Each postprocessing task now updates both the current step description AND progress percentage
3. **Better step distribution**: Postprocessing steps are evenly distributed among tasks (PMC lookup and Scopus author ID enrichment)
4. **Progress continuity**: Progress advances even when individual tasks fail, preventing the UI from getting stuck
5. **Clearer phase indicators**: Progress window now shows distinct phases: "Database Synchronization", "Data Enrichment", and "Post-Processing"

**Files modified**: `academic/views.py:run_comprehensive_sync_background()`

[x] ~~the positional matching of authors for identification of Scopus IDs seems to
  be breaking on at least two occasions (10.1093/braincomms/fcae120 and
  10.3389/fninf.2012.00009).  are you checking to make sure that the two
  publications have the same number of authors? it seems that one author may
  have been skipped in one of the records leading to a mismatch.  When a mismatch occurs, we should use the Scopus entry for our database entry, replacing the mismatching author list from the original entry.~~ **FIXED**:

**Root cause**: Positional matching algorithm did not handle cases where author counts differed between the publication record and Scopus data, leading to incorrect author-Scopus ID assignments.

**Solution implemented**:
1. **Enhanced author count validation**: Added explicit check for author count mismatches between publication and Scopus records
2. **Authoritative Scopus replacement**: When counts don't match, completely replace the publication's author list with Scopus data instead of attempting name-based matching
3. **Improved logging**: Added detailed logging to show when author counts match/mismatch and what action is taken
4. **Positional match validation**: Added basic name similarity checking to warn when positional matches seem questionable
5. **Audit trail**: Added edit history tracking when author lists are replaced due to mismatches
6. **New method `replace_authors_with_scopus_data`**: Handles complete author list replacement while preserving necessary metadata
7. **Enhanced validation with `names_reasonably_similar`**: Provides early warning for potentially incorrect positional matches

**Files modified**: `academic/management/commands/enrich_scopus_authors.py`

[x] ~~the progress bar when using the "Sync All Databases" function is not working correctly - it shows "initializing" but then goes away as if the sync was complete, when in reality the sync is ongoing (as seen from the progress messages printed to the server console)~~ **FIXED**:

**Root cause**: The form was submitting normally causing page reload, instead of being handled by JavaScript AJAX
**Solution implemented**:
1. **Fixed form submission**: Prevented default form submission and handled entirely via AJAX with proper headers
2. **Fixed thread synchronization**: Background sync function now receives sync_id parameter to ensure progress tracking matches
3. **Updated view responses**: Return JSON for AJAX requests instead of redirecting
4. **Added race condition protection**: Pre-initialize progress data before starting thread
5. **Updated command names**: Fixed postprocessing to use correct `enrich_scopus_authors` command
6. **Added comprehensive debugging**: Console logging and error handling for progress tracking
7. **Memory cleanup**: Added automatic cleanup of completed sync progress data

**Files modified**: `academic/views.py`, `academic/templates/academic/dashboard.html`
