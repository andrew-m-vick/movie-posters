import os
import json
import time
import re as _re_mod
import requests
from flask import Flask, send_file, send_from_directory, request, jsonify

# Flask serves ./static/ at /static/<filename> automatically
app = Flask(__name__)


@app.route('/')
def index():
    return send_file('index.html')


# Ratings barely move day to day, and every page load asks for the same ~20
# films. Without this the free tier (1,000 req/day) runs out at ~50 visits.
OMDB_TTL_HIT = 24 * 3600
OMDB_TTL_MISS = 3600
OMDB_CACHE_MAX = 2000
_omdb_cache = {}  # key -> (expires_at, payload)


@app.route('/api/omdb')
def omdb_proxy():
    """Proxy OMDb lookups so the API key stays server-side.

    index.html is served byte-for-byte via send_file, so a key embedded
    there would be public. The browser calls this instead and the key
    never leaves Railway. Query params (i, t, y, ...) pass straight through.
    """
    api_key = os.environ.get('OMDB_API_KEY')
    if not api_key:
        return jsonify({'Response': 'False', 'Error': 'OMDB_API_KEY not set on the server'}), 200

    params = dict(request.args.items())
    key = tuple(sorted(params.items()))
    now = time.time()
    cached = _omdb_cache.get(key)
    if cached and cached[0] > now:
        resp = jsonify(cached[1])
        resp.headers['X-Cache'] = 'HIT'
        return resp, 200

    try:
        r = requests.get('https://www.omdbapi.com/', params={**params, 'apikey': api_key}, timeout=8)
        payload = r.json()
    except Exception as e:
        return jsonify({'Response': 'False', 'Error': f'{type(e).__name__}: {str(e)[:120]}'}), 200

    # Cache real answers ("found" or "not found"); never cache key/quota errors.
    err = payload.get('Error', '')
    if payload.get('Response') == 'True' or 'not found' in err.lower():
        if len(_omdb_cache) >= OMDB_CACHE_MAX:
            for k in sorted(_omdb_cache, key=lambda k: _omdb_cache[k][0])[:OMDB_CACHE_MAX // 10]:
                del _omdb_cache[k]
        # New releases often exist in OMDb before their scores do; re-check
        # those hourly so ratings appear soon after OMDb adds them.
        rated = payload.get('Response') == 'True' and (
            payload.get('imdbRating', 'N/A') != 'N/A' or payload.get('Ratings'))
        ttl = OMDB_TTL_HIT if rated else OMDB_TTL_MISS
        _omdb_cache[key] = (now + ttl, payload)

    resp = jsonify(payload)
    resp.headers['X-Cache'] = 'MISS'
    return resp, 200


@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory('static', 'apple-touch-icon.png')


@app.route('/sw.js')
def service_worker():
    # A worker's scope is capped at its own path, so it must be served from
    # the root to control the app; from /static/ it only ever covered /static/*.
    resp = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ─── Recommender endpoint (Groq · GPT-OSS 120B) ───────────────────────────
# Groq retired llama-3.3-70b-versatile on 2026-08-16; gpt-oss-120b is its
# named replacement. Override with the GROQ_MODEL env var.
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'openai/gpt-oss-120b')

