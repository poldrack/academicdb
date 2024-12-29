from abc import ABC, abstractmethod
from Bio import Entrez
from pybliometrics.scopus import AuthorRetrieval
import pybliometrics

# tomllib is included in standard library in Python 3.11+
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


class AbstractQuery(ABC):
    """ """

    def __init__(self, **kwargs):
        self.db = None
        self.results = None
        self.records = None

    @abstractmethod
    def query(self, query_string, **kwargs):
        """ """
        pass


class PubmedQuery(AbstractQuery):
    """ """

    def __init__(self, email, **kwargs):
        super().__init__(**kwargs)
        # an email address is required for Entrez queries
        Entrez.email = email

    def query(self, query_string, max_results=1000):
        with Entrez.esearch(
            db='pubmed', term=query_string, retmax=max_results
        ) as handle:
            record = Entrez.read(handle)

        id_list = record['IdList']
        if not id_list:
            return None

        with Entrez.efetch(
            db='pubmed', id=id_list, rettype='medline', retmode='xml'
        ) as handle:
            records = Entrez.read(handle)

        records_list = []
        for recordtype, records in records.items():
            records_list += list(records)

        return records_list


class ScopusQuery(AbstractQuery):
    """ """

    def __init__(self, **kwargs):
        pybliometrics.scopus.init()
        super().__init__(**kwargs)

    def query(self, query_string):
        pass

    def author_query(self, authorid):
        scopus_au = AuthorRetrieval(authorid)
        return scopus_au.get_documents(view='COMPLETE')
