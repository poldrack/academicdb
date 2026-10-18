"""
Tests for importing resource links (Code/Data/OSF) from CSV and site JSON.
"""
import json

import pytest
from django.urls import reverse

from academic.data_ingestion import ingest_links
from academic.link_import import (
    LinkRecord,
    import_link_records,
    normalize_doi,
    read_links_csv,
    read_links_from_publications_json,
)
from academic.models import Link, Publication


MIXED_CASE_DOI = '10.1038/S41562-024-01942-4'


@pytest.fixture
def user(academic_user):
    return academic_user


@pytest.fixture
def pubs(user):
    Publication.objects.create(owner=user, doi='10.1/abc', title='ABC', year=2024)
    mixed = Publication.objects.create(owner=user, doi='10.1038/tmp', title='Mixed', year=2024)
    # Bypass save() (which lowercases), as legacy rows and bulk updates do
    Publication.objects.filter(pk=mixed.pk).update(doi=MIXED_CASE_DOI)


def write_csv(path, text):
    path.write_text(text)
    return path


@pytest.mark.parametrize('raw', [
    'https://doi.org/10.1/ABC', 'doi:10.1/abc', ' 10.1/abc ',
    'http://dx.doi.org/10.1/abc', 'https://dx.doi.org/10.1/abc',
])
def test_normalize_doi(raw):
    assert normalize_doi(raw) == '10.1/abc'


def test_read_links_csv_example_format(tmp_path):
    path = write_csv(
        tmp_path / 'links.csv',
        'type,DOI,url\n'
        'Code,https://doi.org/10.1/abc,https://github.com/x/y\n'
        'Data,https://doi.org/10.1/abc,\n',
    )
    assert read_links_csv(path) == [LinkRecord('10.1/abc', 'Code', 'https://github.com/x/y')]


def test_read_links_csv_missing_column(tmp_path):
    path = write_csv(tmp_path / 'links.csv', 'type,url\nCode,https://github.com/x/y\n')
    with pytest.raises(ValueError, match='DOI'):
        read_links_csv(path)


def test_read_links_from_publications_json(tmp_path):
    path = tmp_path / 'publications.json'
    path.write_text(json.dumps({'publications': [
        {'doi': '10.1/abc', 'links': {'resources': [
            {'type': 'OSF', 'url': 'https://osf.io/a6t8k/', 'title': 'OSF'}]}},
        {'doi': '10.1/none', 'links': {}},
    ]}))
    assert read_links_from_publications_json(path) == [
        LinkRecord('10.1/abc', 'OSF', 'https://osf.io/a6t8k', 'OSF')
    ]


@pytest.mark.django_db
def test_import_dedupes_across_sources_and_is_idempotent(user, pubs):
    recs = [
        LinkRecord('10.1/abc', 'Code', 'https://github.com/x/y'),
        LinkRecord('10.1/ABC', 'Code', 'https://github.com/x/y/'),
    ]
    assert import_link_records(user, recs).created == 1
    assert import_link_records(user, recs).existing == 1
    assert Link.objects.count() == 1


@pytest.mark.django_db
def test_import_reports_unmatched_dois(user, pubs):
    result = import_link_records(
        user, [LinkRecord('10.9/none', 'Data', 'https://openneuro.org/datasets/ds000001')]
    )
    assert result.unmatched_dois == ['10.9/none']
    assert Link.objects.count() == 0


@pytest.mark.django_db
def test_links_found_for_mixed_case_publication_doi(user, pubs):
    import_link_records(
        user, [LinkRecord('10.1038/s41562-024-01942-4', 'Code', 'https://zenodo.org/records/5748130')]
    )
    pub = Publication.objects.get(doi=MIXED_CASE_DOI)
    assert Link.get_links_for_publication(pub).count() == 1


@pytest.mark.django_db
def test_ingest_links_reads_example_csv_format(user, pubs, tmp_path):
    write_csv(
        tmp_path / 'links.csv',
        'type,DOI,url\nCode,https://doi.org/10.1/abc,https://github.com/x/y\n',
    )
    assert ingest_links(user, str(tmp_path)) == 1


@pytest.mark.django_db
def test_publication_list_counts_links_for_mixed_case_doi(user, pubs, client):
    Link.objects.create(owner=user, type='Code', doi='10.1038/s41562-024-01942-4',
                        url='https://zenodo.org/records/5748130')
    client.force_login(user)
    response = client.get(reverse('academic:publication_list'))
    counts = {p.doi: p.link_count for p in response.context['publications']}
    assert counts[MIXED_CASE_DOI] == 1
