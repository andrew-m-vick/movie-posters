# CINEDATA

A cinephile's dashboard for tracking what's in theaters, what's streaming, and what's coming — with a focus on premium formats and the curation a repertory programmer would actually give you.

**Live:** https://andrew-vick-movies.up.railway.app

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
Three datasets, two questions:
- **Now Playing in IMAX** — auto-updated weekly. A GitHub Actions workflow scrapes Wikipedia's "List of films released in IMAX" every Saturday morning and commits the most recent entry to `static/imax-now-playing.json`. Click the headline card to open the full TMDB detail modal (synopsis, cast, trailer).
- **Films confirmed to have been *filmed* in IMAX** — manually curated, append-only. Not DMR upconverts, not post-converted. Each entry includes the format used (15/70mm film, IMAX-certified digital, or hybrid) and a detailed production note. Click any poster to open the production-notes modal.
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

## Maintaining the IMAX data

| File | How it's maintained |
|---|---|
| `static/imax-films.json` | **Manual, append-only.** Entries are confirmed to have been filmed in IMAX and are never removed. New films added only when confirmed (e.g. *The Odyssey* on 70mm). |
| `static/imax-theaters.json` | **Manual.** Updated periodically from venues associated with 70mm IMAX releases. |
| `static/imax-now-playing.json` | **Auto.** Refreshed every Saturday by `.github/workflows/imax-update.yml`, which scrapes Wikipedia's "List of films released in IMAX" and commits the most recent entry. Manual edits are overwritten on the next workflow run. |

The auto-update workflow can be triggered on demand from the repo's **Actions** tab → *Update IMAX Now Playing* → *Run workflow*.
