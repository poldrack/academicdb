"""
CV generation must use a fixed number of queries regardless of how many
publications, years, talks or links exist: with a hosted database each
query is a network round trip (~90 ms to Neon).
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from academic.cv_renderer import generate_cv_latex
from academic.models import Conference, Link, Publication, Talk


pytestmark = pytest.mark.django_db


def add_records(user, start_year, n_years):
    for year in range(start_year, start_year + n_years):
        for i in range(2):
            doi = f'10.1000/cv-{year}-{i}'
            Publication.objects.create(
                owner=user, doi=doi, title=f'Paper {year} {i}', year=year,
                publication_type='journal-article',
                authors=[{'name': f'Author{i}, A.'}],
            )
            Link.objects.create(owner=user, type='Code', doi=doi,
                                url=f'https://github.com/lab/{year}-{i}')
        Talk.objects.create(owner=user, year=year, place=f'University {year}')
        Conference.objects.create(owner=user, year=year, title=f'Talk {year}',
                                  authors='Poldrack, R.', location='Somewhere', month='May')


def cv_query_count(user):
    with CaptureQueriesContext(connection) as ctx:
        tex = generate_cv_latex(user)
    return len(ctx.captured_queries), tex


def test_cv_query_count_does_not_grow_with_data(academic_user):
    add_records(academic_user, 2010, 3)
    small, _ = cv_query_count(academic_user)
    add_records(academic_user, 2013, 6)
    large, tex = cv_query_count(academic_user)
    assert large == small
    assert 'https://github.com/lab/2018-1' in tex
