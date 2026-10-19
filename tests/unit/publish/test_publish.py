"""Tests for publishing the public YAML and driving the review PR."""
import base64
import json
from io import StringIO
from datetime import datetime, timezone

import pytest
import responses
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from freezegun import freeze_time

from academic.models import (
    PreprintHideProposal, Publication, RejectedWork, ReviewBatch,
)
from academic.publish.batches import create_batch
from academic.publish.github import GitHub, GitHubError
from academic.publish.publish import (
    DryRunGitHub, PublishConfig, publish_public,
)
from academic.publish.review_pr import review_yaml
from academic.publish.site_yaml import render_site_yaml, site_records
from tests.factories import PublicationFactory

API = 'https://api.github.com'
PERSONAL = 'me/personal'
LAB = 'lab/site'
SITE_PATH = 'publications.yml'
REVIEW_PATH = 'review/2026-10-19-090000.yml'
ORCID = '0000-0000-0000-0001'
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
MESSAGE = 'Update publications (academicdb)'


# Helpers

def site_url(repo):
    return f'{API}/repos/{repo}/contents/{SITE_PATH}'


def review_url(repo=PERSONAL, path=REVIEW_PATH):
    return f'{API}/repos/{repo}/contents/{path}'


def file_json(text, sha):
    return {'content': base64.b64encode(text.encode()).decode(), 'sha': sha}


def mock_site(repo, text=None, sha='s0', put_status=201):
    if text is None:
        responses.get(site_url(repo), status=404)
    else:
        responses.get(site_url(repo), json=file_json(text, sha))
    responses.put(site_url(repo), json={'commit': {'sha': 'c1'}},
                  status=put_status)


def calls_to(method, url):
    return [c for c in responses.calls if c.request.method == method
            and c.request.url.split('?')[0] == url]


def put_body(repo):
    puts = calls_to('PUT', site_url(repo))
    assert len(puts) == 1
    return json.loads(puts[0].request.body)


def put_text(repo):
    return base64.b64decode(put_body(repo)['content']).decode('utf-8')


def writes():
    return [c for c in responses.calls
            if c.request.method in ('POST', 'PUT', 'DELETE', 'PATCH')]


def public_text(user):
    return render_site_yaml(site_records(user))


def targets():
    return [(GitHub('p-tok'), PERSONAL), (GitHub('l-tok'), LAB)]


def pending(user, doi, **kw):
    return PublicationFactory(owner=user, doi=doi, review_status='pending',
                              **kw)


def approved(user, doi, **kw):
    return PublicationFactory(owner=user, doi=doi, review_status='approved',
                              **kw)


def preprint(user, doi):
    return PublicationFactory(
        owner=user, is_preprint=True, publication_type='preprint', doi=doi,
        review_status='approved')


def proposal(user, pre, published):
    return PreprintHideProposal.objects.create(
        owner=user, preprint=pre, published=published,
        method='crossref_relation', evidence={'relation': 'is-preprint-of'})


def batch_for(user, pubs, proposals, number=7):
    return create_batch(user, number, 'academicdb/review-2026-10-12',
                        'review/2026-10-12.yml', pubs, proposals, NOW)


def dois(text):
    return {r['doi'] for r in yaml.safe_load(text)['publications']}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('PERSONAL_SITE_REPO', PERSONAL)
    monkeypatch.setenv('LAB_SITE_REPO', LAB)
    monkeypatch.setenv('PIPELINE_REPO', 'me/pipeline')
    monkeypatch.setenv('PERSONAL_GITHUB_TOKEN', 'p-tok')
    monkeypatch.setenv('LAB_GITHUB_TOKEN', 'l-tok')
    return monkeypatch


# PublishConfig

def test_from_env_defaults():
    config = PublishConfig.from_env(
        {'PERSONAL_GITHUB_TOKEN': 'a', 'LAB_GITHUB_TOKEN': 'b'})
    assert config.personal_repo == 'poldrack/poldrack.github.io'
    assert config.lab_repo == 'poldracklab/poldracklab.github.io'
    assert config.pipeline_repo == 'poldrack/academicdb'
    assert config.site_path == 'publications.yml'
    assert (config.personal_token, config.lab_token) == ('a', 'b')


