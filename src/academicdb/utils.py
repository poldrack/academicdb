"""
utility functions
"""

import os
import pandas as pd
import numpy as np
import random
import string
import json
import scholarly
from contextlib import suppress
import math
from Bio import Entrez
import subprocess


def get_valid_date(pub):
    if 'publication-date' in pub:
        date = pub['publication-date']
    elif 'coverDate' in pub:
        date = pub['coverDate']
    elif 'year' in pub:
        date = f'{pub["year"]}-01-01'
    try:
        datetime = pd.to_datetime(date)
        return datetime.strftime("%Y-%m-%d")
    except:
        return f'{pub["year"]}-01-01'


def serialize_pubs_to_json(pubs, outfile):
    """
    save a list of publications to json

    parameters:
    -----------
    pubs: a list of Publication objects
    outfile: string, filename to save to
    """

    # first combine into a single dictionary
    pubdict = {}
    for p in pubs:
        if p.hash in pubdict:
            print('WARNING: hash collision')
            p.hash = p.hash + get_random_hash(4)
        pubdict[p.hash] = vars(p)
    with open(outfile, 'w') as f:
        json.dump(pubdict, f)
    return pubdict


def shorten_authorlist(authors, maxlen=10, n_to_show=3):
    authors_split = authors.split(',')
    if len(authors_split) > maxlen:
        authors = ','.join(authors_split[:n_to_show]) + ' et al.'
    return authors


def load_pubs_from_json(infile):
    pubdict = {}
    with open(infile) as f:
        pubdict = json.load(f)
    return pubdict


def run_shell_cmd(cmd, cwd=[]):
    """run a command in the shell using Popen"""
    stdout_holder = []
    if cwd:
        process = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, cwd=cwd
        )
    else:
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    for line in process.stdout:
        print(line.strip())
        stdout_holder.append(line.strip())
    process.wait()
    return stdout_holder


def get_pmcid_from_pmid(pmid: str, email: str):
    """
    get the pmcid from the pmid
    """

    with Entrez.elink(
        dbfrom='pubmed',
        db='pmc',
        linkname='pubmed_pmc',
        id=pmid,
        retmode='text',
        email=email,
    ) as handle:
        record = Entrez.read(handle)

    try:
        pmcid = record[0]['LinkSetDb'][0]['Link'][0]['Id']
        pmcid = pmcid.replace('PMC', '')
    except Exception:
        pmcid = None
    return pmcid


def has_skip_strings(target, skip_strings=None):
    if skip_strings is None:
        skip_strings = [
            'corrigendum',
            'erratum',
            'author correction',
            'publisher correction',
        ]
    for skip_string in skip_strings:
        if target.lower().find(skip_string) > -1:
            return True
    return False


def remove_nans_from_pub(pub: dict):
    """
    remove nans from the publication record
    """
    for k, v in pub.items():
        with suppress(KeyError, TypeError):
            if math.isnan(v):
                pub[k] = None
    return pub


def load_config(configfile):
    import toml

    config = toml.load(configfile)
    return config


def get_random_hash(length=16):
    return ''.join(
        random.choice(string.ascii_lowercase) for i in range(length)
    )


# from https://stackoverflow.com/questions/50916422/python-typeerror-object-of-type-int64-is-not-json-serializable/50916741
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, scholarly._navigator.Navigator):
            return ''
        elif isinstance(obj, set):
            return ''
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif obj is None:
            return ''
        else:
            return super(CustomJSONEncoder, self).default(obj)


def get_params(param_file='params.json'):
    if os.path.exists(param_file):
        with open(param_file) as f:
            params = json.load(f)
    else:
        raise FileNotFoundError(
            'Please create a json file called params.json containing the fields email (with your email address), orcid (with your ORCID id) and query (with your pubmed query)- see documentation for help'
        )
    required_fields = [
        'address',
        'lastname',
        'firstname',
        'email',
        'orcid',
        'query',
        'url',
        'phone',
    ]
    for field in required_fields:
        assert field in params
    return params


def drop_excluded_pubs(pubs, exclusions_file='exclusions.txt'):
    if os.path.exists(exclusions_file):
        e = pd.read_csv(exclusions_file)
        for i in e.index:
            doi = e.loc[i, 'DOI']
            if doi in pubs:
                print('dropping excluded doi:', doi)
                del pubs[doi]
    return pubs


