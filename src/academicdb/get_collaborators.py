import datetime
from contextlib import suppress
from academicdb.utils import (
    remove_nans_from_pub,
    escape_characters_for_latex,
    load_config,
    run_shell_cmd,
)
from academicdb.dbbuilder import setup_db, get_coauthors
import logging
import argparse
import os
from academicdb import database
import pkgutil
import pandas as pd
from pybliometrics.scopus import AuthorRetrieval
from academicdb.dbbuilder import get_affiliation
import datetime


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
        '-d', '--outdir', type=str, help='output dir', default='./'
    )
    parser.add_argument(
        '-o', '--outfile', type=str, help='output file stem', default='nsf_collaborators'
    )
    parser.add_argument(
        '-n', '--nyears', 
        type=int, 
        help='number of years back to include',
        default=4
    )
    return parser.parse_args()


def process_coauthors(coauthors):
    """Process coauthors into a dataframe"""
    coauthors_df = pd.DataFrame(coauthors)
    coauthors_df['n_pubs'] = coauthors_df['pubs'].apply(len)
    coauthors_df = coauthors_df.sort_values('n_pubs', ascending=False)
    return coauthors_df


def main():
   
    args = parse_args()
    print(args)
    logging.info('Running get_collaborators.py')

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

    publications = db.get_collection('publications')

    coauthors = get_coauthors(publications)

    coauthor_df = pd.DataFrame(coauthors).T.sort_values('name')
    coauthor_df = coauthor_df[['name', 'affiliation', 'date', 'year']]
    coauthor_df['dt'] = pd.to_datetime(coauthor_df['date'])
    coauthor_df = coauthor_df.query(f'dt > "{datetime.datetime.now() - datetime.timedelta(days=365*args.nyears)}"')
    coauthor_df['date'] = coauthor_df['dt'].apply(lambda x: x.strftime("%m/%d/%Y"))
    del coauthor_df['dt']
    del coauthor_df['year']
    coauthor_df['email'] = ''
    coauthor_df['type'] = 'A:'
    coauthor_df = coauthor_df[['type', 'name', 'affiliation', 'email', 'date']]
    coauthor_df['affiliation'] = coauthor_df['affiliation'].apply(lambda x: x[0])
    coauthor_df.to_csv(os.path.join(args.outdir, f'{args.outfile}.csv'), index=False)

if __name__ == "__main__":

    main()