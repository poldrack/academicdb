"""Tests for the GitHub REST client (no network; mocked with responses)."""
import base64
import json
from datetime import datetime, timezone

import pytest
import responses

from academic.publish.github import GitHub, GitHubError, RepoFile

API = 'https://api.github.com'
REPO = 'owner/site'
TOKEN = 'secret-token-xyz'


@pytest.fixture
def gh():
    return GitHub(TOKEN)


def body(call):
    return json.loads(call.request.body)


@responses.activate
def test_auth_and_standard_headers(gh):
    responses.get(f'{API}/repos/{REPO}/pulls/1', json={'state': 'open'})
    gh.get_pr(REPO, 1)
    h = responses.calls[0].request.headers
    assert h['Authorization'] == f'Bearer {TOKEN}'
    assert h['Accept'] == 'application/vnd.github+json'
    assert h['X-GitHub-Api-Version'] == '2022-11-28'


@responses.activate
def test_no_auth_header_without_token():
    responses.get(f'{API}/repos/{REPO}/pulls/1', json={'state': 'open'})
    GitHub(None).get_pr(REPO, 1)
    assert 'Authorization' not in responses.calls[0].request.headers


@responses.activate
def test_get_file_decodes(gh):
    content = base64.b64encode('héllo'.encode()).decode()
    responses.get(f'{API}/repos/{REPO}/contents/a/b.yml',
                  json={'content': content, 'sha': 'abc'})
    result = gh.get_file(REPO, 'a/b.yml', ref='dev')
    assert result == RepoFile(text='héllo', sha='abc')
    assert 'ref=dev' in responses.calls[0].request.url


@responses.activate
def test_get_file_404_is_none(gh):
    responses.get(f'{API}/repos/{REPO}/contents/x', status=404)
    assert gh.get_file(REPO, 'x') is None


@responses.activate
def test_put_file_without_sha(gh):
    responses.put(f'{API}/repos/{REPO}/contents/x.yml',
                  json={'commit': {'sha': 'c1'}})
    assert gh.put_file(REPO, 'x.yml', 'hi', 'msg', branch='b') == 'c1'
    sent = body(responses.calls[0])
    assert sent == {'message': 'msg', 'branch': 'b',
                    'content': base64.b64encode(b'hi').decode()}


@responses.activate
def test_put_file_with_sha(gh):
    responses.put(f'{API}/repos/{REPO}/contents/x.yml',
                  json={'commit': {'sha': 'c2'}})
    gh.put_file(REPO, 'x.yml', 'hi', 'msg', sha='old')
    assert body(responses.calls[0])['sha'] == 'old'
    assert body(responses.calls[0])['branch'] == 'main'


@responses.activate
def test_delete_file(gh):
    responses.delete(f'{API}/repos/{REPO}/contents/x.yml', json={})
    assert gh.delete_file(REPO, 'x.yml', 'rm', 'sha1', branch='b') is None
    assert body(responses.calls[0]) == {'message': 'rm', 'sha': 'sha1',
                                        'branch': 'b'}


@responses.activate
def test_create_branch(gh):
    responses.get(f'{API}/repos/{REPO}/git/ref/heads/main',
                  json={'object': {'sha': 's0'}})
    responses.post(f'{API}/repos/{REPO}/git/refs', json={}, status=201)
    gh.create_branch(REPO, 'feat')
    assert body(responses.calls[1]) == {'ref': 'refs/heads/feat', 'sha': 's0'}


@responses.activate
def test_create_branch_tolerates_existing(gh):
    responses.get(f'{API}/repos/{REPO}/git/ref/heads/main',
                  json={'object': {'sha': 's0'}})
    responses.post(f'{API}/repos/{REPO}/git/refs', status=422,
                   json={'message': 'Reference already exists'})
    assert gh.create_branch(REPO, 'feat') is None


