import argparse
import logging
import os
from academicdb import database, researcher, orcid, utils, publication
import pandas as pd
from pybliometrics.scopus import AuthorRetrieval
import pybliometrics

# setup logging as global
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)


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
        '-b', '--basedir', type=str, help='base directory', default='.'
    )
    parser.add_argument(
        '-d', '--debug', action='store_true', help='log debug messages'
    )
    parser.add_argument(
        '-o',
        '--overwrite',
        action='store_true',
        help='overwrite existing database',
    )
    parser.add_argument(
        '--no_add_pubs', action='store_true', help='do not get publications'
    )
    parser.add_argument(
        '--no_add_info',
        action='store_true',
        help='do not add additional information from csv files',
    )
    parser.add_argument(
        '--nodb', action='store_true', help='do not write to database'
    )
    parser.add_argument(
        '-t',
        '--test',
        action='store_true',
        help='test mode (limit number of publications)',
    )
    parser.add_argument(
        '--bad_ids_file',
        type=str,
        help='file with bad ids to remove',
        default='bad_ids.csv',
    )
    return parser.parse_args()


def load_config(configfile):
    import toml

    return toml.load(configfile)


def df_to_dicts(df):
    """
    take a dataframe and return a list of dictionaries
    """
    return [df.loc[i].to_dict() for i in df.index]


def add_citations(publications, reftypes=None):
    if reftypes is None:
        reftypes = ['latex', 'md']

    for doi, pub in publications.items():
        pub_func = {
            'journal-article': publication.JournalArticle,
            'proceedings-article': publication.JournalArticle,
            'book-chapter': publication.BookChapter,
            'book': publication.Book,
        }
        pubstruct = pub_func[pub['type']]().from_dict(pub)
        publications[doi]['citation'] = {
            reftype: pubstruct.format_reference(reftype)
            for reftype in reftypes
        }
    return publications


def drop_empty_pubs(publications):
    empty_pubs = [i for i in publications if publications[i] is None]
    for i in empty_pubs:
        del publications[i]
    return publications


def setup_db(configfile, overwrite=False):
    logging.info(f'Using database config from {configfile}')
    config = load_config(configfile)
    if config is not None and 'mongo' in config and 'CONNECT_STRING' in config['mongo']:
        logging.info('Using custom mongodb config')
        return database.Database(
            database.MongoDatabase(
                overwrite=overwrite,
                connect_string=config['mongo']['CONNECT_STRING'],
            )
        )
    logging.info('Using default localhost database config')
    return database.Database(
        database.MongoDatabase(overwrite=overwrite))


def get_affiliation(aff):
    if aff.parent_preferred_name is not None:
        return f'{aff.preferred_name}, {aff.parent_preferred_name}, {aff.city}, {aff.country}'
    else:
        return f'{aff.preferred_name}, {aff.city}, {aff.country}'


def get_coauthors(publications):

    coauthors = {}
    for pub in publications:
        if 'scopus_coauthor_ids' not in pub:
            print(f'No coauthors for {pub}')
            continue
        for coauthor in pub['scopus_coauthor_ids']:
            if coauthor not in coauthors:
                coauthor_info = AuthorRetrieval(coauthor)
                if coauthor_info.indexed_name is None:
                    continue
                if coauthor_info.affiliation_current is None:
                    affil = None
                    affil_id = None
                else:
                    affil = [
                        get_affiliation(aff)
                        for aff in coauthor_info.affiliation_current
                    ]
                    affil_id = [
                        aff.id for aff in coauthor_info.affiliation_current
                    ]
                if 'publication-date' in pub:
                    date = pub['publication-date']
                elif 'coverDate' in pub:
                    date = pub['coverDate']
                elif 'year' in pub:
                    date = f'{pub["year"]}-01-01'
                try:
                    datetime = pd.to_datetime(date)
                except:
                    date = f'{pub["year"]}-01-01'
                coauthors[coauthor] = {
                    'scopus_id': coauthor,
                    'name': f'{coauthor_info.surname}, {coauthor_info.given_name} ',
                    'affiliation': affil,
                    'affiliation_id': affil_id,
                    'date': date,
                    'year': int(date.split('-')[0]),
                }
            else:
                try:
                    datetime = pd.to_datetime(date)
                except:
                    date = f'{pub["year"]}-01-01'
                    datetime = pd.to_datetime(date)
                if datetime > pd.to_datetime(coauthors[coauthor]['date']):
                    coauthors[coauthor]['date'] = date
    return coauthors


