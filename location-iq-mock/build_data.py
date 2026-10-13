"""Builds the data of the LocationIQ mock in data/ (run once, offline from the image build; the output is committed).

    python3 build_data.py

Sources:
- GeoNames (https://www.geonames.org, CC BY 4.0): the cities with more than 15,000 inhabitants (cities15000), the
  first-level administrative divisions (admin1CodesASCII) and the countries (countryInfo), with the names of the
  divisions and countries in other languages (alternateNamesV2).
- OpenStreetMap, through taginfo (https://taginfo.openstreetmap.org, ODbL): the most frequent values of addr:street,
  i.e., the most common street names in the world.
"""
import gzip
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEONAMES = 'https://download.geonames.org/export/dump/'
TAGINFO = 'https://taginfo.openstreetmap.org/api/4/key/values'
STREETS = 3000              # number of street names
USER_AGENT = 'RESTgym LocationIQ mock data build (https://github.com/restgym)'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def build_cities():
    """data/cities.tsv.gz: id, name, ASCII name, alternate names (|-separated), latitude, longitude, country code,
    admin1 code, population, feature code."""
    archive = zipfile.ZipFile(io.BytesIO(fetch(GEONAMES + 'cities15000.zip')))
    lines = archive.read('cities15000.txt').decode('utf-8').splitlines()
    rows = []
    for line in lines:
        f = line.split('\t')
        # Alternate names: only names of places, not codes (e.g., airport codes such as SAO, postal codes) nor URLs
        names = sorted({n for n in f[3].split(',')
                        if len(n) >= 3 and not re.search(r'\d|https?:', n) and not (n.isupper() and len(n) <= 4)}
                       - {f[1], f[2]})
        rows.append('\t'.join([f[0], f[1], f[2], '|'.join(names), f[4], f[5], f[8], f[10], f[14], f[7]]))
    with gzip.open(os.path.join(DATA_DIR, 'cities.tsv.gz'), 'wt', encoding='utf-8', compresslevel=9) as out:
        out.write('\n'.join(rows) + '\n')
    return len(rows)


def alternate_names(geonameids):
    """{geonameid: set of names in other languages} for the given places (alternateNamesV2 of GeoNames, about 200 MB:
    read as a stream). Codes (e.g., of airports), links and postal codes are left out."""
    skip = {'link', 'post', 'iata', 'icao', 'faac', 'tcid', 'unlc', 'wkdt', 'fr_1793'}
    names = {g: set() for g in geonameids}
    path = os.path.join(DATA_DIR, '.alternateNamesV2.zip')
    request = urllib.request.Request(GEONAMES + 'alternateNamesV2.zip', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=600) as response, open(path, 'wb') as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    try:
        with zipfile.ZipFile(path) as archive, archive.open('alternateNamesV2.txt') as f:
            for line in io.TextIOWrapper(f, encoding='utf-8'):
                fields = line.rstrip('\n').split('\t')
                if fields[1] in names and fields[2] not in skip and len(fields[3]) >= 2 and not re.search(r'\d|https?:', fields[3]):
                    names[fields[1]].add(fields[3])
    finally:
        os.remove(path)
    return names


def build_admin1_and_countries():
    """data/admin1.tsv.gz: code (country.admin1), name, ASCII name, other names (|-separated).
    data/countries.tsv.gz: ISO 3166 alpha-2 code, alpha-3 code, name, other names (|-separated)."""
    admin1 = [line.split('\t') for line in fetch(GEONAMES + 'admin1CodesASCII.txt').decode('utf-8').splitlines()]
    countries = [line.split('\t') for line in fetch(GEONAMES + 'countryInfo.txt').decode('utf-8').splitlines()
                 if not line.startswith('#')]
    others = alternate_names({f[3] for f in admin1} | {f[16] for f in countries})
    with gzip.open(os.path.join(DATA_DIR, 'admin1.tsv.gz'), 'wt', encoding='utf-8', compresslevel=9) as out:
        for f in admin1:
            out.write('\t'.join(f[:3] + ['|'.join(sorted(others[f[3]] - {f[1], f[2]}))]) + '\n')
    with gzip.open(os.path.join(DATA_DIR, 'countries.tsv.gz'), 'wt', encoding='utf-8', compresslevel=9) as out:
        for f in countries:
            out.write('\t'.join([f[0], f[1], f[4], '|'.join(sorted(others[f[16]] - {f[4]}))]) + '\n')
    return len(admin1), len(countries)


def build_streets():
    """data/streets.txt: the most frequent street names in OpenStreetMap (one per line, the most frequent first)."""
    names = []
    page = 1
    while len(names) < STREETS:
        query = urllib.parse.urlencode({'key': 'addr:street', 'sortname': 'count', 'sortorder': 'desc',
                                        'page': page, 'rp': 999})
        data = json.loads(fetch(f'{TAGINFO}?{query}'))['data']
        if not data:
            break
        names += [d['value'].strip() for d in data if d['value'].strip() and '\n' not in d['value']]
        page += 1
        time.sleep(1)      # be gentle with taginfo
    with open(os.path.join(DATA_DIR, 'streets.txt'), 'w', encoding='utf-8') as out:
        out.write('\n'.join(names[:STREETS]) + '\n')
    return len(names[:STREETS])


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    print('cities:', build_cities())
    print('admin1, countries:', build_admin1_and_countries())
    print('streets:', build_streets())