RECOMMENDER_SYSTEM = """You are the head programmer at a cinephile repertory theatre. You've seen everything from Tarkovsky to Tsai Ming-liang, know the French extremity movement and second-wave 70s horror, and can recommend a Chantal Akerman film without irony.

The user will describe what they want to watch in their OWN words — free-form, one sentence or a paragraph. Your job has THREE parts:

1. PARSE. Extract every signal from their input: mood, pacing, visual style, anchor films they reference, runtime caps, era restrictions, anti-patterns ("no horror"), emotional needs ("need something gentle"). Read between the lines — "want something for a rainy Sunday" implies contemplative and indoor. Don't ask clarifying questions.

2. REFLECT. Write a one-sentence "interpretation" in their own register — proof you understood. Use their specific language. Example: if they wrote "I felt gutted by Past Lives and want that quiet ache under 2 hours", you might write: "Contemplative-heartbreak mode, Past Lives flavor specifically, sub-120 minutes." Be concrete, not generic.

3. CONSTRAIN. Write down the hard limits they stated or clearly implied, so they can be checked against real film data. Use null (or false / []) when they didn't set one; never invent limits they didn't ask for.
   - year_from / year_to: release-year range, e.g. 1990 and 1999 for "90s movies".
   - max_runtime_min: e.g. 120 for "under 2 hours".
   - family_friendly: true only if kids are watching or they asked for family viewing.
   - include_genres: only if they explicitly named a genre — e.g. ["Crime"] for "crime movies", ["Science Fiction"] for "sci-fi". Each pick must be in at least one. Leave [] for moods or vibes.
   - exclude_genres: genre names they ruled out, e.g. ["Horror"] for "no horror".
   Genre names must come from: Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, War, Western.

4. RECOMMEND exactly 16 films, best fit first. (They are fact-checked afterwards and the first 10 that pass are shown, so every one must be a real, released feature film with its correct original release year and director.)

Recommendation rules:
- FIT BEATS NOVELTY. Every pick must squarely satisfy every stated constraint — era, runtime, audience, genre, mood. A famous film that fits is better than an obscure one that doesn't.
- Within that, lean away from the most obvious picks. If they say "patient dread," don't lead with The Shining — think Under the Skin, Sauvage, Memories of Murder. Mix eras and countries when the request allows it.
- Only recommend films you are certain exist. If unsure of a title, year, or director, leave that film out.
- Each "why" must reference their OWN language in 2–4 sentences. Don't just say "similar tone" — quote their phrase or paraphrase it tightly.
- Write like a friend who actually watched it. No adjective padding.
- Respect runtime ceilings strictly.
- Respect anti-patterns (things they said to avoid).
- Tags: 3–5 concrete descriptors each ("slow-burn", "body horror", "New Hollywood", "neorealism"). Not genres alone — texture words.

Return ONLY valid JSON, no markdown, no preamble:
{
  "interpretation": "one-sentence reflection of their request in their register",
  "constraints": {
    "year_from": null,
    "year_to": null,
    "max_runtime_min": null,
    "family_friendly": false,
    "include_genres": [],
    "exclude_genres": []
  },
  "recommendations": [
    {
      "title": "film title",
      "year": 2013,
      "director": "director name",
      "why": "2-4 sentences; reference their language specifically",
      "tags": ["tag1", "tag2", "tag3"]
    }
  ]
}
"""


# ─── Fact-checking picks against TMDB ──────────────────────────────────────
# The model is good at taste and bad at facts: it misdates films, credits the
# wrong director, invents titles, and drifts outside stated limits ("90s"
# answered with 2004 films). Every pick is looked up on TMDB; missing films are
# dropped, year/director/runtime come from TMDB, and the stated constraints are
# enforced on those real values.
TMDB_KEY = os.environ.get('TMDB_API_KEY', '5257b8de97581229fd5a52d5e61a48ec')
_tmdb = requests.Session()
_NOT_FAMILY = {'R', 'NC-17'}
MIN_VOTES = 25


def _norm_title(t):
    t = (t or '').lower().replace('&', 'and')
    t = _re_mod.sub(r'^(the|a|an)\s+', '', t)
    return _re_mod.sub(r'[^a-z0-9]', '', __import__('unicodedata').normalize('NFKD', t).encode('ascii', 'ignore').decode())


def _tmdb_get(path, **params):
    r = _tmdb.get(f'https://api.themoviedb.org/3{path}', params={'api_key': TMDB_KEY, **params}, timeout=8)
    r.raise_for_status()
    return r.json()


