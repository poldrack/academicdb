import pytest
import sys
import os

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import tomli_w

myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(myPath, '../academcicdb'))

from src.academicdb.researcher import Researcher, researcher_fields


@pytest.fixture(scope='session')
def config_file(tmp_path_factory):
    config = {
        'researcher': {
            'lastname': 'poldrack',
            'middlename': 'alan',
            'firstname': 'russell',
            'email': 'russ@nowhere.edu',
            'orcid': '0000-0001-6755-0259',
            'query': 'poldrack-r',
            'url': 'http://poldrack.github.io',
            'twitter': '@russpoldrack',
            'github': 'http://github.com/poldrack',
            'phone': '650-497-8488',
            'scholar_id': 'RbmLvDIAAAAJi',
            'scopus_id': '7004739390',
            'address': [
                'Stanford University',
                'Department of Psychology',
                'Building 420',
                '450 Jane Stanford Way',
                'Stanford, CA, 94305-2130',
            ],
        }
    }
    fn = tmp_path_factory.mktemp('data') / 'config.toml'
    with open(fn, 'wb') as f:
        tomli_w.dump(config, f)
    return fn


@pytest.fixture
def researcher(config_file):
    return Researcher(config_file)


def test_researcher_creation(researcher):
    assert researcher is not None
    assert researcher.metadata.orcid is not None
    for field in researcher_fields:
        assert hasattr(researcher, field)


def test_orcid_data(researcher):
    researcher.get_orcid_data()
    assert researcher.orcid_data is not None
    assert (
        researcher.orcid_data['orcid-identifier']['path']
        == researcher.metadata.orcid
    )
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
    assert len(researcher.coauthors) >= len(researcher.publications)
