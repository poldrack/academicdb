import datetime
from contextlib import suppress
from academicdb.utils import (
    remove_nans_from_pub,
    escape_characters_for_latex,
    load_config,
    run_shell_cmd,
)
from academicdb.dbbuilder import setup_db
import logging
import argparse
import os
from academicdb import database
import pkgutil



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
        '-o', '--outfile', type=str, help='output file stem', default='nsf_collaborators'
    )
    parser.add_argument(
        '-n', '--nyears', 
        type=int, 
        help='number of years back to include',
        default=4
    )
    return parser.parse_args()


#def main():
if __name__ == "__main__":
    
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

    coauthors = db.get_collection('coauthors')

