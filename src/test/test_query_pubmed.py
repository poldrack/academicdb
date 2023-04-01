import pytest
import sys

sys.path.append('../academicdb')
from src.academicdb.query import PubmedQuery

@pytest.fixture
def email():
    return 'nobody@nowhere.edu'


def test_single_record_returned(email):
    pubmed_search = PubmedQuery(email=email)
    query_string = '31452104'  # PubMed ID known to return a single record
    results = pubmed_search.query(query_string, max_results=1)

    assert len(results) == 1
    assert 'MedlineCitation' in results[0]


def test_multiple_records_returned(email):
    pubmed_search = PubmedQuery(email=email)
    query_string = 'cancer'
    results = pubmed_search.query(query_string, max_results=5)

    assert len(results) > 1
    for record in results:
        assert 'MedlineCitation' in record


def test_no_records_returned(email):
    pubmed_search = PubmedQuery(email=email)
    query_string = 'non_existing_pubmed_id:00000000'  # A query that should not match any records
    results = pubmed_search.query(query_string)

    assert results is None
