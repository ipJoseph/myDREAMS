"""
Photo download engine.

Downloads photos from CDN URLs with retry, timeout, and skip-on-failure.
This is the HTTP layer only — it doesn't know about MLS sources, databases,
or file naming. The PhotoManager calls it.

Key design choices:
- 10-second timeout per photo (not 30s — fail fast, move on)
- Skip on failure (log and continue, never stall the batch)
- Chunk downloads (8KB) for memory efficiency on large galleries
- Returns bytes, not files — the caller decides where to save
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = 5   # seconds to establish TCP + TLS
DEFAULT_READ_TIMEOUT = 30     # seconds to receive the full body
MAX_RETRIES = 2
MAX_BYTES = 20_000_000        # 20MB per photo, defensive upper bound


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
    """
    if not url or not url.startswith("http"):
        return None

    t = timeout or (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=t)
            if resp.status_code != 200:
                if attempt == MAX_RETRIES - 1:
                    logger.debug(f"Photo download failed: HTTP {resp.status_code} for {url[:80]}")
                continue

            data = resp.content
            if len(data) > MAX_BYTES:
                logger.warning(f"Photo too large ({len(data)} bytes > {MAX_BYTES}), skipping: {url[:80]}")
                return None
            if len(data) < 100:
                logger.debug(f"Photo too small ({len(data)} bytes), skipping: {url[:80]}")
                return None

            return data

        except requests.Timeout:
            if attempt == MAX_RETRIES - 1:
                logger.debug(f"Photo download timeout: {url[:80]}")
        except requests.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                logger.debug(f"Photo download error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected photo download error: {e}")
            return None

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
