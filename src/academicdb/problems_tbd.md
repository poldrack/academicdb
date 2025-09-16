## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.

[ ] I would like to add links to CV entries, as we had done in the original code.  

The first step is to create a new table, which we call Links, based on an uploaded CSV file like data/links.csv.  This will have columns named "type", "DOI", and "url".  Type refers to the kind of link it is, and should be used as the link text.  DOI refers to the DOI and should be used as a reference to identify the relevant publication.  url refers to the URL to be linked to.  I think it would be best to add a button to the links page named "Add links to pubs" that will add the links to the publication entries, so that they will be easily accessible when we are ready to generate the CV.

The second step is to add link rendering to the CV generator.  The links should be added after the OA/DOI links for each publication if they exist.

[ ] I would like to generate a tool to find publication entries with duplicate names.  This primarily occurs when there is a preprint that overlaps with a journal paper.  Let's add a button to the publications page called "Find duplicates".  When pressed, this should identify all publications with matching titles, and present them in a table with buttons that allow one to mark them as ignored or delete them.

