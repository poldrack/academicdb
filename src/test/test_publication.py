import pytest
import sys

sys.path.append('../academicdb')
from src.academicdb.publication import (
    Publication,
    JournalArticle,
    Book,
    BookChapter,
)
from src.academicdb import utils


@pytest.fixture
def article_dict():
    return {
        'DOI': '10.1038/s41592-022-01681-2',
        'PMCID': '9718663',
        'PMID': '36456786',
        'affiliation_ids': [
            '60012708',
            '60012708-60016437-60012311',
            '60012708-60029069-114427552',
            '60012708',
            '60011520',
            '60012708',
            '60010756',
            '60100145-60002746',
            '60012708',
            '60012708',
            '60012708-60000239',
        ],
        'author_ids': [
            '57190392076',
            '56608578700',
            '56559386700',
            '57204965665',
            '57223889578',
            '57190371018',
            '6503870081',
            '7404806211',
            '55355064700',
            '7004739390',
            '6601965136',
        ],
        'authors': 'Ciric R, Thompson WH, Lorenz R, Goncalves M, MacNicol EE, Markiewicz CJ, Halchenko YO, Ghosh SS, Gorgolewski KJ, Poldrack RA, Esteban O',
        'journal': 'Nature Methods',
        'page': '1568-1571',
        'publisher': 'Springer Science and Business Media LLC',
        'scopus_coauthor_ids': [
            '57190392076',
            '56608578700',
            '56559386700',
            '57204965665',
            '57223889578',
            '57190371018',
            '6503870081',
            '7404806211',
            '55355064700',
            '7004739390',
            '6601965136',
        ],
        'source': 'Crossref',
        'title': 'TemplateFlow: FAIR-sharing of multi-scale, multi-species brain models',
        'type': 'journal-article',
        'volume': '19',
        'year': 2022,
    }


@pytest.fixture
def book_dict():
    return {
        'DOI': 'nodoi_avgakammsjdbtpmd',
        'ISBN': '9780000000000',
        'aggregationType': 'Book',
        'authors': 'Poldrack RA, Mumford JA, Nichols TE',
        'authors_abbrev': ['Poldrack RA', 'Mumford JA', 'Nichols TE'],
        'coverDate': '2011-01-01',
        'editors': None,
        'firstauthor': 'Poldrack RA',
        'pageRange': None,
        'publicationName': 'Handbook of Functional MRI Data Analysis',
        'publisher': 'Cambridge: Cambridge University Press ',
        'subtypeDescription': 'Book',
        'title': 'Handbook of Functional MRI Data Analysis',
        'type': 'book',
        'volume': None,
        'year': 2011,
    }


def test_publication():
    pub = Publication()
    assert pub is not None


def test_from_article_dict(article_dict):
    pub = JournalArticle()
    pub.from_dict(article_dict)
    assert pub.DOI == article_dict['DOI']


def test_latex_reference_article(article_dict):
    pub = JournalArticle(etalthresh=100)
    pub.from_dict(article_dict)
    ref = pub.format_reference(format='latex')
    assert (
        ref
        == 'Ciric R, Thompson WH, Lorenz R, Goncalves M, MacNicol EE, Markiewicz CJ, Halchenko YO, Ghosh SS, Gorgolewski KJ, Poldrack RA, Esteban O (2022). TemplateFlow: FAIR-sharing of multi-scale, multi-species brain models. \\textit{Nature Methods, 19}, 1568-1571.'
    )


def test_md_reference_article(article_dict):
    pub = JournalArticle(etalthresh=100)
    pub.from_dict(article_dict)
    ref = pub.format_reference(format='md')
    assert (
        ref
        == 'Ciric R, Thompson WH, Lorenz R, Goncalves M, MacNicol EE, Markiewicz CJ, Halchenko YO, Ghosh SS, Gorgolewski KJ, Poldrack RA, Esteban O (2022). TemplateFlow: FAIR-sharing of multi-scale, multi-species brain models. *Nature Methods, 19*, 1568-1571.'
    )


def test_from_book_dict(book_dict):
    pub = Book()
    pub.from_dict(book_dict)
    assert pub.title == book_dict['title']


def test_latex_reference_book(book_dict):
    pub = Book()
    pub.from_dict(book_dict)
    ref = pub.format_reference(format='latex')
    assert (
        ref
        == 'Poldrack RA, Mumford JA, Nichols TE (2011). \\textit{Handbook of Functional MRI Data Analysis}. Cambridge: Cambridge University Press.'
    )


def test_md_reference_book(book_dict):
    pub = Book()
    pub.from_dict(book_dict)
    ref = pub.format_reference(format='md')
    assert (
        ref
        == 'Poldrack RA, Mumford JA, Nichols TE (2011). *Handbook of Functional MRI Data Analysis*. Cambridge: Cambridge University Press.'
    )
