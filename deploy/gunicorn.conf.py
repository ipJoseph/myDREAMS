"""
Gunicorn configuration for myDREAMS production services.

Used by both mydreams-api and mydreams-dashboard systemd services.
"""

# Worker configuration
workers = 2
worker_class = "sync"
timeout = 180  # Raised from 120 (2026-04-21) as a safety net while B4 removes
               # the synchronous CDN fallback from the request path. Once B4
               # lands and invariant #6 of PHOTO_PIPELINE_SPEC.md is enforced,
               # this can drop back toward 60 since no endpoint should legitimately
               # take longer than a few seconds.

# Load app in master process so background threads (Notion sync, IDX validation)
# start once rather than being duplicated per worker.
preload_app = True

# Only trust X-Forwarded-* headers from Caddy on localhost
forwarded_allow_ips = "127.0.0.1"

# Logging
accesslog = "-"  # stdout -> journald
errorlog = "-"   # stderr -> journald
loglevel = "info"
