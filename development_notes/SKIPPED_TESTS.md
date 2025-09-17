# Skipped Tests Documentation

This document provides detailed information about the 15 tests that are currently skipped in the test suite and the rationale for skipping them.

## Summary
- **Total Skipped**: 15 tests
- **Integration Tests for Future Functionality**: 12 tests
- **Feature-Specific Tests**: 2 tests
- **Implementation-Dependent Tests**: 1 test

## Detailed Breakdown

### 1. External API Integration Tests (12 tests skipped)

**File**: `tests/integration/test_external_api_mocking.py`
**Skip Reason**: These tests require the `academic.services` module which contains external API integration logic that hasn't been implemented yet.

#### ORCID Integration Tests (3 tests)
**Class**: `TestORCIDIntegration`
**Skip Decorator**: `@pytest.mark.skip(reason="Requires academic.services.orcid module to be implemented")`

1. **`test_orcid_publication_sync_success`**
   - **Purpose**: Test successful ORCID publication synchronization
   - **Mock Pattern**: ORCID API response with publication data
   - **Expected Behavior**: Sync publications from ORCID to local database
   - **Dependencies**: `academic.services.orcid.sync_orcid_publications`

2. **`test_orcid_api_error_handling`**
   - **Purpose**: Test handling of ORCID API errors (401, 403, etc.)
   - **Mock Pattern**: ORCID API error responses
   - **Expected Behavior**: Graceful error handling and user notification
   - **Dependencies**: `academic.services.orcid.sync_orcid_publications`

3. **`test_orcid_rate_limiting`**
   - **Purpose**: Test ORCID API rate limiting handling
   - **Mock Pattern**: HTTP 429 response with Retry-After header
   - **Expected Behavior**: Respect rate limits and retry after specified time
   - **Dependencies**: `academic.services.orcid.sync_orcid_publications`

#### Scopus Integration Tests (2 tests)
**Class**: `TestScopusIntegration`
**Skip Decorator**: `@pytest.mark.skip(reason="Requires academic.services.scopus module to be implemented")`

4. **`test_scopus_publication_search`**
   - **Purpose**: Test Scopus publication search functionality
   - **Mock Pattern**: Scopus API search response with publication results
   - **Expected Behavior**: Search and retrieve publications from Scopus
   - **Dependencies**: `academic.services.scopus.search_publications`

5. **`test_scopus_api_key_error`**
   - **Purpose**: Test Scopus API key authentication error handling
   - **Mock Pattern**: HTTP 401 response for invalid API key
   - **Expected Behavior**: Handle authentication errors gracefully
   - **Dependencies**: `academic.services.scopus.search_publications`

#### PubMed Integration Tests (2 tests)
**Class**: `TestPubMedIntegration`
**Skip Decorator**: `@pytest.mark.skip(reason="Requires academic.services.pubmed module to be implemented")`

6. **`test_pubmed_search_success`**
   - **Purpose**: Test successful PubMed search functionality
   - **Mock Pattern**: PubMed eSearch and eSummary API responses
   - **Expected Behavior**: Search PubMed and retrieve publication metadata
   - **Dependencies**: `academic.services.pubmed.search_publications`

7. **`test_pubmed_no_results`**
   - **Purpose**: Test PubMed search with no results
   - **Mock Pattern**: Empty PubMed search response
   - **Expected Behavior**: Handle empty search results gracefully
   - **Dependencies**: `academic.services.pubmed.search_publications`

#### CrossRef Integration Tests (2 tests)
**Class**: `TestCrossRefIntegration`
**Skip Decorator**: `@pytest.mark.skip(reason="Requires academic.services.crossref module to be implemented")`

8. **`test_crossref_doi_lookup`**
   - **Purpose**: Test CrossRef DOI metadata lookup
   - **Mock Pattern**: CrossRef API response with publication metadata
   - **Expected Behavior**: Retrieve publication metadata by DOI
   - **Dependencies**: `academic.services.crossref.get_publication_metadata`

9. **`test_crossref_doi_not_found`**
   - **Purpose**: Test CrossRef lookup for non-existent DOI
   - **Mock Pattern**: HTTP 404 response from CrossRef API
   - **Expected Behavior**: Handle missing DOI gracefully
   - **Dependencies**: `academic.services.crossref.get_publication_metadata`

#### Comprehensive API Workflow Tests (3 tests)
**Class**: `TestAPIIntegrationWorkflow`
**Skip Decorator**: `@pytest.mark.skip(reason="Requires academic.services module to be implemented")`

10. **`test_comprehensive_publication_sync`**
    - **Purpose**: Test syncing publications from multiple external sources
    - **Mock Pattern**: Comprehensive sync service response
    - **Expected Behavior**: Coordinate sync across ORCID, Scopus, PubMed
    - **Dependencies**: `academic.services.comprehensive_sync`

