import datetime
from contextlib import suppress
from academicdb.utils import (
    remove_nans_from_pub,
    escape_characters_for_latex,
    load_config,
    run_shell_cmd,
)
from academicdb.dbbuilder import setup_db #, get_coauthors
import logging
import argparse
import os
from academicdb import database, utils
import pkgutil
import pandas as pd
from pybliometrics.scopus import AuthorRetrieval
from academicdb.dbbuilder import get_affiliation
import datetime
from collections import defaultdict


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

def get_scopus_coauthors(pub):
    # print(f'processing scopus pub', pub['DOI'])
    coauthors = {}
    for coauthor in pub['scopus_coauthor_ids']:
        coauthor_info = AuthorRetrieval(coauthor)
        if coauthor_info.indexed_name is None or 'Poldrack' in coauthor_info.indexed_name:
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
        coauthors[coauthor] = {
            'pubtype': 'scopus',
            'scopus_id': coauthor,
            'name': f'{coauthor_info.surname}, {coauthor_info.given_name} ',
            'affiliation': affil,
            'affiliation_id': affil_id,
            'date': pub['publication-date'],
            'year': int(pub['publication-date'].split('-')[0]),
        }
    return coauthors


def get_generic_coauthors(pub):
    # print(f'processing generic pub', pub['DOI'])
    coauthors = {}
    if 'authors_abbrev' not in pub:
        return None
    for coauthor in pub['authors_abbrev']:
        if 'Poldrack' in coauthor:
            continue
        namehash = hash(coauthor)
        if 'publication-date' in pub:
            date = pub['publication-date']
        elif 'coverDate' in pub:
            date = utils.get_valid_date(pub)
        else:
            print('invalid date:', pub)
            date = None
        coauthors[namehash] = {
            'pubtype': 'generic',
            'scopus_id': None,
            'name': ', '.join(coauthor.split(' ')),
            'affiliation': None,
            'affiliation_id': None,
            'date': date,
            'year': int(date.split('-')[0]),
        }
    return coauthors


def abbreviate_name(name):
    name_parts = name.rstrip().split(',')
    lastname = name_parts[0].strip()
    initials = [i[0] for i in name_parts[1].lstrip().split(' ')]
    return f"{lastname} {''.join(initials)}"


def add_pub_coauthors(coauthors, pub_coauthors):
    for coauthor, coauthor_info in pub_coauthors.items():
        coauthor_info['name'] = coauthor_info['name'].rstrip().lstrip()
        if coauthor_info['scopus_id'] is not None:
            coauthor_info['name_abbrev'] = abbreviate_name(coauthor_info['name'])
            coauthor_info['name_hash'] = hash(coauthor_info['name_abbrev'])
        if coauthor not in coauthors:
            coauthors[coauthor] = coauthor_info
        else:
            try:
                datetime = pd.to_datetime(coauthor_info['date'])
            except:
                date = f'{pub["year"]}-01-01'
                datetime = pd.to_datetime(date)
            if datetime > pd.to_datetime(coauthors[coauthor]['date']):
                coauthors[coauthor]['date'] = datetime.strftime("%Y-%m-%d")
    return coauthors

# refactoring
def get_coauthors(publications, verbose=True):
    coauthors = {}
    for pub in publications: 
        # figure out which type of author record there is

        if 'scopus_coauthor_ids' in pub:
            pubtype = 'scopus'
            pub_coauthors = get_scopus_coauthors(pub)
            coauthors = add_pub_coauthors(coauthors, pub_coauthors)
        else:
            pubtype = 'generic'
            pub_coauthors = get_generic_coauthors(pub)
            if pub_coauthors is not None:
                coauthors = add_pub_coauthors(coauthors, pub_coauthors)

    return coauthors


def find_coauthor_by_name(coauthors, name_abbrev):
    coauthors = {coauthor: coauthor_info for coauthor, coauthor_info in coauthors.items() if coauthor_info['pubtype'] == 'scopus'}
    match = [coauthor for coauthor, coauthor_info in coauthors.items() if coauthor_info['name_abbrev'] == name_abbrev]
    if len(match) == 0:
        return None
    else:
        return match[0]
    

def combine_coauthors(coauthors):
    # first get scopus coauthors
    scopus_coauthors = {}
    skipped_authors = []
    for coauthor, coauthor_info in coauthors.items():
        if coauthor_info['pubtype'] == 'scopus':
            scopus_coauthors[coauthor] = coauthor_info
    # then get generic coauthors
    generic_coauthors = {}
    for coauthor, coauthor_info in coauthors.items():
        if coauthor_info['pubtype'] == 'generic':
            print('adding generic coauthor', coauthor)
            generic_coauthors[coauthor] = coauthor_info
    assert len(scopus_coauthors) + len(generic_coauthors) == len(coauthors)

    # integrate generic coauthors into scopus coauthors
    scopus_names = [coauthor_info['name_abbrev'] for coauthor_info in scopus_coauthors.values()]
    for coauthor, coauthor_info in generic_coauthors.items():
        name_abbrev = coauthor_info['name'].replace(', ', ' ')
        if name_abbrev not in scopus_names:
            scopus_coauthors[str(coauthor)] = coauthor_info
        else:
            # print('checking generic coauthor', coauthor, coauthor_info['name'])
            scopus_coauthor = find_coauthor_by_name(scopus_coauthors, name_abbrev)
            if scopus_coauthor is None:
                print('could not find coauthor by name', name_abbrev)
                skipped_authors.append(name_abbrev)
            else:
                datetime = pd.to_datetime(coauthor_info['date'])
                if datetime > pd.to_datetime(coauthors[scopus_coauthor]['date']):
                    coauthors[scopus_coauthor]['date'] = datetime.strftime("%Y-%m-%d")
                 
    return scopus_coauthors, skipped_authors

def get_coauthors_prev(publications, verbose=True):

    coauthors = {}
    for pub in publications:
   
        if 'scopus_coauthor_ids' not in pub and 'author_records' not in pub:
            if verbose:
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



if __name__ == "__main__":

#def main():
   
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
    coauthors, skipped_authors = combine_coauthors(coauthors)
    print(f'Found {len(coauthors)} total coauthors')

    if True:
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
        coauthor_df['affiliation'] = coauthor_df['affiliation'].apply(lambda x: x[0] if x is not None else '')
        coauthor_df.to_csv(os.path.join(args.outdir, f'{args.outfile}.csv'), index=False)
        print(f'Wrote {len(coauthor_df)} coauthors to {args.outdir}/{args.outfile}.csv')

#if __name__ == "__main__":

#    main()