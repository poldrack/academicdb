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


def get_education(education):
    output = ''
    if education:
        output += """
\\section*{Education and training}
\\noindent
"""
        for e in education:
            output += f"\\textit{{{e['start_date']}-{e['end_date']}}}: {e['degree']}, {e['institution']}, {e['city']}\n\n"
    return output


def get_employment(employment):
    output = ''
    if employment:
        output += """
\\section*{Employment and professional aﬀiliations}
\\noindent
"""
        for e in employment:
            output += f"\\textit{{{e['start_date']}-{e['end_date']}}}: {e['role']} ({e['dept']}), {e['institution']}\n\n"
    return output


def get_distinctions(distinctions):
    output = ''
    if distinctions:
        output += """
\\section*{Honors and Awards}
\\noindent
"""
        for e in distinctions:
            output += f"\\textit{{{e['start_date']}}}: {e['title']}, {e['organization']}\n\n"
    return output


def get_editorial(editorial):
    output = """
\\section*{Editorial duties}
\\noindent
"""
    # do this to keep roles in the same order as in the csv
    roles = []
    for e in editorial:
        if e['role'] not in roles:
            roles.append(e['role'])
    if editorial:
        for role in roles:
            role_entries = [e for e in editorial if e['role'] == role]
            if role_entries:
                output += f'\\textit{{{role}}}: '
                journals = [entry['journal'] for entry in role_entries]
                output += f"{', '.join(journals)}\n\n"
    return output


def get_service(service):
    output = ''
    if service:
        output += """
\\section*{Service}
\\noindent
"""
        for e in service:
            output += f"{e['role']}, {e['organization']}, {e['start_date']}-{e['end_date']}\n\n"
    return output


def get_memberships(memberships):
    output = ''
    if memberships:
        output += """
\\section*{Professional societies}
\\noindent
"""
        orgs = [e['organization'] for e in memberships]
    return output + ', '.join(orgs) + '\n\n'


def get_conference_years(conferences):
    years = list(set([i['year'] for i in conferences]))
    years.sort(reverse=True)
    return years


def get_conferences(conferences):
    years = get_conference_years(conferences)
    output = ''
    if conferences:
        output += """
\\section*{Conference Presentations}
\\noindent
"""
    for year in years:
        year_talks = [i for i in conferences if i['year'] == year]
        # list(db['conferences'].find({'date': {'$regex': f'^{year}'}}).sort("monthnum", pymongo.DESCENDING))
        output += f'\\subsection*{{{year}}}'
        for talk in year_talks:
            title = talk['title'].rstrip('.').rstrip(' ')
            if title[-1] != '?':
                title += '.'
            location = talk['location'].rstrip('.').rstrip(' ').rstrip(',')
            output += f"\\textit{{{title}}} {location}, {talk['month']}.\n\n"
    return output


def get_talks(talks):
    years = list(set([int(i['year']) for i in talks]))
    years.sort(reverse=True)
    output = ''
    if talks:
        output += """
\\section*{Invited addresses and colloquia (* - talks given virtually)}
\\noindent
"""
    for year in years:
        year_talks = [i for i in talks if i['year'] == year]
        # list(db['talks'].find({'year': year}))
        output += f'{year}: '
        talk_locations = [talk['place'] for talk in year_talks]
        output += ', '.join(talk_locations) + '\n\n'
    return output


def get_teaching(teaching):
    output = ''
    if teaching:
        output += """
\\section*{Teaching}
\\noindent
"""
    for level in ['Undergraduate', 'Graduate']:
        level_entries = [e for e in teaching if e['type'] == level]
        if level_entries:
            output += f'\\textit{{{level}}}: '
            courses = [entry['name'] for entry in level_entries]
            output += f"{', '.join(courses)}\\vspace{{2mm}}\n\n"
    return output