def _verify_pick(rec):
    """Return the pick enriched with TMDB facts, or None if no such film."""
    title, year = str(rec.get('title') or '').strip(), rec.get('year')
    try:
        year = int(str(year)[:4])
    except (TypeError, ValueError):
        year = None
    if not title:
        return None
    try:
        results = _tmdb_get('/search/movie', query=title, include_adult='false').get('results', [])
    except Exception:
        return None
    key = _norm_title(title)
    def score(m):
        names = {_norm_title(m.get('title')), _norm_title(m.get('original_title'))}
        exact = key in names
        y = int((m.get('release_date') or '0')[:4] or 0)
        dy = abs(y - year) if (year and y) else 99
        return (exact, dy <= 1, -dy, m.get('vote_count', 0))
    # Feature films with some audience only: a same-titled obscure film or
    # TV movie is almost never the one the model meant.
    cands = [m for m in results if m.get('release_date') and m.get('vote_count', 0) >= MIN_VOTES]
    if not cands:
        return None
    best = max(cands, key=score)
    exact, close, _, _ = score(best)
    if not exact:
        # Release titles vary ("The Raid: Redemption" is "The Raid" on TMDB;
        # "Hundred-Year-Old" vs "100 Year-Old"): accept a close title only
        # when the year also matches.
        from difflib import SequenceMatcher
        def near(m):
            y = int((m.get('release_date') or '0')[:4] or 0)
            if not (year and y and abs(y - year) <= 1):
                return 0
            n = max((_norm_title(m.get('title')), _norm_title(m.get('original_title'))),
                    key=lambda x: SequenceMatcher(None, key, x).ratio())
            prefix = len(n) >= 4 and (key.startswith(n) or n.startswith(key))
            return max(SequenceMatcher(None, key, n).ratio(), 0.9 if prefix else 0)
        alt = max(cands, key=near)
        if near(alt) < 0.75:
            return None   # no film with this title near this year: hallucinated or misremembered
        best = alt
    elif year and not close:
        return None
    try:
        det = _tmdb_get(f"/movie/{best['id']}", append_to_response='credits,release_dates')
    except Exception:
        return None
    if any(g.get('name') == 'TV Movie' for g in det.get('genres', [])):
        return None
    directors = [c['name'] for c in det.get('credits', {}).get('crew', []) if c.get('job') == 'Director']
    cert = ''
    for rd in det.get('release_dates', {}).get('results', []):
        if rd.get('iso_3166_1') == 'US':
            cert = next((x['certification'] for x in rd.get('release_dates', []) if x.get('certification')), '')
    return {
        **rec,
        'title': det.get('title') or title,
        'year': int(det['release_date'][:4]) if det.get('release_date') else year,
        'director': ', '.join(directors) or rec.get('director'),
        'runtime': det.get('runtime') or None,
        'genres': [g['name'] for g in det.get('genres', [])],
        'certification': cert,
        'tmdb_id': det['id'],
        'poster_path': det.get('poster_path'),
    }


def _misfit(m, c):
    """Why a verified film breaks the request's constraints, or '' if it fits."""
    def num(k):
        try:
            return int(c.get(k)) if c.get(k) not in (None, '', False) else None
        except (TypeError, ValueError):
            return None
    genres = {g.lower() for g in m['genres']}
    if num('year_from') and m['year'] and m['year'] < num('year_from'):
        return f"released {m['year']}, before {num('year_from')}"
    if num('year_to') and m['year'] and m['year'] > num('year_to'):
        return f"released {m['year']}, after {num('year_to')}"
    if num('max_runtime_min') and m['runtime'] and m['runtime'] > num('max_runtime_min'):
        return f"{m['runtime']} min, over {num('max_runtime_min')}"
    if c.get('family_friendly') is True and (m['certification'] in _NOT_FAMILY or 'horror' in genres):
        return f"rated {m['certification'] or 'horror'}, not family-friendly"
    as_list = lambda v: [v] if isinstance(v, str) else [g for g in (v or []) if isinstance(g, str)]
    want = {g.lower() for g in as_list(c.get('include_genres'))}
    if want and not want & genres:
        return f"genres are {', '.join(m['genres']) or 'unknown'}, not {', '.join(as_list(c.get('include_genres')))}"
    banned = {g.lower() for g in as_list(c.get('exclude_genres'))}
    if banned & genres:
        return f"is {', '.join(sorted(banned & genres))}"
    return ''


