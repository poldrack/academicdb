import time

import requests

USER_AGENT = 'academicdb (+https://github.com/poldrack/academicdb)'


class SourceError(Exception):
    pass


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _attempt(url, params, timeout):
    headers = {'User-Agent': USER_AGENT}
    try:
        return requests.get(url, params=params, headers=headers, timeout=timeout), None
    except requests.RequestException as exc:
        return None, exc


def get(url, params=None, *, timeout=30, retries=3, backoff=2.0):
    for attempt in range(retries + 1):
        resp, exc = _attempt(url, params, timeout)
        if exc is None and resp.status_code < 400:
            return resp
        if exc is None and not _retryable(resp.status_code):
            raise SourceError(f'{url}: HTTP {resp.status_code}')
        if attempt == retries:
            if exc is not None:
                raise SourceError(f'{url}: {exc.__class__.__name__}') from exc
            raise SourceError(f'{url}: HTTP {resp.status_code}')
        time.sleep(backoff ** attempt)


def get_json(url, params=None, **kwargs):
    resp = get(url, params, **kwargs)
    try:
        data = resp.json()
    except ValueError as exc:
        raise SourceError(f'{url}: invalid JSON') from exc
    if not isinstance(data, dict):
        raise SourceError(f'{url}: unexpected JSON body')
    return data
