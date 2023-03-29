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


# setup logging as global
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--configfile',
        type=str,
        help='input file',
        default='config.toml'
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
    args = parser.parse_args()
    return(args)


def load_config(configfile):
    import toml
    config = toml.load(configfile)
    return(config)


def df_to_dicts(df):
    """
    take a dataframe and return a list of dictionaries
    """
    dictlist = []
    for i in df.index:
        dictlist.append(df.loc[i].to_dict())
    return(dictlist)


if __name__ == "__main__":
    
    args = parse_args()
    print(args)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    logging.info('Running dbbuilder.py')
    
    db = database.Database(database.MongoDatabase(overwrite=args.overwrite))

    r = researcher.Researcher(args.configfile)
    r.get_orcid_data()

    if args.add_pubs:
        logging.info('Getting publications')
        r.get_publications(maxret=5)
        print(f'Found {len(r.publications)} publications')

        additional_pubs_file = os.path.join(args.basedir, 'additional_pubs.csv')
        if os.path.exists(additional_pubs_file):
            r.get_additional_pubs_from_file(additional_pubs_file)
            print(f'Total of {len(r.publications)} publications after addition')

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


