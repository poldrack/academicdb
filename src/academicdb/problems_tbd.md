## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.


[x] There is a problem with certain papers that are of the type "Conference Paper".  In the rendered CV, the journal is being listed as "TBDconference-paper" in bold text.  The reference should instead display the publicationName.

    Fixed by:
    1. Added case for 'conference-paper' type in get_publication_outlet() function in academic/cv_renderer.py
    2. Now displays the publication name (journal/conference name) in italics like other publication types

[x] The publication search doesn't seem to be searching the author names, only the title.

    Fixed by:
    1. Updated SQLite search method in academic/models.py to include Q(authors__icontains=term)
    2. Created migration 0017_update_search_vector_include_authors.py to update PostgreSQL search vector to include authors field with weight 'D'
    3. Both PostgreSQL and SQLite search now include author names in search results