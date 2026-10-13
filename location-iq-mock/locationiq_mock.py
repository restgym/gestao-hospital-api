"""Mock of the forward geocoding API of LocationIQ (GET /v1/search.php and /v1/search), for Gestão Hospitalar in RESTgym.

    python3 locationiq_mock.py --port 443 --cert certs/server.pem --key certs/server.key --log mock.log

It answers like LocationIQ (as observed on 2026-10-13: bodies, status codes and headers), offline:
- 200 with a JSON array of places for a plausible address, 404 {"error":"Unable to geocode"} otherwise;
- 400 {"error":"Invalid Request"} without q, 401 {"error":"Invalid key"} for an unknown key, 414 (HTML page of nginx)
  for a request line longer than 8 KB;
- 429 {"error":"Rate Limited Second"} beyond the per-second limit of the developer plan (20 requests per second; the
  plan has no per-minute limit, and its daily limit is not simulated);
- every response after 10 ms plus a random jitter of 0-2 ms, as an API reached over the internet.

An address is plausible if it names a known city (GeoNames, more than 15,000 inhabitants), and its other parts are a
street, numbers or postal codes, a region or a country of that city, or (with a street) up to two other parts, such as
the neighborhood. A street is any part with a street type (e.g., Rua, Av., Via, Street, Straße, улица) or one of the
3,000 most frequent street names of OpenStreetMap: it is not checked against the streets of the city. See README.md.
"""
import argparse
import collections
import gzip
import hashlib
import http.server
import json
import math
import os
import random
import re
import ssl
import sys
import threading
import time
import unicodedata
import urllib.parse

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
LICENCE = 'https://locationiq.com/attribution'
DEFAULT_KEYS = ['43b382813d8baa']        # the key in the source code of Gestão Hospitalar
RATE_LIMIT_PER_SECOND = 20                # developer plan of LocationIQ
LATENCY_SECONDS = 0.010                   # fixed latency of each response
JITTER_SECONDS = 0.002                    # plus a random jitter between 0 and this
MAX_REQUEST_LINE = 8192                   # nginx in front of LocationIQ answers 414 beyond it
MAX_RESULTS = 10                          # LocationIQ returns up to 10 places by default
MAX_OTHER_PARTS = 2                       # parts of an address that are not recognized (e.g., neighborhood)

NGINX_414 = ('<html>\r\n<head><title>414 Request-URI Too Large</title></head>\r\n<body>\r\n'
             '<center><h1>414 Request-URI Too Large</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n')

# Street types, normalized (lowercase, without accents), in many languages, with their abbreviations
STREET_TYPES = set('''
street st road rd avenue ave av lane ln drive dr boulevard blvd way court ct place pl square sq terrace highway hwy
parkway pkwy circle cir crescent close row alley path trail
rua r avenida alameda al travessa tv trav praca estrada rodovia rod largo lgo viela beco ladeira passagem servidao
calle c avda paseo pasaje camino carretera plaza pza ronda carrera cra cll diagonal transversal
quadra qd setor conjunto conj bloco lote
via v viale vle piazza p.za corso c.so vicolo strada piazzale lungomare contrada salita
rue chemin allee impasse quai route cours bd
strasse str weg gasse platz allee ring damm chaussee ufer steig
straat laan plein gracht kade singel
ulica ul aleja plac
улица ул проспект пр переулок пер шоссе бульвар площадь набережная проезд тупик
вулиця вул
odos utca ut tér ter katu tie gatan vagen gata vej gade vei
'''.split())
# Endings of street names written as one word (e.g., Hauptstraße, Kalverstraat, Storgatan, 中山路)
STREET_SUFFIXES = ('strasse', 'str', 'weg', 'gasse', 'platz', 'allee', 'ring', 'damm', 'straat', 'laan', 'gracht',
                   'gatan', 'vagen', 'gade', 'vej', 'katu', 'tie', 'utca', '路', '街', '道', '大道', '通り')


def normalize(text):
    """Lowercase, without accents, with punctuation turned into spaces."""
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c)).casefold()
    return ' '.join(re.sub(r'[\W_]+', ' ', text).split())


