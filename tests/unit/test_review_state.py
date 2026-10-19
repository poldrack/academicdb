import pytest
from django.db import transaction
from django.db.models.signals import pre_delete

from academic.cv_renderer import generate_cv_latex
from academic.models import AcademicUser, Publication, RejectedWork
from academic.tombstones import doi_key, record_tombstone, title_key

pytestmark = pytest.mark.django_db


def make_pub(user, doi='10.1/a', title='Title long enough', **kwargs):
    return Publication.objects.create(
        owner=user, doi=doi, title=title, year=kwargs.pop('year', 2024), **kwargs
    )


def test_existing_and_new_publications_default_to_approved(academic_user):
    assert make_pub(academic_user).review_status == 'approved'


@pytest.mark.parametrize('raw,key', [
    ('https://doi.org/10.31234/OSF.IO/ABCDE_V3', '10.31234/osf.io/abcde'),
    ('10.1101//2024.01.01.123', '10.1101/2024.01.01.123'),
    ('10.1234/something_v2', '10.1234/something_v2'),
    (None, ''),
    ('', ''),
])
def test_doi_key(raw, key):
    assert doi_key(raw) == key


def test_title_key_normalizes():
    assert title_key('  The Brain: A (Very) Short Intro! ') == 'the brain a very short intro'


def test_title_key_truncates_to_200_chars():
    assert len(title_key('word ' * 100)) == 200


def test_instance_delete_records_tombstone(academic_user):
    pub = make_pub(academic_user, identifiers={'openalex': 'W1', 'pmid': '9'})
    pub.delete()
    t = RejectedWork.objects.get(owner=academic_user)
    assert (t.doi, t.openalex_id, t.pmid, t.reason) == ('10.1/a', 'W1', '9', 'deleted')


def test_queryset_delete_records_tombstones(academic_user):
    for i in range(3):
        make_pub(academic_user, doi=f'10.1/pub{i}')
    academic_user.publications.all().delete()
    assert RejectedWork.objects.filter(owner=academic_user).count() == 3


def test_no_doi_publication_tombstoned_by_title(academic_user):
    pub = make_pub(academic_user, doi=None, title='Statistical Thinking for the 21st Century')
    pub.delete()
    assert RejectedWork.objects.get().title_key == 'statistical thinking for the 21st century'


def test_rejected_reason_preserved_when_later_deleted(academic_user):
    pub = make_pub(academic_user)
    record_tombstone(pub, 'rejected')
    pub.delete()
    assert list(RejectedWork.objects.values_list('reason', flat=True)) == ['rejected']


def test_cv_excludes_pending_publications(academic_user):
    make_pub(academic_user, doi='10.1/ok', title='Approved paper title', publication_type='article')
    make_pub(academic_user, doi='10.1/pend', title='Pending paper title',
             publication_type='article', review_status='pending')
    tex = generate_cv_latex(academic_user)
    assert 'Approved paper title' in tex and 'Pending paper title' not in tex


def test_cv_excludes_pending_preprints(academic_user):
    make_pub(academic_user, doi='10.1101/2026.01.01.000001', title='Pending preprint title',
             publication_type='preprint', review_status='pending')
    assert 'Pending preprint title' not in generate_cv_latex(academic_user)


def test_deleting_owner_does_not_leave_dangling_tombstones(academic_user):
    make_pub(academic_user)
    academic_user.delete()
    assert RejectedWork.objects.count() == 0


def test_failed_user_delete_does_not_suppress_later_tombstones(academic_user):
    pub = make_pub(academic_user)
    owner_id = academic_user.pk  # Model.delete() clears pk on the instance

    def abort(sender, **kwargs):
        raise RuntimeError('abort')

    pre_delete.connect(abort, sender=AcademicUser)
    try:
        with pytest.raises(RuntimeError), transaction.atomic():
            academic_user.delete()
    finally:
        pre_delete.disconnect(abort, sender=AcademicUser)
    Publication.objects.get(pk=pub.pk).delete()
    assert RejectedWork.objects.filter(owner_id=owner_id).count() == 1


