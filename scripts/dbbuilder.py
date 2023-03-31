import argparse
import logging
import os
from academicdb import (
    database,
    researcher,
    query,
    recordConverter,
    orcid,
    utils
)
import pandas as pd
import src.academicdb.publication as publication # import JournalArticle, Book, BookChapter

# setup logging as global
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--configdir',
        type=str,
        help='directory for config files',
        default=os.path.join(os.path.expanduser('~'), '.academicdb')
    )
    parser.add_argument(
        '-b',
        '--basedir',
        type=str,
        help='base directory',
        default='.'
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='log debug messages'
    )
    parser.add_argument(
        '-o',
        '--overwrite',
        action='store_true',
        help='overwrite existing database'
    )
    parser.add_argument(
        '-p',
        '--add_pubs',
        action='store_true',
        help='get publications'
    )
    parser.add_argument(
        '-i',
        '--add_info',
        action='store_true',
        help='add additional information from csv files'
    )
    parser.add_argument(
        '--nodb',
        action='store_true',
        help='do not write to database'
    )
    parser.add_argument(
        '-t',
        '--test',
        action='store_true',
        help='test mode'
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


if __name__ == "__main__":
    
    args = parse_args()
    print(args)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.info('Running dbbuilder.py')
    
    if not os.path.exists(args.configdir):
        raise FileNotFoundError(f'Config directory {args.configdir} does not exist')
    
    configfile = os.path.join(args.configdir, 'config.toml')
    dbconfigfile = os.path.join(args.configdir, 'dbconfig.toml')
    bad_doi_file = os.path.join(args.basedir, 'bad_dois.csv')

    if os.path.exists(dbconfigfile):
        logging.info(f'Using database config file {dbconfigfile}')
        dbconfig = load_config(dbconfigfile)
        assert dbconfig['mongo']['CONNECT_STRING'], 'CONNECT_STRING must be specified in dbconfig'
        db = database.Database(database.MongoDatabase(overwrite=args.overwrite, 
                                                      connect_string = dbconfig['mongo']['CONNECT_STRING']))
    else:
        logging.info(f'Using default localhost database config')
        db = database.Database(database.MongoDatabase(overwrite=args.overwrite))

    r = researcher.Researcher(configfile)
    r.get_orcid_data()
    r.get_google_scholar_data()

    if args.add_pubs:
        logging.info('Getting publications')
        maxret = 5 if args.test else None
        r.get_publications(maxret=maxret)
        print(f'Found {len(r.publications)} publications')

        additional_pubs_file = os.path.join(args.basedir, 'additional_pubs.csv')
        if os.path.exists(additional_pubs_file):
            r.get_additional_pubs_from_file(additional_pubs_file)
            print(f'Total of {len(r.publications)} publications after addition')

    # drop bad dois
    if os.path.exists(bad_doi_file):
        bad_dois = pd.read_csv(bad_doi_file)
        for doi in bad_dois['doi']:
            del r.publications[doi]
    empty_pubs = [i for i in r.publications if r.publications[i] is None]
    for i in empty_pubs:
        del r.publications[i]

    if args.add_info:
        additional_files = [
            'editorial.csv',
            'talks.csv',
            'conference.csv',
            'teaching.csv',
            'funding.csv'
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

    # create citations
    reftypes = ['latex', 'md']
    for doi, pub in r.publications.items():
        pub_func = {
            'journal-article': publication.JournalArticle,
            'proceedings-article': publication.JournalArticle,
            'book-chapter': publication.BookChapter,
            'book': publication.Book
        }
        pubstruct = pub_func[pub['type']]().from_dict(pub)
        r.publications[doi]['citation'] = {
            reftype: pubstruct.format_reference(reftype) for reftype in reftypes
        }

    if not args.nodb:
        r.to_database(db)
