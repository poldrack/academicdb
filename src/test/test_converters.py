## tests for the recordConverter module
import pytest
import sys
sys.path.append('../academicdb')
from src.academicdb.query import PubmedQuery
from src.academicdb.recordConverter import (
    AbstractRecordConverter,
    PubmedRecordConverter
)
from src.test.required_fields import required_fields

@pytest.fixture
def pubmed_record():
    pubmed_search = PubmedQuery()
    query_string = "31452104"  # PubMed ID known to return a single record
    results = pubmed_search.query(query_string, max_results=1)
    assert len(results) == 1
    assert "MedlineCitation" in results[0]
    return(results[0])


# smoke test for AbstractRecordConverter
def test_abstract_record_converter():
    with pytest.raises(TypeError):
        AbstractRecordConverter()


def check_required_fields(pub):
    for field in required_fields:
        assert field in pub


def test_pubmed_converter(pubmed_record):
    pub = PubmedRecordConverter(pubmed_record).convert()
    check_required_fields(pub)
