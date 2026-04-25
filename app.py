import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, send_file, send_from_directory, request, jsonify

# Flask serves ./static/ at /static/<filename> automatically
app = Flask(__name__)


@app.route('/')
def index():
    return send_file('index.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory('static', 'apple-touch-icon.png')


# ─── Recommender endpoint (Groq · Llama 3.3 70B) ──────────────────────────
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')

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
            max_tokens=4096,
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
        client.models.list()
        latency_ms = int((time.time() - t0) * 1000)
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


# ─── IMAX "Now Playing" — auto-scrape r/imax weekly sticky ─────────────────
# r/imax has a weekly stickied "General Discussion Thread" whose title lists
# every film currently in IMAX rotation, e.g.:
#   "General Discussion Thread - Week of 04-19-26 -
#    Project Hail Mary, The Super Mario Galaxy Movie, Michael, 2DIE4, ..."
# Reddit's JSON API is free, no key, no Cloudflare. We parse the sticky title
# and return the headline film (first in list), with the rest available as
# `films`. Falls back to /static/imax-now-playing.json if Reddit is down.
# Cached in-memory for IMAX_CACHE_TTL seconds.

# Cache is invalidated at the most recent Thursday 8pm ET — r/imax mods post
# the next week's discussion thread Thursday night ahead of Friday releases,
# so this gives us exactly one Reddit fetch per week per server instance.
_imax_cache = {'data': None, 'fetched_at': 0}


def _last_thursday_8pm_et_ts():
    """Unix timestamp of the most recent Thursday 8:00 PM US/Eastern."""
    now_et = datetime.now(ZoneInfo('America/New_York'))
    # Monday=0 ... Thursday=3 ... Sunday=6
    days_since_thu = (now_et.weekday() - 3) % 7
    last_thu = (now_et - timedelta(days=days_since_thu)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    if last_thu > now_et:
        last_thu -= timedelta(days=7)
    return last_thu.timestamp()

REDDIT_HEADERS = {
    'User-Agent': 'cinedata-app/1.0 (https://movie-posters-production.up.railway.app)',
    'Accept': 'application/json',
}


def _scrape_reddit_imax():
    """Pull this week's IMAX films from r/imax's stickied discussion thread.

    Returns {'title': str, 'year': None, 'films': [str, ...], 'source': 'reddit'}
    on success, or None on any failure (network, parse, missing sticky).
    """
    try:
        r = requests.get(
            'https://www.reddit.com/r/imax/hot.json?limit=10',
            headers=REDDIT_HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return None
        posts = r.json().get('data', {}).get('children', []) or []
        for p in posts:
            d = p.get('data', {}) or {}
            if not d.get('stickied'):
                continue
            title = d.get('title', '') or ''
            # Match the canonical weekly format
            m = re.search(r'Week of \d{2}-\d{2}-\d{2}\s*[-–—]\s*(.+)$', title)
            if not m:
                continue
            films = [f.strip() for f in m.group(1).split(',') if f.strip()]
            if not films:
                continue
            return {
                'title': films[0],
                'year': None,
                'films': films,
                'source': 'reddit',
            }
        return None
    except Exception:
        return None


def _read_manual_fallback():
    try:
        with open(os.path.join(app.root_path, 'static', 'imax-now-playing.json')) as f:
            data = json.load(f)
            data['source'] = 'manual'
            return data
    except Exception:
        return None


@app.route('/api/imax-now-playing')
def imax_now_playing():
    now = time.time()
    week_boundary = _last_thursday_8pm_et_ts()
    # Cache is valid only if it was fetched after the most recent Thursday 8pm ET.
    if _imax_cache['data'] and _imax_cache['fetched_at'] >= week_boundary:
        return jsonify({**_imax_cache['data'], 'cached': True})

    payload = _scrape_reddit_imax() or _read_manual_fallback()
    if not payload:
        return jsonify({'error': 'No IMAX data available'}), 503

    _imax_cache['data'] = payload
    _imax_cache['fetched_at'] = now
    return jsonify({**payload, 'cached': False})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
