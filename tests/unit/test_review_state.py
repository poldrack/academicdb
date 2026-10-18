import pytest
from django.db import transaction

from academic.cv_renderer import generate_cv_latex
from academic.models import Publication, RejectedWork
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


def test_rolled_back_user_delete_does_not_suppress_later_tombstones(academic_user):
    pub = make_pub(academic_user)
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            academic_user.delete()
            raise RuntimeError('abort')
    Publication.objects.get(pk=pub.pk).delete()
    assert RejectedWork.objects.filter(owner=academic_user).count() == 1
