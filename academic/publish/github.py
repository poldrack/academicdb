"""Small GitHub REST client for the publishing pipeline."""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

TIMEOUT = 30
LABEL = 'pipeline'


class GitHubError(Exception):
    """Carries method, path and status only; never tokens or bodies."""


@dataclass
class RepoFile:
    text: str
    sha: str


def _b64(text: str) -> str:
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.astimezone(timezone.utc)


class GitHub:
    def __init__(self, token: str | None, api: str = 'https://api.github.com'):
        self.api = api.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'

    def _request(self, method, path, allow=(), **kw):
        kw.setdefault('timeout', TIMEOUT)
        try:
            resp = self.session.request(method, self.api + path, **kw)
        except requests.RequestException as exc:
            raise GitHubError(
                f'{method} {path} -> {type(exc).__name__}') from None
        if resp.status_code >= 400 and resp.status_code not in allow:
            raise GitHubError(f'{method} {path} -> {resp.status_code}')
        return resp

    # Files
    def get_file(self, repo, path, ref='main') -> RepoFile | None:
        resp = self._request('GET', f'/repos/{repo}/contents/{path}',
                             allow=(404,), params={'ref': ref})
        if resp.status_code == 404:
            return None
        data = resp.json()
        text = base64.b64decode(data['content']).decode('utf-8')
        return RepoFile(text=text, sha=data['sha'])

    def put_file(self, repo, path, text, message, branch='main',
                 sha=None) -> str:
        payload = {'message': message, 'content': _b64(text),
                   'branch': branch}
        if sha:
            payload['sha'] = sha
        resp = self._request('PUT', f'/repos/{repo}/contents/{path}',
                             json=payload)
        return resp.json()['commit']['sha']

    def delete_file(self, repo, path, message, sha, branch='main') -> None:
        self._request('DELETE', f'/repos/{repo}/contents/{path}',
                      json={'message': message, 'sha': sha,
                            'branch': branch})

    # Branches and pull requests
    def create_branch(self, repo, branch, from_branch='main') -> None:
        ref = self._request('GET',
                            f'/repos/{repo}/git/ref/heads/{from_branch}')
        resp = self._request(
            'POST', f'/repos/{repo}/git/refs', allow=(422,),
            json={'ref': f'refs/heads/{branch}',
                  'sha': ref.json()['object']['sha']})
        if resp.status_code == 422 and not _already_exists(resp):
            raise GitHubError(
                f'POST /repos/{repo}/git/refs -> {resp.status_code}')

    def open_pr(self, repo, head, title, body, base='main') -> int:
        resp = self._request('POST', f'/repos/{repo}/pulls',
                             json={'head': head, 'title': title,
                                   'body': body, 'base': base})
        return resp.json()['number']

    def get_pr(self, repo, number) -> dict:
        return self._request('GET', f'/repos/{repo}/pulls/{number}').json()

    def comment(self, repo, number, body) -> None:
        self._request('POST', f'/repos/{repo}/issues/{number}/comments',
                      json={'body': body})

    # Issues
    def find_open_issue(self, repo, title) -> int | None:
        resp = self._request(
            'GET', f'/repos/{repo}/issues',
            params={'state': 'open', 'labels': LABEL, 'per_page': 100})
        for item in resp.json():
            if 'pull_request' not in item and item.get('title') == title:
                return item['number']
        return None

    def open_issue(self, repo, title, body) -> int:
        resp = self._request('POST', f'/repos/{repo}/issues',
                             json={'title': title, 'body': body,
                                   'labels': [LABEL]})
        return resp.json()['number']

    def close_issue(self, repo, number, body) -> None:
        self.comment(repo, number, body)
        self._request('PATCH', f'/repos/{repo}/issues/{number}',
                      json={'state': 'closed'})

    # Runs
    def latest_success(self, repo, workflow_file) -> datetime | None:
        resp = self._request(
            'GET', f'/repos/{repo}/actions/workflows/{workflow_file}/runs',
            params={'status': 'success', 'per_page': 1})
        runs = resp.json().get('workflow_runs') or []
        return _parse_time(runs[0]['updated_at']) if runs else None


def _already_exists(resp) -> bool:
    try:
        return 'already exists' in str(resp.json().get('message', ''))
    except ValueError:
        return False
