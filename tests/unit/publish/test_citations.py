"""Tests for the shared citation formatter used by the static sites."""
import pytest

from academic.publish import citations as pubs


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Poldrack, Russell A", "Poldrack RA"),
        ("Poldrack, Russell A.", "Poldrack RA"),
        ("Dunleavy, Daniel J.", "Dunleavy DJ"),
        ("Santos, Eduardo S. A.", "Santos ESA"),
        ("Kovacs, Lilla Nora", "Kovacs LN"),
        ("Poline, Jean-Baptiste", "Poline JB"),
        ("LASTRES-LÓPEZ, CRISTINA", "LASTRES-LÓPEZ C"),
        ("Haan, Bianca de", "de Haan B"),
    ],
)
def test_format_author_name_converts_last_first(name, expected):
    assert pubs.format_author_name(name) == expected


@pytest.mark.parametrize("name", ["Poldrack RA", "Russell A. Poldrack", "Xi-Nian Zuo"])
def test_format_author_name_leaves_other_formats_unchanged(name):
    assert pubs.format_author_name(name) == name


def test_format_author_name_strips_whitespace():
    assert pubs.format_author_name("  Poldrack ,  Russell  A ") == "Poldrack RA"


def _names(n):
    return [f"Author{i} A" for i in range(1, n + 1)]


def test_format_author_list_joins_short_lists():
    assert pubs.format_author_list(["Smith, John", "Doe, Jane"]) == "Smith J, Doe J"


def test_format_author_list_keeps_exactly_twenty():
    assert pubs.format_author_list(_names(20)) == ", ".join(_names(20))


def test_format_author_list_truncates_more_than_twenty():
    names = _names(21)
    expected = ", ".join(names[:10]) + ", ..., " + names[-1]
    assert pubs.format_author_list(names) == expected


def test_format_author_list_empty():
    assert pubs.format_author_list([]) == ""


def _preprint(name, doi):
    return {"publication_type": "preprint", "publication_name": name, "doi": doi}


@pytest.mark.parametrize("name", [None, "", "Center for Open Science"])
@pytest.mark.parametrize("doi", ["10.31234/osf.io/cn59h_v2", "10.31222/osf.io/x64tn_v1"])
def test_venue_name_osf_preprints(name, doi):
    assert pubs.venue_name(_preprint(name, doi)) == "OSF Preprints"


def test_venue_name_osf_requires_preprint_type():
    pub = {
        "publication_type": "journal-article",
        "publication_name": "Center for Open Science",
        "doi": "10.31234/osf.io/abc",
    }
    assert pubs.venue_name(pub) == "Center for Open Science"


def test_venue_name_osf_requires_osf_doi():
    pub = _preprint("Center for Open Science", "10.1101/2020.01.01.123456")
    assert pubs.venue_name(pub) == "Center for Open Science"


def test_venue_name_osf_keeps_other_publisher_names():
    assert pubs.venue_name(_preprint("PsyArXiv", "10.31234/osf.io/abc")) == "PsyArXiv"


def test_venue_name_shortens_arxiv():
    pub = {"publication_type": "preprint", "publication_name": "arXiv (Cornell University)"}
    assert pubs.venue_name(pub) == "arXiv"


def test_venue_name_missing_is_empty():
    assert pubs.venue_name({"publication_type": "journal-article"}) == ""


@pytest.mark.parametrize(
    ("raw", "rendered", "expected"),
    [
        ("A title", "*A title*", "*A title*."),
        ("A title.", "*A title.*", "*A title.*"),
        ("A title. ", "[A title. ](x)", "[A title. ](x)"),
    ],
)
def test_terminate_adds_period_only_when_missing(raw, rendered, expected):
    assert pubs.terminate(raw, rendered) == expected


def _pub(**overrides):
    pub = {
        "title": "A study",
        "year": 2020,
        "publication_type": "journal-article",
        "publication_name": "NeuroImage",
        "doi": "10.1/abc",
        "volume": "12",
        "page_range": "1-10",
        "authors": [{"name": "Poldrack, Russell A"}, {"name": "Smith J"}],
    }
    pub.update(overrides)
    return pub


def test_format_publication_full_citation():
    assert pubs.format_publication(_pub()) == (
        "Poldrack RA, Smith J. [A study](https://doi.org/10.1/abc). NeuroImage, *12*, 1-10."
    )


def test_format_publication_no_double_period_after_title():
    result = pubs.format_publication(_pub(title="A study."))
    assert "[A study.](https://doi.org/10.1/abc) NeuroImage" in result
    assert ".." not in result


def test_format_publication_no_double_period_after_venue():
    pub = _pub(publication_name="Proc. Natl. Acad.", volume=None, page_range=None)
    assert pubs.format_publication(pub).endswith("Proc. Natl. Acad.")


def test_format_publication_no_double_period_after_authors():
    pub = _pub(authors=[{"name": "Smith J."}])
    assert pubs.format_publication(pub).startswith("Smith J. [A study]")


def test_format_publication_without_doi_italicizes_title():
    pub = _pub(doi=None, publication_name=None, volume=None, page_range=None)
    assert pubs.format_publication(pub) == "Poldrack RA, Smith J. *A study*."


def test_format_publication_marks_preprints():
    pub = _pub(
        publication_type="preprint",
        is_preprint=True,
        publication_name=None,
        doi="10.31234/osf.io/abc",
        volume=None,
        page_range=None,
    )
    assert pubs.format_publication(pub).endswith("OSF Preprints (preprint).")
