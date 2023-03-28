from abc import ABC, abstractmethod
import pymongo
import logging


class AbstractDatabase(ABC):
    def __init__(self, **kwargs):
        self.db = None
        self.collections = ['coauthors', 'funding', 'conferences', 'talks', 
            'education', 'employment', 'distinctions', 'metadata', 'publications',
            'invited_positions', 'memberships', 'service', 'trainees', 'pmcid']

    @abstractmethod
    def setup_db(self,  **kwargs):
        pass

    @abstractmethod
    def setup_collections(self,  **kwargs):
        pass

    @abstractmethod
    def connect(self, **kwargs):
        pass

    @abstractmethod
    def query(self, query_string: str, **kwargs):
        pass

    @abstractmethod
    def add(self, table: str, content: dict, **kwargs):
        pass


class MongoDatabase(AbstractDatabase):
    def __init__(self, dbname: str ='academicdb', overwrite: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.client = None
        self.dbname = dbname
        self.overwrite = overwrite

    def connect(self, **kwargs):
        self.client = pymongo.MongoClient(host="127.0.0.1", port=27017)

    def setup_db(self, **kwargs):
        # it exists and overwrite is False, just return client
        if self.dbname in self.client.list_database_names() and not overwrite:
            # check to make sure only one metadata record exists
            if len(list(self.client[self.dbname]['metadata'].find())) > 1:
                raise ValueError(
                    "more than one metadata record exists in the database - please rerun with overwrite set to True")
            logging.debug("keeping existing database")

        # otherwise clean everything out and start over
        elif self.dbname in self.client.list_database_names():
            logging.debug('dropping database')
            if self.collections is None:
                for c in self.collections:
                    self.client[self.dbname].drop_collection(c)
            self.client[self.dbname].drop_database(self.dbname)


    def setup_collections(self, **kwargs):
        logging.debug('setting up collections')
        result = self.client[self.dbname]
        for c in self.collections:
            if c not in result.list_collection_names():
                result.create_collection(c)
        indices_to_create = {
            'metadata': 'orcid',
            'publications': 'eid',
            'pmcid': 'pmid',
        }
        for c, idx in indices_to_create.items():
            logging.debug(f'creating index {idx} on collection {c}')
            result[c].create_index([(idx, pymongo.ASCENDING)], unique=True)

    def query(self, query_string: str, **kwargs):
        pass


# dependency inversion
class Database():
    def __init__(self, db: AbstractDatabase, **kwargs):
        super().__init__(**kwargs)
        self.db = db

    def query(self, query_string: str, **kwargs):
        self.db.query(query_string, **kwargs)

    def connect(self, **kwargs):
        self.db.connect(**kwargs)

    def disconnect(self, **kwargs):
        self.db.disconnect(**kwargs)