def test_from_env_reads_repos():
    config = PublishConfig.from_env({
        'PERSONAL_SITE_REPO': PERSONAL, 'LAB_SITE_REPO': LAB,
        'PIPELINE_REPO': 'me/pipeline',
        'PERSONAL_GITHUB_TOKEN': 'a', 'LAB_GITHUB_TOKEN': 'b'})
    assert (config.personal_repo, config.lab_repo, config.pipeline_repo) == (
        PERSONAL, LAB, 'me/pipeline')


def test_missing_token_names_variable(academic_user, monkeypatch):
    with pytest.raises(CommandError, match='PERSONAL_GITHUB_TOKEN'):
        PublishConfig.from_env({'LAB_GITHUB_TOKEN': 'b'})
    with pytest.raises(CommandError, match='LAB_GITHUB_TOKEN'):
        PublishConfig.from_env({'PERSONAL_GITHUB_TOKEN': 'a'})
    config = PublishConfig.from_env({}, dry_run=True)
    assert config.personal_token is None and config.lab_token is None
    monkeypatch.delenv('PERSONAL_GITHUB_TOKEN', raising=False)
    monkeypatch.setenv('LAB_GITHUB_TOKEN', 'b')
    with pytest.raises(CommandError, match='PERSONAL_GITHUB_TOKEN'):
        call_command('publish_sites', orcid_id=ORCID)


# publish_public

@pytest.mark.parametrize('remote', ['same', 'different', 'missing'])
@responses.activate
def test_publish_commits_only_when_content_differs(academic_user, remote):
    approved(academic_user, '10.1000/a')
    text = public_text(academic_user)
    remote_text = {'same': text, 'different': 'old: true\n',
                   'missing': None}[remote]
    for repo in (PERSONAL, LAB):
        mock_site(repo, remote_text, sha=f'{repo}-sha')
    updated = publish_public(academic_user, targets(), SITE_PATH)
    if remote == 'same':
        assert updated == []
        assert writes() == []
        return
    assert updated == [PERSONAL, LAB]
    for repo in (PERSONAL, LAB):
        body = put_body(repo)
        assert body['message'] == MESSAGE
        assert body['branch'] == 'main'
        assert put_text(repo) == text
        if remote == 'different':
            assert body['sha'] == f'{repo}-sha'
        else:
            assert 'sha' not in body


@responses.activate
def test_public_publish_during_open_review(academic_user):
    new = pending(academic_user, '10.1000/new')
    pre = preprint(academic_user, '10.1101/pre')
    target = approved(academic_user, '10.1000/target')
    prop = proposal(academic_user, pre, target)
    batch_for(academic_user, [new], [prop])
    mock_site(PERSONAL)
    publish_public(academic_user, targets()[:1], SITE_PATH)
    pushed = dois(put_text(PERSONAL))
    assert '10.1000/new' not in pushed
    assert {'10.1101/pre', '10.1000/target'} <= pushed


def test_publish_is_idempotent_after_partial_failure(academic_user):
    approved(academic_user, '10.1000/a')
    text = public_text(academic_user)
    with responses.RequestsMock() as first:
        first.get(site_url(PERSONAL), status=404)
        first.put(site_url(PERSONAL), json={'commit': {'sha': 'c1'}},
                  status=201)
        first.get(site_url(LAB), status=404)
        first.put(site_url(LAB), status=500)
        with pytest.raises(GitHubError):
            publish_public(academic_user, targets(), SITE_PATH)
        assert [c.request.method for c in first.calls] == [
            'GET', 'PUT', 'GET', 'PUT']
    with responses.RequestsMock() as second:
        second.get(site_url(PERSONAL), json=file_json(text, 'p1'))
        second.get(site_url(LAB), status=404)
        second.put(site_url(LAB), json={'commit': {'sha': 'c2'}},
                   status=201)
        updated = publish_public(academic_user, targets(), SITE_PATH)
        puts = [c for c in second.calls if c.request.method == 'PUT']
    assert updated == [LAB]
    assert len(puts) == 1 and puts[0].request.url == site_url(LAB)


# DryRunGitHub

