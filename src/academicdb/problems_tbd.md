## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]

[x] The "Sync All Databases" function should also ingest a set of data files at once from a data directory that is specified by the user (by default set to ${PWD}/data).  These should include:
- additional publications: additional_pubs.csv
- conferences: conference.csv
- editorial activities: editorial.csv
- links for papers: links.csv
- talks: talks.csv
- teaching: teaching.csv

[x] The "Collaborators" function needs to be implemented. There should be a Collaborators table that includes all unique Scopus IDs from all publications.  For each ID, we should then obtain that individual's current affiliation information from the Scopus API; see src/academicdb/get_collaborators.py for an example of how this was done in the previous code.  The building of the collaborators database can be triggered using a button on the collaborators page called "Build collaborators table" which should generate the entire table, looking up affiliations as needed for newly added collaborators.

