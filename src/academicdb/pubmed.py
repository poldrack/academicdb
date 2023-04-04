"""
functions to work with pubmed data
"""

from Bio import Entrez
from datetime import datetime

def get_pubmed_data(query, email, retmax=1000):
    Entrez.email = email
    print(f'using {email} for Entrez service')
    print('searching for', query)
    handle = Entrez.esearch(db='pubmed', retmax=retmax, term=query)
    record = Entrez.read(handle)
    handle.close()
    pmids = [int(i) for i in record['IdList']]
    print('found %d matches' % len(pmids))

    # load full records
    handle = Entrez.efetch(
        db='pubmed',
        id=','.join(['%d' % i for i in pmids]),
        retmax=retmax,
        retmode='xml',
    )
    return Entrez.read(handle)


def parse_pubmed_pubs(pubmed_records):
    pubs = {}
    for i in pubmed_records['PubmedArticle']:
        parsed_record = parse_pubmed_record(i)
        pubs[parsed_record['DOI']] = parsed_record
    return pubs


def get_pubmed_journal_name(record):
    return record['MedlineCitation']['Article']['Journal']['ISOAbbreviation']


def get_pubmed_title(record):
    return record['MedlineCitation']['Article']['ArticleTitle']


def get_pubmed_pmid(record):
    return int(record['MedlineCitation']['PMID'])


def get_pubmed_doi(record):
    doi = None
    for j in record['PubmedData']['ArticleIdList']:
        if j.attributes['IdType'] == 'doi':
            doi = str(j).lower().replace('http://dx.doi.org/', '')
    return doi


def get_pubmed_pmcid(record):
    pmc = None
    for j in record['PubmedData']['ArticleIdList']:
        if j.attributes['IdType'] == 'pmc':
            pmc = str(j)
    return pmc


def get_pubmed_year(record):
    year = None
    if (
        'Year'
        in record['MedlineCitation']['Article']['Journal']['JournalIssue'][
            'PubDate'
        ]
    ):
        year = int(
            record['MedlineCitation']['Article']['Journal']['JournalIssue'][
                'PubDate'
            ]['Year']
        )
    elif (
        'MedlineDate'
        in record['MedlineCitation']['Article']['Journal']['JournalIssue'][
            'PubDate'
        ]
    ):
        year = int(
            record['MedlineCitation']['Article']['Journal']['JournalIssue'][
                'PubDate'
            ]['MedlineDate'].split(' ')[0]
        )
    return year


def get_pubmed_volume(record):
    volume = None
    if (
        'Volume'
        in record['MedlineCitation']['Article']['Journal']['JournalIssue']
    ):
        volume = record['MedlineCitation']['Article']['Journal'][
            'JournalIssue'
        ]['Volume']
    return volume


def get_pubmed_pages(record):
    pages = None
    if 'Pagination' in record['MedlineCitation']['Article']:
        pages = record['MedlineCitation']['Article']['Pagination'][
            'MedlinePgn'
        ]
    return pages


def get_pubmed_authors(record):
    authors = None
    if 'AuthorList' in record['MedlineCitation']['Article']:
        authorlist = [
            ' '.join([author['LastName'], author['Initials']])
            for author in record['MedlineCitation']['Article']['AuthorList']
            if 'LastName' in author and 'Initials' in author
        ]

        authors = ', '.join(authorlist)
    return authors


def get_pubmed_abstract(record):
    abstract = None
    if 'Abstract' in record['MedlineCitation']['Article']:
        if 'AbstractText' in record['MedlineCitation']['Article']['Abstract']:
            abstract = ' '.join(
                record['MedlineCitation']['Article']['Abstract'][
                    'AbstractText'
                ]
            )
    return abstract

def convert_to_datestring(datestruct):
    # convert date structure to string YYYY-MM-DD
    # convert month to number
    if 'Month' in datestruct:
        try:
            int(datestruct['Month'])
        except:
            datestruct['Month'] = str(datetime.strptime(datestruct['Month'], '%b').month)
    else:
        datestruct['Month'] = '12'
    
    if 'Day'  not in datestruct:
        datestruct['Day'] = '31'
    return '%s-%s-%s' % (
        f"{int(datestruct['Year']):02}",
        f"{int(datestruct['Month']):02}",
        f"{int(datestruct['Day']):02}",
    )

    
def get_pubmed_date(record):
    # get full date as string YYYY-MM-DD
    if 'ArticleDate' in record['MedlineCitation']['Article'] and \
        len(record['MedlineCitation']['Article']['ArticleDate']) > 0:
        return convert_to_datestring(record['MedlineCitation']['Article']['ArticleDate'][0])
    elif 'Journal' in record['MedlineCitation']['Article'] and \
        'JournalIssue' in record['MedlineCitation']['Article']['Journal'] and \
        'PubDate' in record['MedlineCitation']['Article']['Journal']['JournalIssue'] and \
        'Year' in record['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']:
        return convert_to_datestring(record['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate'])
        

    return None

def parse_pubmed_record(record):

    return {
        'DOI': get_pubmed_doi(record),
        'abstract': get_pubmed_abstract(record),
        'PMC': get_pubmed_pmcid(record),
        'PMID': get_pubmed_pmid(record),
        'type': 'journal-article',
        'journal': get_pubmed_journal_name(record),
        'year': get_pubmed_year(record),
        'publication-date': get_pubmed_date(record),
        'volume': get_pubmed_volume(record),
        'title': get_pubmed_title(record),
        'page': get_pubmed_pages(record),
        'authors': get_pubmed_authors(record),
    }
