"""
CV renderer service for Django web interface
Adapted from src/academicdb/render_cv.py to work with Django models
"""

import datetime
import os
import tempfile
import subprocess
from contextlib import suppress
from django.conf import settings
from django.template.loader import get_template
from django.templatetags.static import static
from django.contrib.staticfiles.finders import find
from .models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity


def escape_characters_for_latex(data):
    """
    Escape special characters for LaTeX
    Handles both strings and dictionaries
    """
    if isinstance(data, str):
        # Escape LaTeX special characters
        latex_chars = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
        }
        result = data
        for char, escaped in latex_chars.items():
            result = result.replace(char, escaped)
        return result
    elif isinstance(data, dict):
        return {key: escape_characters_for_latex(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [escape_characters_for_latex(item) for item in data]
    else:
        return data


def get_education(user):
    """Get education data for CV from ProfessionalActivity model"""
    education = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type='education'
    ).order_by('-start_date')

    output = ''
    if education.exists():
        output += """
\\section*{Education and training}
\\noindent
"""
        for e in education:
            # Format dates properly
            start_year = e.start_date.year if e.start_date else ''
            if e.end_date:
                end_year = e.end_date.year
                date_range = f"{start_year}-{end_year}" if start_year else str(end_year)
            elif e.is_current:
                date_range = f"{start_year}-Present" if start_year else 'Present'
            else:
                date_range = str(start_year) if start_year else 'Unknown'

            # Format location
            location = f"{e.city}, {e.country}" if e.city and e.country else e.organization
            output += f"\\textit{{{date_range}}}: {e.title}, {e.organization}, {location}\n\n"
    return output


def get_employment(user):
    """Get employment data for CV from ProfessionalActivity model"""
    employment = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type='employment'
    ).order_by('-start_date')

    output = ''
    if employment.exists():
        output += """
\\section*{Employment and professional affiliations}
\\noindent
"""
        for e in employment:
            # Format dates properly
            start_year = e.start_date.year if e.start_date else ''
            if e.end_date:
                end_year = e.end_date.year
                date_range = f"{start_year}-{end_year}" if start_year else str(end_year)
            elif e.is_current:
                date_range = f"{start_year}-Present" if start_year else 'Present'
            else:
                date_range = str(start_year) if start_year else 'Unknown'

            dept_string = f" ({e.department})" if e.department else ''
            output += f"\\textit{{{date_range}}}: {e.title}{dept_string}, {e.organization}\n\n"
    return output


def get_distinctions(user):
    """Get distinctions/awards data for CV from ProfessionalActivity model"""
    distinctions = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type='distinction'
    ).order_by('-start_date')

    output = ''
    if distinctions.exists():
        output += """
\\section*{Honors and Awards}
\\noindent
"""
        for e in distinctions:
            # Use start_date for awards, but handle missing dates properly
            if e.start_date:
                date_str = str(e.start_date.year)
            elif e.end_date:
                date_str = str(e.end_date.year)
            else:
                date_str = 'Unknown'
            output += f"\\textit{{{date_str}}}: {e.title}, {e.organization}\n\n"
    return output


def get_memberships(user):
    """Get memberships data for CV from ProfessionalActivity model"""
    memberships = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type='membership'
    ).order_by('organization')

    output = ''
    if memberships.exists():
        output += """
\\section*{Professional societies}
\\noindent
"""
        orgs = [m.organization for m in memberships]
        output += ', '.join(orgs) + '\n\n'
    return output


def get_service(user):
    """Get service data for CV from ProfessionalActivity model"""
    service = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type='service'
    ).order_by('-start_date')

    output = ''
    if service.exists():
        output += """
\\section*{Service}
\\noindent
"""
        for e in service:
            # Format dates properly
            start_year = e.start_date.year if e.start_date else ''
            if e.end_date:
                end_year = e.end_date.year
                date_range = f"{start_year}-{end_year}" if start_year else str(end_year)
            elif e.is_current:
                date_range = f"{start_year}-Present" if start_year else 'Present'
            else:
                date_range = str(start_year) if start_year else 'Unknown'

            output += f"{e.title}, {e.organization}, {date_range}\n\n"
    return output


