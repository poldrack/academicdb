## create an abstract base class for record conversion
from abc import ABC, abstractmethod
from .pubmed import parse_pubmed_record


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
    
# create a converter for pubmed records

class PubmedRecordConverter(AbstractRecordConverter):
    """
    """
    def __init__(self, record):
        super().__init__(record)
        self.pub_type = 'pubmed'

    def convert(self):
        """
        """
        self.pub = parse_pubmed_record(self.record)
        return(self.pub)
    
