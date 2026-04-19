# CINEDATA

A cinephile's dashboard for tracking what's in theaters, what's streaming, and what's coming — with a focus on premium formats.

**Live:** https://movie-posters-production.up.railway.app

---

## Features

### Now Playing
Browse current theatrical releases with posters, ratings, and release info. Click any film to open a detailed modal with cast, runtime, genres, and trailer links.

### Streaming
Discover what's available across major streaming platforms, filtered by service.

### Upcoming
Most-anticipated unreleased films sourced from TMDB's discover and upcoming endpoints, pulling up to two years out so major blockbusters (Avengers, Spider-Man, The Odyssey, etc.) always appear. Includes:
- Spotlight card for the #1 most anticipated film with backdrop, overview, and countdown to release
- Filterable grid by genre and time window (90 days → all announced)
- Sort by popularity, release date, or rating

### IMAX Theater Finder
Interactive map to locate premium-format IMAX theaters near you — no LIEMAX. Powered entirely by free APIs (no key required).
- **Gold markers** — 70mm Film IMAX (the best)
- **Teal markers** — Laser Digital IMAX
- Format filter to show one or both
- Enter any US zip code or city to drop a pin and auto-route to the nearest theater
- Click any theater in the results list to reroute from your pin
- Results capped at 10 nearest theaters

---

## Tech Stack

| Layer | Tool |
|---|---|
| App | Single-file HTML/CSS/JS — no build step |
| Movie data | [TMDB API](https://developer.themoviedb.org) |
| Map | [Leaflet.js](https://leafletjs.com) + CartoDB Dark Matter tiles |
| Geocoding | OpenStreetMap Nominatim (free, no key) |
| Routing | OSRM (free, no key) |
| Hosting | [Railway](https://railway.app) via minimal Flask wrapper |

---

## Setup

1. Clone the repo
2. Add your TMDB API key in the config section at the top of `index.html`
3. Open `index.html` directly in a browser — or run the Flask app locally:

```bash
pip install -r requirements.txt
python app.py
```

---

## Deployment

Deployed on Railway using the included `Procfile` and `app.py` (a simple Flask static file server). Push to `main` to trigger a redeploy.
