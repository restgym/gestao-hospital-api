# Mock of LocationIQ for Gestão Hospitalar

Gestão Hospitalar geocodes the address of every new hospital (`POST /v1/hospitais/`) with the forward geocoding API of [LocationIQ](https://locationiq.com), at `https://us1.locationiq.com/v1/search.php`, with a key hard-coded in its source code. The real service rate-limits that key (shared by all the runs of RESTgym), so the results of a run depended on it. In RESTgym, this mock answers in its place, in the container of the API, without changing the API.

## How it is plugged in

- `entrypoint.sh` adds `127.0.0.1 us1.locationiq.com` to `/etc/hosts`, and starts the mock (`locationiq_mock.py`) on port 443 before the API.
- The API calls `https://...`: the Dockerfile creates a private certificate authority, a certificate of `us1.locationiq.com` signed by it (in `certs/`, inside the image only), and adds the authority to the certificates trusted by Java (`cacerts` of the JRE).
- The mock logs every request (time, status, address, beginning of the response) in `logs/location-iq-mock.log` of the results of the run.

## What it answers

As LocationIQ answered in 2026-10 (checked with the key of the API: bodies, status codes and headers `Content-Type: application/json; charset=UTF-8`, `Server: cloudflare`, `X-Powered-By: LocationIQ`, `Access-Control-Allow-Origin: *`), in this order:

| Request | Status | Body |
|---|---|---|
| Request line longer than 8 KB | 414 | The HTML page of nginx (`414 Request-URI Too Large`) |
| Malformed HTTP request | 400 | `{"error":"Invalid Request"}` |
| Path other than `/v1/search.php` or `/v1/search` | 404 | `{"error":"Invalid Request"}` |
| Unknown or missing key | 401 | `{"error":"Invalid key"}` |
| More than 20 requests in a second | 429 | `{"error":"Rate Limited Second"}` |
| Missing or empty `q` | 400 | `{"error":"Invalid Request"}` |
| Address not plausible (see below) | 404 | `{"error":"Unable to geocode"}` |
| Plausible address | 200 | A JSON array of places (see below) |

- **Rate limit**: the per-second limit of the developer plan of LocationIQ, 20 requests per second (sliding window; checked on the pricing page of LocationIQ, 2026-10). The plan has no per-minute limit; its daily limit (25,000 requests) is not simulated.
- **Latency**: every response is sent after 10 ms plus a random jitter between 0 and 2 ms, as by a service over the internet.
- **Places**: with a street, one place at street level, in the format of LocationIQ for addresses (`place_id`, `licence`, `lat`, `lon`, `display_name`, `boundingbox`, `importance: 0.25`, without `osm_type`, `osm_id`, `class`, `type`); without a street, up to 10 places at city level (cities with the name, the most populous first), in the format of LocationIQ for administrative boundaries (with `osm_type: relation`, `class: boundary`, `type: administrative`). As LocationIQ, the JSON is ASCII with escaped slashes (`https:\/\/locationiq.com\/attribution`), and coordinates are strings. The coordinates of a city are those of GeoNames; those of an address are near its city, at a distance and direction derived from the street and the number: the same address always gets the same coordinates.

## Which addresses are plausible

The address is split into parts at commas and at dashes between spaces (e.g., `Av. Albert Einstein, 627 - Jardim Leonor, São Paulo - SP, 05652-900`). It is plausible if:

1. A part names a **known city**: one of the 34,162 cities of GeoNames with more than 15,000 inhabitants, by its name, its ASCII name or one of its names in other languages (e.g., `Roma`, `Rome`, `Firenze`). The city may also follow the house number in the street part, without a comma (e.g., `Via Roma 10 Milano`). If several parts name cities, the city is that of the last one consistent with the country and the region of the address (the city usually follows the neighborhood).
2. The other parts are:
   - a **street**: a part with a street type and a name, in many languages and with abbreviations (e.g., `Rua Augusta`, `R. Campo Verde`, `Av. Paulista`, `Via Roma`, `Main Street`, `Calle Mayor`, `Rue de Rivoli`, `улица Ленина`; a full type may be followed by a number only, e.g., `Quadra 101`), or a word ending like a type (e.g., `Hauptstraße`, `中山路`), or one of the 3,000 most frequent street names of OpenStreetMap (2,987 once names that differ only in case or accents are merged). The street is **not** checked against the streets of the city (e.g., `Peach Tree Road, Roma` is plausible);
   - house numbers and postal codes (any word with a digit), abbreviations of one or two letters (e.g., `SP`, `NY`). Abbreviations of street types of one or two letters (e.g., `R.`, `Av.`, `St`, `Al.`) are types only before the name of the street, so `AL` of `Montgomery, AL` is the state, not a street;
   - regions (first-level divisions of GeoNames) and countries, by any of their names (e.g., `Lombardia`, `España`, `Brasil`, `BRA`). A country excludes the cities of other countries (`Roma, France` is not plausible); a region only prefers its cities;
   - with a street only, up to two other parts (e.g., the neighborhood, `Jardim Leonor`).

So `antiaristocratical`, `{{7*7}}`, `G`, `string` or `Bairro Centro, São Paulo` (no street) are not plausible, while LocationIQ geocodes some of them (e.g., `{{7*7}}`): the mock is stricter, so that the tools must generate realistic addresses. All the addresses of the hospitals that the API creates at startup are plausible.

## Data

In `data/`, built by `build_data.py` (run it again to update them; it needs internet access, not the image):

| File | Content | Source |
|---|---|---|
| `cities.tsv.gz` | The cities with more than 15,000 inhabitants: id, name, ASCII name, other names, coordinates, country, region, population | [GeoNames](https://www.geonames.org) `cities15000` (CC BY 4.0) |
| `admin1.tsv.gz` | The first-level divisions (regions, states): code, name, ASCII name, other names | GeoNames `admin1CodesASCII` and `alternateNamesV2` (CC BY 4.0) |
| `countries.tsv.gz` | The countries: ISO codes, name, other names | GeoNames `countryInfo` and `alternateNamesV2` (CC BY 4.0) |
| `streets.txt` | The 3,000 most frequent street names (values of `addr:street`) | [OpenStreetMap](https://www.openstreetmap.org/copyright) through [taginfo](https://taginfo.openstreetmap.org) (ODbL) |

## Running it outside the container

```bash
python3 locationiq_mock.py --port 8443                    # plain HTTP, log on standard output
curl 'http://localhost:8443/v1/search.php?key=43b382813d8baa&q=Rua+Augusta+500,+S%C3%A3o+Paulo&format=json'
```

Options: `--cert` and `--key` (HTTPS), `--api-key` (accepted keys, default the key of the API), `--rate-limit` (requests per second, default 20), `--log` (log file).
