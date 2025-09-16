## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.

[x] Pybliometrics requires the scopus key to be provided the first time that pybliometrics is loaded.  this is causing the process to get stuck here:
    Creating config file at /home/appuser/.config/pybliometrics.cfg with default paths...
    Please enter your API Key(s), obtained from http://dev.elsevier.com/myapikey.html.  Separate multiple keys by comma:

This key is defined as an environment variable: SCOPUS_API_KEY
Can this be passed directly to pybliometrics?

FIXED: Modified all pybliometrics.scopus.init() calls to use SCOPUS_API_KEY environment variable when available. Created utility functions in both academic/utils.py and src/academicdb/utils.py to handle this initialization consistently across the codebase.

[x] A latex distribution needs to be installed within the docker container so that the PDF file can be rendered.

FIXED: Added texlive-xetex, texlive-fonts-recommended, and texlive-fonts-extra packages to the Dockerfile. This provides the xelatex engine required for CV PDF generation.

[x] The secret key for the server is currently defined as an unsafe plain text entry. That key should instead be read in from an environment variable defined by the user.  If that environment variable doesn't exist, then we should offer to create a random hash value and save it to the .env file so that it can be shared via the docker call.

FIXED: Modified Django settings to use SECRET_KEY environment variable in base.py. Created get_or_generate_secret_key() utility function in academic/utils.py that checks for environment variable, generates a random secret key if not found, and saves it to .env file. Updated docker.py settings to use this utility function for secure key management.