def get_conference_years(conferences):
    """Get sorted list of conference years"""
    years = list(set([c.year for c in conferences]))
    years.sort(reverse=True)
    return years


def get_conferences(user):
    """Get conference presentations for CV"""
    conferences = Conference.objects.filter(owner=user).order_by('-year', 'month')
    years = get_conference_years(conferences)
    output = ''
    if conferences.exists():
        output += """
\\section*{Conference Presentations}
\\noindent
"""
    for year in years:
        year_talks = conferences.filter(year=year)
        output += f'\\subsection*{{{year}}}'
        for talk in year_talks:
            title = talk.title.rstrip('.').rstrip(' ')
            if title and title[-1] != '?':
                title += '.'
            location = talk.location.rstrip('.').rstrip(' ').rstrip(',')
            month_str = talk.month if talk.month else ''
            output += f"\\textit{{{title}}} {location}, {month_str}.\n\n"
    return output


def get_talks(user):
    """Get invited talks for CV"""
    talks = Talk.objects.filter(owner=user).order_by('-year')
    years = list(set([t.year for t in talks]))
    years.sort(reverse=True)
    output = ''
    if talks.exists():
        output += """
\\section*{Invited addresses and colloquia (* - talks given virtually)}
\\noindent
"""
    for year in years:
        year_talks = talks.filter(year=year)
        output += f'{year}: '
        talk_locations = []
        for talk in year_talks:
            location = talk.place
            if talk.virtual:
                location += '*'
            talk_locations.append(location)
        output += ', '.join(talk_locations) + '\n\n'
    return output


def get_teaching(user):
    """Get teaching data for CV"""
    teaching = Teaching.objects.filter(owner=user).order_by('level', 'name')
    output = ''
    if teaching.exists():
        output += """
\\section*{Teaching}
\\noindent
"""
    for level in ['undergraduate', 'graduate']:
        level_entries = teaching.filter(level=level)
        if level_entries.exists():
            level_display = level.capitalize()
            output += f'\\textit{{{level_display}}}: '
            courses = [entry.name for entry in level_entries]
            output += f"{', '.join(courses)}\\vspace{{2mm}}\n\n"
    return output


def get_funding(user):
    """Get funding data for CV from Funding model"""
    current_year = datetime.datetime.now().year
    funding = Funding.objects.filter(owner=user).order_by('-start_date')

    active_funding = []
    completed_funding = []

    for f in funding:
        fund_data = {
            'role': f.get_role_display(),
            'organization': f.agency,
            'title': f.title,
            'start_date': f.start_date.year if f.start_date else 'Unknown',
            'end_date': f.end_date.year if f.end_date else 'Present',
            'id': f.grant_number or '',
            'url': ''  # Add if URL field exists in model
        }

        if f.end_date and f.end_date.year < current_year:
            completed_funding.append(fund_data)
        else:
            active_funding.append(fund_data)

    output = ''
    if funding.exists():
        output += """
\\section*{Research funding}
\\noindent

\\subsection*{Active:}
"""
        for e in active_funding:
            linkstring = ''
            if e.get('url') and e['url']:
                linkstring = f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
            output += f"{e['role']}, {e['organization'].rstrip(' ')}{linkstring}, {e['title'].capitalize()}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"

        output += '\\subsection*{Completed:}'
        for e in completed_funding:
            linkstring = ''
            if e.get('url') and e['url']:
                linkstring = f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
            output += f"{e['role']}, {e['organization'].rstrip()} {linkstring}, {e['title'].capitalize()}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"
    return output


def get_publication_years(publications):
    """Get sorted list of publication years"""
    years = list(set([p.year for p in publications]))
    years.sort(reverse=True)
    return years


