import pytest
import sys
import os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(myPath, '../academcicdb'))

from src.academicdb.researcher import Researcher, researcher_fields

@pytest.fixture
def researcher():
    return Researcher()


def test_researcher_creation(researcher):
    assert researcher is not None
    assert researcher.metadata.orcid is not None
    for field in researcher_fields:
        assert hasattr(researcher, field)
 
def test_orcid_data(researcher):
    researcher.get_orcid_data()
    assert researcher.orcid_data is not None
    assert researcher.orcid_data['orcid-identifier']['path'] == researcher.metadata.orcid
    assert 'activities-summary' in researcher.orcid_data
    assert 'works' in researcher.orcid_data['activities-summary']

    researcher.get_orcid_dois()
    assert researcher.dois['orcid'] is not None

def test_pubmed_data(researcher):
    researcher.get_pubmed_data()
    assert researcher.pubmed_data is not None
    assert 'PubmedArticle' in researcher.pubmed_data
    assert len(researcher.pubmed_data['PubmedArticle']) > 250

# skip this test for now, because it takes a long time to run and is currently working
# def test_google_scholar(researcher):
#     researcher.get_google_scholar_data()
#     assert researcher.gscholar_data is not None


def test_get_publications(researcher):
    researcher.get_publications(maxret=5)
    assert researcher.publications is not None
    assert len(researcher.publications) == 5


def test_get_coauthors(researcher):
    researcher.get_publications(maxret=5)
    researcher.get_coauthors()
    assert researcher.coauthors is not None