class Gazetteer:
    """Cities, regions, countries and street names."""

    def __init__(self, data_dir):
        self.cities = {}                                  # id -> dict
        self.city_names = collections.defaultdict(set)    # normalized name -> ids
        with gzip.open(os.path.join(data_dir, 'cities.tsv.gz'), 'rt', encoding='utf-8') as f:
            for line in f:
                gid, name, ascii_name, alternates, lat, lon, cc, admin1, population, feature = line.rstrip('\n').split('\t')
                self.cities[gid] = dict(id=gid, name=name, lat=float(lat), lon=float(lon), country=cc, admin1=admin1,
                                        population=int(population or 0), feature=feature)
                for n in {name, ascii_name, *[a for a in alternates.split('|') if a]}:
                    key = normalize(n)
                    if key:
                        self.city_names[key].add(gid)
        self.admin1 = {}                                  # 'CC.code' -> name
        self.admin1_names = collections.defaultdict(set)  # normalized name -> 'CC.code'
        with gzip.open(os.path.join(data_dir, 'admin1.tsv.gz'), 'rt', encoding='utf-8') as f:
            for line in f:
                code, name, ascii_name, others = line.rstrip('\n').split('\t')
                self.admin1[code] = name
                for n in {name, ascii_name, *[o for o in others.split('|') if o]}:
                    self.admin1_names[normalize(n)].add(code)
        self.countries = {}                               # ISO alpha-2 -> name
        self.country_names = collections.defaultdict(set) # normalized name or code -> ISO alpha-2
        with gzip.open(os.path.join(data_dir, 'countries.tsv.gz'), 'rt', encoding='utf-8') as f:
            for line in f:
                iso2, iso3, name, others = line.rstrip('\n').split('\t')
                self.countries[iso2] = name
                for n in {name, iso3, *[o for o in others.split('|') if o]}:
                    self.country_names[normalize(n)].add(iso2)
        with open(os.path.join(data_dir, 'streets.txt'), encoding='utf-8') as f:
            self.streets = {normalize(line) for line in f if normalize(line)}
        self.max_ngram = 6

    def match(self, tokens, i, names):
        """The longest name of `names` that starts at tokens[i]: (length, ids), or (0, None)."""
        for n in range(min(self.max_ngram, len(tokens) - i), 0, -1):
            ids = names.get(' '.join(tokens[i:i + n]))
            if ids:
                return n, ids
        return 0, None


def is_street_type(token):
    return token in STREET_TYPES or is_street_word(token)


def is_street_word(token):
    """A street name written as one word, with its type as ending (e.g., Hauptstraße, 中山路)."""
    return (len(token) > 4 and token.endswith(STREET_SUFFIXES)) or any(token.endswith(s) for s in ('路', '街', '大道', '通り'))


def is_street(tokens):
    """Whether a part of an address is a street: a type and a name (e.g., "Rua Augusta", "Main Street"), or a street
    name written as one word (e.g., "Hauptstraße 5"). Abbreviations of one or two letters (e.g., R., Av., St) are types
    only before the name (so "AL" of "Montgomery, AL" or "PL" of "Kraków, PL" is not a street)."""
    words = [t for t in tokens if not is_number(t)]
    if any(is_street_word(t) for t in words):
        return True
    if tokens[0] in STREET_TYPES:
        # A type and a name; a full type may also be followed by a number only (e.g., "Quadra 101", "Rua 7")
        return len(words) >= 2 or (len(tokens[0]) > 2 and len(tokens) >= 2)
    return len(words) >= 2 and any(t in STREET_TYPES and len(t) > 2 for t in words[1:])


def is_number(token):
    return any(c.isdigit() for c in token)


def part_words(text, count):
    """The first `count` words of a part of an address, as written (e.g., "Via Roma" of "Via Roma 10 Milano")."""
    return ' '.join(text.split()[:count])


