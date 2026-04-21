import os
import json
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