@responses.activate
def test_dry_run_github_reads_but_logs_writes():
    responses.get(site_url(PERSONAL), json=file_json('x', 's'))
    gh = DryRunGitHub(None)
    assert gh.get_file(PERSONAL, SITE_PATH).text == 'x'
    assert gh.put_file(PERSONAL, SITE_PATH, 'y', 'm') == 'dry-run'
    assert gh.open_pr(PERSONAL, 'b', 't', 'body') == 0
    assert gh.create_branch(PERSONAL, 'b') is None
    assert gh.delete_file(PERSONAL, SITE_PATH, 'm', 's') is None
    assert gh.comment(PERSONAL, 1, 'hi') is None
    assert len(gh.writes) == 5
    assert writes() == []


# publish_sites

def mock_merged_batch_pr(text, number=7, path='review/2026-10-12.yml'):
    responses.get(f'{API}/repos/{PERSONAL}/pulls/{number}',
                  json={'state': 'closed', 'merged': True,
                        'merge_commit_sha': 'm123'})
    url = review_url(path=path)
    responses.get(url, json=file_json(text, 'old'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'm123'})])
    responses.get(url, json=file_json(text, 'mainsha'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'main'})])
    responses.delete(url, json={})


def mock_review_pr(number=9):
    responses.get(f'{API}/repos/{PERSONAL}/git/ref/heads/main',
                  json={'object': {'sha': 'abc'}})
    responses.post(f'{API}/repos/{PERSONAL}/git/refs', json={}, status=201)
    responses.get(review_url(), status=404)
    responses.put(review_url(), json={'commit': {'sha': 'r1'}}, status=201)
    responses.post(f'{API}/repos/{PERSONAL}/pulls', json={'number': number},
                   status=201)


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_publish_sites_processes_decided_pr_first(academic_user, env):
    new = pending(academic_user, '10.1000/new')
    batch = batch_for(academic_user, [new], [])
    mock_merged_batch_pr(review_yaml([new], []))
    mock_site(PERSONAL)
    mock_site(LAB)
    call_command('publish_sites', orcid_id=ORCID)
    assert ReviewBatch.objects.get(pk=batch.pk).status == 'merged'
    assert Publication.objects.get(pk=new.pk).review_status == 'approved'
    for repo in (PERSONAL, LAB):
        assert '10.1000/new' in dois(put_text(repo))
    assert calls_to('POST', f'{API}/repos/{PERSONAL}/pulls') == []
    assert ReviewBatch.objects.count() == 1


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_publish_sites_opens_review_pr_when_pending(academic_user, env):
    approved(academic_user, '10.1000/old')
    new = pending(academic_user, '10.1000/new')
    mock_site(PERSONAL)
    mock_site(LAB)
    mock_review_pr(number=9)
    call_command('publish_sites', orcid_id=ORCID)
    batch = ReviewBatch.objects.get(pr_number=9)
    assert batch.status == 'open'
    assert list(batch.publications.all()) == [new]
    assert dois(put_text(PERSONAL)) == {'10.1000/old'}
    review = calls_to('PUT', review_url())
    assert len(review) == 1


@freeze_time('2026-11-19 09:00:00')
@responses.activate
def test_publish_sites_reminds_when_pr_still_open(academic_user, env):
    new = pending(academic_user, '10.1000/new')
    batch = batch_for(academic_user, [new], [])
    responses.get(f'{API}/repos/{PERSONAL}/pulls/7',
                  json={'state': 'open', 'merged': False})
    responses.post(f'{API}/repos/{PERSONAL}/issues/7/comments', json={},
                   status=201)
    mock_site(PERSONAL)
    mock_site(LAB)
    call_command('publish_sites', orcid_id=ORCID)
    assert ReviewBatch.objects.get(pk=batch.pk).reminded_at is not None
    assert len(calls_to(
        'POST', f'{API}/repos/{PERSONAL}/issues/7/comments')) == 1
    assert calls_to('POST', f'{API}/repos/{PERSONAL}/pulls') == []


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_publish_sites_reports_and_comments_on_held_items(
        academic_user, env, capsys):
    new = pending(academic_user, '10.1000/new')
    batch_for(academic_user, [new], [])
    edited = review_yaml([new], []).replace('10.1000/new', '10.1000/typo')
    mock_merged_batch_pr(edited)
    responses.post(f'{API}/repos/{PERSONAL}/issues/7/comments', json={},
                   status=201)
    mock_site(PERSONAL)
    mock_site(LAB)
    mock_review_pr(number=9)
    out = _run_command('publish_sites')
    assert 'Review PR #7: approved 0, rejected 0, hidden 0, kept 0, held 1' \
        in out
    comments = calls_to('POST', f'{API}/repos/{PERSONAL}/issues/7/comments')
    assert len(comments) == 1
    body = json.loads(comments[0].request.body)['body']
    assert '10.1000/typo' in body
    assert 'next review' in body
    assert Publication.objects.get(pk=new.pk).review_status == 'pending'
    assert ReviewBatch.objects.filter(pr_number=9).exists()


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_publish_sites_github_failure_is_command_error(academic_user, env):
    mock_site(PERSONAL, put_status=500)
    with pytest.raises(CommandError, match='PUT'):
        call_command('publish_sites', orcid_id=ORCID)


