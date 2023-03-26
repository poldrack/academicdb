from abc import ABC, abstractmethod
from Bio import Entrez
# tomllib is included in standard library in Python 3.11+
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from .recordConverter import PubmedRecordConverter


class AbstractQuery(ABC):
    """
    """
    def __init__(self, **kwargs):
        self.db = None
        self.results = None
        self.records = None

    @abstractmethod
    def query(self, query_string, **kwargs):
        """
        """
        pass


class PubmedQuery(AbstractQuery):
    """
    """
    def __init__(self, email=None, **kwargs):
        super().__init__(**kwargs)
        if email is None:
            with open("config.toml", 'rb') as f:
                config = tomllib.load(f)
            email = config['biopython']['email']
            assert email is not None, \
                "No email provided for Entrez query (in congig.toml or as argument)"
        Entrez.email = email

    def query(self, query_string, max_results=10):
        with Entrez.esearch(db="pubmed", term=query_string, retmax=max_results) as handle:
            record = Entrez.read(handle)

        id_list = record["IdList"]
        if not id_list: 
            return None

        with Entrez.efetch(db="pubmed", id=id_list, rettype="medline", retmode="xml") as handle:
            records = Entrez.read(handle)

        records_list = []
        for recordtype, records in records.items():
            records_list += list(records)

        return records_list


if __name__ == "__main__":
    # Example usage
    email = "your_email@example.com"
    pubmed_search = PubmedQuery(email)
    query_string = "cancer"
    results = pubmed_search.query(query_string)

    pub = []
    for record in results:
        pub.append(PubmedRecordConverter(record).convert())

