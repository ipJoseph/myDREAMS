"""
Photo download engine.

Downloads photos from CDN URLs with retry, timeout, and skip-on-failure.
This is the HTTP layer only — it doesn't know about MLS sources, databases,
or file naming. The PhotoManager calls it.

Key design choices:
- (connect, read) timeout tuple per photo — fail fast, move on
- Skip on failure (log and continue, never stall the batch)
- Returns bytes, not files — the caller decides where to save
- Per-category failure counters for post-mortem triage (see stats())
"""

import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = 5   # seconds to establish TCP + TLS
DEFAULT_READ_TIMEOUT = 30     # seconds to receive the full body
MAX_RETRIES = 2
MAX_BYTES = 20_000_000        # 20MB per photo, defensive upper bound

# Module-level failure taxonomy. Workers can read/reset via stats() and
# reset_stats() to report breakdown in their own logs. Cheap to maintain,
# zero impact on hot path, lets us tell "chronic upstream 404" apart from
# "transient network flake" without a return-type refactor.
_stats: Dict[str, int] = {
    "ok": 0,
    "http_404": 0,
    "http_403": 0,
    "http_4xx_other": 0,
    "http_5xx": 0,
    "timeout": 0,
    "connection_error": 0,
    "too_large": 0,
    "too_small": 0,
    "other": 0,
}


def stats() -> Dict[str, int]:
    """Snapshot of download counters since last reset_stats() (or process start)."""
    return dict(_stats)


def reset_stats() -> None:
    """Zero all counters. Call at the start of each batch for clean accounting."""
    for key in _stats:
        _stats[key] = 0


def _bucket_status_code(code: int) -> str:
    if code == 404:
        return "http_404"
    if code == 403:
        return "http_403"
    if 400 <= code < 500:
        return "http_4xx_other"
    return "http_5xx"


def download_photo(url: str, timeout: Optional[tuple] = None) -> Optional[bytes]:
    """Download a single photo from a URL. Returns bytes or None on failure.

    Never raises exceptions — returns None so the caller can skip and continue.

    Uses a (connect, read) timeout tuple and does NOT use stream=True. The
    previous implementation streamed with a single scalar `timeout` that
    only covers connect + headers; the body read via iter_content then had
    no timeout and could hang indefinitely on a CLOSE-WAIT socket (observed
    on PRD 2026-04-20, froze a sync for 27+ minutes). Buffering the whole
    response with a real read timeout is simpler and correct for MLS photos
    (typically 50KB–2MB).

    On failure, bumps the relevant per-category counter in `_stats` (accessible
    via stats()) so workers can distinguish upstream-dead (http_404 chronic)
    from network-flake (timeout transient) from rate-limit (http_5xx/403)
    in their end-of-run summaries.
    """
    if not url or not url.startswith("http"):
        _stats["other"] += 1
        return None

    t = timeout or (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)
    last_bucket = "other"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=t)
            if resp.status_code != 200:
                last_bucket = _bucket_status_code(resp.status_code)
                if attempt == MAX_RETRIES - 1:
                    logger.debug(
                        f"Photo download failed [{last_bucket}]: HTTP {resp.status_code} for {url[:80]}"
                    )
                continue

            data = resp.content
            if len(data) > MAX_BYTES:
                logger.warning(f"Photo too large ({len(data)} bytes > {MAX_BYTES}), skipping: {url[:80]}")
                _stats["too_large"] += 1
                return None
            if len(data) < 100:
                logger.debug(f"Photo too small ({len(data)} bytes), skipping: {url[:80]}")
                _stats["too_small"] += 1
                return None

            _stats["ok"] += 1
            return data

        except requests.Timeout:
            last_bucket = "timeout"
            if attempt == MAX_RETRIES - 1:
                logger.debug(f"Photo download timeout: {url[:80]}")
        except requests.ConnectionError as e:
            last_bucket = "connection_error"
            if attempt == MAX_RETRIES - 1:
                logger.debug(f"Photo download connection error: {str(e)[:120]}")
        except requests.RequestException as e:
            last_bucket = "other"
            if attempt == MAX_RETRIES - 1:
                logger.debug(f"Photo download error: {str(e)[:120]}")
        except Exception as e:
            last_bucket = "other"
            logger.warning(f"Unexpected photo download error: {str(e)[:120]}")
            _stats[last_bucket] += 1
            return None

    _stats[last_bucket] += 1
    return None


def detect_extension(url: str) -> str:
    """Detect file extension from URL path. Always uses .jpg for JPEG
    (not .jpeg) for consistency with existing photo files on disk."""
    try:
        path = urlparse(url).path.lower()
        if path.endswith(".png"):
            return ".png"
        if path.endswith(".webp"):
            return ".webp"
        # .jpeg → .jpg for consistency
    except Exception:
        pass
    return ".jpg"
