import pytest
import sys
sys.path.append('../academicdb')
from src.academicdb.database import AbstractDatabase

# smoke test for AbstractDatabase
def test_abstract_database():
    with pytest.raises(TypeError):
        AbstractDatabase()
