## fix conference file

import pandas as pd

infile = '/home/poldrack/Dropbox/Documents/Vita/autoCV/conference.csv'
outfile = '/home/poldrack/Dropbox/Documents/Vita/autoCV/conference_fixed.csv'

df = pd.read_csv(infile)
df['month'] = None

for i in df.index:
    split_title = df.loc[i, 'location'].rstrip(' ').split(' ')
    df.loc[i, 'month'] = split_title[-1].rstrip('.')
    df.loc[i, 'location'] = ' '.join(split_title[:-1])

df.to_csv(outfile, index=False)
