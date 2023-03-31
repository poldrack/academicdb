import contextlib
import pymongo
import requests
import orcid
from pubmed import get_pubmed_data
from researcher import Researcher
from bs4 import BeautifulSoup
import urllib.request
import hashlib
import autocv.orcid as orcid
from pybliometrics.scopus import AuthorRetrieval
import pybliometrics
from collections import defaultdict
import os
import pandas as pd
from collections import OrderedDict
from utils import get_links
from Bio import Entrez
from orcid import get_dois_from_orcid_record
from collections import Counter
import math
from contextlib import suppress


def get_scopus_id_from_orcid(orcid_data: dict):
    # get the scopus id from the orcid record
    for ext_id in orcid_data['person']['external-identifiers']['external-identifier']:
        if ext_id['external-id-type'] == 'Scopus Author ID':
            return ext_id['external-id-value']
    return None


def setup_db(dbname='academicdb', collections=None, overwrite=False):
    """
    setup the database and collections
    
    Parameters
    ----------
    dbname : str
            name of the database
    collections : list
            list of collections to create/overwrite (default: all)
    overwrite : bool
            overwrite the database if it already exists (default: False)
    """

    client = pymongo.MongoClient(host="127.0.0.1", port=27017)
    if dbname in client.list_database_names() and not overwrite:
        # check to make sure only one metadata record exists
        if len(list(client[dbname]['metadata'].find())) > 1:
            raise ValueError(
                "more than one metadata record exists in the database - please rerun with overwrite set to True")
        return client[dbname]
    elif dbname in client.list_database_names():
        if collections is None:
            client.drop_database(dbname)
        else:
            for c in collections:
                client[dbname].drop_collection(c)
    return setup_collections(client, dbname)


def setup_collections(client: pymongo.mongo_client.MongoClient, dbname: str):
    result = client[dbname]
    collections_to_create = ['coauthors', 'funding', 'conferences', 'talks', 
        'education', 'employment', 'distinctions', 'metadata', 'publications',
        'invited_positions', 'memberships', 'service', 'trainees', 'pmcid']
    for c in collections_to_create:
        if c not in result.list_collection_names():
            result.create_collection(c)
    indices_to_create = {
        'metadata': 'orcid',
        'publications': 'eid',
        'pmcid': 'pmid',
    }
    for c, idx in indices_to_create.items():
        result[c].create_index([(idx, pymongo.ASCENDING)], unique=True)

    return result


def load_params_from_json(paramfile='params.json'):
    import json
    with open(paramfile, 'r') as f:
        params = json.load(f)
    return params


    

def get_pmcid_from_pmid(pmid: str, db: pymongo.database.Database):
    """
    get the pmcid from the pmid
    """

    # check if the pmcid is already in the database
    pmid_match = db['pmcid'].find_one({'pmid': pmid})
    if pmid_match:
        return pmid_match['pmcid']

    handle = Entrez.elink(dbfrom="pubmed", db="pmc", linkname="pubmed_pmc", id=pmid, retmode="text")
    record = Entrez.read(handle)
    handle.close()
    try:
        pmcid = record[0]['LinkSetDb'][0]['Link'][0]['Id']
    except Exception:
        pmcid = None
    print(f'adding pmcid for {pmid} to database: {pmcid}')
    db['pmcid'].insert_one({'pmid': pmid, 'pmcid': pmcid})
    return None

def remove_nans_from_pub(pub: dict):
    """
    remove nans from the publication record
    """
    for k, v in pub.items():
        with suppress(KeyError, TypeError):
            if math.isnan(v):
                pub[k] = None
    return pub

def add_publications_to_db(pubs: dict, db: pymongo.database.Database, links: dict):
    """
    Insert the records into the database
    - pubs should be a list of dicts
    - db should be a pymongo database object
    - if no DOI is present, a random one will be generated
    """
    newctr = 0
    existctr = 0

    for item in pubs.values():
        if not db['publications'].find_one({'eid': item['eid']}):
            newctr += 1
        else:
            existctr += 1
        item['firstauthor'] = item['author_names'][0]
        item['authors_abbrev'] = [abbrev_authorname(i) for i in item['author_names']]
        # dois should be case insensitive but scopus dois are mixed- convert to lowercase for easier matching
        if 'doi' in item and item['doi'] is not None:
            item['doi'] = item['doi'].lower()
        if 'PMCID' not in item:
            item['PMCID'] = get_pmcid_from_pmid(item['pubmed_id'], db)
        for linktype, linkdict in links.items():
            if item['doi'] in linkdict:
                item[linktype] = linkdict[item['doi']]
        item = remove_nans_from_pub(item)
    
        db['publications'].replace_one({'eid': item['eid']}, item, upsert=True)

    print(f'added {newctr} publications to the database')
    print(f'found {existctr} existing publications in the database')


