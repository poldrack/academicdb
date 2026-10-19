"""Tests for opening the weekly review PR (GitHub mocked with responses)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import responses
import yaml

from academic.models import PreprintHideProposal, ReviewBatch
from academic.publish.batches import create_batch
from academic.publish.github import GitHub, GitHubError
from academic.publish.review_pr import (
    REVIEW_HEADER, open_review_pr, pr_body, pr_title, remind_if_stale,
    review_yaml,
)
from tests.factories import PublicationFactory

API = 'https://api.github.com'
REPO = 'owner/site'
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def gh():
    return GitHub('tok')


def make_pub(user, **kw):
    kw.setdefault('review_status', 'pending')
    return PublicationFactory(owner=user, **kw)


def make_proposal(user, method='crossref_relation', evidence=None):
    preprint = PublicationFactory(
        owner=user, is_preprint=True, publication_type='preprint',
        doi='10.1101/abc', title='The Preprint', review_status='approved')
    published = PublicationFactory(
        owner=user, doi='10.1000/pub', title='The Published',
        review_status='approved')
    return PreprintHideProposal.objects.create(
        owner=user, preprint=preprint, published=published, method=method,
        evidence=evidence or {'relation': 'is-preprint-of'})


def mock_github(pr_number=7):
    responses.get(f'{API}/repos/{REPO}/git/ref/heads/main',
                  json={'object': {'sha': 'abc'}})
    responses.post(f'{API}/repos/{REPO}/git/refs', json={}, status=201)
    responses.put(f'{API}/repos/{REPO}/contents/review/2026-10-19.yml',
                  json={'commit': {'sha': 'c1'}}, status=201)
    responses.post(f'{API}/repos/{REPO}/pulls', json={'number': pr_number},
                   status=201)


def test_review_yaml_sections_and_header(academic_user):
    pub = make_pub(academic_user, title='New One')
    prop = make_proposal(academic_user)
    text = review_yaml([pub], [prop])
    assert text.startswith(REVIEW_HEADER)
    for line in (
        '# Delete an entry under "new" to reject that paper.',
        '# Delete an entry under "hide" to keep that preprint visible.',
        '# Edits to fields are ignored; make content edits in the local app.',
    ):
        assert line in REVIEW_HEADER
    data = yaml.safe_load(text)
    assert [r['title'] for r in data['new']] == ['New One']
    hide = data['hide'][0]
    assert hide['doi'] == '10.1101/abc'
    assert hide['published_as'] == {'doi': '10.1000/pub',
                                    'title': 'The Published'}
    assert hide['evidence'] == {'method': 'crossref_relation',
                                'relation': 'is-preprint-of'}


def test_pr_title_counts(academic_user):
    pubs = [make_pub(academic_user) for _ in range(3)]
    prop = make_proposal(academic_user)
    assert pr_title(pubs, [prop]) == (
        'Review: 3 new papers, 1 preprint to hide')
    assert pr_title(pubs[:1], []) == 'Review: 1 new paper'
    assert pr_title([], [prop]) == 'Review: 1 preprint to hide'


def test_pr_body_lists_items_with_links_and_evidence(academic_user):
    full = make_pub(
        academic_user, title='Full Paper', doi='10.5/full', year=2025,
        publication_name='Journal of Tests',
        authors=[{'name': n} for n in ('A One', 'B Two', 'C Three', 'D Four')],
        identifiers={'openalex': 'W123', 'pmid': '999'})
    bare = make_pub(
        academic_user, title='Bare Paper', doi='10.5/bare',
        identifiers={'openalex': '', 'pmid': None})
    prop = make_proposal(academic_user, evidence={'relation': 'is-preprint-of'})
    body = pr_body([full, bare], [prop])
    assert 'Full Paper' in body and 'Journal of Tests' in body
    assert '2025' in body
    assert 'A One, B Two, C Three, et al.' in body
    assert 'D Four' not in body
    assert 'https://doi.org/10.5/full' in body
    assert 'https://openalex.org/W123' in body
    assert 'https://pubmed.ncbi.nlm.nih.gov/999/' in body
    assert 'https://doi.org/10.5/bare' in body
    assert 'openalex.org/)' not in body and 'openalex.org/\n' not in body
    assert 'pubmed.ncbi.nlm.nih.gov/None' not in body
    assert body.count('openalex.org') == 1
    assert body.count('pubmed.ncbi.nlm.nih.gov') == 1
    assert ('"The Preprint" hidden because it was published as '
            '"The Published" (https://doi.org/10.1000/pub)') in body
    assert 'crossref_relation' in body and 'is-preprint-of' in body


@responses.activate
def test_open_review_pr_creates_branch_file_pr_and_batch(academic_user, gh):
    pub = make_pub(academic_user)
    prop = make_proposal(academic_user)
    mock_github()
    batch = open_review_pr(academic_user, gh, REPO, NOW)
    assert batch.pr_number == 7
    assert batch.branch == 'academicdb/review-2026-10-19'
    assert batch.path == 'review/2026-10-19.yml'
    assert batch.status == 'open'
    assert list(batch.publications.all()) == [pub]
    assert list(batch.proposals.all()) == [prop]
    calls = {(c.request.method, c.request.url.split('?')[0]): c
             for c in responses.calls}
    put = json.loads(calls[(
        'PUT', f'{API}/repos/{REPO}/contents/review/2026-10-19.yml')
    ].request.body)
    assert put['branch'] == 'academicdb/review-2026-10-19'
    assert put['message'] == 'Add review file'
    pr = json.loads(calls[('POST', f'{API}/repos/{REPO}/pulls')].request.body)
    assert pr['head'] == 'academicdb/review-2026-10-19'
    assert pr['base'] == 'main'
    assert pr['title'] == 'Review: 1 new paper, 1 preprint to hide'


@responses.activate
def test_open_review_pr_noop_when_batch_open(academic_user, gh):
    make_pub(academic_user)
    create_batch(academic_user, 1, 'b', 'p', [], [], NOW)
    assert open_review_pr(academic_user, gh, REPO, NOW) is None
    assert len(responses.calls) == 0


@responses.activate
def test_open_review_pr_noop_when_nothing_pending(academic_user, gh):
    assert open_review_pr(academic_user, gh, REPO, NOW) is None
    assert len(responses.calls) == 0


@responses.activate
def test_failed_pr_creation_saves_no_batch(academic_user, gh):
    make_pub(academic_user)
    mock_github()
    responses.replace(responses.POST, f'{API}/repos/{REPO}/pulls', status=500)
    with pytest.raises(GitHubError):
        open_review_pr(academic_user, gh, REPO, NOW)
    assert ReviewBatch.objects.count() == 0


@responses.activate
def test_remind_once_after_14_days(academic_user, gh):
    batch = create_batch(academic_user, 7, 'b', 'p', [], [], NOW)
    responses.post(f'{API}/repos/{REPO}/issues/7/comments', json={})
    assert remind_if_stale(batch, gh, REPO, NOW + timedelta(days=13)) is False
    assert len(responses.calls) == 0
    later = NOW + timedelta(days=14)
    assert remind_if_stale(batch, gh, REPO, later) is True
    assert len(responses.calls) == 1
    assert json.loads(responses.calls[0].request.body)['body'] == (
        'This review has been open for 14 days. '
        'New discoveries wait until it is merged or closed.')
    batch.refresh_from_db()
    assert batch.reminded_at == later
    assert remind_if_stale(
        batch, gh, REPO, NOW + timedelta(days=20)) is False
    assert len(responses.calls) == 1
