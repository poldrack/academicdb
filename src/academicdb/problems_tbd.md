## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.


[x] It seems that different databases have different information regarding page numbers, such that the presence of non-null page number info depends on which database the entry comes from.  For example,  10.1038/s41562-024-01942-4 shows pageRange as None in its metadata (which appear to come from scopus), while the pubmed entry for that same DOI shows a page range of 2003-2017.  The following is IMPORTANT: Page range and volume number should be first-class variables in the publication record, rather than having to infer them from metadata.  These should be identified when the records are imported, such that the page range and volume records will be populated if that information is present in any of the databases.  Non-null page range information should not be overwritten by null page range information during ingestion.

**FIXED**: Added `volume` and `page_range` as first-class fields to the Publication model. Updated all sync commands (Scopus, PubMed) to extract and populate these fields from API responses. Modified `save_with_edit_protection` method to prevent non-null values from being overwritten with null values during API sync. Updated CV renderer to prioritize first-class fields over metadata. Created data migration that successfully populated 375 existing publications with volume/page_range data extracted from metadata. The solution ensures that page range and volume information from any database is preserved and prioritized correctly.

[x] The details about specific publications are still missing from the CV.  for example, for 10.1126/science.1134239, there is information about the page range in metadata['raw_data']['pageRange'] and the volume in metadata['raw_data']['volume'] but this is not being displayed in the reference.  I think that the publication ingestion from the database should populate fields in the main publication record for page range and volume, if those are present.

**FIXED**: Updated CV renderer in `academic/cv_renderer.py` to extract volume and page information from nested metadata structures, specifically `metadata['raw_data']['volume']` and `metadata['raw_data']['pageRange']`. The CV now properly displays volume and page range information for publications like 10.1126/science.1134239.