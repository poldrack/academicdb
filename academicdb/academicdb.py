import pymongo
import requests
from autocv.orcid import get_dois_from_orcid_record
from autocv.pubmed import get_pubmed_data
from autocv.researcher import Researcher
from bs4 import BeautifulSoup
import urllib.request
import secrets
import autocv.orcid as orcid
from pybliometrics.scopus import AuthorRetrieval


def get_scopus_id_from_orcid(orcid_data):
    # get the scopus id from the orcid record
    for ext_id in orcid_data['person']['external-identifiers']['external-identifier']:
        if ext_id['external-id-type'] == 'Scopus Author ID':
            return ext_id['external-id-value']
    return None


def setup_db(dbname='academicdb', overwrite=False):
    # Connect to the MongoDB
    client = pymongo.MongoClient(port=27017)
    if dbname in client.list_database_names() and not overwrite:
        # check to make sure only one metadata record exists
        if len(list(client[dbname]['metadata'].find())) > 1:
            raise ValueError(
                "more than one metadata record exists in the database - please rerun with overwrite set to True")
        return client[dbname]
    elif dbname in client.list_database_names():
        client.drop_database(dbname)
    return setup_collections(client, dbname)


def setup_collections(client, dbname):
    result = client[dbname]
    result.create_collection('metadata')
    result.metadata.create_index([('orcid', pymongo.ASCENDING)], unique=True)
    result.create_collection('publications')
    result.metadata.create_index([('DOI', pymongo.ASCENDING)], unique=True)

    result.create_collection('authors')
    result.create_collection('funding')
    result.create_collection('conferences')
    result.create_collection('talks')
    result.create_collection('education')
    result.create_collection('employment')
    result.create_collection('distinctions')
    result.create_collection('invited_positions')
    result.create_collection('memberships')
    result.create_collection('service')
    return result


def load_params_from_json(paramfile='params.json'):
    import json
    with open(paramfile, 'r') as f:
        params = json.load(f)
    return params


def add_publications_to_db(pubs, db):
    """
    Insert the records into the database
    - pubs should be a list of dicts
    - db should be a pymongo database object
    - if no DOI is present, a random one will be generated
    """
    newctr = 0
    existctr = 0

    for key, item in pubs.items():
        if 'DOI' not in item:
            if db['publications'].find_one({'title': item['title']}) is not None:
                existing_pub = db['publications'].find_one({'title': item['title']})
                item['DOI'] = existing_pub['DOI']
                print(f'found existing publication by title {item["title"]}')
            else:
                item['DOI'] = f'nodoi_{secrets.token_urlsafe(10)}'
                print(f'no DOI found for {item["title"]}, generating random DOI {item["DOI"]}')
        if not db['publications'].find_one({'DOI': item['DOI']}):
            db['publications'].insert_one(item)
            newctr += 1
        else:
            existctr += 1
    print(f'added {newctr} publications to the database')
    print(f'found {existctr} existing publications in the database')


def add_researcher_metadata_to_db(researcher, db):
    """
    add metadata from params
    - include all string fields from the researcher object
    - if the researcher already exists in the db, update the metadata

    index by orcid
    """
    researcher_md_dict = {
        k: v for k, v in researcher.__dict__.items() if isinstance(v, str) and len(v) > 0}

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


if __name__ == "__main__":

    paramfile = 'params.json'
    overwrite_db = True
    verbose = True
    refresh_publications = False
    get_coauthors = True
    # NSF requires all relationships within last 48 months
    authorship_cutoff_years = 4

    # Connect to the MongoDB
    db = setup_db(overwrite=overwrite_db)

    r = Researcher(paramfile)
    r.get_orcid_data()
    add_researcher_metadata_to_db(r, db)
    r.get_orcid_dois()

    if refresh_publications:
        r.get_pubmed_data() # gets all records from pubmed
        r.make_publication_records()
        r.serialize()
        add_publications_to_db(r.serialized['publications'], db)

    if get_coauthors:
        for pub in db['publications'].find():
            if 'authors' not in pub:
                print("no authors found, skipping")
                continue
            authors = [i.lstrip() for i in pub['authors'].split(',')]
            for author in authors:
                if db.authors.find_one({'name': author}) is None:
                    db.authors.insert_one({'name': author})
