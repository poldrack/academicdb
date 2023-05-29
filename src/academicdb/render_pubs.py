# render publications in markdown for web site

from contextlib import suppress
from academicdb.dbbuilder import setup_db
from academicdb.utils import escape_characters_for_latex
import logging
import argparse
import os


def get_publication_years(publications):
    years = list(set([i['year'] for i in publications]))
    years.sort(reverse=True)
    return years


def mk_author_string(authors, maxlen=10, n_to_show=3):
    authors = [i.lstrip(' ').rstrip(' ') for i in authors]
    if len(authors) > maxlen:
        return ', '.join(authors[:n_to_show]) + ' et al.'
    else:
        return ', '.join(authors) + '. '


def get_publication_outlet(pub):
    """
    format the publication outlet string based on the publication type
    """
    volstring, pagestring, pubstring = '', '', ''
    if 'journal' in pub:
        pub['journal'] = pub['journal'].replace('&amp;', '\&')
    if pub['type'] in ['journal-article', 'proceedings-article']:
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f", {pub['volume']}"
        if 'page' in pub and pub['page'] is not None:
            pagestring = f", {pub['page']}"
        # elif 'article_number' in pub and pub['article_number'] is not None:
        #    pagestring = f", {pub['article_number']}"
        return f" *{pub['journal']}{volstring}*{pagestring}. "
    elif pub['type'] == 'book-chapter':
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        if 'page' in pub and pub['page'] is not None:
            pagestring = f", {pub['page']}"
        return f" In *{pub['journal']}{volstring}*{pagestring}. "
    elif pub['type'] == 'book':
        if 'publisher' in pub and pub['publisher'] is not None:
            pubstring = f"{pub['publisher']}"
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        return f" *{pub['journal']}{volstring}*. {pubstring}."
    else:
        return f"*TBD{pub['type']}*"


def format_publication(pub, debug=False):
    output = pub['citation']['md'].lstrip().replace(' &', ' \\&')

    with suppress(KeyError):
        if pub['PMCID'] is not None:
            output += f" [OA](https://www.ncbi.nlm.nih.gov/pmc/articles/{pub['PMCID']})"
        elif pub['freetoread'] is not None and pub['freetoread'] in [
            'publisherhybridgold',
            'publisherfree2read',
        ]:
            output += f" [OA](https://doi.org/{pub['doi']})"
    if (
        'DOI' in pub
        and pub['DOI'] is not None
        and pub['DOI'].find('nodoi') == -1
    ):
        output += f" [DOI](https://doi.org/{pub['DOI']})"
    if 'links' in pub:
        if 'Data' in pub['links'] and pub['links']['Data'] is not None:
            output += f" [Data]({pub['links']['Data']})"
        if 'Code' in pub['links'] and pub['links']['Code'] is not None:
            output += f" [Code]({pub['links']['Code']})"
        if 'OSF' in pub['links'] and pub['links']['OSF'] is not None:
            output += f" [OSF]({pub['links']['OSF']})"

    output += '\\vspace{2mm}\n\n'
    return output


def get_publications(publications, exclude_dois=None):
    years = get_publication_years(publications)
    output = ''

    for year in years:
        year_pubs = [i for i in publications if i['year'] == year]
        year_pubs.sort(key=lambda x: x['authors'])
        # list(db['publications'].find({'year': {'$regex': f'^{year}'}}).sort("firstauthor", pymongo.ASCENDING))
        output += f'###  {year}\n\n'
        for pub in year_pubs:
            if (
                'Corrigendum' in pub['title']
                or 'Author Correction' in pub['title']
                or 'Erratum' in pub['title']
            ):
                continue
            if exclude_dois is not None and pub['doi'] in exclude_dois:
                continue
            pub = escape_characters_for_latex(pub)
            # output += f"\\textit{{{pub['eid'].replace('_','-')}}} "
            output += format_publication(pub)

    return output



def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--configdir',
        type=str,
        help='directory for config files',
        default=os.path.join(os.path.expanduser('~'), '.academicdb'),
    )
    parser.add_argument(
        '-d', '--outdir', type=str, help='output dir', default='./output'
    )
    parser.add_argument(
        '-o', '--outfile', type=str, help='output file stem', default='publications'
    )

    return parser.parse_args()


def main():

    args = parse_args()
    print(args)
    logging.info('Making markdown publications files')

    # this needs to be configured as package_data
    datadir = 'src/data'

    if not os.path.exists(args.configdir):
        raise FileNotFoundError(
            f'Config directory {args.configdir} does not exist'
        )

    configfile = os.path.join(args.configdir, 'config.toml')
    if not os.path.exists(configfile):
        raise FileNotFoundError(
            f'You must first set up the config.toml file in {args.configdir}'
        )
    db = setup_db(configfile)

    metadata = db.get_collection('metadata')
    assert len(metadata) == 1, 'There should be only one metadata document'
    metadata = metadata[0]


    doc = get_publications(
        db.get_collection('publications'),
    )


    # write to file
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)
    outfile = os.path.join(args.outdir, f'{args.outfile}.md')
    with open(outfile, 'w') as f:
        f.write(doc)

