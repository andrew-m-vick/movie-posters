import os
import json
from flask import Flask, send_file, send_from_directory, request, jsonify

# Flask serves ./static/ at /static/<filename> automatically
app = Flask(__name__)


@app.route('/')
def index():
    return send_file('index.html')


# Browsers look for /favicon.ico at the root by default
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


# iOS looks for apple-touch-icon at the root level
@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory('static', 'apple-touch-icon.png')


# ─── Recommender endpoint (Google Gemini) ─────────────────────────────────
GEMINI_MODEL_NAME = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

RECOMMENDER_SYSTEM = """You are the head programmer at a cinephile repertory theatre — someone who has seen everything from Tarkovsky to Tsai Ming-liang, who knows the second wave of 70s horror, the French extremity movement, and can confidently recommend a Chantal Akerman film without irony.

Given the user's stated preferences, recommend EXACTLY 3 films.

Rules:
- Avoid obvious picks. If they describe "patient dread," don't suggest The Shining — suggest Under the Skin, or Sauvage, or Memories of Murder. Go global, go era-diverse.
- Write each "why" in 2–4 sentences that reference the user's OWN language back to them. If they named an anchor film, specifically connect to what they loved ABOUT it — don't just say "similar tone."
- No adjective padding. Write like a friend who actually watched it.
- Strictly respect the runtime ceiling.
- Respect anti-patterns (things they said to avoid).
- Tags should be concrete and descriptive (e.g. "slow-burn", "body horror", "New Hollywood", "neorealism"). 3–5 tags each.

Return ONLY valid JSON in this shape:
{
  "recommendations": [
    {
      "title": "film title",
      "year": 2013,
      "director": "director name",
      "why": "2-4 specific sentences grounded in their stated preferences",
      "tags": ["tag1", "tag2", "tag3"]
    }
  ]
}
"""


def _build_user_prompt(prefs: dict) -> str:
    lines = []
    if prefs.get('anchor'):
        lines.append(f"ANCHOR FILM & WHAT THEY LOVED: {prefs['anchor']}")
    if prefs.get('mood'):
        m = prefs['mood']
        lines.append(f"DESIRED MOOD: {', '.join(m) if isinstance(m, list) else m}")
    if prefs.get('pacing'):
        lines.append(f"PACING TOLERANCE: {prefs['pacing']}")
    if prefs.get('visual'):
        v = prefs['visual']
        lines.append(f"VISUAL STYLE PREFERENCES: {', '.join(v) if isinstance(v, list) else v}")
    if prefs.get('ambiguity'):
        lines.append(f"AMBIGUITY TOLERANCE: {prefs['ambiguity']}")
    if prefs.get('runtime'):
        lines.append(f"RUNTIME CEILING: {prefs['runtime']}")
    if prefs.get('avoid'):
        lines.append(f"AVOID: {prefs['avoid']}")
    return '\n\n'.join(lines) if lines else 'No preferences — surprise me with three genuinely surprising deep cuts.'


@app.route('/api/recommend', methods=['POST'])
def recommend():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'GEMINI_API_KEY environment variable not set on the server'}), 500

    prefs = request.get_json(silent=True) or {}
    user_prompt = _build_user_prompt(prefs)

    raw_text = None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            system_instruction=RECOMMENDER_SYSTEM,
            generation_config=genai.GenerationConfig(
                response_mime_type='application/json',
                temperature=0.85,
            ),
        )
        resp = model.generate_content(user_prompt)
        raw_text = (resp.text or '').strip()
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
