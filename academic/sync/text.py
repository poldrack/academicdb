"""Shared text helpers for sync sources."""
import html
import re

from academic.models import Publication

TAG_RE = re.compile(r'<[^>]+>')


def clean_markup(raw) -> str:
    """Strip HTML/XML tags, unescape entities and collapse whitespace."""
    text = html.unescape(TAG_RE.sub('', str(raw or '')))
    return ' '.join(text.split())


def fit_field(name: str, value):
    """Truncate a string to the Publication field's max_length (if any)."""
    limit = Publication._meta.get_field(name).max_length
    if isinstance(value, str) and limit:
        return value[:limit]
    return value
