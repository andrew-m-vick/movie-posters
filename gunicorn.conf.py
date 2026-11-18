# Gunicorn reads this file automatically from the working directory, so these
# settings apply however Railway starts the app (Procfile or a dashboard start
# command). Without it production ran Gunicorn's defaults: one sync worker and
# a 30 s timeout — a For You request (LLM + TMDB checks, 10-40 s) blocked every
# other visitor and was killed if it ran long.
import os

workers = int(os.environ.get('WEB_CONCURRENCY', 2))
threads = 4
worker_class = 'gthread'
timeout = 120
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
