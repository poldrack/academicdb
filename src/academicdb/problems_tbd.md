## Problems to be fixed

Open problems marked with [ ]
Fixed problems marked with [x]

[x] Add an button on the Editorial page to delete all entries in the Editorial table.
    - COMPLETED: Added delete all button to Editorial spreadsheet interface
    - Implementation: Uses API endpoint `/api/v1/editorial/delete_all/` with confirmation dialog
    - Testing: All tests passing

[x] Convert Editorial to use spreadsheet interface like other models
    - COMPLETED: Editorial now uses the same spreadsheet interface as talks, teaching, conferences
    - Created: EditorialViewSet, EditorialSerializer, editorial_spreadsheet.html template
    - Features: Import CSV, Delete All, inline editing via spreadsheet interface
    - Consistency: All models now use the same API-based pattern

[ ] Create unified CSV import architecture (IN PROGRESS)
    - ROOT CAUSE: Duplicate logic between individual "Import CSV" buttons and "Sync Data Files"
    - PLAN: Create single csv_importers.py module that both systems use
    - CURRENT STATUS: All models now have consistent API-based CSV import methods
    - NEXT STEPS:
      1. Extract common CSV import logic into csv_importers.py
      2. Refactor API ViewSets to use unified functions
      3. Refactor data_ingestion.py to use unified functions
      4. Ensure data_ingestion.py calls the same logic as Import CSV buttons

## Technical Implementation Notes

### Current Architecture (GOOD):
- All models (editorial, teaching, talks, conferences) use API ViewSets with import_csv methods
- Spreadsheet interfaces call API endpoints consistently
- Delete all functionality works via API endpoints
- Source field standardized to 'csv_import' across all imports

### Next Phase - Unified CSV Import:
```
academic/
├── csv_importers.py          # NEW: Single source of truth for CSV logic
├── api_views.py             # REFACTOR: Call csv_importers functions
├── data_ingestion.py        # REFACTOR: Call csv_importers functions
└── views.py                 # Keep existing upload views for legacy support
```

This will ensure "Import CSV" buttons and "Sync Data Files" use identical logic.