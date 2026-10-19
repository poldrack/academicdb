"""Tests for applying review decisions when the review PR is decided."""
import base64
import json
from datetime import datetime, timezone

import pytest
import responses

from academic.models import (
    PreprintHideProposal, Publication, RejectedWork, ReviewBatch,
)
from academic.publish.batches import create_batch
from academic.publish.decisions import (
    Decisions, ReviewFileError, apply_closed, apply_merged,
    parse_review_file, process_pr,
)
from academic.publish.github import GitHub
from academic.publish.review_pr import review_yaml
from academic.sync.review import confirm_hide
from tests.factories import PublicationFactory

API = 'https://api.github.com'
REPO = 'owner/site'
PATH = 'review/2026-10-19.yml'
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def gh():
    return GitHub('tok')


def make_pending(user, doi, **kw):
    return PublicationFactory(owner=user, doi=doi, review_status='pending',
                              **kw)


def make_preprint(user, doi):
    return PublicationFactory(
        owner=user, is_preprint=True, publication_type='preprint', doi=doi,
        review_status='approved')


def make_proposal(user, preprint, published):
    return PreprintHideProposal.objects.create(
        owner=user, preprint=preprint, published=published,
        method='crossref_relation', evidence={'relation': 'is-preprint-of'})


def make_batch(user, pubs, proposals):
    return create_batch(user, 7, 'academicdb/review-2026-10-19', PATH,
                        pubs, proposals, NOW)


def pub_exists(pub):
    return Publication.objects.filter(pk=pub.pk).exists()


def status_of(proposal):
    return PreprintHideProposal.objects.get(pk=proposal.pk).status


@pytest.fixture
def scenario(academic_user):
    """Two pending pubs and two hide proposals, all in one open batch."""
    keep = make_pending(academic_user, '10.1000/keep')
    drop = make_pending(academic_user, '10.1000/drop')
    target = PublicationFactory(owner=academic_user, doi='10.1000/target',
                                review_status='approved')
    hide_pp = make_preprint(academic_user, '10.1101/hide')
    keep_pp = make_preprint(academic_user, '10.1101/keep')
    hide_prop = make_proposal(academic_user, hide_pp, target)
    keep_prop = make_proposal(academic_user, keep_pp, target)
    batch = make_batch(academic_user, [keep, drop], [hide_prop, keep_prop])
    text = review_yaml([keep], [hide_prop])
    return dict(keep=keep, drop=drop, hide_pp=hide_pp, keep_pp=keep_pp,
                hide_prop=hide_prop, keep_prop=keep_prop, batch=batch,
                text=text)


def snapshot():
    pubs = sorted(Publication.objects.values_list(
        'id', 'review_status', 'is_ignored'))
    props = sorted(PreprintHideProposal.objects.values_list('id', 'status'))
    return pubs, props, RejectedWork.objects.count()


# parse_review_file

def test_parse_review_file_returns_keys(academic_user, scenario):
    new, hide = parse_review_file(scenario['text'])
    assert new == {'10.1000/keep'}
    assert hide == {'10.1101/hide'}


def test_parse_review_file_pmid_key_and_empty_lists():
    new, hide = parse_review_file(
        'new:\n- {doi: null, identifiers: {pmid: "123"}}\nhide: []\n')
    assert new == {'pmid:123'}
    assert hide == set()


@pytest.mark.parametrize('text', [
    'new: [unclosed', '[]', 'new: []', 'hide: []', 'new: {}\nhide: []',
    'new: []\nhide: 3', 'new: [3]\nhide: []',
])
def test_parse_review_file_rejects_invalid(text):
    with pytest.raises(ReviewFileError):
        parse_review_file(text)


def test_parse_review_file_skips_keyless_entries():
    new, hide = parse_review_file(
        'new:\n- {doi: "10.1/a"}\n- {doi: null, identifiers: {}}\n'
        'hide:\n- {doi: null, title: x}\n- {doi: "10.1101/b"}\n')
    assert new == {'10.1/a'}
    assert hide == {'10.1101/b'}


# apply_merged

def test_merge_approves_present_and_rejects_deleted(academic_user, scenario):
    decisions = apply_merged(scenario['batch'], scenario['text'], LATER)
    keep = Publication.objects.get(pk=scenario['keep'].pk)
    assert keep.review_status == 'approved'
    assert not pub_exists(scenario['drop'])
    assert RejectedWork.objects.filter(
        owner=academic_user, doi='10.1000/drop', reason='rejected').exists()
    assert decisions.approved == [scenario['keep'].pk]
    assert decisions.rejected == [scenario['drop'].pk]


