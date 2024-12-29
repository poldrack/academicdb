"""
class for a researcher
"""

import os
import requests
import scholarly
from scholarly import MaxTriesExceededException
import logging
import pandas as pd
from contextlib import suppress
import math
from pybliometrics.scopus import AuthorRetrieval, ScopusSearch
import pybliometrics
from crossref.restful import Works

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from . import orcid, pubmed, utils, query, recordConverter, database


researcher_fields = [
    'scopus_id',
    'orcid_data',
    'dois',
    'pubmed_data',
    'crossref_data',
    'gscholar_data',
    'patent_data',
    'serialized',
    'publications',
]

database_fields = [
    'publications',
    'metadata',
    'teaching',
    'talks',
    'service',
    'memberships',
    'distinctions',
    'education',
    'employment',
    'funding',
    'editorial',
    'conference',
    'coauthors',
]


def get_affiliation(aff):
    if aff.parent_preferred_name is not None:
        return f'{aff.preferred_name}, {aff.parent_preferred_name}, {aff.city}, {aff.country}'
    else:
        return f'{aff.preferred_name}, {aff.city}, {aff.country}'


def process_scopus_record(scopus_record, r):
    if utils.has_skip_strings(scopus_record.title):
        logging.info(
            f'Skipping record with title: {scopus_record.title}'
        )
        return None

    doi = (
        scopus_record.doi
        if scopus_record.doi is not None
        else scopus_record.eid
    )
    if doi is None:
        logging.warning(
            f'Could not get DOI for record {scopus_record.title}'
        )
        return None
    try:
        record = recordConverter.ScopusRecordConverter(
            scopus_record, r.metadata.email
        ).convert()
        if record is None:
            logging.warning(f'Empty record {doi}')
            return None
    except RuntimeError:
        logging.warning(f'Runtime error converting record {doi}')
        return None

    # remove funky _id object that messes with serialization
    if '_id' in record:
        del record['_id']

    # save authors and affiliations from scopus
    try:
        record[
            'author_ids'
        ] = scopus_record.author_ids.split(';')
        record[
            'affiliation_ids'
        ] = scopus_record.author_afids.split(';')
    except AttributeError:
        logging.warning(
            f'Could not get author_ids or affiliation_ids for record {doi}'
        )

    # get pmid and pmcid if available
    record['PMID'] = scopus_record.pubmed_id
    record['PMCID'] = utils.get_pmcid_from_pmid(
        scopus_record.pubmed_id, email=r.metadata.email
    )
    
    # fix date format
    record['publication-date'] = utils.get_valid_date(
        record)

    return record

class ResearcherMetadata:
    def __init__(self):
        fields = [
            'lastname',
            'middlename',
            'firstname',
            'email',
            'orcid',
            'query',
            'url',
            'twitter',
            'github',
            'phone',
            'scholar_id',
            'scopus_id',
            'hindex',
            'address',
        ]
        for field in fields:
            setattr(self, field, None)


