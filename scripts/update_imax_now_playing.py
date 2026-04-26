#!/usr/bin/env python3
"""Scrape Wikipedia's "List of films released in IMAX" and write the most
recent (already-released) entry to static/imax-now-playing.json.

Run weekly via GitHub Actions (.github/workflows/imax-update.yml).

Wikipedia advantages: no auth, no datacenter-IP block, no rate limit
(unlike Reddit). Trade-off: editors typically update the list 1-2 days
after a new IMAX release, so the headline lags the actual release weekend.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests


WIKI_API = (
    'https://en.wikipedia.org/w/api.php'
    '?action=parse&format=json&prop=wikitext&redirects=1'
    '&page=List_of_films_released_in_IMAX'
)
HEADERS = {'User-Agent': 'cinedata-imax-updater/1.0 (github actions)'}

OUTPUT = Path(__file__).resolve().parent.parent / 'static' / 'imax-now-playing.json'

# Date in dmy plain text e.g. "14 January 2026"
PLAIN_DATE_RE = re.compile(
    r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b'
)
# Wikipedia dts template e.g. "{{#invoke:dts|main|format=dmy|2026|1|23}}"
DTS_RE = re.compile(r'#invoke:dts\|[^}]*?\|(\d{4})\|(\d{1,2})\|(\d{1,2})')

# Italicized linked title: ''[[Article (suffix)|Display]]'' or ''[[Article]]''
TITLE_RE = re.compile(r"''\[\[([^|\]]+?)(?:\|([^\]]+?))?\]\]''")

MONTH_TO_NUM = {m: i for i, m in enumerate(
    ['January','February','March','April','May','June','July','August',
     'September','October','November','December'], start=1)}


def _parse_row_date(row_text):
    """Return a datetime for the first date found in a row's wikitext, or None."""
    m = DTS_RE.search(row_text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = PLAIN_DATE_RE.search(row_text)
    if m:
        try:
            return datetime(int(m.group(3)), MONTH_TO_NUM[m.group(2)], int(m.group(1)))
        except (ValueError, KeyError):
            pass
    return None


def _parse_row_title(row_text):
    m = TITLE_RE.search(row_text)
    if not m:
        return None
    # Display name (after the pipe) takes priority over article name
    return (m.group(2) or m.group(1)).strip()


def scrape():
    r = requests.get(WIKI_API, headers=HEADERS, timeout=15)
    r.raise_for_status()
    wt = r.json()['parse']['wikitext']['*']

    # Split the article into table rows (|-) and look at each.
    # rowspan can carry a date across multiple rows — track the last seen date
    # so a row whose dt cell is empty still gets associated correctly.
    today = datetime.now()
    candidates = []  # (datetime, title)
    last_date = None

    for raw_row in wt.split('|-'):
        title = _parse_row_title(raw_row)
        dt = _parse_row_date(raw_row)
        if dt:
            last_date = dt
        # If this row has a title but no own date, inherit the most recent
        # (handles rowspan'd date cells).
        effective = dt or last_date
        if title and effective and effective <= today:
            candidates.append((effective, title))

    if not candidates:
        return None

    # Most recent release. Tie-break: prefer the row that physically appeared
    # latest in the article (later wikitext usually = later edit / bigger film).
    candidates.sort(key=lambda x: x[0])
    dt, title = candidates[-1]
    return {
        'title': title,
        'year': dt.year,
        'release_date': dt.strftime('%Y-%m-%d'),
        'source': 'wikipedia',
    }


def main():
    payload = scrape()
    if not payload:
        print('Could not extract a recent IMAX film from Wikipedia', file=sys.stderr)
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + '\n')
    print(f'Wrote {OUTPUT}')
    print(f'Headline: {payload["title"]} ({payload["release_date"]})')


if __name__ == '__main__':
    main()
