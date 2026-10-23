"""Tests for the site YAML export."""
import datetime

import pytest
import yaml
from django.core.management import call_command

from academic.models import Link
from academic.publish.site_yaml import (
    record_key, render_site_yaml, site_record, site_records,
)
from tests.factories import PublicationFactory

FIELDS = [
    'doi', 'title', 'year', 'publication_date', 'publication_name',
    'publication_type', 'is_preprint', 'volume', 'page_range', 'authors',
    'identifiers', 'links', 'oa_url', 'citation',
]


def make_pub(user, **kwargs):
    kwargs.setdefault('review_status', 'approved')
    return PublicationFactory(owner=user, **kwargs)


def test_record_has_exactly_the_site_fields_in_order(academic_user):
    record = site_record(make_pub(academic_user))
    assert list(record) == FIELDS


def test_citation_is_formatted_from_the_record(academic_user):
    pub = make_pub(
        academic_user, title='A study.', doi='10.1/abc', publication_name='NeuroImage',
        volume='12', page_range='1-10', publication_type='journal-article',
        is_preprint=False,
        authors=[{'name': 'Poldrack, Russell A'}, {'name': 'Smith J'}],
    )
    assert site_record(pub)['citation'] == (
        'Poldrack RA, Smith J. [A study.](https://doi.org/10.1/abc) NeuroImage, *12*, 1-10.'
    )


def test_identifiers_keep_only_nonempty_pmid_and_pmcid(academic_user):
    pub = make_pub(academic_user, identifiers={'pmid': '1', 'pmcid': '', 'scopus': 'x'})
    assert site_record(pub)['identifiers'] == {'pmid': '1'}
    pub = make_pub(academic_user, identifiers={'pmid': '', 'pmcid': None, 'scopus': 'x'})
    assert site_record(pub)['identifiers'] == {}


def test_integer_pmid_is_stringified(academic_user):
    pub = make_pub(academic_user, identifiers={'pmid': 123})
    assert site_record(pub)['identifiers'] == {'pmid': '123'}


def test_links_include_resources_from_link_table(academic_user):
    pub = make_pub(academic_user, doi='10.1/ABC', links={})
    Link.objects.create(owner=academic_user, type='Data', doi='10.1/abc', url='http://b', title='B')
    Link.objects.create(owner=academic_user, type='Code', doi='10.1/abc', url='http://z', title='Z')
    Link.objects.create(owner=academic_user, type='Code', doi='10.1/abc', url='http://a', title='A')
    record = site_records(academic_user)[0]
    assert record['links'] == {'resources': [
        {'type': 'Code', 'url': 'http://a', 'title': 'A'},
        {'type': 'Code', 'url': 'http://z', 'title': 'Z'},
        {'type': 'Data', 'url': 'http://b', 'title': 'B'},
    ]}


def test_links_empty_without_resources(academic_user):
    pub = make_pub(academic_user, links={})
    assert site_record(pub)['links'] == {}


def test_pub_links_field_is_not_exported(academic_user):
    pub = make_pub(academic_user, links={
        'pdf': 'x', 'resources': [{'type': 'Code', 'url': 'stale'}]})
    assert site_record(pub)['links'] == {}
    assert site_records(academic_user)[0]['links'] == {}


def test_link_with_url_form_doi_attaches(academic_user):
    make_pub(academic_user, doi='10.1/abc')
    Link.objects.create(owner=academic_user, type='Code', doi='https://doi.org/10.1/ABC', url='http://a')
    assert len(site_records(academic_user)[0]['links']['resources']) == 1


def test_link_with_blank_doi_attaches_to_nothing(academic_user):
    make_pub(academic_user, doi='')
    make_pub(academic_user, doi='10.1/x')
    Link.objects.create(owner=academic_user, type='Code', doi='', url='http://a')
    assert all(r['links'] == {} for r in site_records(academic_user))


def test_author_name_falls_back_to_given_family(academic_user):
    pub = make_pub(academic_user, authors=[
        {'given': 'Ann', 'family': 'Lee'},
        {'name': 'Bo Chen', 'orcid': 'x'},
        {'affiliation': 'nowhere'},
    ])
    assert site_record(pub)['authors'] == [{'name': 'Ann Lee'}, {'name': 'Bo Chen'}]


def test_oa_url_from_metadata(academic_user):
    assert site_record(make_pub(academic_user, metadata={'oa_url': 'u'}))['oa_url'] == 'u'
    assert site_record(make_pub(academic_user, metadata={}))['oa_url'] is None


def test_public_records_exclude_ignored_and_pending(academic_user):
    ok = make_pub(academic_user)
    make_pub(academic_user, is_ignored=True)
    make_pub(academic_user, review_status='pending')
    assert [r['doi'] for r in site_records(academic_user)] == [ok.doi]


def test_include_pending_adds_pending(academic_user):
    make_pub(academic_user)
    make_pub(academic_user, review_status='pending')
    make_pub(academic_user, is_ignored=True)
    assert len(site_records(academic_user, include_pending=True)) == 2


def test_other_users_publications_excluded(academic_user):
    make_pub(academic_user)
    PublicationFactory(review_status='approved')
    assert len(site_records(academic_user)) == 1


def test_order_year_date_title(academic_user):
    d = datetime.date
    specs = [
        ('old', 2019, None), ('b-title', 2020, d(2020, 5, 1)),
        ('A-title', 2020, d(2020, 5, 1)), ('nodate', 2020, None),
        ('later', 2020, d(2020, 6, 1)), ('new', 2021, None),
    ]
    for title, year, date in specs:
        make_pub(academic_user, title=title, year=year, publication_date=date)
    titles = [r['title'] for r in site_records(academic_user)]
    assert titles == ['new', 'later', 'A-title', 'b-title', 'nodate', 'old']


def test_two_queries_regardless_of_count(academic_user, django_assert_num_queries):
    for _ in range(5):
        pub = make_pub(academic_user)
        Link.objects.create(owner=academic_user, type='Code', doi=pub.doi, url='http://x')
    with django_assert_num_queries(2):
        assert len(site_records(academic_user)) == 5


def test_render_is_deterministic_and_round_trips(academic_user):
    title = 'A very long title ' * 20
    make_pub(
        academic_user, title=title, publication_date=datetime.date(2020, 1, 2),
        authors=[{'name': 'José Müller'}],
    )
    records = site_records(academic_user)
    text = render_site_yaml(records)
    assert text == render_site_yaml(records)
    loaded = yaml.safe_load(text)
    assert loaded['publications'][0]['publication_date'] == '2020-01-02'
    assert loaded['publications'][0]['title'] == title
    assert 'José Müller' in text
    assert title in text


def test_record_key():
    assert record_key({'doi': 'https://doi.org/10.1/ABC', 'identifiers': {'pmid': '5'}}) == '10.1/abc'
    assert record_key({'doi': '', 'identifiers': {'pmid': '5'}}) == 'pmid:5'
    assert record_key({'doi': '', 'identifiers': {}}) == ''


def test_export_site_yaml_command_writes_file(academic_user, tmp_path):
    make_pub(academic_user, title='Hello')
    out = tmp_path / 'pubs.yml'
    call_command('export_site_yaml', orcid_id=academic_user.orcid_id, output=str(out))
    assert yaml.safe_load(out.read_text())['publications'][0]['title'] == 'Hello'


def test_command_unknown_orcid_raises(db, tmp_path):
    from django.core.management import CommandError
    with pytest.raises(CommandError):
        call_command('export_site_yaml', orcid_id='nope', output=str(tmp_path / 'x.yml'))
