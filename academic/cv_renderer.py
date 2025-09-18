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
from .models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity, Link


def convert_html_to_latex(text):
    """
    Convert HTML formatting tags to LaTeX commands
    """
    if not isinstance(text, str):
        return text

    import re

    # Convert HTML tags to LaTeX commands
    # Handle italic/emphasis tags
    text = re.sub(r'<i>(.*?)</i>', r'\\textit{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<em>(.*?)</em>', r'\\textit{\1}', text, flags=re.IGNORECASE)

    # Handle bold/strong tags
    text = re.sub(r'<b>(.*?)</b>', r'\\textbf{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<strong>(.*?)</strong>', r'\\textbf{\1}', text, flags=re.IGNORECASE)

    # Handle underline tags
    text = re.sub(r'<u>(.*?)</u>', r'\\underline{\1}', text, flags=re.IGNORECASE)

    # Handle superscript and subscript
    text = re.sub(r'<sup>(.*?)</sup>', r'\\textsuperscript{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<sub>(.*?)</sub>', r'\\textsubscript{\1}', text, flags=re.IGNORECASE)

    # Remove any remaining HTML tags (sanitization)
    text = re.sub(r'<[^>]+>', '', text)

    return text


def escape_characters_for_latex(data):
    """
    Escape special characters for LaTeX
    Handles both strings and dictionaries
    Avoids double-escaping already escaped characters
    """
    if isinstance(data, str):
        import re
        result = data

        # Check if the string appears to already be LaTeX-escaped
        # If it contains escaped characters, don't re-escape
        if ('\\&' in result or '\\%' in result or '\\$' in result or
            '\\#' in result or '\\_' in result or '\\{' in result or
            '\\}' in result or '\\textasciitilde{}' in result or
            '\\textasciicircum{}' in result):
            # String appears to already be escaped, return as-is
            return result

        # Check if string contains LaTeX commands (like \textit{}, \textbf{}, etc.)
        latex_command_pattern = r'\\[a-zA-Z]+\{[^}]*\}'
        if re.search(latex_command_pattern, result):
            # String contains LaTeX commands, use more careful escaping
            # First escape other characters that are NOT part of LaTeX commands
            result = re.sub(r'(?<!\\)&', r'\\&', result)
            result = re.sub(r'(?<!\\)%', r'\\%', result)
            result = re.sub(r'(?<!\\)\$', r'\\$', result)
            result = re.sub(r'(?<!\\)#', r'\\#', result)
            result = re.sub(r'(?<!\\)_', r'\\_', result)

            # For braces, avoid escaping those that are part of LaTeX commands
            # Split the text and process non-command parts
            parts = re.split(r'(\\[a-zA-Z]+\{[^}]*\})', result)
            escaped_parts = []
            for i, part in enumerate(parts):
                if i % 2 == 0:  # Non-command part, escape braces
                    part = re.sub(r'(?<!\\)\{', r'\\{', part)
                    part = re.sub(r'(?<!\\)\}', r'\\}', part)
                # Command parts (odd indices) are left unchanged
                escaped_parts.append(part)
            result = ''.join(escaped_parts)
        else:
            # No LaTeX commands, use normal escaping
            result = re.sub(r'(?<!\\)&', r'\\&', result)
            result = re.sub(r'(?<!\\)%', r'\\%', result)
            result = re.sub(r'(?<!\\)\$', r'\\$', result)
            result = re.sub(r'(?<!\\)#', r'\\#', result)
            result = re.sub(r'(?<!\\)_', r'\\_', result)
            result = re.sub(r'(?<!\\)\{', r'\\{', result)
            result = re.sub(r'(?<!\\)\}', r'\\}', result)

        # Handle ~ and ^ carefully
        result = result.replace('~', r'\textasciitilde{}')
        result = result.replace('^', r'\textasciicircum{}')

        return result
    elif isinstance(data, dict):
        return {key: escape_characters_for_latex(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [escape_characters_for_latex(item) for item in data]
    else:
        return data


def prepare_title_for_latex(title):
    """
    Prepare title for LaTeX by converting HTML tags and escaping characters
    """
    if not title:
        return title

    # First convert HTML tags to LaTeX
    latex_title = convert_html_to_latex(title)

    # Then escape LaTeX special characters
    return escape_characters_for_latex(latex_title)


def get_education(user):
    """Get education data for CV from ProfessionalActivity model"""
    # Include both 'education' and 'qualification' types (e.g., postdoctoral training)
    from django.db.models import Q
    education = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type__in=['education', 'qualification']
    ).order_by('start_date')

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

            # Format location (city and region only, no country)
            location_parts = []
            if e.city:
                location_parts.append(e.city)
            if e.region:
                location_parts.append(e.region)
            location = ", ".join(location_parts) if location_parts else e.organization
            # Escape LaTeX characters
            escaped_title = escape_characters_for_latex(e.title)
            escaped_organization = escape_characters_for_latex(e.organization)
            escaped_location = escape_characters_for_latex(location)
            output += f"\\textit{{{date_range}}}: {escaped_title}, {escaped_organization}, {escaped_location}\n\n"
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

            dept_string = f" ({escape_characters_for_latex(e.department)})" if e.department else ''
            escaped_title = escape_characters_for_latex(e.title)
            escaped_organization = escape_characters_for_latex(e.organization)
            output += f"\\textit{{{date_range}}}: {escaped_title}{dept_string}, {escaped_organization}\n\n"
    return output


def get_distinctions(user):
    """Get distinctions/awards data for CV from ProfessionalActivity model"""
    # Include both 'distinction' and 'invited_position' types for Honors and Awards
    distinctions = ProfessionalActivity.objects.filter(
        owner=user,
        activity_type__in=['distinction', 'invited_position']
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
            escaped_title = escape_characters_for_latex(e.title)
            escaped_organization = escape_characters_for_latex(e.organization)
            output += f"\\textit{{{date_str}}}: {escaped_title}, {escaped_organization}\n\n"
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
        orgs = [escape_characters_for_latex(m.organization) for m in memberships]
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

            escaped_title = escape_characters_for_latex(e.title)
            escaped_organization = escape_characters_for_latex(e.organization)
            output += f"{escaped_title}, {escaped_organization}, {date_range}\n\n"
    return output


def get_conference_years(conferences):
    """Get sorted list of conference years"""
    years = list(set([c.year for c in conferences]))
    years.sort(reverse=True)
    return years


def get_month_number(month_name):
    """Convert month name to numerical representation for sorting"""
    if not month_name:
        return 0

    month_mapping = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12
    }

    return month_mapping.get(month_name.lower(), 0)


def get_conferences(user):
    """Get conference presentations for CV"""
    conferences = Conference.objects.filter(owner=user).order_by('-year')
    years = get_conference_years(conferences)
    output = ''
    if conferences.exists():
        output += """
\\section*{Conference Presentations}
\\noindent
"""
    for year in years:
        year_talks = list(conferences.filter(year=year))
        # Sort by month in reverse chronological order (most recent first)
        year_talks.sort(key=lambda conf: get_month_number(conf.month), reverse=True)
        output += f'\\subsection*{{{year}}}'
        for talk in year_talks:
            title = talk.title.rstrip('.').rstrip(' ')
            if title and title[-1] != '?':
                title += '.'
            location = talk.location.rstrip('.').rstrip(' ').rstrip(',')
            month_str = talk.month if talk.month else ''
            # Escape LaTeX characters
            escaped_title = escape_characters_for_latex(title)
            escaped_location = escape_characters_for_latex(location)
            escaped_month = escape_characters_for_latex(month_str)
            output += f"\\textit{{{escaped_title}}} {escaped_location}, {escaped_month}.\n\n"
    return output


def get_talks(user):
    """Get invited talks for CV"""
    talks = Talk.objects.filter(owner=user).order_by('-year')
    years = list(set([t.year for t in talks]))
    years.sort(reverse=True)
    output = ''
    if talks.exists():
        output += """
\\section*{Invited addresses and colloquia}
\\noindent
"""
    for year in years:
        year_talks = talks.filter(year=year)
        output += f'{year}: '
        talk_locations = []
        for talk in year_talks:
            location = talk.place
            # Note: Talk model doesn't have a virtual field currently
            # Remove the virtual check for now
            escaped_location = escape_characters_for_latex(location)
            talk_locations.append(escaped_location)
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
        # Get all unique levels from the actual teaching entries
        levels = teaching.values_list('level', flat=True).distinct().order_by('level')

        for level in levels:
            level_entries = teaching.filter(level=level)
            if level_entries.exists():
                level_display = level.replace('_', ' ').title()
                output += f'\\textit{{{level_display}}}: '
                courses = [escape_characters_for_latex(entry.name) for entry in level_entries]
                output += f"{', '.join(courses)}\\vspace{{2mm}}\n\n"
    return output


def get_editorial_activities(user):
    """Get editorial activities for CV grouped by role in compact format"""
    from .models import Editorial
    from collections import defaultdict

    editorial_activities = Editorial.objects.filter(owner=user).order_by('role', 'journal')

    if not editorial_activities.exists():
        return ''

    output = """
\\section*{Editorial duties}
\\noindent
"""

    # Group activities by role
    roles_dict = defaultdict(list)
    for activity in editorial_activities:
        # Include dates if present, otherwise just the journal name
        journal = escape_characters_for_latex(activity.journal)
        if activity.dates:
            journal_entry = f"{journal}, {escape_characters_for_latex(activity.dates)}"
        else:
            journal_entry = journal
        roles_dict[activity.role].append(journal_entry)

    # Output in compact format: "Role: journal1, journal2, journal3"
    for role in sorted(roles_dict.keys()):
        role_escaped = escape_characters_for_latex(role)
        journals_list = ', '.join(roles_dict[role])
        output += f"\\textit{{{role_escaped}}}: {journals_list}\n\n"

    return output


def get_funding(user):
    """Get funding data for CV from Funding model"""
    current_year = datetime.datetime.now().year
    funding = Funding.objects.filter(owner=user).order_by('-end_date')

    active_funding = []
    completed_funding = []

    for f in funding:
        # Extract URL from additional_info JSONField
        url = ''
        if f.additional_info and isinstance(f.additional_info, dict):
            url = f.additional_info.get('url', '')

        fund_data = {
            'role': escape_characters_for_latex(f.get_role_display()),
            'organization': escape_characters_for_latex(f.agency),
            'title': escape_characters_for_latex(f.title),
            'start_date': f.start_date.year if f.start_date else 'Unknown',
            'end_date': f.end_date.year if f.end_date else 'Present',
            'id': escape_characters_for_latex(f.grant_number) if f.grant_number else '',
            'url': url
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
            # Build grant number display
            grant_info = ''
            if e['id']:  # grant_number is stored in 'id'
                if e.get('url') and e['url']:
                    # If URL exists, link the grant number
                    grant_info = f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
                else:
                    # If no URL, just show the grant number
                    grant_info = f" {e['id']}"

            output += f"{e['role']}, {e['organization'].rstrip(' ')}{grant_info}, {e['title']}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"

        output += '\\subsection*{Completed:}'
        for e in completed_funding:
            # Build grant number display
            grant_info = ''
            if e['id']:  # grant_number is stored in 'id'
                if e.get('url') and e['url']:
                    # If URL exists, link the grant number
                    grant_info = f" (\\href{{{e['url']}}}{{\\textit{{{e['id']}}}}})"
                else:
                    # If no URL, just show the grant number
                    grant_info = f" {e['id']}"

            output += f"{e['role']}, {e['organization'].rstrip()}{grant_info}, {e['title']}, {e['start_date']}-{e['end_date']}\\vspace{{2mm}}\n\n"
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

            # Standardize the name format and escape LaTeX characters
            standardized_name = standardize_author_name(name.strip())
            escaped_name = escape_characters_for_latex(standardized_name)
            author_names.append(escaped_name)

        if len(author_names) > maxlen:
            return ', '.join(author_names[:n_to_show]) + ' et al.'
        else:
            return ', '.join(author_names) + '. '
    else:
        escaped_authors = escape_characters_for_latex(str(authors))
        return escaped_authors + '. '


def get_preprint_server_name(publication_name):
    """Map preprint publication names to standardized server names"""
    preprint_mapping = {
        'Cold Spring Harbor Laboratory': 'bioRxiv',
        'bioRxiv': 'bioRxiv',
        'medRxiv': 'medRxiv',
        'arXiv': 'arXiv',
        'ChemRxiv': 'ChemRxiv',
        'OSF Preprints': 'OSF Preprints',
        'PsyArXiv': 'PsyArXiv',
        'SocArXiv': 'SocArXiv',
        'EarthArXiv': 'EarthArXiv',
        'Research Square': 'Research Square',
        'SSRN': 'SSRN',
    }

    return preprint_mapping.get(publication_name, publication_name or 'Preprint Server')


def get_publication_outlet(pub_data):
    """Format the publication outlet string based on the publication type"""
    volstring, pagestring, pubstring = '', '', ''

    # Get journal/venue name from publication_name field or metadata
    journal = pub_data.get('journal') or pub_data.get('publication_name', '')
    if journal:
        # Escape LaTeX characters properly instead of just handling &amp;
        journal = escape_characters_for_latex(journal)

    pub_type = pub_data.get('type') or pub_data.get('publication_type', 'journal-article')

    if pub_type in ['journal-article', 'proceedings-article']:
        volume = pub_data.get('volume')
        page = pub_data.get('page') or pub_data.get('pages')

        # Also check in metadata if not found at top level
        if not volume and pub_data.get('metadata'):
            volume = (pub_data['metadata'].get('volume') or
                     (pub_data['metadata'].get('raw_data', {}).get('volume') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None))
        if not page and pub_data.get('metadata'):
            page = (pub_data['metadata'].get('page') or
                   pub_data['metadata'].get('pages') or
                   (pub_data['metadata'].get('raw_data', {}).get('pageRange') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None) or
                   (pub_data['metadata'].get('raw_data', {}).get('page') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None) or
                   (pub_data['metadata'].get('raw_data', {}).get('pages') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None))

        if volume:
            escaped_volume = escape_characters_for_latex(str(volume))
            volstring = f", {escaped_volume}"
        if page:
            escaped_page = escape_characters_for_latex(str(page))
            pagestring = f", {escaped_page}"
        return f" \\textit{{{journal}{volstring}}}{pagestring}. "
    elif pub_type == 'book-chapter':
        volume = pub_data.get('volume')
        page = pub_data.get('page') or pub_data.get('pages')

        # Also check in metadata if not found at top level
        if not volume and pub_data.get('metadata'):
            volume = (pub_data['metadata'].get('volume') or
                     (pub_data['metadata'].get('raw_data', {}).get('volume') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None))
        if not page and pub_data.get('metadata'):
            page = (pub_data['metadata'].get('page') or
                   pub_data['metadata'].get('pages') or
                   (pub_data['metadata'].get('raw_data', {}).get('pageRange') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None) or
                   (pub_data['metadata'].get('raw_data', {}).get('page') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None) or
                   (pub_data['metadata'].get('raw_data', {}).get('pages') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None))

        if volume:
            escaped_volume = escape_characters_for_latex(str(volume))
            volstring = f" (Vol. {escaped_volume})"
        if page:
            escaped_page = escape_characters_for_latex(str(page))
            pagestring = f", {escaped_page}"
        return f" In \\textit{{{journal}{volstring}}}{pagestring}. "
    elif pub_type == 'book':
        publisher = pub_data.get('publisher', '')
        volume = pub_data.get('volume')

        # Also check in metadata if not found at top level
        if not publisher and pub_data.get('metadata'):
            publisher = (pub_data['metadata'].get('publisher', '') or
                        (pub_data['metadata'].get('raw_data', {}).get('publisher', '') if isinstance(pub_data['metadata'].get('raw_data'), dict) else ''))
        if not volume and pub_data.get('metadata'):
            volume = (pub_data['metadata'].get('volume') or
                     (pub_data['metadata'].get('raw_data', {}).get('volume') if isinstance(pub_data['metadata'].get('raw_data'), dict) else None))

        if volume:
            escaped_volume = escape_characters_for_latex(str(volume))
            volstring = f" (Vol. {escaped_volume})"
        if publisher:
            escaped_publisher = escape_characters_for_latex(publisher)
            pubstring = f"{escaped_publisher}"
        return f" \\textit{{{journal}}}{volstring}. {pubstring}."
    elif pub_type == 'preprint':
        server_name = get_preprint_server_name(journal)
        escaped_server_name = escape_characters_for_latex(server_name)
        return f" \\textit{{{escaped_server_name} (preprint)}}. "
    elif pub_type == 'conference-paper':
        escaped_journal = escape_characters_for_latex(journal)
        return f" \\textit{{{escaped_journal}}}. "
    else:
        escaped_type = escape_characters_for_latex(pub_type)
        return f"\\textbf{{TBD{escaped_type}}}"


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

    # Add volume and page information, prioritizing first-class fields over metadata
    # First check for first-class fields (added to address page range issue)
    pub_data['volume'] = pub.volume or None
    pub_data['page'] = pub.page_range or None

    # Fall back to metadata if first-class fields are not available
    if not pub_data['volume'] and pub.metadata:
        pub_data['volume'] = (pub.metadata.get('volume') or
                             (pub.metadata.get('raw_data', {}).get('volume') if isinstance(pub.metadata.get('raw_data'), dict) else None))

    if not pub_data['page'] and pub.metadata:
        pub_data['page'] = (pub.metadata.get('page') or
                           pub.metadata.get('pages') or
                           (pub.metadata.get('raw_data', {}).get('pageRange') if isinstance(pub.metadata.get('raw_data'), dict) else None) or
                           (pub.metadata.get('raw_data', {}).get('page') if isinstance(pub.metadata.get('raw_data'), dict) else None) or
                           (pub.metadata.get('raw_data', {}).get('pages') if isinstance(pub.metadata.get('raw_data'), dict) else None))

        # Also map the journal name from metadata if not in publication_name
        if not pub_data['publication_name'] and pub.metadata.get('journal'):
            pub_data['journal'] = pub.metadata.get('journal')
        elif pub_data['publication_name']:
            pub_data['journal'] = pub_data['publication_name']

    # Create formatted citation with escaped content
    authors_str = mk_author_string(pub.authors)
    outlet_str = get_publication_outlet(pub_data)
    escaped_title = prepare_title_for_latex(pub.title)

    # Build citation with proper spacing for et al.
    # Add space before year if authors_str ends with "et al."
    if authors_str.endswith('et al.'):
        output = f"{authors_str} ({pub.year}). {escaped_title}.{outlet_str}"
    else:
        output = f"{authors_str}({pub.year}). {escaped_title}.{outlet_str}"

    # Add links and identifiers (URLs should NOT be escaped for LaTeX)
    with suppress(KeyError, AttributeError):
        pmcid = pub.identifiers.get('pmcid') or pub.identifiers.get('PMCID')
        if pmcid:
            pmcid = pmcid.replace('PMC', '')
            # PMCIDs are numeric, so no escaping needed
            output += f" \\href{{https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}}}{{OA}}"
        elif pub.metadata.get('freetoread') in ['publisherhybridgold', 'publisherfree2read']:
            # DOI URLs should not be escaped
            output += f" \\href{{https://doi.org/{pub.doi}}}{{OA}}"

    if pub.doi and 'nodoi' not in pub.doi.lower():
        # DOI URLs should not be escaped
        output += f" \\href{{https://doi.org/{pub.doi}}}{{DOI}}"

    # Add additional links from Link model (URLs should NOT be escaped for LaTeX)
    links_from_model = Link.get_links_for_publication(pub)
    for link in links_from_model:
        output += f" \\href{{{link.url}}}{{{link.type}}}"

    # Add additional links from publication links field (URLs should NOT be escaped for LaTeX)
    if pub.links:
        if pub.links.get('Data'):
            output += f" \\href{{{pub.links['Data']}}}{{Data}}"
        if pub.links.get('Code'):
            output += f" \\href{{{pub.links['Code']}}}{{Code}}"
        if pub.links.get('OSF'):
            output += f" \\href{{{pub.links['OSF']}}}{{OSF}}"

    output += '\\vspace{2mm}\n\n'
    return output


def get_preprints(user, exclude_dois=None):
    """Get preprints data for CV (separate section)"""
    preprints = Publication.objects.filter(
        owner=user,
        is_ignored=False,
        publication_type='preprint'
    ).order_by('-year')

    if exclude_dois:
        preprints = preprints.exclude(doi__in=exclude_dois)

    # Filter out preprints that have been published
    unpublished_preprints = []
    for preprint in preprints:
        # Use the enhanced detection method from the Publication model
        published_version = Publication.find_published_version_of_preprint(preprint, user)
        if not published_version:
            unpublished_preprints.append(preprint)

    output = ''

    if unpublished_preprints:
        output += """
\\section*{Preprints}
\\noindent
"""
        # Sort preprints by year in reverse chronological order (most recent first)
        unpublished_preprints.sort(key=lambda pub: pub.year, reverse=True)

        for pub in unpublished_preprints:
            # Skip corrections/errata
            if any(term in pub.title for term in ['Corrigendum', 'Author Correction', 'Erratum']):
                continue

            # format_publication handles escaping internally
            output += format_publication(pub)

    return output


def get_publications(user, exclude_dois=None):
    """Get publications data for CV (excluding preprints)"""
    publications = Publication.objects.filter(
        owner=user,
        is_ignored=False
    ).exclude(publication_type='preprint').order_by('-year')

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

            # format_publication handles escaping internally
            output += format_publication(pub)

    return output


def get_heading(user):
    """Generate CV heading from user profile"""
    # Build full address from user profile
    address_lines = []
    if user.department:
        address_lines.append(escape_characters_for_latex(user.department))
    if user.institution:
        address_lines.append(escape_characters_for_latex(user.institution))

    # Add street address if available
    if hasattr(user, 'address1') and user.address1:
        address_lines.append(escape_characters_for_latex(user.address1))
    if hasattr(user, 'address2') and user.address2:
        address_lines.append(escape_characters_for_latex(user.address2))

    # Add city, state, zip if available
    city_state_zip = []
    if hasattr(user, 'city') and user.city:
        city_state_zip.append(escape_characters_for_latex(user.city))
    if hasattr(user, 'state') and user.state:
        city_state_zip.append(escape_characters_for_latex(user.state))
    if hasattr(user, 'zip_code') and user.zip_code:
        city_state_zip.append(escape_characters_for_latex(user.zip_code))

    if city_state_zip:
        address_lines.append(', '.join(city_state_zip))

    # Country is intentionally excluded from CV address per requirements

    # Build address string for first column
    address = ''
    for addr_line in address_lines:
        address += f'{addr_line}\\\\\n'

    # Get name components
    firstname = escape_characters_for_latex(user.first_name or 'First')
    lastname = escape_characters_for_latex(user.last_name or 'Last')
    middlename = escape_characters_for_latex(user.middle_name or '')

    # Build name string with proper middle name/initial handling
    if middlename:
        # If it's just an initial (1 char), use it as is. If longer, use first initial
        middle_part = middlename if len(middlename) == 1 else middlename[0]
        name_string = f"{firstname} {middle_part}. {lastname}"
    else:
        name_string = f"{firstname} {lastname}"

    # Build heading with proper column layout
    heading = f"""
\\reversemarginpar
{{\\LARGE {name_string}}}\\\\[4mm]
\\vspace{{-1cm}}

\\begin{{multicols}}{{2}}
{address}
\\columnbreak

email: {escape_characters_for_latex(user.email)} \\\\
"""

    # Add ORCID (should be in second column with email)
    if user.orcid_id:
        heading += f"ORCID: \\href{{https://orcid.org/{user.orcid_id}}}{{{user.orcid_id}}} \\\\\n"

    # Add phone number if available
    if user.phone:
        heading += f"Phone: {escape_characters_for_latex(user.phone)} \\\\\n"

    # Add websites from the websites JSONField (supporting multiple URLs)
    if user.websites and isinstance(user.websites, list):
        for website_entry in user.websites:
            if isinstance(website_entry, dict) and 'url' in website_entry:
                url = website_entry['url']
                label = website_entry.get('label', 'URL')
                # Remove protocol for display
                display_url = url.replace('https://', '').replace('http://', '')
                heading += f"{escape_characters_for_latex(label)}: \\href{{{url}}}{{{escape_characters_for_latex(display_url)}}} \\\\\n"
            elif isinstance(website_entry, str):
                # Handle simple string URLs for backward compatibility
                display_url = website_entry.replace('https://', '').replace('http://', '')
                heading += f"URL: \\href{{{website_entry}}}{{{escape_characters_for_latex(display_url)}}} \\\\\n"

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


def generate_cv_latex(user, exclude_dois=None, exclude_preprints=False):
    """
    Generate complete LaTeX CV document for a user

    Args:
        user: AcademicUser instance
        exclude_dois: List of DOIs to exclude from publications
        exclude_preprints: Boolean to exclude the preprints section entirely

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
    doc += get_editorial_activities(user)
    doc += get_funding(user)
    doc += get_teaching(user)
    if not exclude_preprints:
        doc += get_preprints(user, exclude_dois)  # Add preprints before publications
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

    # Log the location for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"LaTeX file written to: {tex_path}")

    # Compile with xelatex
    try:
        # Use full path to xelatex to avoid PATH issues in web server context
        xelatex_paths = [
            '/usr/bin/xelatex',             # Linux (texlive-xetex package)
            '/Library/TeX/texbin/xelatex',  # macOS
            '/usr/local/bin/xelatex',       # Linux alternative
            'xelatex'                       # fallback to PATH
        ]

        xelatex_cmd = None
        for path in xelatex_paths:
            if os.path.exists(path) or path == 'xelatex':
                xelatex_cmd = path
                break

        if not xelatex_cmd:
            # Debug: List what's available in common paths
            debug_info = []
            for check_path in ['/usr/bin', '/usr/local/bin', '/Library/TeX/texbin']:
                if os.path.exists(check_path):
                    try:
                        files = [f for f in os.listdir(check_path) if 'tex' in f.lower()]
                        debug_info.append(f"{check_path}: {files}")
                    except:
                        debug_info.append(f"{check_path}: permission denied")
                else:
                    debug_info.append(f"{check_path}: not found")

            return {
                'success': False,
                'pdf_path': None,
                'tex_path': tex_path,
                'log': '',
                'error': f'xelatex not found in standard locations. Debug info: {"; ".join(debug_info)}',
                'output_dir': output_dir
            }

        result = subprocess.run([
            xelatex_cmd,
            '-halt-on-error',
            '-output-directory', output_dir,
            'cv.tex'
        ],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, 'PATH': '/Library/TeX/texbin:/usr/bin:/usr/local/bin:' + os.environ.get('PATH', '')}
        )

        pdf_path = os.path.join(output_dir, 'cv.pdf')
        success = result.returncode == 0 and os.path.exists(pdf_path)

        # Enhanced error reporting
        error_message = result.stderr
        if not success:
            if result.returncode != 0:
                # Include both stdout and stderr for better debugging
                error_details = []
                if result.stderr.strip():
                    error_details.append(f"stderr: {result.stderr.strip()}")
                if result.stdout.strip():
                    error_details.append(f"stdout: {result.stdout.strip()}")

                error_message = f"xelatex failed with return code {result.returncode}. " + "; ".join(error_details) if error_details else "No output captured"
            if not os.path.exists(pdf_path):
                error_message += f" (PDF file not created at {pdf_path})"

        return {
            'success': success,
            'pdf_path': pdf_path if success else None,
            'tex_path': tex_path,
            'log': result.stdout,
            'error': error_message,
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