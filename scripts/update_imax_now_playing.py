#!/usr/bin/env python3
"""Scrape r/imax's stickied weekly discussion thread and write the headline
film + full slate to static/imax-now-playing.json.

Run weekly via GitHub Actions (.github/workflows/imax-update.yml). The action
commits the updated JSON, Railway redeploys, and the frontend's manual
fallback path serves fresh Reddit-derived data.

Requires Reddit OAuth (Reddit blocks unauthenticated requests from
datacenter IPs including GitHub Actions runners). Setup:

  1. Create a "script" type Reddit app at https://www.reddit.com/prefs/apps
  2. Add to GitHub repo Secrets (Settings -> Secrets and variables -> Actions):
       REDDIT_CLIENT_ID      = the string under your app name
       REDDIT_CLIENT_SECRET  = the field labeled "secret"

Local testing: set the same env vars in your shell before running.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests


# Reddit's policy requires a UA in the form "platform:app:version (by /u/user)".
USER_AGENT = 'github-actions:cinedata-imax-updater:v1.0 (by /u/andrew-m-vick)'

REDDIT_TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
REDDIT_OAUTH_HOST = 'https://oauth.reddit.com'

OUTPUT = Path(__file__).resolve().parent.parent / 'static' / 'imax-now-playing.json'


def _get_oauth_token():
    """Reddit script-app OAuth, client_credentials grant. Avoids the
    datacenter-IP block that affects unauthenticated calls."""
    cid = os.environ.get('REDDIT_CLIENT_ID')
    csec = os.environ.get('REDDIT_CLIENT_SECRET')
    if not cid or not csec:
        raise RuntimeError(
            'REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set. '
            'See scripts/update_imax_now_playing.py docstring.'
        )
    r = requests.post(
        REDDIT_TOKEN_URL,
        auth=requests.auth.HTTPBasicAuth(cid, csec),
        data={'grant_type': 'client_credentials'},
        headers={'User-Agent': USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    token = r.json().get('access_token')
    if not token:
        raise RuntimeError(f'Reddit token response missing access_token: {r.text[:200]}')
    return token


def scrape():
    token = _get_oauth_token()
    r = requests.get(
        f'{REDDIT_OAUTH_HOST}/r/imax/hot?limit=10',
        headers={
            'User-Agent': USER_AGENT,
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    posts = data.get('data', {}).get('children', []) or []
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