def test_merge_hides_present_and_keeps_deleted(academic_user, scenario):
    decisions = apply_merged(scenario['batch'], scenario['text'], LATER)
    hidden = Publication.objects.get(pk=scenario['hide_pp'].pk)
    assert hidden.is_ignored is True
    assert hidden.metadata['hidden_by']['proposal_id'] == (
        scenario['hide_prop'].pk)
    assert status_of(scenario['hide_prop']) == 'confirmed'
    kept = Publication.objects.get(pk=scenario['keep_pp'].pk)
    assert kept.is_ignored is False
    assert status_of(scenario['keep_prop']) == 'rejected'
    assert decisions.hidden == [scenario['hide_pp'].pk]
    assert decisions.kept == [scenario['keep_pp'].pk]


def test_merge_marks_batch_merged(academic_user, scenario):
    apply_merged(scenario['batch'], scenario['text'], LATER)
    batch = ReviewBatch.objects.get(pk=scenario['batch'].pk)
    assert batch.status == 'merged'
    assert batch.decided_at == LATER


def test_rejecting_published_target_keeps_preprint_visible(academic_user):
    published = make_pending(academic_user, '10.1000/journal')
    preprint = make_preprint(academic_user, '10.1101/pre')
    proposal = make_proposal(academic_user, preprint, published)
    batch = make_batch(academic_user, [published], [proposal])
    text = review_yaml([], [proposal])
    decisions = apply_merged(batch, text, LATER)
    assert not pub_exists(published)
    assert Publication.objects.get(pk=preprint.pk).is_ignored is False
    assert decisions.rejected == [published.pk]
    assert decisions.kept == [preprint.pk]
    assert decisions.hidden == []
    assert RejectedWork.objects.filter(doi='10.1000/journal').exists()


def test_merge_hide_with_published_target_approved(academic_user):
    published = make_pending(academic_user, '10.1000/journal')
    preprint = make_preprint(academic_user, '10.1101/pre')
    proposal = make_proposal(academic_user, preprint, published)
    batch = make_batch(academic_user, [published], [proposal])
    decisions = apply_merged(batch, review_yaml([published], [proposal]),
                             LATER)
    assert Publication.objects.get(pk=published.pk).review_status == (
        'approved')
    assert Publication.objects.get(pk=preprint.pk).is_ignored is True
    assert decisions == Decisions(approved=[published.pk], rejected=[],
                                  hidden=[preprint.pk], kept=[])


def test_merge_matches_keys_not_raw_doi(academic_user):
    pub = make_pending(academic_user, '10.1000/CaseMix')
    batch = make_batch(academic_user, [pub], [])
    text = 'new:\n- {doi: "https://doi.org/10.1000/casemix"}\nhide: []\n'
    decisions = apply_merged(batch, text, LATER)
    assert decisions.approved == [pub.pk]


def test_close_rejects_everything(academic_user, scenario):
    decisions = apply_closed(scenario['batch'], LATER)
    assert not pub_exists(scenario['keep'])
    assert not pub_exists(scenario['drop'])
    assert RejectedWork.objects.filter(owner=academic_user).count() == 2
    for key in ('hide_pp', 'keep_pp'):
        assert Publication.objects.get(pk=scenario[key].pk).is_ignored is False
    assert status_of(scenario['hide_prop']) == 'rejected'
    assert status_of(scenario['keep_prop']) == 'rejected'
    batch = ReviewBatch.objects.get(pk=scenario['batch'].pk)
    assert batch.status == 'closed'
    assert batch.decided_at == LATER
    assert decisions.approved == [] and decisions.hidden == []
    assert sorted(decisions.rejected) == sorted(
        [scenario['keep'].pk, scenario['drop'].pk])
    assert sorted(decisions.kept) == sorted(
        [scenario['hide_pp'].pk, scenario['keep_pp'].pk])


@pytest.mark.parametrize('text', ['new: [unclosed', '[]', 'new: []'])
def test_invalid_review_file_decides_nothing(academic_user, scenario, text):
    before = snapshot()
    with pytest.raises(ReviewFileError):
        apply_merged(scenario['batch'], text, LATER)
    assert snapshot() == before
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'open'


def test_item_already_decided_elsewhere_is_skipped(academic_user, scenario):
    confirm_hide(scenario['keep_prop'], NOW)
    decisions = apply_merged(scenario['batch'], scenario['text'], LATER)
    assert status_of(scenario['keep_prop']) == 'confirmed'
    assert Publication.objects.get(pk=scenario['keep_pp'].pk).is_ignored
    assert decisions.kept == []
    assert decisions.hidden == [scenario['hide_pp'].pk]
    assert decisions.approved == [scenario['keep'].pk]
    assert decisions.rejected == [scenario['drop'].pk]


