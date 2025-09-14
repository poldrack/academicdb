## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.  

[x] ~~It appears that the DOI-based Scopus author ID enrichment is being rerun each time.  We should only run it for publications that don't already have Scopus Author IDs assigned~~ **FIXED**:

**Root cause**: The Scopus author enrichment command was processing publications every time, even if they had already been enriched or had complete Scopus author information.

**Solution implemented**:
1. **Enhanced filtering**: Added pre-filtering to skip publications that have already been processed or have all authors with Scopus IDs
2. **Enrichment tracking**: Added `metadata['scopus_author_enriched']` flag to track processing attempts
3. **Timestamp tracking**: Added `metadata['scopus_author_enriched_at']` to record when enrichment was attempted
4. **Skip logic**: Publications are skipped if they have the enrichment flag set or all authors already have Scopus IDs (unless `--force` is used)
5. **Mark all attempts**: Both successful enrichments and failed lookups are marked to avoid re-processing

**Files modified**: `academic/management/commands/enrich_scopus_authors.py`

[x] ~~Add "PI (Subcontract)" as an additional role (under "Your Role") for funding entries.~~ **FIXED**:

**Root cause**: The funding role choices were missing the "PI (Subcontract)" option which is commonly used in academic funding scenarios.

**Solution implemented**:
1. **Added role choice**: Added `('pi_subcontract', 'PI (Subcontract)')` to the `ROLE_CHOICES` in the Funding model
2. **Database migration**: Created migration `0011_add_pi_subcontract_role.py` to update the database schema
3. **Proper ordering**: Placed the new role after "Principal Investigator" and before "Co-Principal Investigator" for logical grouping

**Files modified**: `academic/models.py`, plus new migration `academic/migrations/0011_add_pi_subcontract_role.py`

[x] ~~UNIQUE constraint failed: academic_publication.owner_id, academic_publication.doi error during Scopus author enrichment~~ **FIXED**:

**Root cause**: The Publication model's `save()` method automatically normalizes DOI to lowercase. When the Scopus author enrichment command saves publications, this DOI normalization could create duplicate entries if a publication with the lowercase DOI already exists, causing a UNIQUE constraint violation.

**Solution implemented**:
1. **Selective field updates**: Modified all `publication.save()` calls in the Scopus author enrichment command to use `update_fields` parameter
2. **Avoid DOI normalization**: By specifying only the fields being changed (`authors`, `manual_edits`, `edit_history`, `metadata`), the save method doesn't trigger DOI normalization
3. **Preserve functionality**: All functionality remains intact while preventing constraint violations

**Files modified**: `academic/management/commands/enrich_scopus_authors.py`

[x] ~~Currently it seems that ignored publications are not showing up in the listing. I would prefer that they appear in the listing but are marked with an "Ignored" badge.~~ **FIXED**:

**Root cause**: The `PublicationListView` was filtering out ignored publications by default, preventing them from appearing in the publication list.

**Solution implemented**:
1. **Modified queryset**: Removed the filter that excluded ignored publications from the queryset in `PublicationListView`
2. **Added visual indicator**: Added an "Ignored" badge with eye-slash icon in the publication list template
3. **Tooltip support**: Badge shows the ignore reason as a tooltip when available
4. **Counts tracking**: Added separate tracking for ignored vs active publication counts

**Files modified**: `academic/views.py`, `academic/templates/academic/publication_list.html`
[x] ~~For preprints, don't worry about finding PMC links for them.~~ **FIXED**
[x] ~~When searching for PMC IDs using the PMID, it seems that some PMIDs are searched twice (the message "Searching for PMID: ..." appears twice for each one).  This is unncessary - each PMID should just be searched once.~~ **FIXED**
[x] ~~If a publication does not have a PMID then there is no need to search for a PMC ID since that is a prerequisite for a publication to appear in PMC.~~ **FIXED**
[x] ~~Ignored publications can be skipped in the PMC ID search process.~~ **FIXED**

**Combined fix for all PMC search issues**:

**Root causes**:
1. Preprints were being unnecessarily searched for PMC IDs
2. When searching by DOI, the code would find a PMID and then search again with that PMID, causing duplicate messages
3. Publications without PMIDs were still being searched
4. Ignored publications were being processed unnecessarily

**Solution implemented in `lookup_pmc_ids.py`**:
1. **Skip filters**: Added pre-filtering to skip ignored publications, preprints, and publications without PMIDs or DOIs
2. **Search order**: Changed to search by PMID first (if available), then by DOI only if no PMID exists
3. **Duplicate prevention**: Added `print_message` parameter to `lookup_pmc_by_pmid()` to suppress duplicate messages when called from DOI search
4. **Removed title search**: Removed unreliable title-based search completely
5. **Better reporting**: Added counters to show how many publications were skipped for each reason

**Files modified**: `academic/management/commands/lookup_pmc_ids.py`


