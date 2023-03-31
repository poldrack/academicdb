import pytest
import sys

sys.path.append('../academicdb')
from src.academicdb.query import ScopusQuery


def test_single_record_returned():
    scopus_search = ScopusQuery()
    authorid = '7004739390'
    results = scopus_search.author_query(authorid)

    assert len(results) > 300
    for record in results:
        # author names are truncated at 100
        if len(record.author_names.split(';')) < 100:
            assert record.author_names.lower().find('poldrack') > -1
