"""Format site publication records as compact Markdown citations."""

MAX_AUTHORS = 20
N_FIRST_AUTHORS = 10
N_LAST_AUTHORS = 1

OSF_PUBLISHER_NAMES = {None, '', 'Center for Open Science'}
VENUE_ALIASES = {'arXiv (Cornell University)': 'arXiv'}


def _initials(given):
    """Return PubMed-style initials and any lowercase particles (e.g. "de")."""
    initials, particles = [], []
    for token in given.replace('.', ' ').split():
        if token.islower():
            particles.append(token)
        else:
            initials.extend(part[0] for part in token.split('-') if part)
    return ''.join(initials), particles


def format_author_name(name):
    """Convert "Last, First Middle" to "Last FM"; leave other formats as is."""
    name = name.strip()
    if ',' not in name:
        return name
    surname, given = (part.strip() for part in name.split(',', 1))
    initials, particles = _initials(given)
    surname = ' '.join(particles + [surname])
    return f'{surname} {initials}' if initials else surname


def format_author_list(names):
    """Join author names, abbreviating lists longer than MAX_AUTHORS."""
    names = [format_author_name(n) for n in names]
    if len(names) > MAX_AUTHORS:
        names = names[:N_FIRST_AUTHORS] + ['...'] + names[-N_LAST_AUTHORS:]
    return ', '.join(names)


def _is_osf_preprint(pub):
    return (
        pub.get('publication_type') == 'preprint'
        and pub.get('publication_name') in OSF_PUBLISHER_NAMES
        and 'osf.io' in (pub.get('doi') or '')
    )


def venue_name(pub):
    """Return a display name for the publication venue."""
    if _is_osf_preprint(pub):
        return 'OSF Preprints'
    name = pub.get('publication_name') or ''
    return VENUE_ALIASES.get(name, name)


def terminate(raw, rendered):
    """Append a period to rendered text unless the raw text already ends in one."""
    return rendered if raw.rstrip().endswith('.') else rendered + '.'


def _title_part(pub):
    title = pub.get('title') or 'Untitled'
    doi = pub.get('doi')
    rendered = f'[{title}](https://doi.org/{doi})' if doi else f'*{title}*'
    return title, rendered


def _venue_part(pub):
    venue = venue_name(pub)
    if venue and pub.get('is_preprint', False):
        venue = f'{venue} (preprint)'
    parts = [venue] if venue else []
    if pub.get('volume'):
        parts.append(f"*{pub['volume']}*")
    if pub.get('page_range'):
        parts.append(pub['page_range'])
    text = ', '.join(parts)
    return text, text


def format_publication(pub):
    """Format a site publication record as a single Markdown citation."""
    names = [a.get('name', '') for a in pub.get('authors') or []]
    authors = format_author_list(names)
    parts = [(authors, authors)] if authors else []
    parts.append(_title_part(pub))
    venue = _venue_part(pub)
    if venue[0]:
        parts.append(venue)
    return ' '.join(terminate(raw, rendered) for raw, rendered in parts)
