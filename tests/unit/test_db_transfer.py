"""
Tests for row counting and copying all data between database aliases.
"""
import gzip
import json

import pytest
from django.contrib.sites.models import Site

from academic.db_transfer import (
    TargetNotEmptyError,
    copy_all_data,
    count_mismatches,
    dump_fixture,
    load_fixture,
    model_counts,
)
from academic.models import AcademicUser, Link, Publication


pytestmark = pytest.mark.django_db(databases=['default', 'source'], transaction=True)

EDITED_DOI = '10.1000/edited'


@pytest.fixture
def source_data():
    user = AcademicUser.objects.using('source').create(
        username='russell', orcid_id='0000-0001-6755-0259'
    )
    Publication.objects.using('source').create(
        owner=user, doi='10.1000/plain', title='Plain paper', year=2024
    )
    Publication.objects.using('source').create(
        owner=user,
        doi=EDITED_DOI,
        title='Edited paper',
        year=2025,
        authors=[{'name': 'Poldrack, R. A.'}],
        identifiers={'pmcid': 'PMC123', 'pmid': '456'},
        manual_edits={'title': True},
        edit_history=[{'field': 'title'}],
        is_ignored=True,
        ignore_reason='Published as journal article',
    )
    Link.objects.using('source').create(
        owner=user, type='Code', doi=EDITED_DOI, url='https://github.com/x/y'
    )
    return user


def test_model_counts_reports_source_rows(source_data):
    counts = model_counts('source')
    assert counts['academic.publication'] == 2
    assert counts['academic.link'] == 1
    assert 'contenttypes.contenttype' not in counts


def test_count_mismatches_lists_only_differences():
    assert count_mismatches({'a.x': 2, 'a.y': 1}, {'a.x': 2}) == [('a.y', 1, 0)]


def test_copy_all_data_produces_matching_counts(source_data, tmp_path):
    assert copy_all_data('source', 'default', tmp_path) == []
    assert Publication.objects.using('default').count() == 2


def test_copy_preserves_json_fields_and_flags(source_data, tmp_path):
    copy_all_data('source', 'default', tmp_path)
    pub = Publication.objects.using('default').get(is_ignored=True)
    assert pub.authors == [{'name': 'Poldrack, R. A.'}]
    assert pub.identifiers == {'pmcid': 'PMC123', 'pmid': '456'}
    assert pub.manual_edits == {'title': True}
    assert pub.edit_history == [{'field': 'title'}]
    assert pub.ignore_reason == 'Published as journal article'


def test_copy_refuses_nonempty_target_and_leaves_it_unchanged(source_data, tmp_path):
    AcademicUser.objects.using('default').create(username='existing')
    with pytest.raises(TargetNotEmptyError, match='academic.academicuser'):
        copy_all_data('source', 'default', tmp_path)
    assert Publication.objects.using('default').count() == 0
    assert AcademicUser.objects.using('default').count() == 1


def test_new_rows_after_copy_get_fresh_ids(source_data, tmp_path):
    copy_all_data('source', 'default', tmp_path)
    owner = AcademicUser.objects.using('default').get(username='russell')
    max_id = max(Publication.objects.using('default').values_list('id', flat=True))
    new = Publication.objects.using('default').create(
        owner=owner, doi='10.1000/new', title='New paper', year=2026
    )
    assert new.id > max_id


def test_copy_keeps_site_primary_key(source_data, tmp_path):
    # The real database's site is not example.com; SITE_ID=1 must still resolve
    Site.objects.using('source').filter(pk=1).update(domain='127.0.0.1:8000')
    copy_all_data('source', 'default', tmp_path)
    assert list(Site.objects.using('default').values_list('pk', 'domain')) == [
        (1, '127.0.0.1:8000')
    ]


def test_load_fixture_does_not_run_token_signal(tmp_path):
    # dumpdata can emit a SocialToken before its SocialAccount; loading must
    # not run app signal handlers that dereference it or rewrite the user
    path = tmp_path / 'social.json'
    path.write_text(json.dumps([
        {'model': 'academic.academicuser', 'pk': 1,
         'fields': {'username': 'russell', 'password': '', 'orcid_token': 'kept',
                    'profile_updated': '2026-01-01T00:00:00Z'}},
        {'model': 'socialaccount.socialapp', 'pk': 1,
         'fields': {'provider': 'orcid', 'name': 'ORCID', 'client_id': 'x', 'secret': 'y'}},
        {'model': 'socialaccount.socialtoken', 'pk': 1,
         'fields': {'app': 1, 'account': 1, 'token': 'new'}},
        {'model': 'socialaccount.socialaccount', 'pk': 1,
         'fields': {'user': 1, 'provider': 'orcid', 'uid': '0000-0001-6755-0259',
                    'last_login': '2026-01-01T00:00:00Z', 'date_joined': '2026-01-01T00:00:00Z'}},
    ]))
    load_fixture(path, 'default')
    assert AcademicUser.objects.get(username='russell').orcid_token == 'kept'


def test_dump_fixture_gzip_roundtrip(source_data, tmp_path):
    path = tmp_path / 'b.json.gz'
    dump_fixture('source', path)
    with gzip.open(path) as f:
        assert f.read(1) == b'['