class Geocoder:
    def __init__(self, gazetteer):
        self.g = gazetteer

    def parse(self, query):
        """Splits the address into parts (by commas and dashes between spaces) and classifies them.
        Returns None if the address is not plausible, else a dict describing it."""
        parts = [p.strip() for p in re.split(r'[,;\n]|\s[-–—]\s', query) if p.strip()]
        street = number = postcode = None
        city_parts, countries, admins, others = [], set(), set(), []
        street_tokens = None
        for part in parts:
            tokens = normalize(part).split()
            if not tokens:
                continue
            if street is None and (is_street(tokens) or self._is_street_name(tokens)):
                street, street_tokens = part, tokens
                # The house number is before or after the street name (e.g., "1600 Pennsylvania Avenue", "Via Roma
                # 10"), not inside it (e.g., "Rua 25 de Março")
                number = number or next((t for t in (tokens[-1], tokens[0]) if t.isdigit()), None)
                continue
            explained, part_cities = self._classify(tokens, countries, admins)
            if part_cities and explained:
                city_parts.append(part_cities)
            if not explained:
                others.append(part)
            elif all(is_number(t) for t in tokens):
                # A short number alone is a house number (e.g., "627"), anything else a postal code (e.g., 05652-900)
                if number is None and len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) <= 4:
                    number = part
                else:
                    postcode = postcode or part
        if not city_parts and street_tokens:
            # The city may follow the house number in the street part, without a comma (e.g., "Via Roma 10 Milano")
            for i in range(len(street_tokens) - 1, 1, -1):
                n, ids = self.g.match(street_tokens, i, self.g.city_names)
                if n and street_tokens[i - 1].isdigit() and all(is_number(t) for t in street_tokens[i + n:]):
                    city_parts.append(ids)
                    number = number or street_tokens[i - 1]
                    words = part_words(street, i - 1)
                    street = words or street
                    break
        if not city_parts:
            return None
        if others and (street is None or len(others) > MAX_OTHER_PARTS):
            return None
        candidates = self._choose_city(city_parts, countries, admins)
        if not candidates:
            return None
        candidates.sort(key=lambda c: (-c['population'], c['id']))
        return dict(street=street, number=number, postcode=postcode, others=others, cities=candidates)

    def _choose_city(self, city_parts, countries, admins):
        """The cities of the part that names the city: the last part (the city usually follows the neighborhood)
        whose cities are in the country of the address (if given), preferring those in its region (if given)."""
        best = None
        for ids in reversed(city_parts):
            candidates = [self.g.cities[i] for i in ids]
            if countries:
                candidates = [c for c in candidates if c['country'] in countries]
            if not candidates:
                continue
            in_admin = [c for c in candidates if f"{c['country']}.{c['admin1']}" in admins]
            if in_admin:
                return in_admin
            best = best or candidates
        return best

    def _is_street_name(self, tokens):
        words = [t for t in tokens if not is_number(t)]
        return bool(words) and ' '.join(words) in self.g.streets

    def _classify(self, tokens, countries, admins):
        """Whether every token of a part is a city, region, country, number or abbreviation; and the cities found."""
        i, cities, explained = 0, None, True
        while i < len(tokens):
            n, ids = self.g.match(tokens, i, self.g.city_names)
            if n:
                cities = cities or ids
                # A city may also be a region (e.g., São Paulo): remember it as a region too
                m, codes = self.g.match(tokens, i, self.g.admin1_names)
                if m == n:
                    admins.update(codes)
                i += n
                continue
            n, codes = self.g.match(tokens, i, self.g.admin1_names)
            if n:
                admins.update(codes)
                i += n
                continue
            n, codes = self.g.match(tokens, i, self.g.country_names)
            if n:
                countries.update(codes)
                i += n
                continue
            t = tokens[i]
            if is_number(t) or len(t) <= 2:     # house numbers, postal codes, abbreviations (e.g., SP, NY)
                i += 1
                continue
            explained = False
            i += 1
        return explained, cities

    # ---- Responses in the format of LocationIQ ----

    @staticmethod
    def _hash(*values):
        return int(hashlib.sha256('\x1f'.join(str(v) for v in values).encode()).hexdigest(), 16)

    def _city_extent(self, city):
        """Half-size in degrees of the area of a city (from its population)."""
        return min(0.35, 0.02 + 0.04 * max(0.0, math.log10(max(city['population'], 1)) - 4))

    def _display(self, city):
        names = [city['name']]
        admin = self.g.admin1.get(f"{city['country']}.{city['admin1']}")
        if admin and admin != city['name']:
            names.append(admin)
        names.append(self.g.countries.get(city['country'], city['country']))
        return names

    def address_result(self, parsed):
        """A place at street level: the format of LocationIQ for addresses (without osm_type, osm_id, class, type)."""
        city = parsed['cities'][0]
        h = self._hash(normalize(parsed['street']), parsed['number'] or '', city['id'])
        extent = self._city_extent(city) * 0.6
        angle = (h % 3600) / 3600 * 2 * math.pi
        distance = extent * math.sqrt(((h >> 12) % 10000) / 10000)
        lat = city['lat'] + distance * math.sin(angle)
        lon = city['lon'] + distance * math.cos(angle) / max(0.2, math.cos(math.radians(city['lat'])))
        street = re.sub(r'^\s*\d+[a-zA-Z]?\s+|\s+\d+[a-zA-Z]?\s*$', '', parsed['street']).strip() or parsed['street']
        names = ([parsed['number']] if parsed['number'] else []) + [street] + parsed['others'] + self._display(city)[:-1] \
            + ([parsed['postcode']] if parsed['postcode'] else []) + self._display(city)[-1:]
        lat_s, lon_s = f'{lat:.6f}', f'{lon:.6f}'
        return [collections.OrderedDict([
            ('place_id', str(100000000000 + h % 900000000000)),
            ('licence', LICENCE),
            ('lat', lat_s), ('lon', lon_s),
            ('display_name', ', '.join(names)),
            ('boundingbox', [lat_s, lat_s, lon_s, lon_s]),
            ('importance', 0.25),
        ])]

    def city_results(self, parsed):
        """Places at city level: the format of LocationIQ for administrative boundaries."""
        results = []
        for city in parsed['cities'][:MAX_RESULTS]:
            e = self._city_extent(city)
            ex = e / max(0.2, math.cos(math.radians(city['lat'])))
            importance = round(min(0.85, 0.35 + 0.07 * math.log10(max(city['population'], 1))), 16)
            results.append(collections.OrderedDict([
                ('place_id', str(10000000 + self._hash('place', city['id']) % 90000000)),
                ('licence', LICENCE),
                ('osm_type', 'relation'),
                ('osm_id', str(self._hash('osm', city['id']) % 20000000)),
                ('lat', f"{city['lat']:.7f}"), ('lon', f"{city['lon']:.7f}"),
                ('class', 'boundary'), ('type', 'administrative'),
                ('importance', importance),
                ('display_name', ', '.join(self._display(city))),
                ('boundingbox', [f"{city['lat'] - e:.7f}", f"{city['lat'] + e:.7f}",
                                 f"{city['lon'] - ex:.7f}", f"{city['lon'] + ex:.7f}"]),
            ]))
        return results

    def geocode(self, query):
        parsed = self.parse(query)
        if parsed is None:
            return None
        return self.address_result(parsed) if parsed['street'] else self.city_results(parsed)