def extract_first_author_lastname(authors):
    """Extract the last name of the first author for sorting purposes"""
    if not authors or len(authors) == 0:
        return 'zzz'  # Sort to end

    first_author = authors[0]
    if isinstance(first_author, dict):
        name = first_author.get('name', '')
    else:
        name = str(first_author)

    if not name:
        return 'zzz'

    # Handle different name formats
    name = name.strip()

    # If name contains comma, assume "Last, First" format
    if ',' in name:
        parts = name.split(',')
        return parts[0].strip().lower()

    # Otherwise handle different formats
    parts = name.split()
    if len(parts) == 0:
        return name.lower()
    elif len(parts) == 1:
        return parts[0].lower()
    elif len(parts) == 2:
        # Could be "First Last" or "Last FI" (like "Poldrack RA")
        first_part = parts[0]
        second_part = parts[1]

        # Check if second part looks like initials (all caps, 1-3 chars)
        if second_part.isupper() and len(second_part) <= 3:
            # This is "Last FI" format
            return first_part.lower()
        else:
            # This is "First Last" format
            return second_part.lower()
    else:
        # Multiple parts - assume last word is surname
        return parts[-1].strip().lower()


def standardize_author_name(name):
    """
    Convert author name to standardized format: LastName, FiMi
    where Fi = First Initial, Mi = Middle Initial
    """
    if not name or not isinstance(name, str):
        return name

    name = name.strip()
    if not name:
        return name

    # Handle different formats
    if ',' in name:
        # Already in "Last, First" format - just need to convert to initials
        parts = name.split(',')
        lastname = parts[0].strip()

        if len(parts) > 1:
            first_part = parts[1].strip()
            # Extract initials from first part
            name_parts = first_part.split()
            initials = ''.join([part[0].upper() for part in name_parts if part])
            return f"{lastname}, {initials}" if initials else lastname
        else:
            return lastname
    else:
        # "First Middle Last" or "Last FI" format
        parts = name.split()
        if len(parts) == 0:
            return name
        elif len(parts) == 1:
            return name  # Single name, can't standardize
        elif len(parts) == 2:
            # Could be "First Last" or "Last FI" (like "Poldrack RA")
            first_part = parts[0]
            second_part = parts[1]

            # Check if second part looks like initials (all caps, 1-3 chars)
            if second_part.isupper() and len(second_part) <= 3:
                # This is "Last FI" format - already in desired format
                return f"{first_part}, {second_part}"
            else:
                # This is "First Last" format
                initials = first_part[0].upper()
                return f"{second_part}, {initials}"
        else:
            # "First Middle Last" format
            lastname = parts[-1]

            # Check if all parts except last look like initials
            first_parts = parts[:-1]
            all_initials = all(len(part) <= 2 and part.isupper() for part in first_parts)

            if all_initials:
                # This is "FI MI Last" format
                initials = ''.join(first_parts)
                return f"{lastname}, {initials}"
            else:
                # This is traditional "First Middle Last" format
                initials = ''.join([part[0].upper() for part in first_parts if part])
                return f"{lastname}, {initials}" if initials else lastname


def mk_author_string(authors, maxlen=10, n_to_show=3):
    """Create author string for publications with standardized formatting"""
    if isinstance(authors, list):
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                name = author.get('name', str(author))
            else:
                name = str(author)

            # Standardize the name format
            standardized_name = standardize_author_name(name.strip())
            author_names.append(standardized_name)

        if len(author_names) > maxlen:
            return ', '.join(author_names[:n_to_show]) + ' et al.'
        else:
            return ', '.join(author_names) + '. '
    else:
        return str(authors) + '. '


def get_publication_outlet(pub_data):
    """Format the publication outlet string based on the publication type"""
    volstring, pagestring, pubstring = '', '', ''

    # Get journal/venue name from publication_name field or metadata
    journal = pub_data.get('journal') or pub_data.get('publication_name', '')
    if journal:
        journal = journal.replace('&amp;', '\\&')

    pub_type = pub_data.get('type') or pub_data.get('publication_type', 'journal-article')

    if pub_type in ['journal-article', 'proceedings-article']:
        volume = pub_data.get('volume')
        page = pub_data.get('page') or pub_data.get('pages')

        if volume:
            volstring = f", {volume}"
        if page:
            pagestring = f", {page}"
        return f" \\textit{{{journal}{volstring}}}{pagestring}. "
    elif pub_type == 'book-chapter':
        volume = pub_data.get('volume')
        page = pub_data.get('page') or pub_data.get('pages')

        if volume:
            volstring = f" (Vol. {volume})"
        if page:
            pagestring = f", {page}"
        return f" In \\textit{{{journal}{volstring}}}{pagestring}. "
    elif pub_type == 'book':
        publisher = pub_data.get('publisher', '')
        volume = pub_data.get('volume')

        if volume:
            volstring = f" (Vol. {volume})"
        if publisher:
            pubstring = f"{publisher}"
        return f" \\textit{{{journal}}}{volstring}. {pubstring}."
    else:
        return f"\\textbf{{TBD{pub_type}}}"


