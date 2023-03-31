## tests for the recordConverter module
import pytest
import sys

sys.path.append('../academicdb')
from src.academicdb.query import AbstractQuery

# smoke test for AbstractQuery


def test_abstract_query():
    with pytest.raises(TypeError):
        AbstractQuery()