def make_funding_line(funding_df, i, abbreviate=True):
    if funding_df.loc[i, 'organization'].find('National') == 0 and abbreviate:
        # abbreviate
        org_split = [
            x[0]
            for x in funding_df.loc[i, 'organization'].split(' ')
            if x not in ['of', 'for', 'and', 'on']
        ]
        org = ''.join(org_split)
    else:
        org = funding_df.loc[i, 'organization']
    if funding_df.loc[i, 'id'] == '':
        idtext = ''
    else:
        if funding_df.loc[i, 'url'] != '':
            idtext = ' (\\href{%s}{%s})' % (
                funding_df.loc[i, 'url'],
                funding_df.loc[i, 'id'],
            )
        else:
            idtext = ' (%s)' % funding_df.loc[i, 'id']
    return '%s, %s%s, \\textit{%s}, %s-%s' % (
        funding_df.loc[i, 'role'],
        org,
        idtext,
        funding_df.loc[i, 'title'].title().strip(' '),
        funding_df.loc[i, 'start_date'],
        funding_df.loc[i, 'end_date'],
    )


def get_links(link_file):
    links = {}
    if os.path.exists(link_file):
        data_df = pd.read_csv(link_file)
        for i in data_df.index:
            linktype = data_df.loc[i, 'type']
            id = data_df.loc[i, 'DOI']
            if linktype not in links:
                links[linktype] = {}
            links[linktype][id] = data_df.loc[i, 'url']
    return links


def get_additional_pubs_from_csv(pubfile):
    pubs = {}
    if os.path.exists(pubfile):
        addpubs = pd.read_csv(pubfile)
        addpubs = addpubs.fillna('')
        # resolve duplicate ISBNs (e.g. multiple chapters in a book)
        if 'ISBN' in addpubs.columns:
            isbn_loc = np.where(addpubs.columns == 'ISBN')[0][0]
            addpubs.loc[:, 'ISBN'] = [i.strip(' ') for i in addpubs.ISBN]
            for i in range(1, addpubs.shape[0]):
                if addpubs.iloc[i, isbn_loc] == '':
                    continue
                if (
                    addpubs.iloc[i, isbn_loc]
                    in addpubs.iloc[: (i - 1), isbn_loc].tolist()
                ):
                    print('found match')
                    addpubs.iloc[i, isbn_loc] = (
                        addpubs.iloc[i, isbn_loc]
                        + '-'
                        + ''.join(
                            random.choice(string.ascii_lowercase)
                            for i in range(3)
                        )
                    )
        for i in addpubs.index:
            # make a random string to stand in for pmid
            if addpubs.loc[i, 'DOI'] != '':
                id = addpubs.loc[i, 'DOI']
                idType = 'DOI'
            elif addpubs.loc[i, 'ISBN'] != '':
                id = addpubs.loc[i, 'ISBN']
                idType = 'ISBN'
            else:
                id = ''.join(
                    random.choice(string.ascii_lowercase) for i in range(8)
                )
                idType = 'randomID'
            if id in pubs and pubs[id]['title'] == addpubs.loc[i, 'title']:
                print('found duplicate pub - skipping:', id)
                continue
            elif id in pubs:
                print('found duplicate id - modifying:', id)
                print(pubs[id])
                print('')
                id += '-' + ''.join(
                    random.choice(string.ascii_lowercase) for i in range(8)
                )
            else:
                print('found unique id:', id)
                print('')
            pubs[id] = {idType: id}
            for c in addpubs.columns:
                if c in ['DOI', 'ISBN']:
                    continue
                entry = addpubs.loc[i, c]
                if isinstance(entry, str):
                    entry = entry.strip(' ')
                pubs[id][c] = entry
    return pubs


def get_pubs_by_year(pubs, year):
    year_pubs = {}
    for p in pubs:
        if pubs[p].year == year:
            year_pubs[p] = pubs[p]
    return year_pubs


def get_keys_sorted_by_author(pubs):
    author_df = pd.DataFrame({'author': ''}, index=list(pubs.keys()))
    for pub in pubs:
        if hasattr(pubs[pub], 'authors'):
            author_df.loc[pub, 'author'] = pubs[pub].authors
        else:
            print('missing author:', pub)
    author_df.sort_values('author', inplace=True)
    return list(author_df.index)


def escape_characters_for_latex(pub):
    for field in ['title', 'publicationName']:
        if field in pub and hasattr(pub[field], 'replace'):
            pub[field] = pub[field].replace(r' &', r' \&')   # noqa
    return pub


def abbrev_authorname(author: str):
    """
    abbreviate the author name - replace first/middle names with initials
    assmes the author name is in the format "last, first middle"
    """

    # fix for authors with multiple last names e.g Zeynep Enkavi
    lastname, firstnames = author.split(',')
    if len(lastname.split(' ')) > 1:
        lastname = lastname.split(' ')[-1]
        firstnames += lastname.split(' ')[0]
    return lastname + ' ' + ''.join([i[0] for i in firstnames.split()])
