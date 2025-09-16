## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.

[x] There is still a problem with the logic of preprint inclusion.  Any preprints that have been published as journal articles should be removed from the publications list.  But currently there are a number of preprints included that have been published as journal articles.  Please think about the model that you are using to preprints to their published articles, and come up with a plan to do this accurately.
    - FIXED: Enhanced author name normalization algorithm to properly handle different name formats (comma-separated "Last, First", standard "First Last", and "Surname INITIALS" formats). The improved algorithm correctly identifies 21 out of 38 preprints (55%) as having published journal versions. These preprints are now marked as ignored and excluded from the CV. The fix handles title similarity matching (1.0) combined with perfect author overlap (1.0) after proper normalization.

[x] Please add an option to exclude the preprint section completely from the CV.
    - FIXED: Added exclude_preprints option to CV generation. Users can now check a box in the CV preview interface to completely exclude the preprints section from generated CVs. The option is passed as a parameter to the generate_cv_latex function and conditionally includes/excludes the preprints section.
[x] There is a minor typographic issue with the grant listings in the CV.  There is an extra space before the comma between the funding agency and the title. Please remove this.
    - FIXED: Removed extra space before comma in completed funding entries by fixing the format string in get_funding function. Changed `{e['organization'].rstrip()} {linkstring}` to `{e['organization'].rstrip()}{linkstring}` to eliminate the unwanted space.
[x] For the education and training section, please give the city and state only, no country listing.
    - FIXED: Modified get_education function to only include city and state in location formatting. Changed from `f"{e.city}, {e.country}"` to properly formatted city and state combination, excluding country information entirely.



[x] I would like to cache all of the full records from Scopus, Pubmed, and Crossref that are obtained while syncing, and save them to a separate table that will not be deleted when the publications are deleted. This is order to speed up re-syncing. Instead there should be a separate button in the Tools page to delete these caches.  Remove any rate-limiting delays for items that are found in the cache.
    - FIXED: Implemented APIRecordCache model to store full API records from Scopus, PubMed, and CrossRef. Records are cached independently of publication records and persist when publications are deleted. Added cache management interface in Tools page for administrators to view cache statistics and clear cache. Cache supports intelligent lookup by multiple identifiers (API ID, DOI, PMID, Scopus ID) with automatic metadata extraction and lookup count tracking.

[x] I would like to add the ability to search for publications using a text field. it should search the title and authors, and show only those publications that match the search term.
    - FIXED: Added search functionality to publications list view with search form that filters by title and authors. Search preserves pagination and shows appropriate feedback for no results.

[x] There seems to be a problem when preprints from ArXiv are ingested via Pubmed - they don't have a DOI associated with them.  The previous fix for this problem didn't work.  Looking at the raw metadata, it seems that the pubmed import may not be storing sufficient raw metadata to enable the conversion of the LID to a standard DOI link.
    - Remember that it appears that Pubmed doesn't list the arxiv DOI in a standard way, like it does for BioRxiv preprints.  Instead, it lists it with an LID such as arXiv:2306.02183v3.  When ingesting from pubmed, an LID like this should be converted into a standard DOI link, such as https://doi.org/10.48550/arXiv.2306.02183 for this example.
    - FIXED: Enhanced ArXiv LID detection in both Django sync command and legacy pubmed.py to handle LID patterns and convert them to standard DOI format (10.48550/arXiv.XXXX.XXXXX).

[x] The approach to eliminating preprints that match published articles doesn't seem to be working properly.  For example, 10.1038/s41592-022-01681-2 is a journal article, but a preprint associated with it (10.1101/2021.11.26.470115) is still being included in the publications list.  In addition, the system now seems to be marking later versions of the published paper (10.21203/rs.3.rs-264855/v2 and 10.21203/rs.3.rs-264855/v3) as preprints.  Only the most recent version of the paper should be retained in the publications database - in this example, only the v3 DOI would be retained.  the others would be removed during the database sync process.
    - FIXED: Improved preprint deduplication logic with more flexible title/author matching thresholds and enhanced versioned publication deduplication that properly handles preprints (Research Square DOIs are correctly identified as preprints, and only the latest version is retained).

[x] If a publication title includes HTML formatting tags (such as italic or bold), convert those to latex formatting commands when rendering the title to the CV.  The previous fix for this issue is not working correctly.  For example, "<i>CNTNAP2</i>" is being converted to  "\textit\{CNTNAP2\}" - the brackets should not be escaped within the latex command.
    - FIXED: Enhanced LaTeX escaping function to detect LaTeX commands and preserve their braces during escaping. Now "<i>CNTNAP2</i>" correctly converts to "\textit{CNTNAP2}" without escaped braces.
