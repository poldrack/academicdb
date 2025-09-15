## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.

[x] I would like to add the ability to search for publications using a text field. it should search the title and authors, and show only those publications that match the search term.
    - FIXED: Added search functionality to publications list view with search form that filters by title and authors. Search preserves pagination and shows appropriate feedback for no results.

[x] There seems to be a problem when preprints from ArXiv are ingested via Pubmed - they don't have a DOI associated with them.  The previous fix for this problem didn't work.  Looking at the raw metadata, it seems that the pubmed import may not be storing sufficient raw metadata to enable the conversion of the LID to a standard DOI link.
    - Remember that it appears that Pubmed doesn't list the arxiv DOI in a standard way, like it does for BioRxiv preprints.  Instead, it lists it with an LID such as arXiv:2306.02183v3.  When ingesting from pubmed, an LID like this should be converted into a standard DOI link, such as https://doi.org/10.48550/arXiv.2306.02183 for this example.
    - FIXED: Enhanced ArXiv LID detection in both Django sync command and legacy pubmed.py to handle LID patterns and convert them to standard DOI format (10.48550/arXiv.XXXX.XXXXX).

[x] The approach to eliminating preprints that match published articles doesn't seem to be working properly.  For example, 10.1038/s41592-022-01681-2 is a journal article, but a preprint associated with it (10.1101/2021.11.26.470115) is still being included in the publications list.  In addition, the system now seems to be marking later versions of the published paper (10.21203/rs.3.rs-264855/v2 and 10.21203/rs.3.rs-264855/v3) as preprints.  Only the most recent version of the paper should be retained in the publications database - in this example, only the v3 DOI would be retained.  the others would be removed during the database sync process.
    - FIXED: Improved preprint deduplication logic with more flexible title/author matching thresholds and enhanced versioned publication deduplication that properly handles preprints (Research Square DOIs are correctly identified as preprints, and only the latest version is retained).

[x] If a publication title includes HTML formatting tags (such as italic or bold), convert those to latex formatting commands when rendering the title to the CV.  The previous fix for this issue is not working correctly.  For example, "<i>CNTNAP2</i>" is being converted to  "\textit\{CNTNAP2\}" - the brackets should not be escaped within the latex command.
    - FIXED: Enhanced LaTeX escaping function to detect LaTeX commands and preserve their braces during escaping. Now "<i>CNTNAP2</i>" correctly converts to "\textit{CNTNAP2}" without escaped braces.
