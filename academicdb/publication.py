"""
class for publications
"""

import hashlib
import json
from .pubmed import parse_pubmed_record


class Publication:
    """
    """

    type = 'generic'

    def __init__(self, title=None, year=None, authors=None, etalthresh=10):

        # set up general feature attributes
        self.title = title
        self.year = year
        self.authors = authors
        self.etalthresh = etalthresh
        self.hash = None

    def get_pub_hash(self, digest_size=8):
        """
        create a hash from the title, year, and authors
        - used for finding duplicates
        """
        if self.title is None:
            print('reference must first be loaded')
        else:
            pubstr = '-'.join([str(i) for i in [self.title, self.year, self.authors]])
            self.hash = hashlib.blake2b(pubstr.lower().encode('utf-8'), digest_size=digest_size).hexdigest()

    def from_dict(self, pubdict):
        for k in pubdict:
            if hasattr(self, k):
                setattr(self, k, pubdict[k])

    def to_json(self):
        return(vars(self))


class JournalArticle(Publication):

    type = 'journal-article'

    def __init__(self, title=None, year=None, authors=None,
                 journal=None, volume=None, page=None, DOI=None):
        super().__init__(title, year, authors)

        self.journal = journal
        self.volume = volume
        self.page = page
        self.DOI = DOI
        self.PMC = None
        self.PMID = None
        self.links = {}
        self.reference = None
        self.source = None
        self.pubmed_data = None

    def format_reference(self, etalthresh=10, etalnum=3, format='latex'):

        if self.title is None:
            print('reference must be loaded before formatting')
            return
        authors_shortened = shorten_authorlist(self.authors, etalthresh, etalnum)

        if format == 'latex':
            line = authors_shortened +\
                ' (%d). ' % self.year +\
                self.title +\
                ' \\textit{%s' % self.journal

            line += ', %s}' % self.volume if self.volume is not None else '}'
            if self.page is not None and len(self.page) > 0:
                line += ', %s' % self.page
            line += '.'
        elif format == 'md':
            if self.title is None:
                print('reference must be loaded before formatting')
                return
            authors_shortened = shorten_authorlist(self.authors, etalthresh, etalnum)

            line = authors_shortened +\
                ' (%d). ' % self.year +\
                self.title +\
                ' *%s' % self.journal

            line += ', %s*' % self.volume if self.volume is not None else '*'
            if self.page is not None and len(self.page) > 0:
                line += ', %s' % self.page
            line += '.'
        else:
            raise ValueError('format must be latex or md')
        return(line)

    def from_pubmed(self, pubmed_record):
        parsed_record = parse_pubmed_record(pubmed_record)
        self.source = 'Pubmed'
        for k in parsed_record:
            setattr(self, k, parsed_record[k])
        self.pubmed_data = pubmed_record


class BookChapter(Publication):

    type = 'book-chapter'

    def __init__(self, title=None, year=None, authors=None,
                 journal=None, page=None, ISBN=None,
                 publisher=None, editors=None):
        super().__init__(title, year, authors)

        self.journal = journal
        self.page = page
        self.ISBN = ISBN
        self.links = {}
        self.reference = None
        self.source = None
        self.publisher = publisher
        self.editors = editors

    def format_reference(self, etalthresh=None, etalnum=None, format='latex'):
        if self.title is None:
            print('reference must be loaded before formatting')
            return

        page_string = ''
        if hasattr(self, 'page') and self.page is not None and len(self.page) > 0:
            page_string = '(p. %s). ' % self.page
        if format == 'latex':
            line = self.authors +\
            ' (%s). ' % self.year +\
            self.title.strip('.') +\
           '. In \\textit{%s.} %s%s.' % (
                self.journal,
                page_string,
                self.publisher.strip(' '))

        elif format == 'md':
            line = self.authors +\
            ' (%s). ' % self.year +\
            self.title.strip('.') +\
            '. In *%s.* %s%s.' % (
                self.journal,
                page_string,
                self.publisher.strip(' '))

        else:
            raise ValueError('format must be latex or md')
        return(line)

class Book(Publication):

    type = 'book'

    def __init__(self, title=None, year=None, authors=None,
                 page=None, ISBN=None,
                 publisher=None, editors=None):
        super().__init__(title, year, authors)

        self.page = page
        self.ISBN = ISBN
        self.links = {}
        self.reference = None
        self.source = None
        self.publisher = publisher
        self.editors = editors

    def format_reference(self, etalthresh=None, etalnum=None, format='latex'):
        if self.title is None:
            print('reference must be loaded before formatting')
            return
        if format == 'latex':
            line = self.authors +\
                ' (%s). ' % self.year +\
                ' *%s*. ' % self.title.strip(' ').strip('.') + \
                self.publisher.strip(' ')
        elif format == 'md':
            line = self.authors +\
                ' (%s). ' % self.year +\
                ' \\textit{%s}. ' % self.title.strip(' ').strip('.') + \
                self.publisher.strip(' ')
        else:
            raise ValueError('format must be latex or md')
        line += '.'
        return(line)