# --- Final review fixes ---------------------------------------------------

PREPRINT_TITLE = 'Neural correlates of adaptive decision making under uncertainty'
PAIR_AUTHORS = [{'name': 'Smith, Jane'}, {'name': 'Jones, Bob'}]


def make_cv_pair(user, published_status, **preprint_kwargs):
    preprint = make_pub(user, doi='10.1101/2024.01.01.000777', title=PREPRINT_TITLE,
                        authors=PAIR_AUTHORS, **preprint_kwargs)
    make_pub(user, doi='10.1016/j.neuron.2025.00777', title=PREPRINT_TITLE,
             authors=PAIR_AUTHORS, year=2025, review_status=published_status)
    return preprint


def test_cv_preprint_matched_only_by_pending_paper_still_shown(academic_user):
    make_cv_pair(academic_user, 'pending')
    assert 'Recent preprints' in generate_cv_latex(academic_user)


def test_cv_preprint_matched_by_approved_paper_hidden(academic_user):
    make_cv_pair(academic_user, 'approved')
    assert 'Recent preprints' not in generate_cv_latex(academic_user)


def test_relation_to_pending_paper_does_not_hide_preprint(academic_user):
    relation = {'is-preprint-of': [{'id': 'https://doi.org/10.1016/j.neuron.2025.00777'}]}
    preprint = make_cv_pair(academic_user, 'pending', metadata={'relation': relation})
    assert Publication.find_published_version_of_preprint(preprint, academic_user) is None


def test_new_biorxiv_prefix_saved_as_preprint(academic_user):
    pub = make_pub(academic_user, doi='10.64898/2025.01.01.123456',
                   publication_type='preprint')
    assert pub.is_preprint and pub.publication_type == 'preprint'


def test_osf_preprints_prefix_detected(academic_user):
    pub = make_pub(academic_user, doi='10.31219/osf.io/abcde')
    assert pub.is_preprint and pub.publication_type == 'preprint'


def test_unknown_prefix_preprint_keeps_type_on_save(academic_user):
    pub = make_pub(academic_user, doi='10.9999/some.server.1', publication_type='preprint')
    pub.save()
    pub.refresh_from_db()
    assert pub.publication_type == 'preprint' and pub.is_preprint


def test_unknown_prefix_is_preprint_flag_not_demoted(academic_user):
    pub = make_pub(academic_user, doi='10.9999/some.server.2', is_preprint=True)
    pub.refresh_from_db()
    assert pub.is_preprint


def test_changing_known_preprint_doi_to_journal_doi_demotes(academic_user):
    pub = make_pub(academic_user, doi='10.1101/2024.01.01.000888')
    pub = Publication.objects.get(pk=pub.pk)
    pub.doi = '10.1016/j.neuron.2025.00888'
    pub.save()
    pub.refresh_from_db()
    assert not pub.is_preprint and pub.publication_type == 'journal-article'


def test_delete_doi_less_pub_sharing_title_with_doi_tombstones(academic_user):
    title = 'Shared title of a preprint and its published version'
    make_pub(academic_user, doi='10.1101/2024.02.02.000001', title=title).delete()
    make_pub(academic_user, doi='10.1016/j.x.2025.00001', title=title).delete()
    make_pub(academic_user, doi=None, title=title).delete()
    rows = RejectedWork.objects.filter(owner=academic_user)
    assert rows.count() == 3
    assert rows.filter(doi='', title_key=title_key(title)).exists()


def test_delete_with_null_identifiers(academic_user):
    pub = make_pub(academic_user, identifiers={'openalex': None, 'pmid': None})
    pub.delete()
    t = RejectedWork.objects.get(owner=academic_user)
    assert (t.openalex_id, t.pmid) == ('', '')


def test_tombstone_failure_does_not_break_delete(academic_user, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('tombstone bug')
    monkeypatch.setattr('academic.signals.record_tombstone', boom)
    pub = make_pub(academic_user)
    pub.delete()
    assert not Publication.objects.filter(pk=pub.pk).exists()
