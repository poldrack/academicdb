"""Propose hiding preprints whose published version is already in the database."""
from typing import Callable

from django.db.models import Q

from academic.models import Publication, PreprintHideProposal
from academic.tombstones import doi_key


def visible_preprints(user):
    return Publication.objects.filter(
        Q(is_preprint=True) | Q(publication_type='preprint'),
        owner=user, is_ignored=False, review_status='approved')


def published_candidates(user) -> list:
    return list(Publication.objects.filter(
        owner=user, is_preprint=False, is_ignored=False,
    ).exclude(publication_type='preprint'))


def _by_doi_key(published, doi):
    key = doi_key(doi)
    if not key:
        return None
    return next((p for p in published if doi_key(p.doi) == key), None)


def _crossref_match(published, crossref_dois):
    for doi in crossref_dois:
        pub = _by_doi_key(published, doi)
        if pub:
            return pub, 'crossref_relation', {
                'relation': 'is-preprint-of', 'doi': doi}
    return None


def _location_match(preprint, published, location_index):
    target = location_index.get(doi_key(preprint.doi))
    pub = _by_doi_key(published, target) if target else None
    if not pub:
        return None
    evidence = {'openalex_id': (preprint.identifiers or {}).get('openalex', ''),
                'published_doi': target}
    return pub, 'openalex_location', evidence


def _title_author_scores(preprint, pub):
    return (Publication._calculate_title_similarity(preprint.title, pub.title),
            Publication._calculate_author_overlap(preprint.authors, pub.authors))


def _title_author_match(preprint, published):
    """Best passing candidate: title sim, then author sim, then lowest id."""
    scored = [(_title_author_scores(preprint, pub), pub) for pub in published
              if Publication._is_likely_published_version(preprint, pub)]
    if not scored:
        return None
    (title_sim, author_sim), pub = min(
        scored, key=lambda sp: (-sp[0][0], -sp[0][1], sp[1].id))
    return pub, 'title_author', {
        'title_similarity': title_sim, 'author_similarity': author_sim}


def find_match(preprint, published, crossref_dois, location_index):
    return (_crossref_match(published, crossref_dois)
            or _location_match(preprint, published, location_index)
            or _title_author_match(preprint, published))


def _existing_proposals(user):
    """Return (preprint ids with live proposals, rejected (preprint, published) pairs)."""
    live, rejected = set(), set()
    rows = PreprintHideProposal.objects.filter(owner=user).values_list(
        'preprint_id', 'published_id', 'status')
    for preprint_id, published_id, status in rows:
        if status == 'rejected':
            rejected.add((preprint_id, published_id))
        else:
            live.add(preprint_id)
    return live, rejected


def _match_for(preprint, published, crossref_lookup, location_index, rejected):
    candidates = [p for p in published
                  if p.id != preprint.id and (preprint.id, p.id) not in rejected]
    crossref = crossref_lookup(preprint.doi) if doi_key(preprint.doi) else []
    return find_match(preprint, candidates, crossref, location_index)


def propose_hides(user, crossref_lookup: Callable[[str], list],
                  location_index: dict) -> list:
    published = published_candidates(user)
    live, rejected = _existing_proposals(user)
    created = []
    for preprint in visible_preprints(user):
        if preprint.id in live:
            continue
        match = _match_for(preprint, published, crossref_lookup,
                           location_index, rejected)
        if match:
            created.append(_create(user, preprint, *match))
    return created


def _create(user, preprint, pub, method, evidence):
    proposal, _ = PreprintHideProposal.objects.get_or_create(
        preprint=preprint, published=pub,
        defaults={'owner': user, 'method': method, 'evidence': evidence})
    return proposal
