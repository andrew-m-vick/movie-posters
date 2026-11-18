# CINEDATA

A cinephile's dashboard for tracking what's in theaters, what's streaming, and what's coming — with a focus on premium formats and the curation a repertory programmer would actually give you.

**Live:** https://andrew-vick-movies.up.railway.app

---

## Features

### Home — Poster Search
The original movie-poster search engine that started the project. Search any film and click a poster to view it full size; click again to see it at its native resolution. The hero fades in the backdrop of whatever is #1 in theaters.

### Upcoming
Most-anticipated unreleased films from TMDB, up to two years out (*Avengers: Doomsday*, *Dune: Part Three*):
- Spotlight on the #1 most anticipated film, with backdrop and release countdown
- Filter by genre and window (90 days → all announced); sort by popularity, date, or rating

### Box Office
The real domestic weekend chart from [Box Office Mojo](https://www.boxofficemojo.com/weekend/chart/): weekend gross, change vs. last weekend, theaters, per-theater average, domestic total, and weeks in release. Sort by any of them or filter by genre. Served by `/api/boxoffice` (cached 3 h, so Sunday estimates turn into Monday actuals; the last good chart is kept if Mojo is unreachable). Click any film for the detail modal: cast, runtime, IMDb / Rotten Tomatoes / Metacritic ratings, trailer, and where to stream or rent.

### IMAX
- **Now Playing in IMAX** — refreshed weekly from Wikipedia's IMAX release list, then matched against what's actually in US theaters (see *Maintaining the IMAX data*).
- **Films shot with IMAX cameras** — curated, append-only. Not DMR upconverts. Each entry notes the format (15/70mm film, IMAX-certified digital, or both) and how the cameras were used.
- **IMAX 70mm theater finder** — map of the 41 theaters (7 countries) IMAX booked for *The Odyssey* in 15/70mm film, with city/zip search and directions to the nearest one.

### Streaming
What's available across subscription services and digital retailers, filterable by service.

### For You — AI Recommender
Describe what you want to watch in your own words — mood, pacing, anchor films, runtime caps, things to avoid — and get ten picks with a one-line read of your request. Powered by Groq (GPT-OSS 120B). Every pick is fact-checked against TMDB before it's shown: films that don't exist are dropped, year/director/runtime come from TMDB, and the limits you stated (era, runtime, family-friendly, genre) are enforced on those real values. If too few survive, the model gets one retry with the reasons.

### Auteurs
Christopher Nolan vs. Denis Villeneuve, 1998–2026 — opening on the two of them face to face: career ledger, parallel timeline of every feature, verified scorecards, the Dark Knight vs. Dune trilogies, the 2026 *Odyssey* / *Dune: Part Three* face-off — and a twist. Every film opens the detail modal.

### Data menu — Trends, Forecast, Pipeline, OPS
Market analytics over the current slate, an ML revenue forecaster, the data pipeline view, and an ops dashboard with live API health.

### Installable (PWA)
Add to Home Screen on iOS, Android, or desktop. Pages load network-first so new deploys appear immediately; the cached copy covers offline.

---

## Tech Stack

| Layer | Tool |
|---|---|
| App | Single-file HTML/CSS/JS — no build step |
| Design | Playfair Display · DM Sans · DM Mono |
| Movie data | [Box Office Mojo](https://www.boxofficemojo.com) weekend chart, [TMDB](https://developer.themoviedb.org), [OMDb](https://www.omdbapi.com) (proxied server-side, cached 24 h), Watchmode |
| Recommender | [Groq](https://groq.com) · GPT-OSS 120B |
| Charts / map | Chart.js · [Leaflet](https://leafletjs.com) + Esri Dark Gray Canvas (OpenStreetMap fallback) — both loaded only when a tab needs them |
| Geocoding / routing | OpenStreetMap Nominatim · OSRM (free, no key) |
| Server | Flask + Gunicorn |
| Hosting | [Railway](https://railway.app) |

---

## Setup

```bash
pip install -r requirements.txt
OMDB_API_KEY=... GROQ_API_KEY=... python app.py
```

| Variable | Used for |
|---|---|
| `OMDB_API_KEY` | IMDb / RT / Metacritic ratings, via `/api/omdb` |
| `GROQ_API_KEY` | The For You recommender, via `/api/recommend` |

TMDB and Watchmode work out of the box with built-in keys. To use your own, click the ⚙ icon in the header — overrides are stored in your browser only.

---

## Deployment

Railway builds from `main` using the `Procfile`. Push to deploy.

---

## Maintaining the IMAX data

| File | How it's maintained |
|---|---|
| `static/imax-films.json` | **Manual, append-only.** Only films confirmed to have been *shot* with IMAX cameras; entries are never removed. Each carries a `tmdb_id` and `poster_path` so the page needs no lookups — for new entries these are optional, and the page falls back to a title search. |
| `static/imax-theaters.json` | **Manual.** 70mm film venues only: the theaters on IMAX's official participating-theater list for the latest 15/70mm release (currently *The Odyssey*). Refresh it from IMAX's list when the next 70mm film opens. The map's counts are computed from this file. |
| `static/imax-now-playing.json` | **Auto.** `.github/workflows/imax-update.yml` runs every Saturday, scrapes Wikipedia's per-decade "List of films released in IMAX," and writes the last 60 days of releases. Because that list is worldwide, the page shows whichever of those titles is most popular in US theaters right now. If the scrape ever comes back stale, the workflow fails instead of overwriting good data. |

Run the workflow on demand from the repo's **Actions** tab → *Update IMAX Now Playing* → *Run workflow*.
