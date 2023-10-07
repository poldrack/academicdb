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

The former is easier, but I prefer the latter because it allows the database to accessed from any system. 

Rendering the CV after building the database requires that LaTeX be installed on your system and available from the command line.  There are various LaTeX distributions depending on your operating system.

_Note: If you get an error that the font Tex Gyre Termes is not installed when executing `render_cv`, you can install it using Homebrew like so:_
```{bash}
$ brew tap homebrew/cask-fonts
$ brew install --cask font-tex-gyre-termes
```

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
- **Scopus**: Scopus is a service run by Elsevier. It provides a service that is not available from anywhere else: For each reference it provides a set of unique identifiers for the coauthors, which can be used to retreive their affilation information.  This is essential for generating the NSF collaborators spreadsheet.

### cloud MongoDB setup

If you are going to use a cloud MongoDB server, you will need to add the following lines to your `config.toml`:

```
[mongo]
CONNECT_STRING = 'mongodb+srv://<username>:<password>@<server>'
```

The cloud provider should provide you with the connection string that you can paste into this variable.

## Obtaining an API key for Scopus

  You will need to obtain an API key to access the Scopus database, which you can obtain from [http://dev.elsevier.com/myapikey.html](http://dev.elsevier.com/myapikey.html).  This is used by the [pybliometrics](https://pybliometrics.readthedocs.io/en/stable/) package to access the APIs. Note that this key will only work if you are on your institution's network and the institution has the appropriate license with Elsevier.  You can also request an institutional token from Elsevier if you wish to use the APIs from outside of your institution's network.

  The first time you use the package, you will be asked by pybliometrics to enter your API key (and InstToken if you have one), which will be stored in `~/.pybliometrics/config.ini` for reuse.

## specifying additional information

There are a number of pieces of information that are difficult to reliably obtain from ORCID or other APIs, so they must be specified in a set of text files, which should be saved in the base directory that is specified when the command line `dbbuilder` tool is used.  See the `examples` directory for examples of each of these.

- `editorial.csv`: information about editorial roles
- `talks.csv`: information about non-conference talks at other institutions
- `conference.csv`: Information about conference talks
- `teaching.csv`: Information about teaching
- `funding.csv`: Information about grant funding

In addition, there may be references (including books, book chapters, and published conference papers) that are not detected by the automated search and need to be added by hand, using a file called `additional_pubs.csv` in the base directory.  

Finally there is a file called `links.csv` that allows one to specify links related to individual publications, such as [OSF](http://osf.io)  repositories, shared code, and shared data.  These links will be rendered in the CV alongside the publications.

## Building the database

To build the database, you use the `dbbuilder` command line tool.  The simplest usage is:

```
dbbuilder -b <base directory for files and output>
```

The full usage for the script is:

```
usage: dbbuilder [-h] [-c CONFIGDIR] -b BASEDIR [-d] [-o] [--no_add_pubs] [--no_add_info] [--nodb] [-t] [--bad_dois_file BAD_DOIS_FILE]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIGDIR, --configdir CONFIGDIR
                        directory for config files
  -b BASEDIR, --basedir BASEDIR
                        base directory
  -d, --debug           log debug messages
  -o, --overwrite       overwrite existing database
  --no_add_pubs         do not get publications
  --no_add_info         do not add additional information from csv files
  --nodb                do not write to database
  -t, --test            test mode (limit number of publications)
  --bad_dois_file BAD_DOIS_FILE
                        file with bad dois to remove
```

## Rendering the CV 

The render the CV after building the database, use the `render_cv` command line tool.  The simplest usage is:

```
render_cv
```

This will create a LaTeX version of the CV and then render it using `xelatex`. 

The full usage is:

```
usage: render_cv [-h] [-c CONFIGDIR] [-f FORMAT] [-d OUTDIR] [-o OUTFILE] [--no_render]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIGDIR, --configdir CONFIGDIR
                        directory for config files
  -d OUTDIR, --outdir OUTDIR
                        output dir
  -o OUTFILE, --outfile OUTFILE
                        output file stem
  --no_render           do not render the output file (only create .tex)
```

## Creating the NSF collaborators spreadsheet

To create a list of collaborators from the last 4 years and their affiliations, as needed for NSF grant submissions, simply type `get_collaborators` once the database has been built.  This will create a file called `nsf_collaborators.csv`.  You will still need to complete the remainder of the [NSF COA template](https://www.nsf.gov/bfa/dias/policy/coa/coa_template.xlsx) and then paste the contents of the created file into Table 4 in that template.  *NOTE:* Please closely doublecheck the output to make sure that it has worked properly, as this feature has not been extensively tested.