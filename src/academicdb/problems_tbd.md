## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.


[x] It seems that preprints published in ArXiv (with DOIs beginning with "2306.") are not being properly labeled as preprints.
[x] There are duplicate versions of publications when the DOI includes a version number.  For example, 10.21203/rs.3.rs-264855/v2 and 10.21203/rs.3.rs-264855/v3 refer to different versions of the same article, but both are included as separate articles in the database.  This needs to be dealt with, either during initial ingestion or as a post-processing step, in which we check for dois that match except for a version tag, and then remove all but the latest version.
[x] It also seems that the exclusion of preprints that match to published journal articles is not working.  For example, the preprint with DOI 10.1101/2021.11.26.470115 is a preprint version of published article 10.21203/rs.3.rs-264855/v3.  For this reason, the preprint should be excluded from the CV, but it is not.

**FIXED**: Enhanced arXiv preprint detection to handle multiple DOI formats including bare arXiv IDs like "2306.12345", arXiv: prefixed IDs, and the new 10.48550/arXiv.XXXX.XXXX format. Also added Research Square preprints (10.21203) to the detection list.

**FIXED**: Added DOI deduplication logic to handle versioned publications. Created `normalize_doi_for_deduplication()` and `find_potential_duplicates_by_doi()` methods in the Publication model. Updated Scopus and PubMed sync commands to detect versioned DOIs and keep only the latest version. Created `deduplicate_versioned_publications` management command to clean up existing duplicates.

**FIXED**: Enhanced preprint exclusion logic with intelligent matching. Added `find_published_version_of_preprint()` method that uses both explicit metadata relationships and title/author similarity matching to detect when preprints have been published as journal articles. Updated CV renderer to use this enhanced detection. Created `detect_published_preprints` management command to identify and optionally mark published preprints as ignored for CV exclusion.

[x] It seems that different databases have different information regarding page numbers, such that the presence of non-null page number info depends on which database the entry comes from.  For example,  10.1038/s41562-024-01942-4 shows pageRange as None in its metadata (which appear to come from scopus), while the pubmed entry for that same DOI shows a page range of 2003-2017.  The following is IMPORTANT: Page range and volume number should be first-class variables in the publication record, rather than having to infer them from metadata.  These should be identified when the records are imported, such that the page range and volume records will be populated if that information is present in any of the databases.  Non-null page range information should not be overwritten by null page range information during ingestion.

**FIXED**: Added `volume` and `page_range` as first-class fields to the Publication model. Updated all sync commands (Scopus, PubMed) to extract and populate these fields from API responses. Modified `save_with_edit_protection` method to prevent non-null values from being overwritten with null values during API sync. Updated CV renderer to prioritize first-class fields over metadata. Created data migration that successfully populated 375 existing publications with volume/page_range data extracted from metadata. The solution ensures that page range and volume information from any database is preserved and prioritized correctly.

[x] The details about specific publications are still missing from the CV.  for example, for 10.1126/science.1134239, there is information about the page range in metadata['raw_data']['pageRange'] and the volume in metadata['raw_data']['volume'] but this is not being displayed in the reference.  I think that the publication ingestion from the database should populate fields in the main publication record for page range and volume, if those are present.

**FIXED**: Updated CV renderer in `academic/cv_renderer.py` to extract volume and page information from nested metadata structures, specifically `metadata['raw_data']['volume']` and `metadata['raw_data']['pageRange']`. The CV now properly displays volume and page range information for publications like 10.1126/science.1134239.