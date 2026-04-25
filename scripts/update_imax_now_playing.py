#!/usr/bin/env python3
"""Scrape r/imax's stickied weekly discussion thread and write the headline
film + full slate to static/imax-now-playing.json.

Run weekly via GitHub Actions (.github/workflows/imax-update.yml). The action
commits the updated JSON, Railway redeploys, and the frontend's manual
fallback path serves fresh Reddit-derived data — bypassing the cloud-IP
block that prevents the live Flask scrape from working on Railway.
"""
import json
import re
import sys
from pathlib import Path

import requests


REDDIT_HEADERS = {
    'User-Agent': 'cinedata-app/1.0 (github actions imax updater)',
    'Accept': 'application/json',
}

OUTPUT = Path(__file__).resolve().parent.parent / 'static' / 'imax-now-playing.json'


def scrape():
    r = requests.get(
        'https://www.reddit.com/r/imax/hot.json?limit=10',
        headers=REDDIT_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    posts = r.json().get('data', {}).get('children', []) or []
    for p in posts:
        d = p.get('data', {}) or {}
        if not d.get('stickied'):
            continue
        title = d.get('title', '') or ''
        # Format: "General Discussion Thread - Week of MM-DD-YY - Film1, Film2, ..."
        m = re.search(r'Week of (\d{2})-(\d{2})-(\d{2})\s*[-–—]\s*(.+)$', title)
        if not m:
            continue
        wk_year = 2000 + int(m.group(3))  # 2-digit year -> assume 20xx
        films = [f.strip() for f in m.group(4).split(',') if f.strip()]
        if films:
            return {
                'title': films[0],
                'year': wk_year,
                'films': films,
                'source': 'reddit',
                'sticky_title': title,
            }
    return None


def main():
    payload = scrape()
    if not payload:
        print('Could not find r/imax weekly sticky in hot posts', file=sys.stderr)
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + '\n')
    print(f'Wrote {OUTPUT}')
    print(f'Headline: {payload["title"]}')
    print(f'Slate ({len(payload["films"])}): {", ".join(payload["films"])}')


if __name__ == '__main__':
    main()
