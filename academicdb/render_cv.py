## render as markdown

import pymongo
from poldracklab.utils.run_shell_cmd import run_shell_cmd
import datetime
from utils import escape_characters_for_latex
from contextlib import suppress


def get_education(db):
    education = list(db['education'].find().sort('start_date', pymongo.ASCENDING))
    output = ''
    if education:
        output += """
\\section*{Education and training}
\\noindent
"""
        for e in education:
            output += f"\\textit{{{e['start_date']}-{e['end_date']}}}: {e['degree']}, {e['institution']}, {e['city']}\n\n"
    return output


def get_employment(db):
    employment = list(db['employment'].find().sort('start_date', pymongo.DESCENDING))
    output = ''
    if employment:
        output += """
\\section*{Employment and professional aﬀiliations}
\\noindent
"""
        for e in employment:
            output += f"\\textit{{{e['start_date']}-{e['end_date']}}}: {e['role']} ({e['dept']}), {e['institution']}\n\n"
    return output

def get_distinctions(db):
    distinctions = list(db['distinctions'].find().sort('start_date', pymongo.DESCENDING))
    output = ''
    if distinctions:
        output += """
\\section*{Honors and Awards}
\\noindent
"""
        for e in distinctions:
            output += f"\\textit{{{e['start_date']}}}: {e['title']}, {e['organization']}\n\n"
    return output


def get_editorial(db):
    roles = [
        'Founding Co-Editor-in-Chief',
        'Associate Editor',
        'Contributing Editor',
        'Handling Editor (ad hoc) ',
        'Editorial board ',]
    editorial = list(db['editorial'].find().sort('role', pymongo.DESCENDING))
    output = """
\\section*{Editorial duties}
\\noindent
"""
    if editorial:
        for role in roles:
            role_entries = [e for e in editorial if e['role'] == role]
            if role_entries:
                output += f"\\textit{{{role}}}: "
                journals = []
                for entry in role_entries:
                    journals.append(entry['journal'])
                output += f"{', '.join(journals)}\n\n"
    return output


def get_service(db):
    service = list(db['service'].find().sort('start_date', pymongo.DESCENDING))
    output = ''
    if service:
        output += """
\\section*{Service}
\\noindent
"""
        for e in service:
            output += f"{e['role']}, {e['organization']}, {e['start_date']}-{e['end_date']}\n\n"
    return output


def get_memberships(db):
    memberships = list(db['memberships'].find().sort('start_date', pymongo.DESCENDING))
    output = ''
    if memberships:
        output += """
\\section*{Professional societies}
\\noindent
"""
        orgs = [e['organization'] for e in memberships]
    return output + ', '.join(orgs) + '\n\n'


def get_teaching(db):
    teaching = list(db['teaching'].find())
    output = ''
    if teaching:
        output += """
\\section*{Teaching}
\\noindent
"""
    for level in ['Undergraduate', 'Graduate']:
        level_entries = [e for e in teaching if e['type'] == level]
        if level_entries:
            output += f"\\textit{{{level}}}: "
            courses = []
            for entry in level_entries:
                courses.append(entry['name'])
            output += f"{', '.join(courses)}\n\n"
    return output

def get_funding(db):
    "TODO: need to figure out role, is not currenlty returned by orcid api"
    current_year = datetime.datetime.now().year
    funding = list(db['funding'].find().sort('start_date', pymongo.DESCENDING))
    active_funding = [f for f in funding if int(f['end_date']) >= current_year]
    completed_funding = [f for f in funding if int(f['end_date']) < current_year]

    output = ''
    if funding:
        output += """
\\section*{Research funding}
\\noindent

\\subsection*{Active:}
"""
        for e in active_funding:
            output += f"{e['role']}, {e['organization']}, {e['start_date']}-{e['end_date']}\n\n"
    return output


def get_publication_years(publications):
    years = list(set([int(i['coverDate'].split('-')[0]) for i in publications]))
    years.sort(reverse=True)
    return years


def mk_author_string(authors, maxlen=10, n_to_show=3):
    authors = [i.lstrip(' ').rstrip(' ') for i in authors]
    if len(authors) > maxlen:
        return(', '.join(authors[:n_to_show]) + ' et al.')
    else:
        return ', '.join(authors) + '. '


