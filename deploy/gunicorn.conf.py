"""
Gunicorn configuration for myDREAMS production services.

Used by both mydreams-api and mydreams-dashboard systemd services.
"""

# Worker configuration
workers = 2
worker_class = "sync"
timeout = 120  # PDF generation and property imports can be slow

# Load app in master process so background threads (Notion sync, IDX validation)
# start once rather than being duplicated per worker.
preload_app = True

# Only trust X-Forwarded-* headers from Caddy on localhost
forwarded_allow_ips = "127.0.0.1"

# Logging
accesslog = "-"  # stdout -> journald
errorlog = "-"   # stderr -> journald
loglevel = "info"
