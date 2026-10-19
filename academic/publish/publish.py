"""Push the public YAML to both sites and drive the weekly review PR."""
from dataclasses import dataclass
from typing import Callable, Mapping

from django.core.management.base import CommandError
from django.db import transaction

from academic.publish.batches import open_batch
from academic.publish.decisions import process_pr
from academic.publish.github import GitHub
from academic.publish.review_pr import open_review_pr, remind_if_stale
from academic.publish.site_yaml import render_site_yaml, site_records

COMMIT_MESSAGE = 'Update publications (academicdb)'
DEFAULT_REPOS = {
    'PERSONAL_SITE_REPO': 'poldrack/poldrack.github.io',
    'LAB_SITE_REPO': 'poldracklab/poldracklab.github.io',
    'PIPELINE_REPO': 'poldrack/academicdb',
}
TOKEN_VARS = ('PERSONAL_GITHUB_TOKEN', 'LAB_GITHUB_TOKEN')
HELD_COMMENT = (
    'These review entries were edited and matched nothing in this review, '
    'so the items they would have decided are held:\n\n{keys}\n\n'
    'The held items will be offered again in the next review.'
)


# Configuration

def _token(env, name, dry_run):
    value = env.get(name) or None
    if value is None and not dry_run:
        raise CommandError(f'{name} is not set')
    return value


@dataclass(frozen=True)
class PublishConfig:
    personal_repo: str
    lab_repo: str
    pipeline_repo: str
    personal_token: str | None
    lab_token: str | None
    site_path: str = 'publications.yml'

    @classmethod
    def from_env(cls, env: Mapping, dry_run: bool = False):
        repos = {k: env.get(k) or v for k, v in DEFAULT_REPOS.items()}
        personal, lab = (_token(env, n, dry_run) for n in TOKEN_VARS)
        return cls(
            personal_repo=repos['PERSONAL_SITE_REPO'],
            lab_repo=repos['LAB_SITE_REPO'],
            pipeline_repo=repos['PIPELINE_REPO'],
            personal_token=personal, lab_token=lab,
        )


# Dry-run client

class DryRunGitHub(GitHub):
    """Reads go to GitHub; writes are only recorded in ``self.writes``."""

    def __init__(self, token, api='https://api.github.com'):
        super().__init__(token, api=api)
        self.writes = []

    def _log(self, text):
        self.writes.append(text)

    def put_file(self, repo, path, text, message, branch='main', sha=None):
        self._log(f'PUT {repo}/{path} on {branch}: {message}')
        return 'dry-run'

    def delete_file(self, repo, path, message, sha, branch='main'):
        self._log(f'DELETE {repo}/{path} on {branch}: {message}')

    def create_branch(self, repo, branch, from_branch='main'):
        self._log(f'CREATE BRANCH {repo}:{branch} from {from_branch}')

    def open_pr(self, repo, head, title, body, base='main'):
        self._log(f'OPEN PR {repo} {head} -> {base}: {title}')
        return 0

    def comment(self, repo, number, body):
        first = (body.splitlines() or [''])[0]
        self._log(f'COMMENT {repo}#{number}: {first}')

    def open_issue(self, repo, title, body):
        self._log(f'OPEN ISSUE {repo}: {title}')
        return 0

    def close_issue(self, repo, number, body):
        self._log(f'CLOSE ISSUE {repo}#{number}')


def _as_dry_run(gh):
    if isinstance(gh, DryRunGitHub):
        return gh
    dry = DryRunGitHub(None, api=gh.api)
    dry.session = gh.session
    return dry


# Public YAML

def _publish_one(gh, repo, site_path, text):
    current = gh.get_file(repo, site_path)
    if current is not None and current.text == text:
        return False
    gh.put_file(repo, site_path, text, COMMIT_MESSAGE,
                sha=current.sha if current else None)
    return True


def publish_public(user, targets, site_path, dry_run=False):
    """Push the public YAML to each (client, repo); return repos updated."""
    text = render_site_yaml(site_records(user))
    updated = []
    for gh, repo in targets:
        client = _as_dry_run(gh) if dry_run else gh
        if _publish_one(client, repo, site_path, text):
            updated.append(repo)
    return updated


# Review PR decisions

def decisions_summary(number, decisions):
    return (f'Review PR #{number}: approved {len(decisions.approved)}, '
            f'rejected {len(decisions.rejected)}, '
            f'hidden {len(decisions.hidden)}, kept {len(decisions.kept)}, '
            f'held {len(decisions.unmatched)}')


def _comment_held(batch, gh, repo, unmatched):
    keys = '\n'.join(f'- {key}' for key in unmatched)
    gh.comment(repo, batch.pr_number, HELD_COMMENT.format(keys=keys))


def decide_batch(batch, gh, repo, now, log):
    """Apply a decided review PR; report it and comment on held items."""
    decisions = process_pr(batch, gh, repo, now)
    if decisions is None:
        return None
    log(decisions_summary(batch.pr_number, decisions))
    if decisions.unmatched:
        _comment_held(batch, gh, repo, decisions.unmatched)
    return decisions


# Commands

@dataclass
class Sites:
    personal: GitHub
    lab: GitHub
    config: PublishConfig

    @classmethod
    def build(cls, config, dry_run=False):
        make = DryRunGitHub if dry_run else GitHub
        return cls(make(config.personal_token), make(config.lab_token),
                   config)

    def targets(self):
        return [(self.personal, self.config.personal_repo),
                (self.lab, self.config.lab_repo)]

    def writes(self):
        return [w for gh in (self.personal, self.lab)
                for w in getattr(gh, 'writes', [])]


def _publish_and_log(user, sites, dry_run, log):
    updated = publish_public(user, sites.targets(), sites.config.site_path,
                             dry_run=dry_run)
    for _, repo in sites.targets():
        state = 'updated' if repo in updated else 'unchanged'
        log(f'{repo}/{sites.config.site_path}: {state}')


def _review_step(user, sites, now, log):
    repo = sites.config.personal_repo
    batch = open_batch(user)
    if batch is not None:
        if remind_if_stale(batch, sites.personal, repo, now):
            log(f'Reminded on review PR #{batch.pr_number}')
        return
    opened = open_review_pr(user, sites.personal, repo, now)
    if opened is not None:
        log(f'Opened review PR #{opened.pr_number}')


def _publish_sites_body(user, sites, now, dry_run, log):
    batch = open_batch(user)
    if batch is not None:
        decide_batch(batch, sites.personal, sites.config.personal_repo,
                     now, log)
    _publish_and_log(user, sites, dry_run, log)
    _review_step(user, sites, now, log)


class _DryRunRollback(Exception):
    pass


def _log_planned(sites, log):
    log('Planned writes (dry run, nothing written):')
    for write in sites.writes():
        log(f'  {write}')


def run_publish_sites(user, config, now, dry_run=False,
                      log: Callable[[str], None] = print):
    """Decide any finished review, publish both sites, then review/remind."""
    sites = Sites.build(config, dry_run=dry_run)
    if not dry_run:
        _publish_sites_body(user, sites, now, False, log)
        return
    try:
        with transaction.atomic():
            _publish_sites_body(user, sites, now, True, log)
            raise _DryRunRollback
    except _DryRunRollback:
        pass
    _log_planned(sites, log)


def run_process_review(user, batch, config, now, log=print):
    """Decide one review PR (from a dispatch), then publish both sites."""
    sites = Sites.build(config)
    decide_batch(batch, sites.personal, config.personal_repo, now, log)
    _publish_and_log(user, sites, False, log)
