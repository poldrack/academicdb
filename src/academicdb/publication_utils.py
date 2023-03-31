from . import utils


# older stuff below


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
            p.hash = p.hash + utils.get_random_hash(4)
        pubdict[p.hash] = vars(p)
    with open(outfile, 'w') as f:
        json.dump(pubdict, f)
    return pubdict


def shorten_authorlist(authors, maxlen=10, n_to_show=3):
    authors_split = [i.lstrip().rstrip() for i in authors.split(',')]
    if len(authors_split) > maxlen:
        return ', '.join(authors_split[:n_to_show]) + ' et al.'
    else:
        return ', '.join(authors_split)


def load_pubs_from_json(infile):
    pubdict = {}
    with open(infile) as f:
        pubdict = json.load(f)
    return pubdict
