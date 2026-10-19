"""Failure issues and the stale-pipeline heartbeat."""
from datetime import datetime, timedelta

RETRY_LINE = ('Check the run log; the next scheduled run will retry, but a '
              'broken review file needs the fix described in the README.')


def _failing_title(workflow: str) -> str:
    return f'Pipeline failing: {workflow}'


def _stalled_title(workflow_file: str) -> str:
    return f'Pipeline stalled: {workflow_file}'


def _open_or_comment(gh, repo, title, body) -> int:
    number = gh.find_open_issue(repo, title)
    if number is None:
        return gh.open_issue(repo, title, body)
    gh.comment(repo, number, body)
    return number


def _close_if_open(gh, repo, title, body) -> bool:
    number = gh.find_open_issue(repo, title)
    if number is None:
        return False
    gh.close_issue(repo, number, body)
    return True


def report_failure(gh, repo, workflow: str, run_url: str) -> int:
    body = f'Run failed: {run_url}\n\n{RETRY_LINE}'
    return _open_or_comment(gh, repo, _failing_title(workflow), body)


def resolve_failure(gh, repo, workflow: str, run_url: str) -> bool:
    return _close_if_open(gh, repo, _failing_title(workflow),
                          f'Recovered in {run_url}.')


def _stalled_body(workflow_file, last, max_age_days) -> str:
    when = last.strftime('%Y-%m-%d') if last else 'never'
    return (f'No successful run of {workflow_file} in the last '
            f'{max_age_days} days. Last success: {when}.')


def check_heartbeat(gh, repo, workflow_file: str, now: datetime,
                    max_age_days: int = 14) -> bool:
    """Return True when the workflow has succeeded recently."""
    title = _stalled_title(workflow_file)
    last = gh.latest_success(repo, workflow_file)
    if last is None or now - last > timedelta(days=max_age_days):
        _open_or_comment(gh, repo, title,
                         _stalled_body(workflow_file, last, max_age_days))
        return False
    _close_if_open(gh, repo, title,
                   f'{workflow_file} has succeeded again ({last:%Y-%m-%d}).')
    return True
