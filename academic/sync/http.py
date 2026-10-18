import time

import requests

USER_AGENT = 'academicdb (+https://github.com/poldrack/academicdb)'


class SourceError(Exception):
    pass


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def get(url, params=None, *, timeout=30, retries=3, backoff=2.0):
    headers = {'User-Agent': USER_AGENT}
    for attempt in range(retries + 1):
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code < 400:
            return resp
        if not _retryable(resp.status_code) or attempt == retries:
            raise SourceError(f'{url}: HTTP {resp.status_code}')
        time.sleep(backoff ** attempt)