[x] ~~I am seeing errors related to the importing of some new funding entires from ORCID - they appear to have a None in one of the fields.  (I can't tell which because the error disappeared)~~ **FIXED**:

**Root cause**: The ORCID funding sync code was not properly handling None values in nested dictionary structures from the ORCID API response, causing AttributeError exceptions when trying to access fields on None objects.

**Solution implemented**:
1. **Safe dictionary access**: Added robust None checks for all nested dictionary accesses using the pattern `dict.get('key') or {}`
2. **Improved value extraction**: Changed from chained `.get()` calls to safe extraction with None checks at each level
3. **Better error logging**: Added warning messages when date/amount parsing fails to help debug future issues
4. **Defensive programming**: All field extractions now handle None values gracefully and provide sensible defaults

**Files modified**: `academic/management/commands/sync_orcid.py` (sync_funding_record method)

[x] ~~It seems that crossref data is being downloaded for all DOIs during syncing, even if they have already been enriched.  Each publication record should have any entry noting whether it has already been enriched using crossref data, and those should not be downloaded again.~~ **FIXED**:

**Root cause**: The CrossRef enrichment command was not properly tracking which publications had already been enriched, causing unnecessary API calls and re-downloading of data.

**Solution implemented**:
1. **Enrichment tracking**: Added `metadata['crossref_enriched']` flag that is set to `True` when CrossRef data is successfully retrieved
2. **Timestamp tracking**: Added `metadata['crossref_enriched_at']` to record when enrichment occurred
3. **Smart filtering**: Modified `get_publications_to_enrich()` to exclude publications where `metadata['crossref_enriched']=True`
4. **Progress logging**: Added logging to show how many publications are being skipped because they're already enriched
5. **Force option**: Retained `--force` flag to allow re-enrichment when needed

**Files modified**: `academic/management/commands/enrich_crossref.py`

[x] ~~There is not currently a way to delete a publication.  Please add this functionality.~~ **FIXED**:

**Root cause**: No delete functionality existed for publications, limiting users' ability to remove unwanted or incorrect publications from their database.

**Solution implemented**:
1. **Delete view**: Added `PublicationDeleteView` with proper authentication and authorization to ensure users can only delete their own publications
2. **Confirmation page**: Created a comprehensive delete confirmation template (`publication_confirm_delete.html`) with publication details and warnings about permanent deletion
3. **URL routing**: Added delete URL pattern (`publications/<int:pk>/delete/`) to the URL configuration
4. **UI integration**: Added delete buttons to both publication list and detail views for easy access
5. **User guidance**: Included helpful information about the difference between deleting and ignoring publications
6. **Success messaging**: Added confirmation message when deletion is successful

**Files modified**: `academic/views.py`, `academic/urls.py`, `academic/templates/academic/publication_list.html`, `academic/templates/academic/publication_detail.html`, plus new `academic/templates/academic/publication_confirm_delete.html`

[x] ~~It seems that DOIs with differences in capitalization are being treated as different publications (e.g. 10.3758/BF03214547 and 10.3758/bf03214547).  It seems that in the general convention is for DOIs to be lower cased, so we should change all DOIs to lower case to prevent duplicated references. Add this to the sync process, and also add a management feature to allow removal of duplicates with matching DOIs that differ only in letter case.~~ **FIXED**:

**Root cause**: DOIs were not being normalized to lowercase during import and save operations, leading to duplicate publications that differed only in case (e.g., "10.3758/BF03214547" vs "10.3758/bf03214547").

**Solution implemented**:
1. **Model-level normalization**: Modified `Publication.save()` method to automatically lowercase and strip DOIs before saving
2. **Sync process updates**: Updated all sync commands (`sync_scopus.py`, `sync_pubmed.py`, `sync_scopus_enhanced.py`) to normalize DOIs to lowercase during import
3. **Deduplication command**: Created `deduplicate_doi_case.py` management command to find and merge existing publications with case-different DOIs
4. **Automatic future prevention**: All new publications will have normalized DOIs, preventing future case-sensitivity duplicates

**Files modified**: `academic/models.py`, `academic/management/commands/sync_scopus.py`, `academic/management/commands/sync_pubmed.py`, `academic/management/commands/sync_scopus_enhanced.py`, plus new `academic/management/commands/deduplicate_doi_case.py`

[x] ~~There is no way within the edit window for a publication to mark it as ignored.  Please add a way for the user to mark a publication as ignored.~~ **FIXED**:

**Root cause**: The publication edit form did not include the `is_ignored` and `ignore_reason` fields that were already available in the model, preventing users from marking publications as ignored through the UI.

**Solution implemented**:
1. **Enhanced edit form**: Added "Ignore this publication" checkbox and optional "Reason for ignoring" text field to the publication edit form
2. **Dynamic UI**: Implemented JavaScript to show/hide the reason field when the ignore checkbox is toggled
3. **User guidance**: Added helpful explanations in the form and sidebar about when and why to ignore publications (corrigenda, misattributed works, duplicates, etc.)
4. **Form integration**: Leveraged existing model fields and view logic that were already configured to handle ignore functionality

**Files modified**: `academic/templates/academic/publication_form.html`

[x] ~~The position matching tests for author similarity seem to brittle. for example, I see this warning message: "    ⚠️  Position 5: Names seem very different - J He vs He J."  It seems obvious that "J He" and "He J." would refer to the same person.  Improve the logic so that it is more robust to these kinds of differences.~~ **FIXED**:

**Root cause**: The `names_reasonably_similar` function was too strict for cases like "J He" vs "He J." which are clearly the same author with different formatting.

**Solution implemented**:
1. **Enhanced name normalization**: Added removal of periods and better whitespace handling
2. **Reversed order matching**: Added specific logic to detect "initial+surname vs surname+initial" patterns (e.g., "J He" vs "He J.")
3. **Flexible initial matching**: Improved handling of single-letter names and initials
4. **Better surname matching**: Relaxed surname length requirements to allow single-letter surnames
5. **Initial+surname cross-validation**: Added logic to match initials against given names across different formats

**Files modified**: `academic/management/commands/enrich_scopus_authors.py:names_reasonably_similar()`