@app.route('/api/recommend', methods=['POST'])
def recommend():
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return jsonify({'error': 'GROQ_API_KEY environment variable not set on the server'}), 500

    body = request.get_json(silent=True) or {}
    query = (body.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    # Soft cap so the free-tier context stays happy
    if len(query) > 1500:
        query = query[:1500]

    from groq import Groq
    client = Groq(api_key=api_key)
    messages = [
        {'role': 'system', 'content': RECOMMENDER_SYSTEM},
        {'role': 'user',   'content': query},
    ]

    def ask():
        # Groq fails a call two ways that a retry fixes: the free tier's
        # tokens-per-minute 429, and json_validate_failed — the reasoning model
        # occasionally ends with an empty/invalid answer that JSON mode rejects.
        for attempt in (1, 2, 3):
            try:
                response = _create()
                raw = (response.choices[0].message.content or '').strip()
                parsed = json.loads(raw)
                messages.append({'role': 'assistant', 'content': raw})
                return parsed
            except json.JSONDecodeError:
                if attempt == 3:
                    raise
            except Exception as e:
                status = getattr(e, 'status_code', None)
                if attempt == 3 or status not in (429, 400) or (status == 400 and 'json_validate_failed' not in str(e)):
                    raise
                if status == 429:
                    wait = 8.0
                    try:
                        wait = float(e.response.headers.get('retry-after', wait))
                    except Exception:
                        pass
                    time.sleep(min(max(wait, 1.0), 20.0))

    def _create():
        return client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_format={'type': 'json_object'},
            temperature=0.6,
            # Reasoning models spend output tokens thinking; medium effort
            # noticeably cuts factual slips. Leave room for the JSON.
            max_tokens=8192,
            extra_body={'reasoning_effort': 'medium'} if 'gpt-oss' in GROQ_MODEL else None,
        )

    try:
        data = ask()
    except json.JSONDecodeError:
        return jsonify({'error': 'The recommender returned a garbled answer. Try again.'}), 502
    except Exception as e:
        if getattr(e, 'status_code', None) == 429:
            return jsonify({'error': 'The recommender is busy right now (free-tier rate limit). Try again in a minute.'}), 429
        if 'json_validate_failed' in str(e):
            return jsonify({'error': 'The recommender returned a garbled answer. Try again.'}), 502
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 502
    if not isinstance(data, dict):
        return jsonify({'error': 'Model returned an unexpected format. Try again.'}), 502
    try:
        return jsonify(_finish(data, ask, messages))
    except Exception:
        import traceback
        traceback.print_exc()   # shows in Railway logs
        return jsonify({'error': 'Something went wrong checking the picks. Try again.'}), 502


def _finish(data, ask, messages):
    from concurrent.futures import ThreadPoolExecutor
    constraints = data.get('constraints') if isinstance(data.get('constraints'), dict) else {}
    final, seen, rejected, suggested = [], set(), [], 0

    def check(recs):
        nonlocal suggested
        recs = [r for r in (recs or []) if isinstance(r, dict)]
        suggested += len(recs)
        with ThreadPoolExecutor(8) as ex:
            verified = list(ex.map(_verify_pick, recs))
        for rec, m in zip(recs, verified):
            if not m:
                rejected.append(f"{rec.get('title')} ({rec.get('year')}): no such film found")
            elif m['tmdb_id'] in seen:
                continue
            elif (why := _misfit(m, constraints)):
                seen.add(m['tmdb_id'])
                rejected.append(f"{m['title']} ({m['year']}): {why}")
            else:
                seen.add(m['tmdb_id'])
                final.append(m)

    check(data.get('recommendations'))
    if len(final) < 8:
        # One top-up round: say exactly what failed so it can correct course.
        messages.append({'role': 'user', 'content':
            'These picks failed the fact check or broke the request:\n- ' + '\n- '.join(rejected[:20]) +
            '\n\nAlready accepted: ' + '; '.join(f"{m['title']} ({m['year']})" for m in final) +
            f'\n\nGive 12 more different films that are real and meet every constraint. Same JSON format.'})
        try:
            check(ask().get('recommendations'))
        except Exception:
            pass   # keep what already passed

    return {
        'interpretation': data.get('interpretation'),
        'constraints': constraints,
        'recommendations': final[:10],
        'checked': {'suggested': suggested, 'rejected': len(rejected), 'shown': min(len(final), 10)},
    }


@app.route('/api/health/groq', methods=['GET'])
def groq_health():
    """Lightweight Groq reachability check used by the OPS dashboard.
    Uses the Groq SDK's models.list() call — no generation, no tokens
    billed — so it exercises the exact auth + network path that the
    main /api/recommend endpoint uses.
    """
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return jsonify({'status': 'no-key', 'detail': 'GROQ_API_KEY not set'}), 200

    import time
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        t0 = time.time()
        available = {m.id for m in client.models.list().data}
        latency_ms = int((time.time() - t0) * 1000)
        # Reachable isn't enough: a retired model still lists the API as up.
        if GROQ_MODEL not in available:
            return jsonify({'status': 'error', 'detail': f'Model {GROQ_MODEL} is not available on Groq'}), 200
        return jsonify({
            'status': 'online',
            'latency_ms': latency_ms,
            'model': GROQ_MODEL,
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'detail': f'{type(e).__name__}: {str(e)[:200]}',
        }), 200