11. **`test_duplicate_detection_across_sources`**
    - **Purpose**: Test duplicate publication detection when syncing from multiple sources
    - **Mock Pattern**: Sync response with duplicate detection results
    - **Expected Behavior**: Identify and merge duplicate publications
    - **Dependencies**: `academic.services.comprehensive_sync`

12. **`test_sync_with_manual_edit_preservation`**
    - **Purpose**: Test that manual edits are preserved during external API sync
    - **Mock Pattern**: Sync operation that encounters manually edited publications
    - **Expected Behavior**: Skip updating fields marked as manually edited
    - **Dependencies**: `academic.services.comprehensive_sync`

### 2. Model Functionality Tests (2 tests skipped)

**File**: `tests/regression/test_model_behavior.py`

13. **`test_year_validation_constraints`**
    - **Class**: `TestPublicationModelBehavior`
    - **Skip Reason**: Implementation details of year validation not fully specified
    - **Purpose**: Test year field validation constraints on Publication model
    - **Expected Behavior**: Validate publication year ranges and constraints
    - **Location**: Line in test file with skip logic

14. **`test_search_functionality`**
    - **Class**: `TestPublicationModelBehavior`
    - **Skip Reason**: PostgreSQL full-text search features not available in SQLite test database
    - **Purpose**: Test publication full-text search functionality
    - **Mock Pattern**: Uses pytest.skip when search fails with PostgreSQL-specific features
    - **Expected Behavior**: Search publications by title, abstract, authors
    - **Dependencies**: PostgreSQL with full-text search extensions

### 3. Data Isolation Tests (1 test skipped)

**File**: `tests/unit/test_user_data_isolation.py`

15. **`test_funding_isolation`**
    - **Class**: `TestUserDataIsolation`
    - **Skip Reason**: Funding model API endpoints not yet implemented
    - **Purpose**: Test that users can only access their own funding records
    - **Expected Behavior**: Validate funding data isolation between users
    - **Dependencies**: Funding API endpoints (`/api/v1/funding/`)

## Re-enabling Skipped Tests

### For External API Integration Tests (Tests 1-12)
**Prerequisites**:
1. Implement `academic/services/` module directory
2. Create service modules: `orcid.py`, `scopus.py`, `pubmed.py`, `crossref.py`
3. Implement the following functions:
   - `academic.services.orcid.sync_orcid_publications(user)`
   - `academic.services.scopus.search_publications(author_id)`
   - `academic.services.pubmed.search_publications(query)`
   - `academic.services.crossref.get_publication_metadata(doi)`
   - `academic.services.comprehensive_sync(user)`

**Steps to Re-enable**:
1. Remove `@pytest.mark.skip()` decorators from test classes
2. Implement the actual service functions
3. Update mock patterns to match actual service interfaces
4. Run tests: `pytest tests/integration/test_external_api_mocking.py -v`

### For Model Functionality Tests (Tests 13-14)
**For test_year_validation_constraints**:
1. Clarify year validation requirements
2. Implement validation logic in Publication model
3. Remove skip logic from test
4. Run: `pytest tests/regression/test_model_behavior.py::TestPublicationModelBehavior::test_year_validation_constraints -v`

**For test_search_functionality**:
1. Either implement PostgreSQL test database configuration
2. Or modify test to work with SQLite full-text search
3. Update search method implementation
4. Run: `pytest tests/regression/test_model_behavior.py::TestPublicationModelBehavior::test_search_functionality -v`

### For Data Isolation Tests (Test 15)
**For test_funding_isolation**:
1. Implement Funding API endpoints in `academic/api_views.py`
2. Add funding URLs to `academic/api_urls.py`
3. Create FundingSerializer if not exists
4. Remove skip decorator from test
5. Run: `pytest tests/unit/test_user_data_isolation.py::TestUserDataIsolation::test_funding_isolation -v`

## Test Framework Benefits

These skipped tests demonstrate several key benefits of the testing framework:

1. **Future-Ready**: Tests are written and ready for when features are implemented
2. **Documentation**: Tests serve as specification for expected behavior
3. **Comprehensive Coverage**: All aspects of external API integration are considered
4. **Regression Prevention**: Once enabled, these tests will prevent breaking changes
5. **Development Guidance**: Clear requirements for what needs to be implemented

## Monitoring Skipped Tests

Regular review of skipped tests ensures:
- Tests are re-enabled as features are implemented
- Skipped tests remain relevant to current architecture
- New functionality includes corresponding test coverage
- Technical debt related to unimplemented features is tracked

**Recommendation**: Review this document quarterly and after major feature releases to update the status of skipped tests.

Last Updated: 2025-01-16