def test_publish_sites_unknown_user(db, env):
    with pytest.raises(CommandError, match='0000-0000-0000-9999'):
        call_command('publish_sites', orcid_id='0000-0000-0000-9999')


def _run_command(name, **kw):
    out = StringIO()
    call_command(name, orcid_id=ORCID, stdout=out, **kw)
    return out.getvalue()


def db_counts():
    return (
        sorted(Publication.objects.values_list('id', 'review_status',
                                               'is_ignored')),
        sorted(PreprintHideProposal.objects.values_list('id', 'status')),
        sorted(ReviewBatch.objects.values_list('id', 'status',
                                               'pr_number')),
        RejectedWork.objects.count(),
    )


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_dry_run_makes_no_writes(academic_user, monkeypatch):
    for name in ('PERSONAL_GITHUB_TOKEN', 'LAB_GITHUB_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('PERSONAL_SITE_REPO', PERSONAL)
    monkeypatch.setenv('LAB_SITE_REPO', LAB)
    old = pending(academic_user, '10.1000/old')
    drop = pending(academic_user, '10.1000/drop')
    batch_for(academic_user, [old, drop], [])
    pending(academic_user, '10.1000/later')
    mock_merged_batch_pr(review_yaml([old], []))
    responses.get(site_url(PERSONAL), json=file_json('old: 1\n', 's'))
    responses.get(site_url(LAB), status=404)
    responses.get(review_url(), status=404)
    before = db_counts()
    out = _run_command('publish_sites', dry_run=True)
    assert writes() == []
    assert db_counts() == before
    assert all('Authorization' not in c.request.headers
               for c in responses.calls)
    assert 'Remove processed review file' in out
    assert f'{PERSONAL}/{SITE_PATH}' in out
    assert f'{LAB}/{SITE_PATH}' in out
    assert 'Review: ' in out


# process_review

@responses.activate
def test_process_review_unknown_pr_is_noop(academic_user, env):
    out = _run_command('process_review', pr=99)
    assert 'No review batch for PR 99' in out
    assert len(responses.calls) == 0


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_process_review_decides_and_publishes(academic_user, env):
    new = pending(academic_user, '10.1000/new')
    drop = pending(academic_user, '10.1000/drop')
    batch = batch_for(academic_user, [new, drop], [])
    mock_merged_batch_pr(review_yaml([new], []))
    mock_site(PERSONAL)
    mock_site(LAB)
    out = _run_command('process_review', pr=7)
    assert 'Review PR #7: approved 1, rejected 1, hidden 0, kept 0, held 0' \
        in out
    assert ReviewBatch.objects.get(pk=batch.pk).status == 'merged'
    for repo in (PERSONAL, LAB):
        assert dois(put_text(repo)) == {'10.1000/new'}
    assert calls_to('POST', f'{API}/repos/{PERSONAL}/pulls') == []


@responses.activate
def test_process_review_ignores_other_owners_batch(
        academic_user, second_academic_user, env):
    other = pending(second_academic_user, '10.1000/other')
    batch_for(second_academic_user, [other], [], number=12)
    out = _run_command('process_review', pr=12)
    assert 'No review batch for PR 12' in out
    assert len(responses.calls) == 0


# PublishConfig repr

def test_config_repr_hides_tokens():
    config = PublishConfig.from_env(
        {'PERSONAL_GITHUB_TOKEN': 'secret-personal',
         'LAB_GITHUB_TOKEN': 'secret-lab'})
    text = repr(config)
    assert 'secret-personal' not in text and 'secret-lab' not in text
    assert 'poldrack/poldrack.github.io' in text


# A broken review file must not block routine publishing

BROKEN = '- not a mapping\n'
BROKEN_COMMENT = (
    'The review file could not be read (Review file must be a mapping). '
    'Nothing in this review was decided. To recover, set this review batch '
    'to "closed" in the admin (its items will be offered again next week), '
    'or fix the data and re-run the publish workflow.')
COMMENTS_7 = f'{API}/repos/{PERSONAL}/issues/7/comments'


def mock_broken_review():
    mock_merged_batch_pr(BROKEN)
    responses.post(COMMENTS_7, json={}, status=201)
    mock_site(PERSONAL)
    mock_site(LAB)


def comment_bodies():
    return [json.loads(c.request.body)['body']
            for c in calls_to('POST', COMMENTS_7)]


@pytest.fixture
def broken_batch(academic_user):
    approved(academic_user, '10.1000/old')
    new = pending(academic_user, '10.1000/new')
    pending(academic_user, '10.1000/later')
    return batch_for(academic_user, [new], [])


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_broken_review_file_still_publishes_and_comments_once(
        academic_user, env, broken_batch):
    mock_broken_review()
    with pytest.raises(CommandError, match='must be a mapping'):
        call_command('publish_sites', orcid_id=ORCID)
    for repo in (PERSONAL, LAB):
        assert dois(put_text(repo)) == {'10.1000/old'}
    assert calls_to('POST', f'{API}/repos/{PERSONAL}/pulls') == []
    assert comment_bodies() == [BROKEN_COMMENT]
    batch = ReviewBatch.objects.get(pk=broken_batch.pk)
    assert batch.status == 'open'
    assert batch.error_notified_at is not None
    assert ReviewBatch.objects.count() == 1

    responses.reset()
    mock_broken_review()
    with pytest.raises(CommandError, match='must be a mapping'):
        call_command('publish_sites', orcid_id=ORCID)
    assert comment_bodies() == []
    assert calls_to('POST', f'{API}/repos/{PERSONAL}/pulls') == []


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_process_review_broken_file_publishes_and_comments_once(
        academic_user, env, broken_batch):
    mock_broken_review()
    with pytest.raises(CommandError, match='must be a mapping'):
        _run_command('process_review', pr=7)
    for repo in (PERSONAL, LAB):
        assert dois(put_text(repo)) == {'10.1000/old'}
    assert comment_bodies() == [BROKEN_COMMENT]
    responses.reset()
    mock_broken_review()
    with pytest.raises(CommandError):
        _run_command('process_review', pr=7)
    assert comment_bodies() == []


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_dry_run_broken_review_file_writes_nothing(
        academic_user, monkeypatch, broken_batch):
    for name in ('PERSONAL_GITHUB_TOKEN', 'LAB_GITHUB_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('PERSONAL_SITE_REPO', PERSONAL)
    monkeypatch.setenv('LAB_SITE_REPO', LAB)
    mock_merged_batch_pr(BROKEN)
    responses.get(site_url(PERSONAL), status=404)
    responses.get(site_url(LAB), status=404)
    out = StringIO()
    with pytest.raises(CommandError, match='must be a mapping'):
        call_command('publish_sites', orcid_id=ORCID, dry_run=True,
                     stdout=out)
    assert writes() == []
    assert f'COMMENT {PERSONAL}#7: The review file could not be read' \
        in out.getvalue()
    assert ReviewBatch.objects.get(
        pk=broken_batch.pk).error_notified_at is None


@freeze_time('2026-10-19 09:00:00')
@responses.activate
def test_closed_batch_offers_its_items_again(academic_user, env,
                                             broken_batch):
    """The README recovery: mark the batch closed in the admin."""
    broken_batch.status = 'closed'
    broken_batch.save()
    mock_site(PERSONAL)
    mock_site(LAB)
    mock_review_pr(number=9)
    call_command('publish_sites', orcid_id=ORCID)
    new = ReviewBatch.objects.get(pr_number=9)
    assert {p.doi for p in new.publications.all()} == {
        '10.1000/new', '10.1000/later'}
    assert set(Publication.objects.filter(
        doi__in=['10.1000/new', '10.1000/later'])
        .values_list('review_status', flat=True)) == {'pending'}
    assert calls_to('GET', f'{API}/repos/{PERSONAL}/pulls/7') == []
