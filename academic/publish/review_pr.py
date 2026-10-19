"""Open the weekly review pull request and remind about stale ones."""
from datetime import timedelta

import yaml

from academic.publish.batches import create_batch, open_batch, reviewable_items
from academic.publish.site_yaml import site_record

REVIEW_HEADER = (
    '# Delete an entry under "new" to reject that paper.\n'
    '# Delete an entry under "hide" to keep that preprint visible.\n'
    '# Edits to fields are ignored; make content edits in the local app.\n'
)
STALE_AFTER = timedelta(days=14)
REMINDER = ('This review has been open for 14 days. '
            'New discoveries wait until it is merged or closed.')
MAX_AUTHORS = 3
MAX_BODY = 60000
TRUNCATED = '…list truncated; the review file has every item.'


class ReviewPRError(Exception):
    """The PR was opened but its batch could not be recorded."""


def _hide_entry(proposal):
    published = proposal.published
    return {
        **site_record(proposal.preprint),
        'published_as': {'doi': published.doi or '', 'title': published.title},
        'evidence': {'method': proposal.method, **(proposal.evidence or {})},
    }


def review_yaml(pubs, proposals):
    data = {
        'new': [site_record(p) for p in pubs],
        'hide': [_hide_entry(p) for p in proposals],
    }
    body = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, width=10000)
    return REVIEW_HEADER + body


def _plural(count, noun):
    return f'{count} {noun}' + ('' if count == 1 else 's')


def pr_title(pubs, proposals):
    parts = []
    if pubs:
        parts.append(f'{_plural(len(pubs), "new paper")}')
    if proposals:
        parts.append(f'{_plural(len(proposals), "preprint")} to hide')
    return 'Review: ' + ', '.join(parts)


def _author_names(pub):
    return [a.get('name', '') for a in (pub.authors or [])
            if isinstance(a, dict) and a.get('name')]


def _author_text(pub):
    names = _author_names(pub)
    text = ', '.join(names[:MAX_AUTHORS])
    return text + ', et al.' if len(names) > MAX_AUTHORS else text


def _links(pub):
    ids = pub.identifiers or {}
    links = []
    if pub.doi:
        links.append(f'https://doi.org/{pub.doi}')
    if ids.get('openalex'):
        links.append(f'https://openalex.org/{ids["openalex"]}')
    if ids.get('pmid'):
        links.append(f'https://pubmed.ncbi.nlm.nih.gov/{ids["pmid"]}/')
    return links


def _paper_lines(pub):
    meta = ', '.join(str(x) for x in (pub.publication_name, pub.year) if x)
    lines = [f'- **{pub.title}**' + (f' ({meta})' if meta else '')]
    authors = _author_text(pub)
    if authors:
        lines.append(f'  {authors}')
    lines.extend(f'  {link}' for link in _links(pub))
    return lines


def _hide_lines(proposal):
    published = proposal.published
    doi_link = f'https://doi.org/{published.doi}' if published.doi else ''
    lines = [f'- "{proposal.preprint.title}" hidden because it was '
             f'published as "{published.title}" ({doi_link})',
             f'  method: {proposal.method}']
    lines.extend(f'  {k}: {v}' for k, v in (proposal.evidence or {}).items())
    return lines


def pr_body(pubs, proposals):
    lines = []
    if pubs:
        lines += ['## New papers', '']
        for pub in pubs:
            lines += _paper_lines(pub)
    if proposals:
        lines += ['', '## Preprints to hide', '']
        for proposal in proposals:
            lines += _hide_lines(proposal)
    return _cap_body('\n'.join(lines) + '\n')


def _cap_body(body):
    if len(body) <= MAX_BODY:
        return body
    room = MAX_BODY - len(TRUNCATED) - 1
    cut = body[:room].rsplit('\n', 1)[0]
    return cut + '\n' + TRUNCATED


def open_review_pr(user, gh, repo, now):
    if open_batch(user):
        return None
    pubs, proposals = reviewable_items(user)
    if not pubs and not proposals:
        return None
    day = now.date().isoformat()
    branch, path = f'academicdb/review-{day}', f'review/{day}.yml'
    gh.create_branch(repo, branch)
    existing = gh.get_file(repo, path, ref=branch)
    gh.put_file(repo, path, review_yaml(pubs, proposals),
                'Add review file', branch=branch,
                sha=existing.sha if existing else None)
    number = gh.open_pr(repo, branch, pr_title(pubs, proposals),
                        pr_body(pubs, proposals))
    return _record_batch(user, number, branch, path, pubs, proposals, now)


def _record_batch(user, number, branch, path, pubs, proposals, now):
    try:
        return create_batch(user, number, branch, path, pubs, proposals, now)
    except Exception as exc:
        raise ReviewPRError(
            f'Review PR #{number} was opened but its batch could not be '
            'saved; close it by hand') from exc


def remind_if_stale(batch, gh, repo, now):
    if batch.status != 'open' or batch.reminded_at:
        return False
    if now - batch.opened_at < STALE_AFTER:
        return False
    gh.comment(repo, batch.pr_number, REMINDER)
    batch.reminded_at = now
    batch.save(update_fields=['reminded_at'])
    return True