def test_deleted_item_is_skipped(academic_user, scenario):
    Publication.objects.filter(pk=scenario['drop'].pk).delete()
    decisions = apply_merged(scenario['batch'], scenario['text'], LATER)
    assert decisions.rejected == []
    assert decisions.approved == [scenario['keep'].pk]


def test_failure_mid_merge_rolls_back(academic_user, scenario, monkeypatch):
    before = snapshot()

    def boom(pub):
        raise RuntimeError('db down')

    monkeypatch.setattr('academic.publish.decisions.reject_pending', boom)
    with pytest.raises(RuntimeError):
        apply_merged(scenario['batch'], scenario['text'], LATER)
    assert snapshot() == before
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'open'


# process_pr

def pr_url():
    return f'{API}/repos/{REPO}/pulls/7'


def file_url():
    return f'{API}/repos/{REPO}/contents/{PATH}'


def file_json(text, sha):
    return {'content': base64.b64encode(text.encode()).decode(), 'sha': sha}


def mock_merged_pr():
    responses.get(pr_url(), json={'state': 'closed', 'merged': True,
                                  'merge_commit_sha': 'm123'})


def calls_to(method, url):
    return [c for c in responses.calls if c.request.method == method
            and c.request.url.split('?')[0] == url]


@responses.activate
def test_process_pr_reads_file_at_merge_commit_and_deletes_it(
        academic_user, scenario, gh):
    mock_merged_pr()
    responses.get(file_url(), json=file_json(scenario['text'], 'old'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'm123'})])
    responses.get(file_url(), json=file_json(scenario['text'], 'mainsha'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'main'})])
    responses.delete(file_url(), json={})
    decisions = process_pr(scenario['batch'], gh, REPO, LATER)
    assert decisions.approved == [scenario['keep'].pk]
    gets = calls_to('GET', file_url())
    assert 'ref=m123' in gets[0].request.url
    delete = calls_to('DELETE', file_url())
    assert len(delete) == 1
    body = json.loads(delete[0].request.body)
    assert body == {'message': 'Remove processed review file',
                    'sha': 'mainsha', 'branch': 'main'}
    batch = ReviewBatch.objects.get(pk=scenario['batch'].pk)
    assert batch.status == 'merged'
    assert batch.decided_at == LATER


@responses.activate
def test_process_pr_skips_delete_when_file_gone_from_main(
        academic_user, scenario, gh):
    mock_merged_pr()
    responses.get(file_url(), json=file_json(scenario['text'], 'old'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'm123'})])
    responses.get(file_url(), status=404,
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'main'})])
    decisions = process_pr(scenario['batch'], gh, REPO, LATER)
    assert decisions.approved == [scenario['keep'].pk]
    assert calls_to('DELETE', file_url()) == []


@responses.activate
def test_process_pr_delete_failure_keeps_decisions(
        academic_user, scenario, gh):
    from academic.publish.github import GitHubError
    mock_merged_pr()
    responses.get(file_url(), json=file_json(scenario['text'], 'old'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'm123'})])
    responses.get(file_url(), json=file_json(scenario['text'], 'mainsha'),
                  match=[responses.matchers.query_param_matcher(
                      {'ref': 'main'})])
    responses.delete(file_url(), status=500)
    with pytest.raises(GitHubError):
        process_pr(scenario['batch'], gh, REPO, LATER)
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'merged'
    assert not pub_exists(scenario['drop'])


@responses.activate
def test_missing_review_file_decides_nothing(academic_user, scenario, gh):
    mock_merged_pr()
    responses.get(file_url(), status=404)
    before = snapshot()
    with pytest.raises(ReviewFileError):
        process_pr(scenario['batch'], gh, REPO, LATER)
    assert snapshot() == before
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'open'
    assert calls_to('DELETE', file_url()) == []


@responses.activate
def test_process_pr_closed_unmerged_rejects_everything(
        academic_user, scenario, gh):
    responses.get(pr_url(), json={'state': 'closed', 'merged': False,
                                  'merge_commit_sha': None})
    decisions = process_pr(scenario['batch'], gh, REPO, LATER)
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'closed'
    assert not pub_exists(scenario['keep'])
    assert decisions.hidden == []
    assert [c.request.method for c in responses.calls] == ['GET']