def format_publication(pub, debug=False):
    """Format a single publication for CV"""
    # Convert Django model to dict-like structure
    pub_data = {
        'title': pub.title,
        'year': pub.year,
        'authors': pub.authors,
        'doi': pub.doi,
        'publication_type': pub.publication_type,
        'publication_name': pub.publication_name,
        'metadata': pub.metadata,
        'links': pub.links,
        'identifiers': pub.identifiers,
    }

    # Create formatted citation
    authors_str = mk_author_string(pub.authors)
    outlet_str = get_publication_outlet(pub_data)

    # Build citation
    output = f"{authors_str}({pub.year}). \\textit{{{pub.title}}}.{outlet_str}"

    # Add links and identifiers
    with suppress(KeyError, AttributeError):
        pmcid = pub.identifiers.get('pmcid') or pub.identifiers.get('PMCID')
        if pmcid:
            pmcid = pmcid.replace('PMC', '')
            output += f" \\href{{https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}}}{{OA}}"
        elif pub.metadata.get('freetoread') in ['publisherhybridgold', 'publisherfree2read']:
            output += f" \\href{{https://doi.org/{pub.doi}}}{{OA}}"

    if pub.doi and 'nodoi' not in pub.doi.lower():
        output += f" \\href{{https://doi.org/{pub.doi}}}{{DOI}}"

    # Add additional links
    if pub.links:
        if pub.links.get('Data'):
            output += f" \\href{{{pub.links['Data']}}}{{Data}}"
        if pub.links.get('Code'):
            output += f" \\href{{{pub.links['Code']}}}{{Code}}"
        if pub.links.get('OSF'):
            output += f" \\href{{{pub.links['OSF']}}}{{OSF}}"

    output += '\\vspace{2mm}\n\n'
    return output


def get_publications(user, exclude_dois=None):
    """Get publications data for CV"""
    publications = Publication.objects.filter(
        owner=user,
        is_ignored=False
    ).order_by('-year')

    if exclude_dois:
        publications = publications.exclude(doi__in=exclude_dois)

    years = get_publication_years(publications)
    output = ''
    if publications.exists():
        output += """
\\section*{Publications}
\\noindent
"""

    for year in years:
        year_pubs = list(publications.filter(year=year))

        # Sort by first author's last name within each year
        year_pubs.sort(key=lambda pub: extract_first_author_lastname(pub.authors))

        output += f'\\subsection*{{{year}}}'
        for pub in year_pubs:
            # Skip corrections/errata
            if any(term in pub.title for term in ['Corrigendum', 'Author Correction', 'Erratum']):
                continue

            # Escape LaTeX characters
            pub = escape_characters_for_latex(pub)
            output += format_publication(pub)

    return output


def get_heading(user):
    """Generate CV heading from user profile"""
    # Build address from user profile
    address_lines = []
    if user.institution:
        address_lines.append(user.institution)
    if user.department:
        address_lines.append(user.department)

    # Build address string
    address = ''
    for addr_line in address_lines:
        address += f'{addr_line}\\\\\n'

    # Get name components
    firstname = user.first_name or 'First'
    lastname = user.last_name or 'Last'
    middlename = getattr(user, 'middle_name', '') or 'M'  # Default middle initial

    # Build heading
    heading = f"""
\\reversemarginpar
{{\\LARGE {firstname.capitalize()} {middlename[0].upper()}. {lastname.capitalize()}}}\\\\[4mm]
\\vspace{{-1cm}}

\\begin{{multicols}}{{2}}
{address}
\\columnbreak

email: {user.email} \\\\
"""

    # Add optional fields if available
    if hasattr(user, 'phone') and user.phone:
        heading += f"Phone: {user.phone} \\\\\n"
    if hasattr(user, 'website') and user.website:
        heading += f"url: \\href{{{user.website}}}{{{user.website.replace('https://', '').replace('http://', '')}}} \\\\\n"
    if user.orcid_id:
        heading += f"ORCID: \\href{{https://orcid.org/{user.orcid_id}}}{{{user.orcid_id}}} \\\\\n"

    heading += """\\end{multicols}

\\hrule
"""

    return heading


