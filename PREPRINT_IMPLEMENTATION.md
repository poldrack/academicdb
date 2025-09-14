# Preprint Detection Implementation

## Overview
Successfully implemented automatic preprint detection for publications based on DOI patterns. Publications from bioRxiv, arXiv, and PsyArXiv are automatically identified and marked with appropriate badges in the UI.

## Implementation Details

### 1. Model Changes (`academic/models.py`)

#### New Field
- Added `is_preprint` BooleanField to Publication model
- Defaults to False, automatically detected from DOI

#### New Methods
- `is_preprint_doi(doi)` - Static method to detect preprint DOIs
- `detect_preprint_status()` - Instance method to update preprint status
- `preprint_server` - Property to get preprint server name
- Enhanced `save()` method to auto-detect preprint status

#### Preprint Server Detection
Supports the following preprint servers:
- **bioRxiv**: DOIs starting with `10.1101`
- **arXiv**: DOIs starting with `10.48550`
- **PsyArXiv**: DOIs starting with `10.31234`

### 2. Database Migration
- Created migration `0009_add_preprint_field.py`
- Updated existing publications using management command

### 3. Management Command (`academic/management/commands/detect_preprints.py`)
- `detect_preprints` command to update existing publications
- Supports dry-run mode for testing
- Successfully identified and marked 37 preprints from 458 publications

### 4. API Integration (`academic/serializers.py`)
- Added `is_preprint` and `preprint_server` fields to PublicationSerializer
- Both fields are read-only (automatically computed)
- `preprint_server` uses ReadOnlyField to access model property

### 5. UI Updates

#### Publication List Template (`academic/templates/academic/publication_list.html`)
- Added yellow "Preprint" badges next to publication titles
- Badges include tooltip showing preprint server name
- Icon uses Font Awesome file-alt icon

#### Publication Detail Template (`academic/templates/academic/publication_detail.html`)
- Added "Preprint" badge to title in card header
- Added dedicated "Preprint:" row in Basic Information section
- Shows server name (e.g., "bioRxiv Preprint")

## Results

### Detection Statistics
- **Total publications checked**: 458
- **Preprints identified**: 37 (7.8%)
- **Server breakdown**: All 37 were bioRxiv preprints (10.1101/*)

### User Experience
- Preprints are clearly marked with yellow badges
- Consistent styling across list and detail views
- Informative tooltips show preprint server
- No disruption to existing workflows

### API Response Example
```json
{
    "id": 960,
    "title": "Frontostriatal salience network expands...",
    "is_preprint": true,
    "preprint_server": "bioRxiv",
    "doi": "10.1101/2025.05.21.654808"
}
```

## Technical Features

### Automatic Detection
- Preprint status is automatically detected on publication save
- Works for both new publications and updates
- Preserves manual edits through existing edit protection system

### Performance
- Static method for DOI checking (no database queries)
- Efficient property-based server name resolution
- Index-friendly boolean field for filtering

### Extensibility
- Easy to add new preprint servers by updating DOI prefix list
- Centralized detection logic in model methods
- Consistent badge styling through CSS classes

## Future Enhancements

### Potential Additions
- **medRxiv**: DOIs starting with `10.1101` (subset of bioRxiv)
- **ChemRxiv**: DOIs starting with `10.26434`
- **SSRN**: DOIs starting with `10.2139`
- **RePEc**: Various DOI patterns

### Advanced Features
- Preprint publication date vs. journal publication date tracking
- Automatic linking between preprint and published versions
- Status transitions (preprint → published)
- Email notifications when preprints get published

## Files Modified
1. `academic/models.py` - Added preprint field and detection methods
2. `academic/serializers.py` - Added preprint fields to API
3. `academic/templates/academic/publication_list.html` - Added list view badges
4. `academic/templates/academic/publication_detail.html` - Added detail view badges
5. `academic/management/commands/detect_preprints.py` - Management command for updates

## Files Added
- `academic/migrations/0009_add_preprint_field.py` - Database migration
- `PREPRINT_IMPLEMENTATION.md` - This documentation

## Testing Results
✅ Model methods correctly detect DOI patterns
✅ Database migration applied successfully
✅ Existing publications updated correctly (37/458)
✅ UI badges display properly in list and detail views
✅ API serialization includes preprint fields
✅ Auto-detection works on new publication saves