def get_funding(funding):
    """use data from file since ORCID doesn't yet show role in API"""
    current_year = datetime.datetime.now().year
    active_funding = [
        remove_nans_from_pub(f)
        for f in funding
        if int(f['end_date']) >= current_year
    ]
    completed_funding = [
        remove_nans_from_pub(f)
        for f in funding
        if int(f['end_date']) < current_year
    ]

    output = ''
    if funding:
        output += """
\\section*{Research funding}
\\noindent

\\subsection*{Active:}
"""
        for e in active_funding:
            linkstring = ''
            if 'url' in e and e['url']:
                linkstring = (
                    f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
                )
            output += f"{e['role']}, {e['organization'].rstrip(' ')}{linkstring}, {e['title'].capitalize()}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"

        output += '\\subsection*{Completed:}'
        for e in completed_funding:
            linkstring = ''
            if 'url' in e and e['url']:
                linkstring = (
                    f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
                )
            output += f"{e['role']}, {e['organization'].rstrip()} {linkstring}, {e['title'].capitalize()}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"
    return output


def get_publication_years(publications):
    years = list(set([i['year'] for i in publications]))
    years.sort(reverse=True)
    return years


def mk_author_string(authors, maxlen=10, n_to_show=3):
    authors = [i.lstrip(' ').rstrip(' ') for i in authors]
    if len(authors) > maxlen:
        return ', '.join(authors[:n_to_show]) + ' et al.'
    else:
        return ', '.join(authors) + '. '


def get_publication_outlet(pub):
    """
    format the publication outlet string based on the publication type
    """
    volstring, pagestring, pubstring = '', '', ''
    if 'journal' in pub:
        pub['journal'] = pub['journal'].replace('&amp;', '\&')
    if pub['type'] in ['journal-article', 'proceedings-article']:
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f", {pub['volume']}"
        if 'page' in pub and pub['page'] is not None:
            pagestring = f", {pub['page']}"
        # elif 'article_number' in pub and pub['article_number'] is not None:
        #    pagestring = f", {pub['article_number']}"
        return f" \\textit{{{pub['journal']}{volstring}}}{pagestring}. "
    elif pub['type'] == 'book-chapter':
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        if 'page' in pub and pub['page'] is not None:
            pagestring = f", {pub['page']}"
        return f" In \\textit{{{pub['journal']}{volstring}}}{pagestring}. "
    elif pub['type'] == 'book':
        if 'publisher' in pub and pub['publisher'] is not None:
            pubstring = f"{pub['publisher']}"
        if 'volume' in pub and pub['volume'] is not None:
            volstring = f" (Vol. {pub['volume']})"
        return f" \\textit{{{pub['journal']}}}{volstring}. {pubstring}."
    else:
        return f"\\textbf{{TBD{pub['type']}}}"


def format_publication(pub, debug=False):
    output = pub['citation']['latex'].lstrip().replace(' &', ' \\&')

    with suppress(KeyError):
        if pub['PMCID'] is not None:
            pub['PMCID'] = pub['PMCID'].replace('PMC', '')
            output += f" \\href{{https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pub['PMCID']}}}{{OA}}"
        elif pub['freetoread'] is not None and pub['freetoread'] in [
            'publisherhybridgold',
            'publisherfree2read',
        ]:
            output += f" \\href{{https://doi.org/{pub['doi']}}}{{OA}}"
    if (
        'DOI' in pub
        and pub['DOI'] is not None
        and pub['DOI'].find('nodoi') == -1
    ):
        output += f" \\href{{https://doi.org/{pub['DOI']}}}{{DOI}}"
    if 'links' in pub:
        if 'Data' in pub['links'] and pub['links']['Data'] is not None:
            output += f" \\href{{{pub['links']['Data']}}}{{Data}}"
        if 'Code' in pub['links'] and pub['links']['Code'] is not None:
            output += f" \\href{{{pub['links']['Code']}}}{{Code}}"
        if 'OSF' in pub['links'] and pub['links']['OSF'] is not None:
            output += f" \\href{{{pub['links']['OSF']}}}{{OSF}}"

    output += '\\vspace{2mm}\n\n'
    return output


