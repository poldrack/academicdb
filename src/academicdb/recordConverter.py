## create an abstract base class for record conversion
from abc import ABC, abstractmethod
from pybliometrics.scopus import AbstractRetrieval
from crossref.restful import Works
from . import query # import PubmedQuery
from . import pubmed # import parse_pubmed_record
from . import crossref_utils
import logging


class AbstractRecordConverter(ABC):
    """
    """
    def __init__(self, record):
        self.record = record
        self.pub = None

    def convert(self):
        """
        """
        pass
    

class PubmedRecordConverter(AbstractRecordConverter):
    """
    """
    def __init__(self, record):
        super().__init__(record)

    def convert(self):
        """
        """
        self.pub = pubmed.parse_pubmed_record(self.record)
        return(self.pub)
    

class ScopusRecordConverter(AbstractRecordConverter):
    """
    """
    def __init__(self, record, email):
        super().__init__(record)
        self.email = email

    def convert(self):
        """
        """
        crossref_record = Works().doi(self.record.doi)
        pubmed_record = query.PubmedQuery(email=self.email).query(self.record.doi)
        if pubmed_record is None:
            return None
        # TODO - deal with multiple pubmed records per doi
        if len(pubmed_record) > 1:
            logging.warning(f'Multiple pubmed records found for doi: {self.record.doi}')
    
        self.pub = pubmed.parse_pubmed_record(pubmed_record[0])
        self.pub['scopus_coauthor_ids'] = self.record.author_ids.split(';')
        return(self.pub)

    

class CrossrefRecordConverter(AbstractRecordConverter):
    """
    """
    def __init__(self, record):
        super().__init__(record)

    def convert(self):
        """
        """
        self.pub = crossref_utils.parse_crossref_record(self.record)
        return(self.pub)
    
