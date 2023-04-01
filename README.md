## *academicdb*: An academic database builder

Why build your CV by hand when you can create it programmatically?  This package uses a set of APIs (including Scopus, ORCID, CrossRef, and Pubmed) to generate a database of academic acheivements, and provides a tool to render those into a professional-looking CV.  Perhaps more importantly, it provides a database of collaborators, which can be used to generate the notorious NSF collaborators spreadsheet. 

### Installing academicdb

To install the current version:

```
pip install academicdb
```

In addition to the Python packages required by academicdb (which should be automatically installed), you will also need a MongoDB server to host the database.  There are two relatively easy alternatives:

- [Install MongoDB](https://www.mongodb.com/docs/manual/installation/) on your own system. 
- Create a free cloud MongoDB instance [here](https://www.mongodb.com/cloud).

### Configuring academicdb

To use academicdb, you must first set up some configuration files, which will reside in `~/.academicdb`.  The most important is `config.toml`, which contains all of the details about you that are used to retrieve your information.  Here are the contents of mine as an example:

```
[researcher]
lastname = "poldrack"
middlename = "alan"
firstname = "russell"
email = "russpold@stanford.edu"
orcid = "0000-0001-6755-0259"
query = "poldrack-r"
url = "http://poldrack.github.io"
twitter = "@russpoldrack"
github = "http://github.com/poldrack"
phone = "650-497-8488"
scholar_id = "RbmLvDIAAAAJ"
scopus_id = "7004739390"
address = [
    "Stanford University",
    "Department of Psychology",
    "Building 420",
    "450 Jane Stanford Way",
    "Stanford, CA, 94305-2130",
]
```

Most of this should be self-explanatory. There are several identifiers that you need to specify:

- **ORCID**: This is a unique identifier for researchers.  If you don't already have an ORCID you can get one [here](http://orcid.org).  You will need to enter information about your education, employment, invited position and distinctions, and memberships and service into your ORCID account since that is where academicdb looks for that information.
- **Google Scholar**: You will also need to retrieve your Google Scholar ID.  Once you have set up your profile, go to the "My Profile" page.  The URL from that page contains your id: for example, my URL is *https://scholar.google.com/citations?user=RbmLvDIAAAAJ&hl=en* and the ID is *RbmLvDIAAAAJ*.  
- **Scopus**: Scopus is a service run by Elsevier.  I know that they are the bad guys, but Scopus provides a service that is not available from anywhere else: For each reference it provides a set of unique identifiers for the coauthors, which can be used to retreive their affilation information.  This is essential for generating the NSF collaborators spreadsheet.

#### Database setup

By default, academicdb 



