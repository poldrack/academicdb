# Quickstart Guide: Academic Database Web Interface

**Date**: 2025-09-12  
**Purpose**: End-to-end validation scenarios for Django academic database web interface  
**Prerequisites**: Django app deployed, PostgreSQL configured, ORCID OAuth set up

---

## Quick Start Scenarios

### Scenario 1: New Researcher Registration & Setup

**Goal**: Validate complete user onboarding flow with ORCID authentication

**Steps**:
1. **Navigate to application**
   ```
   Open: http://localhost:8000/
   Expected: Landing page with "Login with ORCID" button
   ```

2. **ORCID Authentication**
   ```
   Click: "Login with ORCID"
   Expected: Redirect to ORCID OAuth (https://orcid.org/oauth/authorize)
   
   ORCID Login: Enter test credentials
   - ORCID iD: 0000-0002-1825-0097 (test account)
   - Password: [test password]
   Expected: ORCID consent screen
   
   Click: "Authorize"
   Expected: Redirect back to app with user profile creation form
   ```

3. **Profile Completion**
   ```
   Form Fields:
   - Institution: "Stanford University" 
   - Department: "Psychology"
   - Research Areas: ["Neuroimaging", "Data Science"]
   
   Click: "Complete Setup"
   Expected: Dashboard page with empty collections summary
   ```

4. **Validation**
   ```
   Check: User logged in (ORCID iD displayed in header)
   Check: Profile information saved
   Check: Empty collections dashboard displayed
   ```

**Success Criteria**: New researcher can authenticate with ORCID and access personalized dashboard

---

### Scenario 2: Publication Import & Management

**Goal**: Validate external API sync preserving manual edits

**Steps**:
1. **Initial Publication Sync**
   ```
   Navigate: Dashboard → Publications
   Click: "Sync from ORCID"
   
   Expected: Progress indicator
   Wait: Sync completion (should import publications from test ORCID profile)
   Expected: Publications list with ORCID-sourced publications
   ```

2. **Manual Publication Addition**
   ```
   Click: "Add Publication"
   Form Data:
   - DOI: "10.1000/test-manual"
   - Title: "Manual Test Publication"
   - Year: 2024
   - Authors: [{"name": "Test Author", "affiliation": "Test University"}]
   - Publication Type: "journal-article"
   
   Click: "Save"
   Expected: Publication added with source="manual"
   ```

3. **Publication Editing**
   ```
   Click: Edit on first ORCID publication
   Modify: Title from "Original Title" to "Edited Title"
   Modify: Add custom link: {"code_url": "https://github.com/test/repo"}
   
   Click: "Save Changes"
   Expected: manual_edits = {"title": true, "links": true}
   ```

4. **Re-sync Test**
   ```
   Click: "Sync from ORCID" again
   Expected: Progress indicator
   
   Validation:
   - Manually edited publication title remains "Edited Title"
   - Custom code link preserved
   - Other fields updated from ORCID if changed
   - manual_edits metadata preserved
   ```

**Success Criteria**: Manual edits preserved during external API synchronization

---

### Scenario 3: Collaboration Network Analysis

**Goal**: Validate coauthor tracking and NSF collaborator export

**Steps**:
1. **Coauthor Discovery**
   ```
   Navigate: Dashboard → Collaborators
   Expected: List of coauthors extracted from publications
   
   Sample coauthor data:
   - Name: "Jane Smith"
   - Scopus ID: "123456789" 
   - Current Institution: "Harvard University"
   - Collaborations: 3 publications
   - Last Collaboration: 2024-01-15
   ```

2. **Coauthor Information Update**
   ```
   Click: Edit on "Jane Smith"
   Update: Email to "jane.smith@harvard.edu"
   Update: Current Institution to "MIT"
   
   Click: "Save"
   Expected: Manual updates preserved, not overwritten by future syncs
   ```

3. **NSF Collaborator Export**
   ```
   Navigate: Collaborators → Export
   Filter: "Last 4 years" (2020-2024)
   Format: "NSF CSV"
   
   Click: "Generate Export"
   Expected: CSV download with format:
   Name,Institution,Collaboration Years
   "Jane Smith","MIT","2022,2023,2024"
   ```

**Success Criteria**: Accurate collaboration tracking with manual override capability

---

### Scenario 4: Multi-Collection Data Management

**Goal**: Validate CRUD operations across all collection types

**Steps**:
1. **Funding Record Management**
   ```
   Navigate: Dashboard → Funding
   Click: "Add Funding"
   
   Form Data:
   - Title: "NSF Career Award"
   - Agency: "National Science Foundation"
   - Amount: 500000.00
   - Start Date: 2024-01-01
   - End Date: 2028-12-31
   - Role: "Principal Investigator"
   
   Click: "Save"
   Expected: Funding record created and displayed
   ```