def add_researcher_metadata_to_db(researcher: Researcher, db: pymongo.database.Database):
    """
    add metadata from params
    - include all string fields from the researcher object
    - if the researcher already exists in the db, update the metadata

    index by orcid
    """
    researcher_md_dict = {
        k: v for k, v in researcher.__dict__.items() if isinstance(v, (str, list, dict)) and len(v) > 0}

    # validate names against ORCID record
    assert researcher.orcid_data['person']['name']['given-names']['value'].lower() == researcher.firstname.lower(), \
        'first name does not match ORCID record'
    assert researcher.orcid_data['person']['name']['family-name']['value'].lower() == researcher.lastname.lower(), \
        'first name does not match ORCID record'

    existing_record = db['metadata'].find_one({'orcid': researcher.orcid})
    if existing_record is None:
        # insert the metadata into the db if they don't already exist
        db['metadata'].insert_one(researcher_md_dict)
    elif existing_record['orcid'] == researcher.orcid:
        # update the metadata
        print("updating metadata")
        db['metadata'].replace_one(
            {'orcid': researcher.orcid},
            researcher_md_dict)
    else:
        raise ValueError("new record has different orcid than existing record")


def serialize_scopus_doc(doc):
    doc_dict = {field: getattr(doc, field) for field in doc._fields}
    # split fields with multiple values into lists
    split_fields = ['afid', 'affilname', 'affiliation_city', 'affiliation_country',
        'author_names', 'author_ids', 'author_afids']
    for field in split_fields:
        with contextlib.suppress(AttributeError):
            doc_dict[field] = doc_dict[field].split(';')
    return(doc_dict)


# need to put these straight into the database so that we can reuse them
def get_coauthors_from_pubs(pubs: dict, db: pymongo.database.Database, my_scopus_id: str):
    print('getting coauthors from publications')
    coauthor_ids = {}
    for key, item in pubs.items():
        if 'author_ids' not in item:
            continue
        if my_scopus_id in item['author_ids']:
            item['author_ids'].remove(my_scopus_id)
        for author_id in item['author_ids']:
            if db['coauthors'].find_one({'identifier': author_id}) is None:
                au_record = AuthorRetrieval(author_id)
                coauthor_dict = {
                    'identifier': author_id,
                    'name': f'{au_record.surname}, {au_record.given_name}',
                    'pubs': {},
                    'orcid': au_record.orcid,
                    'affiliation': au_record.affiliation_current[0]._asdict() if au_record.affiliation_current else None,
                }
            else:
                coauthor_dict = db['coauthors'].find_one({'identifier': author_id})
            coauthor_dict['pubs'][key] = item['coverDate']
            db['coauthors'].replace_one(
                {'identifier': author_id},
                coauthor_dict,
                upsert=True)
    return list(db.coauthors.find())
 

def get_editorial_df(basedir, editorial_filename='editorial.csv'):
    editorial_file = os.path.join(basedir, editorial_filename)
    if os.path.exists(editorial_file):
        return pd.read_csv(editorial_file)
    else:
        return None


def get_talks_df(basedir, talks_filename='talks.csv'):
    talks_file = os.path.join(basedir, talks_filename)
    if os.path.exists(talks_file):
        return pd.read_csv(talks_file)
    else:
        return None



