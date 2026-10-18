"""
Tests for the portable JSON backup and restore commands.
"""
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from freezegun import freeze_time

from academic.models import AcademicUser, Publication


pytestmark = pytest.mark.django_db(transaction=True)

STAMP = 'academicdb_20261018_120000'


@pytest.fixture
def user_with_pubs():
    user = AcademicUser.objects.create(username='russell', orcid_id='0000-0001-6755-0259')
    Publication.objects.create(owner=user, doi='10.1000/a', title='A', year=2024)
    Publication.objects.create(owner=user, doi='10.1000/b', title='B', year=2025)
    return user


@pytest.fixture
def backup(user_with_pubs, tmp_path):
    out = StringIO()
    with freeze_time('2026-10-18 12:00:00'):
        call_command('backup_database', output_dir=str(tmp_path), stdout=out)
    return tmp_path / f'{STAMP}.json.gz', out.getvalue()


def test_backup_writes_fixture_and_counts(backup, tmp_path):
    fixture, output = backup
    counts = json.loads((tmp_path / f'{STAMP}.counts.json').read_text())
    assert fixture.exists()
    assert counts['academic.publication'] == 2
    assert output.strip().splitlines()[-1] == str(fixture)


def test_restore_roundtrip_into_empty_db(backup):
    fixture, _ = backup
    call_command('flush', interactive=False, verbosity=0)
    call_command('restore_database', str(fixture))
    assert Publication.objects.count() == 2


def test_restore_refuses_nonempty_db(backup):
    fixture, _ = backup
    with pytest.raises(CommandError, match='not empty'):
        call_command('restore_database', str(fixture))


def test_restore_detects_count_mismatch(backup, tmp_path):
    fixture, _ = backup
    counts_path = tmp_path / f'{STAMP}.counts.json'
    counts = json.loads(counts_path.read_text())
    counts['academic.publication'] = 3
    counts_path.write_text(json.dumps(counts))
    call_command('flush', interactive=False, verbosity=0)
    with pytest.raises(CommandError, match='Count mismatch'):
        call_command('restore_database', str(fixture))