@responses.activate
def test_process_pr_open_is_noop(academic_user, scenario, gh):
    responses.get(pr_url(), json={'state': 'open', 'merged': False,
                                  'merge_commit_sha': None})
    before = snapshot()
    assert process_pr(scenario['batch'], gh, REPO, LATER) is None
    assert snapshot() == before
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'open'


@responses.activate
def test_process_pr_already_decided_is_noop(academic_user, scenario, gh):
    batch = scenario['batch']
    batch.status = 'merged'
    batch.save()
    before = snapshot()
    assert process_pr(batch, gh, REPO, LATER) is None
    assert snapshot() == before
    assert len(responses.calls) == 0


def _edit_doi(text, old, new):
    assert old in text
    return text.replace(old, new)


def test_edited_new_key_leaves_unkept_pubs_pending(academic_user, scenario):
    text = _edit_doi(scenario['text'], '10.1000/keep', '10.1000/edited')
    decisions = apply_merged(scenario['batch'], text, LATER)
    for key in ('keep', 'drop'):
        pub = Publication.objects.get(pk=scenario[key].pk)
        assert pub.review_status == 'pending'
    assert RejectedWork.objects.count() == 0
    assert decisions.unmatched == ['10.1000/edited']
    assert sorted(decisions.undecided) == sorted(
        [scenario['keep'].pk, scenario['drop'].pk])
    assert decisions.approved == [] and decisions.rejected == []
    # hide entries still matched: decided normally
    assert status_of(scenario['hide_prop']) == 'confirmed'
    assert status_of(scenario['keep_prop']) == 'pending'
    assert scenario['keep_pp'].pk in decisions.undecided
    assert ReviewBatch.objects.get(pk=scenario['batch'].pk).status == 'merged'


def test_edited_hide_key_leaves_proposal_pending(academic_user, scenario):
    text = _edit_doi(scenario['text'], '10.1101/hide', '10.1101/edited')
    decisions = apply_merged(scenario['batch'], text, LATER)
    assert status_of(scenario['hide_prop']) == 'pending'
    assert status_of(scenario['keep_prop']) == 'pending'
    assert Publication.objects.get(pk=scenario['hide_pp'].pk).is_ignored is False
    assert decisions.unmatched == ['10.1101/edited']
    assert decisions.hidden == [] and decisions.kept == []
    assert Publication.objects.get(pk=scenario['keep'].pk).review_status == (
        'approved')
    assert Publication.objects.get(pk=scenario['drop'].pk).review_status == (
        'pending')
    assert sorted(decisions.undecided) == sorted([
        scenario['hide_pp'].pk, scenario['keep_pp'].pk, scenario['drop'].pk])


def test_no_unmatched_keys_means_empty_lists(academic_user, scenario):
    decisions = apply_merged(scenario['batch'], scenario['text'], LATER)
    assert decisions.unmatched == [] and decisions.undecided == []


def _hide_only_batch(user, published):
    preprint = make_preprint(user, '10.1101/pre')
    proposal = make_proposal(user, preprint, published)
    batch = make_batch(user, [], [proposal])
    return preprint, proposal, batch, review_yaml([], [proposal])


def test_hide_rejected_when_published_target_ignored(academic_user):
    published = PublicationFactory(owner=academic_user, doi='10.1000/j',
                                   review_status='approved', is_ignored=True)
    preprint, proposal, batch, text = _hide_only_batch(
        academic_user, published)
    decisions = apply_merged(batch, text, LATER)
    assert status_of(proposal) == 'rejected'
    assert Publication.objects.get(pk=preprint.pk).is_ignored is False
    assert decisions.kept == [preprint.pk]


def test_hide_rejected_when_target_pending_outside_batch(academic_user):
    published = make_pending(academic_user, '10.1000/j')
    preprint, proposal, batch, text = _hide_only_batch(
        academic_user, published)
    decisions = apply_merged(batch, text, LATER)
    assert status_of(proposal) == 'rejected'
    assert Publication.objects.get(pk=preprint.pk).is_ignored is False
    assert decisions.kept == [preprint.pk]
    assert Publication.objects.get(pk=published.pk).review_status == 'pending'


def test_unexpected_value_error_propagates(academic_user, scenario,
                                           monkeypatch):
    def boom(pub):
        raise ValueError('something else')

    monkeypatch.setattr('academic.publish.decisions.approve_pending', boom)
    before = snapshot()
    with pytest.raises(ValueError):
        apply_merged(scenario['batch'], scenario['text'], LATER)
    assert snapshot() == before