@responses.activate
def test_create_branch_other_422_raises(gh):
    responses.get(f'{API}/repos/{REPO}/git/ref/heads/main',
                  json={'object': {'sha': 's0'}})
    responses.post(f'{API}/repos/{REPO}/git/refs', status=422,
                   json={'message': 'Validation Failed'})
    with pytest.raises(GitHubError):
        gh.create_branch(REPO, 'feat')


@responses.activate
def test_open_pr(gh):
    responses.post(f'{API}/repos/{REPO}/pulls', json={'number': 7})
    assert gh.open_pr(REPO, 'feat', 'T', 'B') == 7
    assert body(responses.calls[0]) == {'head': 'feat', 'title': 'T',
                                        'body': 'B', 'base': 'main'}


@responses.activate
def test_get_pr(gh):
    data = {'state': 'closed', 'merged': True, 'merge_commit_sha': 'm',
            'head': {'ref': 'feat'}}
    responses.get(f'{API}/repos/{REPO}/pulls/7', json=data)
    assert gh.get_pr(REPO, 7) == data


@responses.activate
def test_comment(gh):
    responses.post(f'{API}/repos/{REPO}/issues/7/comments', json={})
    assert gh.comment(REPO, 7, 'hello') is None
    assert body(responses.calls[0]) == {'body': 'hello'}


@responses.activate
def test_find_open_issue_exact_title_skips_prs(gh):
    responses.get(f'{API}/repos/{REPO}/issues', json=[
        {'number': 1, 'title': 'Pipe failed', 'pull_request': {}},
        {'number': 2, 'title': 'Pipe failed again'},
        {'number': 3, 'title': 'Pipe failed'},
    ])
    assert gh.find_open_issue(REPO, 'Pipe failed') == 3
    url = responses.calls[0].request.url
    assert 'state=open' in url and 'labels=pipeline' in url
    assert 'per_page=100' in url


@responses.activate
def test_find_open_issue_none(gh):
    responses.get(f'{API}/repos/{REPO}/issues', json=[])
    assert gh.find_open_issue(REPO, 'x') is None


@responses.activate
def test_open_issue(gh):
    responses.post(f'{API}/repos/{REPO}/issues', json={'number': 9})
    assert gh.open_issue(REPO, 'T', 'B') == 9
    assert body(responses.calls[0]) == {'title': 'T', 'body': 'B',
                                        'labels': ['pipeline']}


@responses.activate
def test_close_issue_comments_then_closes(gh):
    responses.post(f'{API}/repos/{REPO}/issues/9/comments', json={})
    responses.patch(f'{API}/repos/{REPO}/issues/9', json={})
    assert gh.close_issue(REPO, 9, 'fixed') is None
    assert responses.calls[0].request.method == 'POST'
    assert body(responses.calls[0]) == {'body': 'fixed'}
    assert responses.calls[1].request.method == 'PATCH'
    assert body(responses.calls[1]) == {'state': 'closed'}


@responses.activate
def test_latest_success(gh):
    responses.get(f'{API}/repos/{REPO}/actions/workflows/p.yml/runs',
                  json={'workflow_runs': [
                      {'updated_at': '2026-10-19T12:30:00Z'}]})
    assert gh.latest_success(REPO, 'p.yml') == datetime(
        2026, 10, 19, 12, 30, tzinfo=timezone.utc)
    url = responses.calls[0].request.url
    assert 'status=success' in url and 'per_page=1' in url


@responses.activate
def test_latest_success_empty(gh):
    responses.get(f'{API}/repos/{REPO}/actions/workflows/p.yml/runs',
                  json={'workflow_runs': []})
    assert gh.latest_success(REPO, 'p.yml') is None


@responses.activate
def test_server_error_hides_token_and_body(gh):
    responses.get(f'{API}/repos/{REPO}/pulls/1', status=500,
                  body='echo secret-body-data')
    with pytest.raises(GitHubError) as exc:
        gh.get_pr(REPO, 1)
    text = str(exc.value)
    assert TOKEN not in text
    assert 'secret-body-data' not in text
    assert 'GET' in text and '500' in text and f'/repos/{REPO}/pulls/1' in text