def get_conference_df(basedir, conference_filename='conference.csv'):
    conference_file = os.path.join(basedir, conference_filename)
    if os.path.exists(conference_file):
        conference_df = pd.read_csv(conference_file)
    else:
        return None

    month_name_to_number = {
        'January': '01',
        'February': '02',
        'March': '03',
        'April': '04',
        'May': '05',
        'June': '06',
        'July': '07',
        'August': '08',
        'September': '09',
        'October': '10',
        'November': '11',
        'December': '12',
    }
    conference_df['monthnum'] = conference_df['month'].map(month_name_to_number)
    conference_df['date'] = conference_df['year'].astype(str) + '-' + conference_df['monthnum'].astype(str) + '-01'
    return conference_df

def get_teaching_df(basedir, teaching_filename='teaching.csv'):
    teaching_file = os.path.join(basedir, teaching_filename)
    if os.path.exists(teaching_file):
        return pd.read_csv(teaching_file)
    else:
        return None


def get_presentations(basedir, presentations_filename='conference.csv'):
    presentations_file = os.path.join(basedir, presentations_filename)
    if os.path.exists(presentations_file):
        presentations = pd.read_csv(presentations_file) #, index_col=0)
    else:
        return

    presentations = presentations.sort_values('year', ascending=False)
    return(presentations)


def get_talks(basedir, talks_filename='talks.csv', verbose=True):
    talks_file = os.path.join(basedir, talks_filename)
    if os.path.exists(talks_file):
        return pd.read_csv(talks_file) #, index_col=0)
    else:
        return None


def get_funding(basedir, funding_filename='funding.csv'):
    return get_df(os.path.join(basedir, funding_filename))


def get_df(filename):
    if os.path.exists(filename):
        return pd.read_csv(filename)
    else:
        return None


def add_df_to_db(df, db, collection_name):
    db[collection_name].delete_many({}) # clear out the collection
    for i in df.index:
        db[collection_name].insert_one(df.loc[i].to_dict())


def add_dict_to_db(dictlist: list, db, collection_name):
    """
    take in a list of dicts and add them to the database
    """
    db[collection_name].delete_many({}) # clear out the collection
    for i in dictlist:
        db[collection_name].insert_one(i)


def remove_matching_pubs(db):
    """
    remove publications that have the same title and authors
    - drop the book version
    """
    alltitles = [i['title'] for i in db.publications.find()]
    cnt = Counter(alltitles)
    matchtitles = [i for i in cnt if cnt[i] > 1]
    print('found %d duplicate titles' % len(matchtitles))

    for matchtitle in matchtitles:
        print(f'matching title: {matchtitle}')
        myquery = {'title': matchtitle, 'aggregationType': 'Book'}
        x = db.publications.delete_many(myquery)
        print(x.deleted_count, " duplicates deleted.") 


def add_additional_pubs_from_file(db, pubfile, verbose=True):
    """
    add additional publications to the database
    """
    addl_pubs = pd.read_csv(pubfile)
    added_pubs = {}
    pubdict = {i['eid']: i for i in db.publications.find()}
    alltitles = [i['title'] for i in pubdict.values()]
    alldois = [i['doi'] for i in pubdict.values()]
    for i in addl_pubs.index:
        pub = addl_pubs.loc[i].to_dict()
        pub['title'] = pub['title'].rstrip('.')
        pub['pageRange'] = pub['page']
        del pub['page']
        pub['coverDate'] = f"{pub['year']}-01-01"
        with suppress(TypeError):
            if math.isnan(pub['DOI']):
                pub['DOI'] = None
        with suppress(TypeError):
            if math.isnan(pub['volume']):
                pub['volume'] = None
        with suppress(TypeError):
            if math.isnan(pub['pageRange']):
                pub['pageRange'] = None
        pub['authors_abbrev'] = [a.lstrip(' ') for a in pub['authors'].split(',')]
        pub['firstauthor'] = pub['authors_abbrev'][0]
        pub['doi'] = pub['DOI']
        del pub['DOI']
        if pub['type'] == 'book':
            pub['publicationName'] = pub['title']
        else:
            pub['publicationName'] = pub['journal']
        del pub['journal']
        typedict = {'journal-article': ('Journal', 'Article'),
                    'book': ('Book', 'Book'),
                    'book-chapter': ('Book', 'Book Chapter'),
                    'proceedings-article': ('Conference Proceeding', 'Conference Paper')
                    }
        pub['aggregationType'], pub['subtypeDescription'] = typedict[pub['type']]
        pub = remove_nans_from_pub(pub)
        if pub['title'] not in alltitles:
            print('adding %s' % pub['title'])
            pub['eid'] = f"added-{hashlib.md5(pub['title'].encode('utf-8')).hexdigest()}"
            db.publications.insert_one(pub)
        else:
            print(f'publication {pub["title"]} already in database, updating')
            existing_pub = [i for i in pubdict.values() if i['title'] == pub['title']][0]
            updated_pub = existing_pub | pub
            db.publications.update_one({'eid': existing_pub['eid']}, {'$set': updated_pub})


