# CINEDATA

A cinephile's dashboard for tracking what's in theaters, what's streaming, and what's coming — with a focus on premium formats and the curation a repertory programmer would actually give you.

**Live:** https://movie-posters-production.up.railway.app

---

## Features

### Home — Poster Search
The original movie-poster search engine that started the project. Search any film and click a poster to view it full size.

### Box Office
Current theatrical releases with posters, ratings, and release info. Click any film for a detailed modal with cast, runtime, genres, and trailer links.

### Streaming
What's available across major streaming platforms, filtered by service.

### Upcoming
Most-anticipated unreleased films sourced from TMDB's discover and upcoming endpoints, pulling up to two years out so major releases (Avengers, Spider-Man, *The Odyssey*) always appear.
- Spotlight card for the #1 most anticipated film with backdrop, overview, and countdown
- Filterable grid by genre and time window (90 days → all announced)
- Sort by popularity, release date, or rating

### For You — AI Recommender
A free-form recommendation engine powered by Groq (Llama 3.3 70B). Describe what you want to watch in your own words — mood, pacing, anchor films, runtime caps, anti-patterns — and get 10 hand-picked recommendations with a one-sentence interpretation of your request. Tuned to avoid obvious picks and go global, era-diverse, and sometimes forgotten.

### IMAX
Two curated datasets, manually maintained:
- **Films confirmed to have been *filmed* in IMAX** — not DMR upconverts, not post-converted. Each entry includes the format used (15/70mm film, IMAX-certified digital, or hybrid) and a detailed production note.
- **Premium IMAX theater finder** — interactive map of venues that actually deliver the format.
  - **Gold markers** — 70mm Film IMAX (the best)
  - **Teal markers** — Laser Digital IMAX
  - Format filter, zip/city geocoding, auto-route to the nearest theater, click any result to reroute

### Trends, Forecast, Pipeline
Analytics views over the box office and upcoming slate.

### OPS
Internal diagnostics — API health, latency, model status.

### Installable (PWA)
CINEDATA is a Progressive Web App — installable on iOS/Android/desktop via "Add to Home Screen." Launches standalone (no browser chrome), with a service worker for offline asset caching and maskable 192/512 icons.

---

## Tech Stack

| Layer | Tool |
|---|---|
| App | Single-file HTML/CSS/JS — no build step |
| Movie data | [TMDB](https://developer.themoviedb.org), OMDB, Watchmode |
| Recommender | [Groq](https://groq.com) · Llama 3.3 70B |
| Map | [Leaflet.js](https://leafletjs.com) + CartoDB Dark Matter tiles |
| Geocoding | OpenStreetMap Nominatim (free, no key) |
| Routing | OSRM (free, no key) |
| Server | Flask (+ Gunicorn in production) |
| Hosting | [Railway](https://railway.app) |

---

## Setup

1. Clone the repo
2. Add your API keys (TMDB, Groq) in the config section at the top of `index.html` / as environment variables for the Flask app
3. Run locally:

```bash
pip install -r requirements.txt
python app.py
```

The Flask server serves `index.html` and the `/static/` assets (including `imax-films.json` and `imax-theaters.json`), and hosts the `/api/recommend` Groq endpoint.

---

## Deployment

Deployed on Railway using the included `Procfile` and `app.py`. Push to `main` to trigger a redeploy.

---

## Maintaining the IMAX list

The IMAX films list is **append-only** — entries are confirmed to have been filmed in IMAX and are never removed. New films are added only when confirmed (e.g. *The Odyssey* on 70mm). The theaters list is updated periodically from venues associated with 70mm IMAX releases.
