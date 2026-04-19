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

DEFAULT_TIMEOUT = 10  # seconds — fail fast, don't stall the batch
MAX_RETRIES = 2
CHUNK_SIZE = 8192


def download_photo(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """Download a single photo from a URL. Returns bytes or None on failure.

    Never raises exceptions — returns None so the caller can skip and continue.
    """
    if not url or not url.startswith("http"):
        return None

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            if resp.status_code != 200:
                if attempt == MAX_RETRIES - 1:
                    logger.debug(f"Photo download failed: HTTP {resp.status_code} for {url[:80]}")
                continue

            # Read into memory (photos are typically 50KB-2MB)
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                chunks.append(chunk)
                total += len(chunk)
                if total > 20_000_000:  # 20MB safety limit
                    logger.warning(f"Photo too large (>20MB), skipping: {url[:80]}")
                    return None

            data = b"".join(chunks)
            if len(data) < 100:  # Suspiciously small
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