def to_json(value):
    """JSON as LocationIQ writes it (PHP json_encode: ASCII with \\u escapes, escaped slashes, no spaces)."""
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).replace('/', '\\/')


class RateLimiter:
    """At most `limit` requests in any second (sliding window)."""

    def __init__(self, limit):
        self.limit, self.times, self.lock = limit, collections.deque(), threading.Lock()

    def allow(self):
        now = time.monotonic()
        with self.lock:
            while self.times and now - self.times[0] >= 1.0:
                self.times.popleft()
            if len(self.times) >= self.limit:
                return False
            self.times.append(now)
            return True


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'cloudflare'
    sys_version = ''

    def version_string(self):
        return 'cloudflare'

    def log_message(self, fmt, *args):         # requests are logged by respond()
        pass

    def send_error(self, code, message=None, explain=None):
        """Errors detected by http.server (e.g., a malformed request, or a request line longer than 64 KB)."""
        self.close_connection = True
        # A request that cannot be parsed is taken as HTTP/0.9, whose responses have no status line nor headers
        self.request_version = 'HTTP/1.1'
        if code == 414:
            return self.respond(414, NGINX_414, 'text/html', query='<request line too long>')
        if not hasattr(self, 'command') or self.command is None:
            self.command = 'GET'
        return self.respond(code, to_json({'error': 'Invalid Request'}), query=f'<{message or code}>')

    def respond(self, status, body, content_type='application/json; charset=UTF-8', query=None):
        time.sleep(LATENCY_SECONDS + random.uniform(0, JITTER_SECONDS))
        data = body.encode('utf-8')
        self.send_response(status, 'Request-URI Too Large' if status == 414 else None)    # as nginx
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        if content_type.startswith('application/json'):
            self.send_header('X-Powered-By', 'LocationIQ')
            self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)
        self.server.log(status, query, body)

    def do_GET(self):
        if len(self.requestline) > MAX_REQUEST_LINE:
            return self.respond(414, NGINX_414, 'text/html', query='<request line of %d bytes>' % len(self.requestline))
        url = urllib.parse.urlsplit(self.path)
        if url.path.rstrip('/') not in ('/v1/search.php', '/v1/search'):
            return self.respond(404, to_json({'error': 'Invalid Request'}), query=self.path[:200])
        params = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        query = params.get('q', [''])[0]
        if params.get('key', [''])[0] not in self.server.keys:
            return self.respond(401, to_json({'error': 'Invalid key'}), query=query)
        if not self.server.rate_limiter.allow():
            return self.respond(429, to_json({'error': 'Rate Limited Second'}), query=query)
        if not query.strip():
            return self.respond(400, to_json({'error': 'Invalid Request'}), query=query)
        results = self.server.geocoder.geocode(query)
        if not results:
            return self.respond(404, to_json({'error': 'Unable to geocode'}), query=query)
        return self.respond(200, to_json(results), query=query)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128
    ssl_context = None              # HTTPS if set
    timeout_seconds = 30            # of the connections of clients that send nothing

    def __init__(self, address, keys, rate_limit, log_file):
        super().__init__(address, Handler)
        self.keys = set(keys)
        self.rate_limiter = RateLimiter(rate_limit)
        self.geocoder = Geocoder(Gazetteer(DATA_DIR))
        self.log_file = log_file
        self.log_lock = threading.Lock()

    def finish_request(self, request, client_address):
        # In the thread of the connection (not in the one that accepts connections), so that a slow or broken TLS
        # handshake delays only its own connection
        request.settimeout(self.timeout_seconds)
        if self.ssl_context:
            try:
                request = self.ssl_context.wrap_socket(request, server_side=True)
            except (OSError, ssl.SSLError):
                return
        super().finish_request(request, client_address)

    def log(self, status, query, body):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {status} q={json.dumps(query, ensure_ascii=False)[:300]} -> {body[:200]}\n"
        with self.log_lock:
            self.log_file.write(line)
            self.log_file.flush()


def main():
    parser = argparse.ArgumentParser(description='Mock of the forward geocoding API of LocationIQ')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=443)
    parser.add_argument('--cert', help='certificate (PEM) for HTTPS; without it, the mock serves plain HTTP')
    parser.add_argument('--key', help='private key (PEM) of the certificate')
    parser.add_argument('--api-key', action='append', dest='api_keys', help='accepted access token (repeatable)')
    parser.add_argument('--rate-limit', type=int, default=RATE_LIMIT_PER_SECOND, help='requests per second')
    parser.add_argument('--log', help='file of the log of the requests (default: standard output)')
    args = parser.parse_args()
    log_file = open(args.log, 'a', encoding='utf-8') if args.log else sys.stdout
    server = Server((args.host, args.port), args.api_keys or DEFAULT_KEYS, args.rate_limit, log_file)
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        server.ssl_context = context
    print(f"LocationIQ mock listening on port {args.port} ({'HTTPS' if args.cert else 'HTTP'}), "
          f"{len(server.geocoder.g.cities)} cities, {len(server.geocoder.g.streets)} street names", flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