# ─── Weekend box office (Box Office Mojo) ──────────────────────────────────
# TMDB has no box-office chart (its "revenue" is a sparse lifetime figure),
# so the Box Office tab ranks by Mojo's domestic weekend chart. Mojo posts
# Sunday estimates and Monday actuals; a 3-hour cache tracks both, and the
# last good chart is served if a refresh fails.
import html as _html
import re as _re

BOM_URL = 'https://www.boxofficemojo.com/weekend/chart/'
BOM_TTL = 3 * 3600
BOM_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/130.0 Safari/537.36')
_bom_cache = {'data': None, 'at': 0}


def _bom_text(cell):
    return _html.unescape(_re.sub(r'<[^>]+>', '', cell)).strip()


def _bom_int(s):
    digits = _re.sub(r'[^\d]', '', s or '')
    return int(digits) if digits else None


def _bom_pct(s):
    m = _re.match(r'^([+-]?\d+(?:\.\d+)?)%$', (s or '').replace(',', ''))
    return float(m.group(1)) if m else None


def _parse_bom(page):
    heading = _re.search(r'<h1[^>]*>(.*?)</h1>', page, _re.S)
    dates = _re.search(r'<h4[^>]*>(.*?)</h4>', page, _re.S)
    rows = []
    for tr in _re.findall(r'<tr[^>]*>(.*?)</tr>', page, _re.S):
        cells = [_bom_text(c) for c in _re.findall(r'<td[^>]*>(.*?)</td>', tr, _re.S)]
        if len(cells) < 13 or not cells[0].isdigit():
            continue
        rank, lw, title, gross, change, theaters, _, avg, total, weeks, dist, new, est = cells[:13]
        rows.append({
            'rank': int(rank),
            'last_week': int(lw) if lw.isdigit() else None,
            'title': title,
            'gross': _bom_int(gross),
            'change_pct': _bom_pct(change),
            'theaters': _bom_int(theaters),
            'average': _bom_int(avg),
            'total': _bom_int(total),
            'weeks': _bom_int(weeks),
            'distributor': dist,
            'new': new == 'true',
            'estimated': est == 'true',
        })
    if not rows:
        raise ValueError('No chart rows found')
    return {
        'weekend': _bom_text(heading.group(1)) if heading else '',
        'dates': _bom_text(dates.group(1)) if dates else '',
        'source': 'Box Office Mojo',
        'url': BOM_URL,
        'rows': rows[:25],
    }


@app.route('/api/boxoffice')
def box_office():
    now = time.time()
    if _bom_cache['data'] and now - _bom_cache['at'] < BOM_TTL:
        return jsonify({**_bom_cache['data'], 'cached': True})
    try:
        r = requests.get(BOM_URL, headers={'User-Agent': BOM_UA, 'Accept-Language': 'en-US'}, timeout=12)
        r.raise_for_status()
        data = _parse_bom(r.text)
        _bom_cache.update(data=data, at=now)
        return jsonify({**data, 'cached': False})
    except Exception as e:
        if _bom_cache['data']:
            return jsonify({**_bom_cache['data'], 'cached': True, 'stale': True})
        return jsonify({'error': f'{type(e).__name__}: {str(e)[:160]}'}), 503


# ─── IMAX "Now Playing" ─────────────────────────────────────────────────────
# static/imax-now-playing.json is refreshed weekly by GitHub Actions
# (.github/workflows/imax-update.yml) which scrapes Wikipedia's "List of
# films released in IMAX". This endpoint just serves the file's contents —
# no live scrape, no upstream auth, no per-request latency.
#
# The file is mtime-cached so we only re-read from disk when it actually
# changes (i.e. when GH Actions commits an update and Railway redeploys).

_imax_cache = {'data': None, 'mtime': 0}
_IMAX_JSON = None  # resolved on first request


def _imax_json_path():
    global _IMAX_JSON
    if _IMAX_JSON is None:
        _IMAX_JSON = os.path.join(app.root_path, 'static', 'imax-now-playing.json')
    return _IMAX_JSON


@app.route('/api/imax-now-playing')
def imax_now_playing():
    path = _imax_json_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return jsonify({'error': 'No IMAX data available'}), 503

    if _imax_cache['data'] and _imax_cache['mtime'] == mtime:
        return jsonify({**_imax_cache['data'], 'cached': True})

    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({'error': f'Failed to read IMAX data: {e}'}), 503

    _imax_cache['data'] = data
    _imax_cache['mtime'] = mtime
    return jsonify({**data, 'cached': False})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
