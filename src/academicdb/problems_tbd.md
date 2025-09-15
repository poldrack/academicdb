## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]
**IMPORTANT**: Only mark a problem as fixed once the user has confirmed that the fix worked.  

[x] Login using ORCID doesn't seem to be working anymore.
    FIXED: Updated site domain from localhost:8000 to 127.0.0.1:8000 to match ORCID OAuth redirect URI configuration. ORCID login now works correctly and users are successfully authenticated. 