def get_publications(publications, exclude_dois=None):
    years = get_publication_years(publications)
    output = ''
    if publications:
        output += """
\\section*{Publications}
\\noindent
"""

    for year in years:
        year_pubs = [i for i in publications if i['year'] == year]
        year_pubs.sort(key=lambda x: x['authors'])
        # list(db['publications'].find({'year': {'$regex': f'^{year}'}}).sort("firstauthor", pymongo.ASCENDING))
        output += f'\\subsection*{{{year}}}'
        for pub in year_pubs:
            if (
                'Corrigendum' in pub['title']
                or 'Author Correction' in pub['title']
                or 'Erratum' in pub['title']
            ):
                continue
            if exclude_dois is not None and pub['doi'] in exclude_dois:
                continue
            pub = escape_characters_for_latex(pub)
            # output += f"\\textit{{{pub['eid'].replace('_','-')}}} "
            output += format_publication(pub)

    return output


def get_heading(metadata):

    address = ''
    for addr_line in metadata['address']:
        address += f'{addr_line}\\\\\n'
    heading = f"""
\\reversemarginpar 
{{\\LARGE {metadata['firstname'].capitalize()} {metadata['middlename'][0].capitalize()}. {metadata['lastname'].capitalize()}}}\\\\[4mm] 
\\vspace{{-1cm}} 

\\begin{{multicols}}{{2}} 
{address}
\\columnbreak 

Phone: {metadata['phone']} \\\\
email: {metadata['email']} \\\\
url: \\href{{{metadata['url']}}}{{{metadata['url'].split("//")[1]}}} \\\\
url: \\href{{{metadata['github']}}}{{{metadata['github'].split("//")[1]}}} \\\\
Twitter: {metadata['twitter']} \\\\
ORCID: \\href{{https://orcid.org/{metadata['orcid']}}}{{{metadata['orcid']}}} \\\\
\\end{{multicols}}

\\hrule
"""

    return heading


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
        '-o', '--outfile', type=str, help='output file stem', default='cv'
    )
    parser.add_argument(
        '--no_render',
        action='store_true',
        help='do not render the output file (only create .tex)',
    )
    return parser.parse_args()


def main():

    args = parse_args()
    print(args)
    logging.info('Running dbbuilder.py')

    # this needs to be configured as package_data
    datadir = 'src/data'

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

    metadata = db.get_collection('metadata')
    assert len(metadata) == 1, 'There should be only one metadata document'
    metadata = metadata[0]

    parsed_twitter_handle = ""
    for char in metadata['twitter']:
        # handle parsing of underscores from twitter handles in latex
        if char == "_":
            parsed_twitter_handle += "\char`" + char
        else:
            parsed_twitter_handle += char
    metadata['twitter'] = parsed_twitter_handle

    header = pkgutil.get_data('academicdb', 'data/latex_header.tex').decode(
        'utf-8'
    )
    footer = pkgutil.get_data('academicdb', 'data/latex_footer.tex').decode(
        'utf-8'
    )

    doc = header

    doc += get_heading(metadata)

    doc += get_education(db.get_collection('education'))

    doc += get_employment(db.get_collection('employment'))

    doc += get_distinctions(db.get_collection('distinctions'))

    doc += get_editorial(db.get_collection('editorial'))

    doc += get_memberships(db.get_collection('memberships'))

    doc += get_service(db.get_collection('service'))

    doc += get_funding(db.get_collection('funding'))

    doc += get_teaching(db.get_collection('teaching'))

    doc += get_publications(
        db.get_collection('publications'),
    )

    doc += get_conferences(db.get_collection('conference'))

    doc += get_talks(db.get_collection('talks'))

    doc += footer

    # write to file
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)
    outfile = os.path.join(args.outdir, f'{args.outfile}.tex')
    with open(outfile, 'w') as f:
        f.write(doc)

    # render latex
    if not args.no_render:
        result = run_shell_cmd(
            f'xelatex -halt-on-error {args.outfile}.tex',
            cwd=args.outdir,
        )
        success = False
        for line in result:
            if hasattr(line, 'decode') and (
                line.decode().find('Output written on') > -1
            ):
                success = True
        if not success:
            raise RuntimeError('Latex failed to compile')
        else:
            print('Latex compiled successfully')
