from abc import ABC, abstractmethod
import pymongo
import logging


class AbstractDatabase(ABC):
    def __init__(self, **kwargs):
        self.db = None
        self.collections = [
            'coauthors',
            'funding',
            'conference',
            'talks',
            'education',
            'employment',
            'distinctions',
            'metadata',
            'publications',
            'memberships',
            'service',
            'trainees',
        ]

    @abstractmethod
    def setup_db(self, **kwargs):
        pass

    @abstractmethod
    def setup_collections(self, **kwargs):
        pass

    @abstractmethod
    def connect(self, **kwargs):
        pass

    @abstractmethod
    def query(self, query_string: str, **kwargs):
        pass

    @abstractmethod
    def add(self, table: str, content: list, **kwargs):
        pass

    @abstractmethod
    def list_collections(self, **kwargs):
        pass

    @abstractmethod
    def get_collection(self, collection_name: str, **kwargs):
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str, **kwargs):
        pass


class MongoDatabase(AbstractDatabase):
    def __init__(
        self,
        dbname: str = 'academicdb',
        connect_string: str = None,
        overwrite: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = None
        self.dbname = dbname
        self.overwrite = overwrite
        self.connect_string = connect_string

        self.connect()
        self.setup_db()
        self.setup_collections()

    def connect(self, **kwargs):
        if self.connect_string is not None:
            self.client = pymongo.MongoClient(self.connect_string)
        else:
            self.client = pymongo.MongoClient(host='127.0.0.1', port=27017)

    def setup_db(self, **kwargs):
        # it exists and overwrite is False, just make sure metadata are ok
        if (
            self.dbname in self.client.list_database_names()
            and not self.overwrite
        ):
            # check to make sure only one metadata record exists
            if len(list(self.client[self.dbname]['metadata'].find())) > 1:
                raise ValueError(
                    'more than one metadata record exists in the database - please rerun with overwrite set to True'
                )
            logging.info('keeping existing database')

        # otherwise clean everything out and start over
        elif self.dbname in self.client.list_database_names():
            logging.info('dropping database')
            if self.collections is None:
                for c in self.collections:
                    self.client[self.dbname].drop_collection(c)
            self.client.drop_database(self.dbname)

    def setup_collections(self, **kwargs):
        logging.info('setting up collections')
        result = self.client[self.dbname]
        for c in self.collections:
            if c not in result.list_collection_names():
                logging.debug(f'creating collection {c}')
                result.create_collection(c)
        indices_to_create = {
            'publications': 'DOI',
            'pmcid': 'pmid',
        }
        for c, idx in indices_to_create.items():
            logging.debug(f'creating index {idx} on collection {c}')
            result[c].create_index([(idx, pymongo.ASCENDING)], unique=True)

    def query(self, query_string: str, **kwargs):
        pass

    def add(self, table: str, content: list, **kwargs):
        if table not in self.list_collections():
            self.client[self.dbname].create_collection(table)

        for c in content:
            if table == 'publications':
                if c and 'DOI' in c:
                    self.client[self.dbname][table].update_one(
                        {'DOI': c['DOI']}, {'$set': c}, upsert=True
                    )
                else:
                    logging.warning(f'no DOI found in publication: {c}')
            else:
                self.client[self.dbname][table].insert_one({'$set': c})

    def list_collections(self, **kwargs):
        return self.client[self.dbname].list_collection_names()

    def get_collection(self, collection_name: str, **kwargs):
        # deal with some tables that don't use $set
        testitem = self.client[self.dbname][collection_name].find_one({})
        if testitem is not None:
            if '$set' not in testitem:
                return list(self.client[self.dbname][collection_name].find({}))
            else:
                return [
                    item['$set']
                    for item in self.client[self.dbname][collection_name].find({})
                ]

    def drop_collection(self, collection_name: str, **kwargs):
        self.client[self.dbname].drop_collection(collection_name)


# dependency inversion
class Database:
    def __init__(self, db: AbstractDatabase, **kwargs):
        super().__init__(**kwargs)
        self.db = db

    def query(self, query_string: str, **kwargs):
        self.db.query(query_string, **kwargs)

    def connect(self, **kwargs):
        self.db.connect(**kwargs)

    def disconnect(self, **kwargs):
        self.db.disconnect(**kwargs)

    def add(self, table: str, content: list, **kwargs):
        self.db.add(table, content, **kwargs)

    def list_collections(self, **kwargs):
        return self.db.list_collections(**kwargs)

    def get_collection(self, collection_name: str, **kwargs):
        return self.db.get_collection(collection_name, **kwargs)

    def drop_collection(self, collection_name: str, **kwargs):
        return self.db.drop_collection(collection_name, **kwargs)