class Researcher:
    def __init__(self, param_file, basedir=None):
        pybliometrics.scopus.init()
        self.param_file = param_file
        self.basedir = (
            os.path.dirname(param_file) if basedir is None else basedir
        )

        self.metadata = ResearcherMetadata()
        self.setup_fields()
        self.load_params()

    def setup_fields(self):
        for field in researcher_fields:
            if not hasattr(self, field):
                setattr(self, field, None)

    def load_params(self):
        if os.path.exists(self.param_file):
            with open(self.param_file, 'rb') as f:
                params = tomllib.load(f)
        else:
            raise FileNotFoundError(
                """Please create a TOML file called config.toml
                                       containing the fields email (with your email address), orcid (with your ORCID id)
                                       and query (with your pubmed query)- see documentation for help')
                                       """
            )
        for field, value in params['researcher'].items():
            setattr(self.metadata, field, value)

    def get_orcid_data(self, timeout=60):
        orcid_url = 'https://pub.orcid.org/v3.0/%s' % self.metadata.orcid
        print('using ORCID URL:', orcid_url)
        resp = requests.get(
            orcid_url,
            headers={'Accept': 'application/vnd.orcid+json'},
            timeout=timeout,
        )
        self.orcid_data = resp.json()
        if 'error-code' in self.orcid_data:
            raise ValueError(
                f"problem accessing ORCID: {self.orcid_data['developer-message']}"
            )

    def get_orcid_dois(self):
        if self.orcid_data is None:
            self.get_orcid_data()
        if self.dois is None:
            self.dois = {}
        self.dois['orcid'] = orcid.get_dois_from_orcid_record(self.orcid_data)

    def get_pubmed_data(self):
        self.pubmed_data = pubmed.get_pubmed_data(
            self.metadata.query, self.metadata.email
        )
        print(
            'retrieved %d full pubmed records'
            % len(self.pubmed_data['PubmedArticle'])
        )

    def get_google_scholar_data(self):
        fields_to_keep = [
            'citedby5y',
            'hindex',
            'hindex5y',
            'i10index',
            'i10index5y',
            'cites_per_year',
        ]
        try:
            search_query = scholarly.scholarly.search_author(
                ' '.join([self.metadata.firstname, self.metadata.lastname])
            )
            query_resp = next(search_query)
            self.gscholar_data = scholarly.scholarly.fill(query_resp)
            self.gscholar_data = {
                i: v
                for i, v in self.gscholar_data.items()
                if i in fields_to_keep
            }
        except MaxTriesExceededException:
            print('problem accessing google scholar')

    def get_crossref_data(self):
        works = Works()
        self.crossref_data = []
        print('searching crossref, this might take a few minutes...')
        query_results = works.query(
            author=f'{self.metadata.firstname} {self.metadata.lastname}'
        )

        for result in query_results:
            # drop the references as they clutter things up and we don't use them
            del result['references']
            self.crossref_data.append(result)

    def get_publications(self, maxret=None):
        """
        get publications from scopus/crossref

        Parameters
        ----------
        maxret : int
            maximum number of publications to return
        """
        self.publications = {}
        
        # first look at scopus records
        scopus_records = query.ScopusQuery().author_query(
            self.metadata.scopus_id
        )

        if maxret is not None:
            scopus_records = scopus_records[:maxret]

        for scopus_record in scopus_records:
            record = process_scopus_record(scopus_record, self)
            if record is not None:
                self.publications[record['DOI']] = record


        # check for additional pubmed dois that are not on scopus
        logging.info('checking for additional pubmed dois')
        pubmed_recs = query.PubmedQuery(self.metadata.email).query(
            self.metadata.query
        )
        for rec in pubmed_recs:
            if maxret is not None and len(self.publications) >= maxret:
                break
            p = recordConverter.PubmedRecordConverter(rec).convert()
            if p['DOI'] not in self.publications:
                # first try to use scopus
                scopus_search_result = ScopusSearch(f'DOI({p["DOI"]})')
                if scopus_search_result is not None and scopus_search_result.results is not None and len(scopus_search_result.results) > 0:
                    self.publications[p['DOI']] = process_scopus_record(
                        scopus_search_result.results[0], self
                    )
                    continue
                if 'PMC' in p:
                    p['PMCID'] = p['PMC']
                    del p['PMC']
                logging.info(f"adding additional pubmed record {p['DOI']}")
                self.publications[p['DOI']] = p
                # convert pmid to int
                if p['PMID'] is not None:
                    p['PMID'] = int(p['PMID'])

                try:
                    self.publications[p]['publication-date'] = utils.get_valid_date(
                        self.publications[p['DOI']])
                except TypeError:
                    print('problem with date:', self.publications[p['DOI']])
                    continue

    def get_additional_pubs_from_file(self, pubfile):
        """
        add additional publications from a csv file
        """
        addl_pubs = pd.read_csv(pubfile)
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
            pub['authors_abbrev'] = [
                a.lstrip(' ') for a in pub['authors'].split(',')
            ]
            pub['firstauthor'] = pub['authors_abbrev'][0]
            if pub['type'] == 'book':
                pub['publicationName'] = pub['title']
            else:
                pub['publicationName'] = pub['journal']
            del pub['journal']
            typedict = {
                'journal-article': ('Journal', 'Article'),
                'book': ('Book', 'Book'),
                'book-chapter': ('Book', 'Book Chapter'),
                'proceedings-article': (
                    'Conference Proceeding',
                    'Conference Paper',
                ),
            }
            pub['aggregationType'], pub['subtypeDescription'] = typedict[
                pub['type']
            ]
            pub = utils.remove_nans_from_pub(pub)
            if pub['DOI'] is None:
                pub['DOI'] = f'nodoi_{utils.get_random_hash()}'
            self.publications[pub['DOI']] = pub
            logging.debug(f'added {pub["DOI"]}:{pub["title"]} from file')

    def add_links_to_publications(self, links_file):
        """
        add links to publications from a csv file
        """
        links = pd.read_csv(links_file)
        for i in links.index:
            doi = links.loc[i].DOI
            if doi in self.publications:
                if 'links' not in self.publications[doi]:
                    self.publications[doi]['links'] = {}
                self.publications[doi]['links'][links.loc[i].type] = links.loc[
                    i
                ].url
            else:
                logging.warning(
                    f'Could not find link DOI {links.loc[i].DOI} in publications'
                )

    def get_coauthors(self):

        if self.publications is None:
            logging.warning('No publications found. Cannot get coauthors.')
            return
        self.coauthors = {}
        for doi, pub in self.publications.items():
            if 'scopus_coauthor_ids' in pub:
                for coauthor in pub['scopus_coauthor_ids']:
                    if coauthor not in self.coauthors:
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
                                aff.id
                                for aff in coauthor_info.affiliation_current
                            ]
                        self.coauthors[coauthor] = {
                            'scopus_id': coauthor,
                            'name': coauthor_info.indexed_name,
                            'affiliation': affil,
                            'affiliation_id': affil_id,
                            'dates': [pub['publication-date']],
                            'num_pubs': 1,
                        }
                    else:
                        self.coauthors[coauthor]['num_pubs'] += 1
                        self.coauthors[coauthor]['dates'].append(
                            pub['publication-date']
                        )
                        self.coauthors[coauthor]['dates'].sort()


    def to_database(self, db: database.Database):
        """
        add this researcher record to the database
        """
        for table in database_fields:
            logging.info(f'adding {table} to database')
            if not hasattr(self, table):
                logging.warning(f'No table {table} in researcher')
                continue
            table_value = getattr(self, table)
            if table == 'metadata':
                table_value = [table_value.__dict__]
            elif isinstance(table_value, dict):
                table_value = list(table_value.values())
            if table_value is not None:
                logging.info(
                    f'adding {table} to database ({len(table_value)} records)'
                )
                db.add(table, table_value)
            else:
                logging.warning(f'Table {table} is None')
