## Problems to be fixed

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
