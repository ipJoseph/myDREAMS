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


def post_fork(server, worker):
    """Reset the psycopg2 pool in each worker after fork.

    With preload_app=True, the master imports DREAMSDatabase, which creates
    the psycopg2 ThreadedConnectionPool eagerly when first used. Forked
    workers inherit those open SSL connections — but SSL session state lives
    inside the libpq client, which can't be safely shared across processes.
    Concurrent reuse causes "SSL error: decryption failed or bad record mac"
    or "SSL SYSCALL error: EOF detected" (observed 2026-05-11 22:15 UTC on
    /properties).

    Fix: in each worker, drop the inherited pool reference and let it lazily
    recreate on first use — that pool will own its own connections.
    """
    try:
        from src.core import pg_adapter
        pg_adapter._pool = None
    except Exception as e:
        worker.log.warning(f"post_fork: failed to reset pg_adapter pool: {e}")
