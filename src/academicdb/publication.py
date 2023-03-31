"""
class for publications
"""
import hashlib
from . import publication_utils


class Publication:
    """ """

    def __init__(self, etalthresh=10):

        self.etalthresh = etalthresh

    def get_pub_hash(self, digest_size=8):
        """
        create a hash from the title, year, and authors
        - used for finding duplicates
        """
        if self.title is None:
            print('reference must first be loaded')
        else:
            pubstr = '-'.join(
                [str(i) for i in [self.title, self.year, self.authors]]
            )
            self.hash = hashlib.blake2b(
                pubstr.lower().encode('utf-8'), digest_size=digest_size
            ).hexdigest()

    def from_dict(self, pubdict):
        for k, v in pubdict.items():
            setattr(self, k, v)
        return self


class JournalArticle(Publication):

    type = 'journal-article'

    def __init__(self, etalthresh=10):
        super().__init__(etalthresh)

    def format_reference(self, format='latex', etalnum=3):

        if not hasattr(self, 'journal') and hasattr(self, 'publicationName'):
            setattr(self, 'journal', self.publicationName)
        if not hasattr(self, 'volume'):
            setattr(self, 'volume', None)
        if self.title is None:
            print('reference must be loaded before formatting')
            return
        self.title = self.title.strip(' ').strip('.')
        authors_shortened = publication_utils.shorten_authorlist(
            self.authors, self.etalthresh, etalnum
        )
        # make sure title has a period at the end
        if self.title[-1] != '.':
            self.title += '.'
        if format == 'latex':
            line = (
                authors_shortened
                + ' (%d). ' % self.year
                + self.title
                + ' \\textit{%s' % self.journal
            )

            line += ', %s}' % self.volume if self.volume is not None else '}'
            if (
                hasattr(self, 'page')
                and self.page is not None
                and len(self.page) > 0
            ):
                line += ', %s' % self.page
            line += '.'
        elif format == 'md':
            if self.title is None:
                print('reference must be loaded before formatting')
                return
            line = (
                authors_shortened
                + ' (%d). ' % self.year
                + self.title
                + ' *%s' % self.journal
            )

            line += ', %s*' % self.volume if self.volume is not None else '*'
            if (
                hasattr(self, 'page')
                and self.page is not None
                and len(self.page) > 0
            ):
                line += ', %s' % self.page
            line += '.'
        else:
            raise ValueError('format must be latex or md')
        return line

    def from_pubmed(self, pubmed_record):
        parsed_record = parse_pubmed_record(pubmed_record)
        self.source = 'Pubmed'
        for k in parsed_record:
            setattr(self, k, parsed_record[k])
        self.pubmed_data = pubmed_record


class BookChapter(Publication):

    type = 'book-chapter'

    def __init__(self):
        super().__init__()

    def format_reference(self, format='latex', etalthresh=None, etalnum=None):
        if self.title is None:
            print('reference must be loaded before formatting')
            return
        self.title = self.title.strip(' ').strip('.')
        if not hasattr(self, 'publicationName') and hasattr(self, 'journal'):
            setattr(self, 'publicationName', self.journal)
        page_string = ''
        ed_string = ''
        if (
            hasattr(self, 'editors')
            and self.editors is not None
            and len(self.editors) > 0
        ):
            ed_string = f' ({self.editors}, Ed.)'
        if (
            hasattr(self, 'page')
            and self.page is not None
            and len(self.page) > 0
        ):
            page_string = '(p. %s). ' % self.page
        if format == 'latex':
            line = (
                self.authors
                + ' (%s). ' % self.year
                + self.title.strip('.')
                + '. In \\textit{%s.}%s %s%s.'
                % (
                    self.publicationName,
                    ed_string,
                    page_string,
                    self.publisher.strip(' '),
                )
            )

        elif format == 'md':
            line = (
                self.authors
                + ' (%s). ' % self.year
                + self.title.strip('.')
                + '. In *%s*%s %s%s.'
                % (
                    self.publicationName,
                    ed_string,
                    page_string,
                    self.publisher.strip(' '),
                )
            )

        else:
            raise ValueError('format must be latex or md')
        return line


class Book(Publication):

    type = 'book'

    def __init__(self):
        super().__init__()

    def format_reference(self, format='latex', etalthresh=None, etalnum=None):
        if self.title is None:
            print('reference must be loaded before formatting')
            return
        self.title = self.title.strip(' ').strip('.')
        if format == 'md':
            line = (
                self.authors
                + ' (%s). ' % self.year
                + '*%s*. ' % self.title.strip(' ').strip('.')
                + self.publisher.strip(' ')
            )
        elif format == 'latex':
            line = (
                self.authors
                + ' (%s). ' % self.year
                + '\\textit{%s}. ' % self.title.strip(' ').strip('.')
                + self.publisher.strip(' ')
            )
        else:
            raise ValueError('format must be latex or md')
        line += '.'
        return line