if __name__ == "__main__":

    basedir = '/home/poldrack/Dropbox/Documents/Vita/autoCV'
    paramfile = os.path.join(basedir, 'params.json')
    Entrez.email = 'poldrack@stanford.edu'
    overwrite_db = True
    verbose = True
    update_publications = True
    get_coauthors = True
    add_additional_pubs = True
    # NSF requires all relationships within last 48 months
    authorship_cutoff_years = 4

    # Connect to the MongoDB
    db = setup_db(overwrite=overwrite_db, collections=['metadata', 'publications'])

    # get orcid data and set up researcher object
    r = Researcher(paramfile)
    r.get_orcid_data()
    
    add_researcher_metadata_to_db(r, db)

    # get publications
    linkfile = os.path.join(basedir, 'links.csv')
    links = get_links(linkfile)

    if update_publications or overwrite_db:
        scopus_au = AuthorRetrieval(r.scopus_id)
        scopus_pubs = scopus_au.get_documents(view='COMPLETE')
        print(f'found {len(scopus_pubs)} publications in scopus')
        # check against ORCID records
        orcid_dois = get_dois_from_orcid_record(r.orcid_data)
        print(f'found {len(orcid_dois)} publications in ORCID')

        r.publications = {}
        for pub in scopus_pubs:
            r.publications[pub.eid] = serialize_scopus_doc(pub)

        # clear matching titles - e.g. from a paper later published in a collection
        add_publications_to_db(r.publications, db, links)
        if add_additional_pubs:
            added_pubs = add_additional_pubs_from_file(
                db, os.path.join(basedir, 'additional_pubs.csv'))
        remove_matching_pubs(db)

        scopus_dois = [i['doi'] for i in db.publications.find()]

    r.publications = {i['eid']: i for i in list(db.publications.find())}

    # get coauthors
    if (get_coauthors and r.publications is not None) or overwrite_db:
        if not hasattr(r, 'coauthors'):
            setattr(r, 'coauthors', None)
        r.coauthors = get_coauthors_from_pubs(r.publications, db, r.scopus_id)
        print('found ', len(r.coauthors), ' coauthors')

    # get data that are available in orcid
    education_df = orcid.get_orcid_education(r.orcid_data)
    add_df_to_db(education_df, db, 'education')

    employment_df = orcid.get_orcid_employment(r.orcid_data)
    add_df_to_db(employment_df, db, 'employment')

    distinctions_df = orcid.get_orcid_distinctions(r.orcid_data)
    add_df_to_db(distinctions_df, db, 'distinctions')

    service_df = orcid.get_orcid_service(r.orcid_data)
    add_df_to_db(service_df, db, 'service')

    memberships_df = orcid.get_orcid_memberships(r.orcid_data)
    add_df_to_db(memberships_df, db, 'memberships')

    funding_df = get_funding(basedir) # orcid.get_orcid_funding(r.orcid_data)
    add_df_to_db(funding_df, db, 'funding')

    presentations_df = get_presentations(basedir)
    add_df_to_db(presentations_df, db, 'presentations')

    editorial_df = get_editorial_df(basedir)
    add_df_to_db(editorial_df, db, 'editorial')

    teaching_df = get_teaching_df(basedir)
    add_df_to_db(teaching_df, db, 'teaching')

    conference_df = get_conference_df(basedir)
    add_df_to_db(conference_df, db, 'conferences')

    talks_df = get_talks_df(basedir)
    add_df_to_db(talks_df, db, 'talks')

    trainee_file = os.path.join(os.path.dirname(basedir), 'trainee_history.xlsx')
    trainee_df = pd.read_excel(trainee_file)
    add_df_to_db(trainee_df, db, 'trainees')
