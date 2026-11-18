import os
import json
import time
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

3. RECOMMEND exactly 10 films.

Recommendation rules:
- Avoid obvious picks. If they say "patient dread," don't pick The Shining — pick Under the Skin, Sauvage, or Memories of Murder. Go global, era-diverse, sometimes international, sometimes documentary, sometimes forgotten.
- Each "why" must reference their OWN language in 2–4 sentences. Don't just say "similar tone" — quote their phrase or paraphrase it tightly.
- Write like a friend who actually watched it. No adjective padding.
- Respect runtime ceilings strictly.
- Respect anti-patterns (things they said to avoid).
- Tags: 3–5 concrete descriptors each ("slow-burn", "body horror", "New Hollywood", "neorealism"). Not genres alone — texture words.

Return ONLY valid JSON, no markdown, no preamble:
{
  "interpretation": "one-sentence reflection of their request in their register",
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

    raw_text = None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {'role': 'system', 'content': RECOMMENDER_SYSTEM},
                {'role': 'user',   'content': query},
            ],
            response_format={'type': 'json_object'},
            temperature=0.85,
            # Reasoning models spend output tokens thinking; keep it light and
            # leave room for the ten-film JSON.
            max_tokens=8192,
            extra_body={'reasoning_effort': 'low'} if 'gpt-oss' in GROQ_MODEL else None,
        )
        raw_text = (response.choices[0].message.content or '').strip()
        data = json.loads(raw_text)
        return jsonify(data)
    except json.JSONDecodeError:
        return jsonify({
            'error': 'Model returned invalid JSON',
            'raw': (raw_text or '')[:500],
        }), 502
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 502


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