def get_publication_outlet(pub):
    """
    format the publication outlet string based on the publication type
    """
    volstring, pagestring, pubstring = '', '', ''
    if pub['aggregationType'] in ['Conference Proceeding', 'Journal', 'Book Series']:
        if pub['volume'] is not None:
            volstring = f", {pub['volume']}"
        if pub['pageRange'] is not None:
            pagestring = f", {pub['pageRange']}"
        elif 'article_number' in pub and pub['article_number'] is not None:
            pagestring = f", {pub['article_number']}"
        return f" \\textit{{{pub['publicationName']}{volstring}}}{pagestring}. "
    elif pub['aggregationType'] == 'Book' and pub['subtypeDescription'] in ['Editorial', 'Book Chapter']:
        if pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        if pub['pageRange'] is not None:
            pagestring = f", {pub['pageRange']}"
        return f" In \\textit{{{pub['publicationName']}{volstring}}}{pagestring}. "
    elif pub['aggregationType'] == 'Book' and pub['subtypeDescription'] == 'Book':
        if 'publisher' in pub and pub['publisher'] is not None:
            pubstring = f"{pub['publisher']}"
        if pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        return f" \\textit{{{pub['publicationName']}}}{volstring}. {pubstring}."
    else:
        return f"\\textbf{{TBD{pub['aggregationType']}}}"


def format_publication(pub, debug=False):
    output = ''
    if debug:
        output += f"\\textbf{{{pub['eid']}}}\n"
    output += mk_author_string(pub['authors_abbrev'])
    output += f" ({pub['coverDate'].split('-')[0]}). "

    if not pub['subtypeDescription'] == 'Book':
        output += f"{pub['title']}."
    output += get_publication_outlet(pub)
    with suppress(KeyError):
        if pub['PMCID'] is not None:
            output += f"\\href{{https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pub['PMCID']}}}{{OA}} "
        elif pub['freetoread'] is not None and pub['freetoread'] in ['publisherhybridgold', 'publisherfree2read']:
            output += f"\\href{{https://doi.org/{pub['doi']}}}{{OA}} "
    if pub['doi'] is not None:
        output += f"\\href{{https://doi.org/{pub['doi']}}}{{DOI}} "
    if 'Data' in pub and pub['Data'] is not None:
        output += f"\\href{{{pub['Data']}}}{{Data}} "
    if 'Code' in pub and pub['Code'] is not None:
        output += f"\\href{{{pub['Code']}}}{{Code}} "
    if 'OSF' in pub and pub['OSF'] is not None:
        output += f"\\href{{{pub['OSF']}}}{{OSF}} "

    output += '\n\n'
    return output



def get_publications(db):
    publications = list(db['publications'].find())
    years = get_publication_years(publications)
    output = ''
    if publications:
        output += """
\\section*{Publications}
\\noindent
"""

    for year in years:
        year_pubs = list(db['publications'].find({'coverDate': {'$regex': f'^{year}'}}).sort("firstauthor", pymongo.ASCENDING))
        output += f"\\subsection*{{{year}}}"
        for pub in year_pubs:
            if 'Corrigendum' in pub['title']:
                continue
            pub = escape_characters_for_latex(pub)
            # output += f"\\textit{{{pub['eid'].replace('_','-')}}} "
            output += format_publication(pub)

    return output

if __name__ == "__main__":
    client = pymongo.MongoClient('localhost', 27017)
    db = client['academicdb']

    outfile = 'cv.tex'

    collection = db['academicdb']
    for doc in collection.find():
        print(doc)

    metadata = list(db['metadata'].find())
    assert len(metadata) == 1, "There should be only one metadata document"
    metadata = metadata[0]

    with open('latex_header.tex', 'r') as f:
        doc = f.read()
    
    # education
    doc += get_education(db)

    doc += get_employment(db)

    doc += get_distinctions(db)

    # todo: editorial
    doc += get_editorial(db)

    doc += get_memberships(db)

    doc += get_service(db)

    # todo: funding

    # todo: teaching - need to populate database

    doc += get_teaching(db)

    doc += get_publications(db)

    with open('latex_footer.tex', 'r') as f:
        doc += f.read()

    # write to file
    with open(outfile, 'w') as f:
        f.write(doc)

    # render latex
    result = run_shell_cmd(f"xelatex -halt-on-error {outfile}")
    success = False
    for line in result[0]:
        if line.find("Output written on") > -1:
            success = True
    if not success:
        raise RuntimeError("Latex failed to compile")
    else:
        print("Latex compiled successfully")