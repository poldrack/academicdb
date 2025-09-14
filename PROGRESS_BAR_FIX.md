# Progress Bar Fix for Sync All Databases Function

## Problem Summary
The progress bar for the "Sync All Databases" function was showing "initializing" then disappearing immediately, even though the sync process was still running in the background (visible in server console).

## Root Causes Identified

### 1. HTTP Header Error
- **Issue**: `AssertionError: Hop-by-hop header, 'Connection: keep-alive', not allowed`
- **Cause**: Django's WSGI handler doesn't allow manual setting of hop-by-hop headers
- **Impact**: Server-Sent Events connection failing immediately

### 2. Form Submission Problem
- **Issue**: Form was submitting normally causing page reload
- **Cause**: JavaScript AJAX handler wasn't properly preventing default form submission
- **Impact**: Page reload wiped out JavaScript state needed for progress tracking

### 3. Thread Synchronization Issues
- **Issue**: Progress tracking sync_id mismatch between view and background function
- **Cause**: Background function was generating its own sync_id instead of using the one from view
- **Impact**: EventSource couldn't find matching sync progress data

### 4. Race Conditions
- **Issue**: EventSource connecting before progress data was initialized
- **Cause**: Background thread starting concurrently with view response
- **Impact**: "No active sync found" errors causing immediate connection closure

### 5. Aggressive Error Handling
- **Issue**: Progress bar disappearing after 5 seconds on any EventSource error
- **Cause**: Error handler immediately hiding progress on connection issues
- **Impact**: Progress tracking terminated prematurely

## Solutions Implemented

### 1. Fixed HTTP Headers (`academic/views.py`)
```python
# Before:
response['Connection'] = 'keep-alive'

# After:
response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
# Removed Connection header (Django handles automatically)
```

### 2. Fixed Form Submission (`academic/templates/academic/dashboard.html`)
```javascript
// Added form submission prevention
const form = syncBtn.closest('form');
if (form) {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
    });
}

// Enhanced AJAX request with proper headers
fetch(form.action, {
    method: 'POST',
    body: formData,
    headers: {
        'X-CSRFToken': formData.get('csrfmiddlewaretoken'),
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
    }
})
```

### 3. Fixed Thread Synchronization (`academic/views.py`)
```python
# Before:
def run_comprehensive_sync_background(user_id):
    sync_id = f"sync_{user_id}_{int(time.time())}"

# After:
def run_comprehensive_sync_background(user_id, sync_id):
    # Use sync_id passed from view

# View now pre-initializes progress data before starting thread
sync_id = f"sync_{user.id}_{int(time.time())}"
sync_progress[sync_id] = { ... }  # Initialize first
sync_thread.start()
```

### 4. Improved User Sync Matching (`academic/views.py`)
```python
# Before:
user_syncs = {sid: data for sid, data in sync_progress.items()
             if str(user.id) in sid}

# After:
user_syncs = {sid: data for sid, data in sync_progress.items()
             if sid.startswith(f'sync_{user.id}_')}
```

### 5. Enhanced EventSource Error Handling (`academic/templates/academic/dashboard.html`)
```javascript
// Added comprehensive error handling and debugging
eventSource.onerror = function(event) {
    console.error('EventSource error occurred');
    console.error('EventSource readyState:', eventSource.readyState);

    if (eventSource.readyState === EventSource.CLOSED) {
        // Wait 10 seconds instead of 5, check status before giving up
        setTimeout(() => {
            checkSyncStatusDebug();
            // Only reset if sync hasn't completed
        }, 10000);
    }
};
```

### 6. Added Comprehensive Debugging
- Console logging for all progress events
- Sync status debugging function
- EventSource connection state monitoring
- Progress data inspection
- Timing analysis for race conditions

### 7. Fixed Command Names
Updated postprocessing tasks to use correct command:
```python
# Before:
('enrich_author_scopus_ids', 'Scopus author ID enrichment'),
('lookup_author_scopus_ids', 'Author Scopus ID lookup'),

# After:
('enrich_scopus_authors', 'DOI-based Scopus author ID enrichment'),
```

## Files Modified

### New Files
- `PROGRESS_BAR_FIX.md` - This documentation

### Modified Files
- `academic/views.py` - Fixed StreamingHttpResponse headers, thread synchronization, sync matching logic
- `academic/templates/academic/dashboard.html` - Fixed AJAX handling, EventSource error handling, added debugging
- `src/academicdb/problems_tbd.md` - Updated problem status

## Testing Verification

The fix addresses all identified issues:

1. **No HTTP header errors** - Removed problematic Connection header
2. **No page reloads** - Form submission handled entirely via AJAX
3. **Progress tracking works** - sync_id synchronization between view and background thread
4. **EventSource stability** - Improved error handling and recovery
5. **Real-time updates** - Server-Sent Events stream progress correctly
6. **Graceful completion** - Progress bar shows through to sync completion

## Expected Behavior After Fix

1. User clicks "Sync All Databases" button
2. Button shows "Starting..." immediately (no page reload)
3. Progress container appears with initialization message
4. EventSource connection establishes successfully
5. Real-time progress updates stream from server
6. Progress bar and status text update throughout sync process
7. Completion or error status shown when sync finishes
8. Console provides detailed debugging information

## Status: ✅ COMPLETED

The progress bar for "Sync All Databases" now correctly tracks the comprehensive sync process from start to completion with real-time updates and robust error handling.