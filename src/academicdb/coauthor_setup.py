from utils import load_config
import database
import os
from pybliometrics.scopus import AuthorRetrieval

configdir = os.path.join(os.path.expanduser('~'), '.academicdb')
configfile = os.path.join(configdir, 'config.toml')
dbconfigfile = os.path.join(configdir, 'dbconfig.toml')


def get_affiliation(aff):
    if aff.parent_preferred_name is not None:
        return f'{aff.preferred_name}, {aff.parent_preferred_name}, {aff.city}, {aff.country}'
    else:
        return f'{aff.preferred_name}, {aff.city}, {aff.country}'


def get_coauthors(publications):

    coauthors = {}
    for pub in publications:
        if 'scopus_coauthor_ids' in pub:
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
                        'name': coauthor_info.indexed_name,
                        'affiliation': affil,
                        'affiliation_id': affil_id,
                        'year': pub['year'],
                    }
                else:
                    if pub['year'] > coauthors[coauthor]['year']:
                        coauthors[coauthor]['year'] = pub['year']
    return coauthors


if os.path.exists(configfile):
    config = load_config(configfile)
    assert config['mongo'][
        'CONNECT_STRING'
    ], 'CONNECT_STRING must be specified in dbconfig'
    db = database.Database(
        database.MongoDatabase(
            connect_string=config['mongo']['CONNECT_STRING']
        )
    )
else:
    db = database.Database(database.MongoDatabase(overwrite=False))

publications = db.get_collection('publications')

#coauthors = get_coauthors(publications)

#db.add('coauthors', list(coauthors.values()))

dois = [i['DOI'] for i in publications if i['DOI'].find('nodoi') == -1]
recs = [Works().doi(doi) for doi in dois]
print(len(recs))
goodrecs = [rec for rec in recs if rec is not None]
print(len(goodrecs))

dep_ctr = 0
for rec in goodrecs:
    if 'published' in rec:
        dep_ctr += 1
print(dep_ctr)