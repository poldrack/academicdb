import pytest
import sys
sys.path.append('../academicdb')
from src.academicdb.database import AbstractDatabase
from src.academicdb.database import MongoDatabase

dbname = 'testdb'

@pytest.fixture
def mongodb():
    db = MongoDatabase(dbname)
    db.connect()
    yield db
    # clean up after tests are done
    db.client.drop_database(dbname)

# smoke test for AbstractDatabase
def test_abstract_database():
    with pytest.raises(TypeError):
        AbstractDatabase()


def test_mongo_creation(mongodb):
    assert mongodb is not None


def test_mongo_setup_db(mongodb):
    mongodb.connect()
    mongodb.setup_db()
    mongodb.setup_collections()
    assert dbname in mongodb.client.list_database_names()