2. **Talk Record Management**
   ```
   Navigate: Dashboard → Talks
   Click: "Add Talk"
   
   Form Data:
   - Title: "Data Science in Psychology"
   - Venue: "APA Annual Convention"
   - Date: 2024-08-15
   - Type: "Invited Talk"
   - Location: "San Diego, CA"
   
   Click: "Save"
   Expected: Talk record created
   ```

3. **Bulk Operations Test**
   ```
   Navigate: Publications list
   Select: Multiple publications (checkboxes)
   Action: "Export Selected" → "BibTeX format"
   
   Expected: BibTeX file download with selected publications
   ```

**Success Criteria**: All collection types support full CRUD operations

---

### Scenario 5: CV Generation & Export

**Goal**: Validate CV export functionality with current data

**Steps**:
1. **CV Preview**
   ```
   Navigate: Dashboard → CV Export
   Sections: Select all (Publications, Education, Employment, etc.)
   Style: "APA Format"
   
   Click: "Preview"
   Expected: Formatted CV preview with all current data
   ```

2. **Export Formats**
   ```
   Test multiple formats:
   
   LaTeX Export:
   Click: "Export LaTeX"
   Expected: .tex file download with proper LaTeX formatting
   
   PDF Export:
   Click: "Export PDF" 
   Expected: PDF file download (if LaTeX → PDF conversion available)
   
   JSON Export:
   Click: "Export JSON"
   Expected: Structured JSON with all data
   ```

3. **Custom Formatting**
   ```
   Settings: Citation Style → "Chicago"
   Sections: Uncheck "Service" and "Memberships"
   
   Click: "Export PDF"
   Expected: PDF with Chicago citation style, selected sections only
   ```

**Success Criteria**: CV exports accurately reflect current database state

---

### Scenario 6: Data Integrity & Security

**Goal**: Validate user data isolation and security measures

**Steps**:
1. **User Data Isolation**
   ```
   Create second test user account (different ORCID)
   Login as User 2
   
   Navigate: Publications
   Expected: Only User 2's publications visible
   Expected: No access to User 1's data
   ```

2. **Permission Testing**
   ```
   Attempt direct URL access to User 1's publication:
   URL: http://localhost:8000/api/v1/publications/1/
   
   Expected: 404 Not Found or 403 Forbidden (if publication belongs to User 1)
   ```

3. **Data Validation**
   ```
   Attempt invalid data entry:
   - DOI: "invalid-doi-format"
   - Year: 1800 (too old)
   - Email: "invalid-email"
   
   Expected: Validation errors with clear messages
   ```

**Success Criteria**: Users can only access their own data, validation prevents invalid entries

---

## Performance Validation

### Load Testing Scenarios

**Database Performance**:
```bash
# Simulate realistic academic database sizes
- 500 publications per researcher
- 200 coauthors per researcher  
- 50+ concurrent researchers
- Complex search queries (author, year, keyword)

Expected Response Times:
- Dashboard load: <2 seconds
- Publication search: <500ms
- API endpoints: <200ms median
```

**Memory Usage**:
```bash
# Monitor during heavy operations
- Large publication import (1000+ records)
- Complex coauthor network analysis
- Concurrent user sessions

Expected: <512MB peak memory usage
```

---

## Error Handling Validation

**Network Issues**:
- ORCID API unavailable → Graceful fallback, clear error messages
- Database connection lost → User-friendly error, session preservation
- External API timeouts → Partial sync with retry mechanisms

**Data Conflicts**:
- Duplicate DOIs → Clear conflict resolution interface
- Malformed API data → Skip with logging, continue processing
- Concurrent edits → Last-write-wins with change notification

---

## Deployment Validation

**Environment Setup**:
```bash
# Test production-like deployment
docker-compose up -d  # PostgreSQL, Django, Redis
python manage.py migrate
python manage.py collectstatic
python manage.py test

# Integration test with real ORCID sandbox
python manage.py test tests.integration.test_orcid_auth
```

**Configuration Validation**:
- ORCID OAuth credentials working
- PostgreSQL connection established  
- Django settings for production security
- Static file serving configured
- Logging and monitoring operational

---

## Success Metrics

**Functional Validation**:
- [ ] All user scenarios complete without errors
- [ ] Data integrity maintained across operations
- [ ] Performance targets met under load
- [ ] Security measures prevent unauthorized access
- [ ] Export formats generate correctly

**Technical Validation**:
- [ ] All API endpoints respond correctly
- [ ] Database queries optimized (no N+1 problems)
- [ ] Error handling graceful and informative
- [ ] Integration tests pass with real external APIs
- [ ] Migration scripts work with production data volumes

**User Experience Validation**:
- [ ] ORCID authentication seamless
- [ ] Interface intuitive for academic researchers
- [ ] Data import/export matches expectations
- [ ] Manual edit preservation works reliably
- [ ] CV generation produces publication-ready output

---

*Quickstart scenarios complete - ready for implementation task generation.*