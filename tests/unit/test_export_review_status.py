"""export_publications must never publish unreviewed (pending) works by default."""
import json

import pytest
from django.core.management import call_command

from tests.factories import PublicationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def pubs(academic_user):
    PublicationFactory(owner=academic_user, title='Approved paper title',
                       review_status='approved')
    PublicationFactory(owner=academic_user, title='Pending paper title',
                       review_status='pending')


def export_titles(user, tmp_path, *extra):
    out = tmp_path / 'pubs.json'
    call_command('export_publications', '--username', user.username,
                 '--output', str(out), *extra)
    return {p['title'] for p in json.loads(out.read_text())['publications']}


def test_export_excludes_pending_by_default(academic_user, pubs, tmp_path):
    assert export_titles(academic_user, tmp_path) == {'Approved paper title'}


def test_export_include_pending_flag(academic_user, pubs, tmp_path):
    titles = export_titles(academic_user, tmp_path, '--include-pending')
    assert titles == {'Approved paper title', 'Pending paper title'}
