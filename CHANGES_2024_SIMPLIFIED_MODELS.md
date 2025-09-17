# Model Simplification and CSV Import Unification - December 2024

## Overview
Major refactoring to simplify Conference and Talk models, and create a unified CSV import architecture that eliminates duplicate code between "Import CSV" buttons and "Sync Data Files" functionality.

## 1. Unified CSV Import Architecture

### Created `academic/csv_importers.py`
- Single source of truth for all CSV import logic
- Base `CSVImporter` class with common functionality
- Individual importers for each model:
  - `PublicationCSVImporter`
  - `TeachingCSVImporter`
  - `TalkCSVImporter`
  - `ConferenceCSVImporter`
  - `EditorialCSVImporter`
- Column validation ensures correct CSV formats
- Handles both creation and updates (by checking for existing records)

### Refactored `academic/data_ingestion.py`
- Now uses unified CSV importers via `_import_csv_unified()`
- Eliminated duplicate CSV parsing logic
- All ingestion functions now consistent

### Updated `academic/api_views.py`
- All ViewSets now use unified CSV importers
- Removed duplicate import logic from individual ViewSets
- Added `get_csv_importer()` method to `BaseBulkViewSet`

## 2. Conference Model Simplification

### Before (complex model):
- Fields: title, authors, year, location, month, conference_name, presentation_type, link, abstract, parsed_authors, additional_info, manual_edits, source, timestamps

### After (simplified model):
- Fields: authors, year, title, location, month, link, source, timestamps
- Removed: conference_name, presentation_type, abstract, parsed_authors, additional_info, manual_edits
- Migration: `0025_simplify_conference_model.py`

### Conference CSV Format:
```csv
authors,year,title,location,month,link
"John Doe","2023","My Presentation","New York","June","https://example.com"
```

## 3. Talk Model Simplification

### Before (complex model):
- Fields: year, place, title, date, invited, virtual, additional_info, manual_edits, source, timestamps

### After (simplified model):
- Fields: year, place, invited, source, timestamps
- Removed: title, date, virtual, additional_info, manual_edits
- Migration: `0026_simplify_talk_model.py`

### Talk CSV Format:
```csv
year,place,invited
"2023","Stanford University","true"
```

## 4. CSV Format Requirements

All CSV importers now validate column names (case-sensitive):

### Publications (additional_pubs.csv):
- Required: title
- Optional: type, year, authors, journal, volume, page, DOI, publisher, ISBN, editors

### Teaching (teaching.csv):
- Required: none (accepts either 'name' or 'course_name')
- Optional: level, name, course_name

### Talks (talks.csv):
- Required: year, place
- Optional: invited

### Conferences (conferences.csv):
- Required: authors, year, title
- Optional: location, month, link

### Editorial (editorial.csv):
- Required: role, journal
- Optional: dates

## 5. Test Updates

### Created `tests/unit/test_unified_csv_import.py`
- Comprehensive tests for unified CSV import architecture
- Tests for each importer class
- Error handling and validation tests

### Updated `tests/unit/test_data_file_ingestion.py`
- Fixed CSV formats to match new simplified models
- Use unique DOIs to avoid test conflicts
- Fixed case-sensitive column names (DOI not doi)

## 6. Bug Fixes

### Fixed Conference/Talk Import Issues:
- Column name case sensitivity (DOI vs doi)
- Updated test CSV formats to match new model structures
- Fixed "Sync Data Files" to use correct importers

### Key Discovery:
When importing CSVs, if a record already exists (matched by unique identifier like DOI), it's **updated** rather than created. The import functions return the count of **created** items, not updated ones.

## 7. Breaking Changes

### Database Schema Changes:
- Conference model structure significantly simplified
- Talk model structure significantly simplified
- Requires running migrations

### CSV Format Changes:
- Conference CSV format completely changed
- Talk CSV format simplified (no title/date)
- Column names are now case-sensitive

## 8. Benefits

1. **Code Deduplication**: Single source of truth for CSV import logic
2. **Consistency**: Both "Import CSV" buttons and "Sync Data Files" use identical logic
3. **Maintainability**: Changes to import logic only need to be made in one place
4. **Validation**: Centralized column validation ensures correct CSV formats
5. **Simplification**: Models are cleaner with only essential fields
6. **Testing**: Comprehensive test coverage for all import scenarios

## Files Modified

### Core Changes:
- `academic/csv_importers.py` (NEW)
- `academic/models.py` (simplified Conference and Talk models)
- `academic/data_ingestion.py` (refactored to use unified importers)
- `academic/api_views.py` (refactored to use unified importers)
- `academic/serializers.py` (updated for simplified models)

### Migrations:
- `academic/migrations/0025_simplify_conference_model.py` (NEW)
- `academic/migrations/0026_simplify_talk_model.py` (NEW)

### Tests:
- `tests/unit/test_unified_csv_import.py` (NEW)
- `tests/unit/test_data_file_ingestion.py` (updated CSV formats)

## Next Steps

1. Run migrations in production:
   ```bash
   python manage.py migrate
   ```

2. Update any existing CSV files to use new formats

3. Notify users of CSV format changes

4. Consider updating documentation with new CSV format requirements