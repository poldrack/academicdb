## tests for the recordConverter module
import pytest
import sys
import os
from crossref.restful import Works

sys.path.append('../academicdb')
from src.academicdb.query import PubmedQuery, ScopusQuery
from src.academicdb.recordConverter import (
    AbstractRecordConverter,
    PubmedRecordConverter,
    ScopusRecordConverter,
    CrossrefRecordConverter,
)
from src.academicdb.utils import load_config
from src.test.required_fields import required_fields


@pytest.fixture
def pubmed_record():
    pubmed_search = PubmedQuery(email='nobody@nowhere.edu')
    query_string = '31452104'  # PubMed ID known to return a single record
    results = pubmed_search.query(query_string, max_results=1)
    assert len(results) == 1
    assert 'MedlineCitation' in results[0]
    return results[0]


@pytest.fixture
def scopus_record():
    scopus_search = ScopusQuery()
    authorid = '7004739390'
    results = scopus_search.author_query(authorid)
    assert len(results) > 300
    return results[0]


@pytest.fixture
def crossref_record():
    return Works().doi('10.1007/s11229-020-02793-y')


@pytest.fixture
def email():
    return 'nobody@nowhere.edu'


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


def test_scopus_converter(scopus_record, email):
    result = ScopusRecordConverter(scopus_record, email).convert()
    assert result is not None


def test_crossref_converter(crossref_record):
    result = CrossrefRecordConverter(crossref_record).convert()
    assert result is not None