def get_latex_header():
    """Get LaTeX header content"""
    try:
        header_path = find('academic/latex/header.tex')
        if header_path:
            with open(header_path, 'r', encoding='utf-8') as f:
                return f.read()
    except:
        pass

    # Fallback to reading from source
    try:
        with open('/Users/poldrack/Dropbox/code/academicdb2/src/academicdb/data/latex_header.tex', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        # Ultimate fallback - minimal header
        return """\\documentclass[10pt, letterpaper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\usepackage{geometry}
\\geometry{letterpaper, textwidth=7.25in, textheight=9.5in}
\\usepackage{hyperref}
\\setlength\\parindent{0in}
\\begin{document}
"""


def get_latex_footer():
    """Get LaTeX footer content"""
    try:
        footer_path = find('academic/latex/footer.tex')
        if footer_path:
            with open(footer_path, 'r', encoding='utf-8') as f:
                return f.read()
    except:
        pass

    # Fallback to reading from source
    try:
        with open('/Users/poldrack/Dropbox/code/academicdb2/src/academicdb/data/latex_footer.tex', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        # Ultimate fallback
        return """
\\begin{center}
{\\footnotesize Last updated: \\today — Generated using academicdb
}
\\end{center}

\\end{document}
"""


def generate_cv_latex(user, exclude_dois=None):
    """
    Generate complete LaTeX CV document for a user

    Args:
        user: AcademicUser instance
        exclude_dois: List of DOIs to exclude from publications

    Returns:
        str: Complete LaTeX document
    """
    # Get LaTeX document structure
    header = get_latex_header()
    footer = get_latex_footer()

    # Build document sections
    doc = header
    doc += get_heading(user)
    doc += get_education(user)
    doc += get_employment(user)
    doc += get_distinctions(user)
    doc += get_memberships(user)
    doc += get_service(user)
    doc += get_funding(user)
    doc += get_teaching(user)
    doc += get_publications(user, exclude_dois)
    doc += get_conferences(user)
    doc += get_talks(user)
    doc += footer

    return doc


def compile_latex_to_pdf(latex_content, output_dir=None):
    """
    Compile LaTeX content to PDF using xelatex

    Args:
        latex_content: LaTeX document string
        output_dir: Directory to save files (defaults to temp dir)

    Returns:
        dict: {'success': bool, 'pdf_path': str, 'log': str, 'error': str}
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    # Write LaTeX to file
    tex_path = os.path.join(output_dir, 'cv.tex')
    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(latex_content)

    # Compile with xelatex
    try:
        result = subprocess.run([
            'xelatex',
            '-halt-on-error',
            '-output-directory', output_dir,
            'cv.tex'
        ],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=60
        )

        pdf_path = os.path.join(output_dir, 'cv.pdf')
        success = result.returncode == 0 and os.path.exists(pdf_path)

        return {
            'success': success,
            'pdf_path': pdf_path if success else None,
            'tex_path': tex_path,
            'log': result.stdout,
            'error': result.stderr,
            'output_dir': output_dir
        }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'pdf_path': None,
            'tex_path': tex_path,
            'log': '',
            'error': 'LaTeX compilation timed out',
            'output_dir': output_dir
        }
    except FileNotFoundError:
        return {
            'success': False,
            'pdf_path': None,
            'tex_path': tex_path,
            'log': '',
            'error': 'xelatex not found. Please install LaTeX.',
            'output_dir': output_dir
        }
    except Exception as e:
        return {
            'success': False,
            'pdf_path': None,
            'tex_path': tex_path,
            'log': '',
            'error': f'Compilation error: {str(e)}',
            'output_dir': output_dir
        }