def main():
    args = parse_args()
    print(args)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.info('Running dbbuilder.py')

    if not os.path.exists(args.configdir):
        raise FileNotFoundError(
            f'Config directory {args.configdir} does not exist'
        )

    configfile = os.path.join(args.configdir, 'config.toml')
    if not os.path.exists(configfile):
        raise FileNotFoundError(
            f'You must first set up the config.toml file in {args.configdir}'
        )

    pybliometrics.scopus.init()

    db = setup_db(configfile, args.overwrite)

    r = researcher.Researcher(configfile)
    r.get_orcid_data()
    r.get_google_scholar_data()

    if not args.no_add_pubs:
        logging.info('Getting publications')
        maxret = 5 if args.test else None
        r.get_publications(maxret=maxret)
        print(f'Found {len(r.publications)} publications')

        additional_pubs_file = os.path.join(
            args.basedir, 'additional_pubs.csv'
        )
        if os.path.exists(additional_pubs_file):
            r.get_additional_pubs_from_file(additional_pubs_file)
            print(
                f'Total of {len(r.publications)} publications after addition'
            )
    else:
        logging.warning('Loading pubs from database')
        r.publications = db.get_collection('publications')

    # drop bad dois
    bad_ids_file = (
        args.bad_ids_file
        if os.path.exists(args.bad_ids_file)
        else os.path.join(args.basedir, 'bad_ids.csv')
    )

    if os.path.exists(bad_ids_file):
        bad_ids = pd.read_csv(bad_ids_file)
        # get list of all pmids for checking
        logging.info(f'Dropping excluded publications')
        all_pmids = [str(pub['PMID']) for pub in r.publications.values() if pub is not None and 'PMID' in pub and pub['PMID'] is not None]
        for idx in bad_ids.index:
            id = bad_ids.loc[idx, 'idval'].strip()
            idtype = bad_ids.loc[idx, 'idtype'].strip()
            if idtype == 'doi':
                if id in r.publications:
                    del r.publications[id]
                    logging.info(f'Dropping excluded publication {id}')
                else:
                    logging.warning(f'Excluded doi {id} not found')
            elif idtype == 'pmid':
                if id in all_pmids:
                    del_id = [k for k, v in r.publications.items() if v is not None and 'PMID' in v and str(v['PMID']) == id]
                    if len(del_id) > 0:
                        del r.publications[del_id[0]]
                        logging.info(f'Dropping excluded publication {id}')
                else:
                    logging.warning(f'Excluded pmid {id} not found')
       
    r.publications = drop_empty_pubs(r.publications)

    if not args.no_add_info:
        additional_files = [
            'editorial.csv',
            'talks.csv',
            'conference.csv',
            'teaching.csv',
            'funding.csv',
        ]

        for f in additional_files:
            additional_file = os.path.join(args.basedir, f)
            target = f.split('.')[0]
            if os.path.exists(additional_file):
                items = []
                logging.info(f'Adding information from {f}')
                df = pd.read_csv(additional_file)
                for i in df.index:
                    line_dict = utils.remove_nans_from_pub(df.loc[i].to_dict())
                    print(line_dict)
                    items.append(line_dict)

                setattr(r, target, items)

        education_df = orcid.get_orcid_education(r.orcid_data)
        setattr(r, 'education', df_to_dicts(education_df))

        employment_df = orcid.get_orcid_employment(r.orcid_data)
        setattr(r, 'employment', df_to_dicts(employment_df))

        distinctions_df = orcid.get_orcid_distinctions(r.orcid_data)
        setattr(r, 'distinctions', df_to_dicts(distinctions_df))

        service_df = orcid.get_orcid_service(r.orcid_data)
        setattr(r, 'service', df_to_dicts(service_df))

        memberships_df = orcid.get_orcid_memberships(r.orcid_data)
        setattr(r, 'memberships', df_to_dicts(memberships_df))

    linksfile = os.path.join(args.basedir, 'links.csv')
    if os.path.exists(linksfile):
        logging.info(f'Adding links from {linksfile}')
        r.add_links_to_publications(linksfile)

    r.publications = add_citations(r.publications)

    r.get_coauthors()

    if not args.nodb:
        r.to_database(db)
