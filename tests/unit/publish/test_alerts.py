"""Tests for failure issues and the heartbeat (GitHub mocked)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import responses
from django.core.management import call_command
from django.core.management.base import CommandError

from academic.publish.alerts import (
    check_heartbeat, report_failure, resolve_failure)
from academic.publish.github import GitHub

API = 'https://api.github.com'
REPO = 'owner/site'
WORKFLOW = 'weekly-sync.yml'
RUN_URL = 'https://github.com/owner/site/actions/runs/42'
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
FAIL_TITLE = f'Pipeline failing: {WORKFLOW}'
STALL_TITLE = f'Pipeline stalled: {WORKFLOW}'


@pytest.fixture
def gh():
    return GitHub('tok')


def body(call):
    return json.loads(call.request.body)


def mock_issues(items):
    responses.get(f'{API}/repos/{REPO}/issues', json=items)


def mock_runs(updated_at):
    runs = [{'updated_at': updated_at}] if updated_at else []
    responses.get(f'{API}/repos/{REPO}/actions/workflows/{WORKFLOW}/runs',
                  json={'workflow_runs': runs})


def posts(path_suffix):
    return [c for c in responses.calls
            if c.request.method == 'POST'
            and c.request.url.endswith(path_suffix)]


@responses.activate
def test_failure_opens_issue_once_then_comments(gh):
    mock_issues([])
    responses.post(f'{API}/repos/{REPO}/issues', json={'number': 7})
    assert report_failure(gh, REPO, WORKFLOW, RUN_URL) == 7
    opened = body(posts('/issues')[0])
    assert opened['title'] == FAIL_TITLE
    assert RUN_URL in opened['body']
    assert ('Check the run log; the next scheduled run will retry, but a broken '
            'review file needs the fix described in the README.'
            in opened['body'])

    responses.reset()
    mock_issues([{'number': 7, 'title': FAIL_TITLE}])
    responses.post(f'{API}/repos/{REPO}/issues/7/comments', json={})
    assert report_failure(gh, REPO, WORKFLOW, RUN_URL) == 7
    assert not posts('/issues')
    assert RUN_URL in body(posts('/issues/7/comments')[0])['body']


@responses.activate
def test_recovered_closes_open_issue(gh):
    mock_issues([{'number': 7, 'title': FAIL_TITLE}])
    responses.post(f'{API}/repos/{REPO}/issues/7/comments', json={})
    responses.patch(f'{API}/repos/{REPO}/issues/7', json={})
    assert resolve_failure(gh, REPO, WORKFLOW, RUN_URL) is True
    assert body(posts('/issues/7/comments')[0])['body'] == (
        f'Recovered in {RUN_URL}.')
    patch = [c for c in responses.calls if c.request.method == 'PATCH'][0]
    assert body(patch) == {'state': 'closed'}


@responses.activate
def test_recovered_without_issue_is_noop(gh):
    mock_issues([])
    assert resolve_failure(gh, REPO, WORKFLOW, RUN_URL) is False
    assert len(responses.calls) == 1


@responses.activate
def test_heartbeat_stale_opens_issue(gh):
    stale = (NOW - timedelta(days=15)).isoformat()
    mock_runs(stale)
    mock_issues([])
    responses.post(f'{API}/repos/{REPO}/issues', json={'number': 9})
    assert check_heartbeat(gh, REPO, WORKFLOW, NOW) is False
    opened = body(posts('/issues')[0])
    assert opened['title'] == STALL_TITLE
    assert '2026-10-04' in opened['body']


@responses.activate
def test_heartbeat_never_succeeded_opens_issue(gh):
    mock_runs(None)
    mock_issues([])
    responses.post(f'{API}/repos/{REPO}/issues', json={'number': 9})
    assert check_heartbeat(gh, REPO, WORKFLOW, NOW) is False
    assert 'never' in body(posts('/issues')[0])['body']


@responses.activate
def test_heartbeat_fresh_closes_issue(gh):
    mock_runs((NOW - timedelta(days=13)).isoformat())
    mock_issues([{'number': 9, 'title': STALL_TITLE}])
    responses.post(f'{API}/repos/{REPO}/issues/9/comments', json={})
    responses.patch(f'{API}/repos/{REPO}/issues/9', json={})
    assert check_heartbeat(gh, REPO, WORKFLOW, NOW) is True
    assert posts('/issues/9/comments')


def test_command_requires_token(monkeypatch):
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    monkeypatch.setenv('GITHUB_REPOSITORY', REPO)
    with pytest.raises(CommandError, match='GITHUB_TOKEN'):
        call_command('pipeline_alert', 'failure', workflow=WORKFLOW,
                     run_url=RUN_URL)


def test_command_requires_repository(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'tok')
    monkeypatch.delenv('GITHUB_REPOSITORY', raising=False)
    with pytest.raises(CommandError, match='GITHUB_REPOSITORY'):
        call_command('pipeline_alert', 'failure', workflow=WORKFLOW,
                     run_url=RUN_URL)


@responses.activate
def test_command_failure_opens_issue(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'tok')
    monkeypatch.setenv('GITHUB_REPOSITORY', REPO)
    mock_issues([])
    responses.post(f'{API}/repos/{REPO}/issues', json={'number': 3})
    call_command('pipeline_alert', 'failure', workflow=WORKFLOW,
                 run_url=RUN_URL)
    assert body(posts('/issues')[0])['title'] == FAIL_TITLE


def test_command_failure_needs_run_url(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'tok')
    monkeypatch.setenv('GITHUB_REPOSITORY', REPO)
    with pytest.raises(CommandError, match='run-url'):
        call_command('pipeline_alert', 'failure', workflow=WORKFLOW)


@responses.activate
def test_command_github_error_is_command_error(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'tok')
    monkeypatch.setenv('GITHUB_REPOSITORY', REPO)
    responses.get(f'{API}/repos/{REPO}/issues', status=500)
    with pytest.raises(CommandError):
        call_command('pipeline_alert', 'failure', workflow=WORKFLOW,
                     run_url=RUN_URL)
