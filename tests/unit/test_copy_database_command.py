"""
Tests for the copy_database management command.
"""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from academic.models import AcademicUser, Publication


pytestmark = pytest.mark.django_db(databases=['default', 'source'], transaction=True)


@pytest.fixture
def source_data():
    user = AcademicUser.objects.using('source').create(
        username='russell', orcid_id='0000-0001-6755-0259'
    )
    Publication.objects.using('source').create(
        owner=user, doi='10.1000/plain', title='Plain paper', year=2024
    )
    return user


def test_copy_database_reports_match(source_data):
    out = StringIO()
    call_command('copy_database', source_alias='source', stdout=out)
    assert 'All counts match.' in out.getvalue()
    assert 'academic.publication' in out.getvalue()
    assert Publication.objects.using('default').count() == 1


def test_copy_database_requires_exactly_one_source():
    with pytest.raises(CommandError):
        call_command('copy_database')


def test_copy_database_rejects_both_sources(tmp_path):
    with pytest.raises(CommandError):
        call_command(
            'copy_database', source_alias='source',
            source_sqlite=str(tmp_path / 'db.sqlite3'),
        )


def test_copy_database_missing_sqlite_file(tmp_path):
    with pytest.raises(CommandError, match='does not exist'):
        call_command('copy_database', source_sqlite=str(tmp_path / 'nope.sqlite3'))


def test_copy_database_nonempty_target_is_command_error(source_data):
    AcademicUser.objects.using('default').create(username='existing')
    with pytest.raises(CommandError, match='not empty'):
        call_command('copy_database', source_alias='source')
