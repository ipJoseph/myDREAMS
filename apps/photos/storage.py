"""
Photo file storage.

Handles all disk I/O for photos: paths, existence checks, atomic writes,
URL generation. Today: local disk. Tomorrow: could wrap S3/Supabase Storage.

Every photo lives at: {PHOTOS_BASE}/{source}/{mls_number}.{ext}
  Primary: CAR4363555.jpg
  Gallery: CAR4363555_01.jpg, CAR4363555_02.jpg, ...
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Base directories per environment
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# PRD uses /mnt/dreams-photos if it exists, DEV uses data/photos
_PRD_PHOTOS = Path("/mnt/dreams-photos")
_DEV_PHOTOS = _PROJECT_ROOT / "data" / "photos"

# Source directories map MLS source names to subdirectories
SOURCE_DIRS = {
    "mlsgrid": "mlsgrid",
    "canopymls": "mlsgrid",
    "canopy": "mlsgrid",
    "navica": "navica",
    "navicamls": "navica",
    "mountainlakesmls": "navica",
    "mountainlakes": "navica",
}


def _get_base() -> Path:
    """Return the base photos directory for this environment."""
    # Check if PRD mount exists and has files
    mlsgrid_prd = _PRD_PHOTOS / "mlsgrid"
    if mlsgrid_prd.is_dir():
        return _PRD_PHOTOS

    # Check if data/photos/mlsgrid exists (symlink or direct)
    mlsgrid_dev = _DEV_PHOTOS / "mlsgrid"
    if mlsgrid_dev.is_dir():
        return _DEV_PHOTOS

    # Fallback: create dev directory
    _DEV_PHOTOS.mkdir(parents=True, exist_ok=True)
    return _DEV_PHOTOS


def get_source_dir(mls_source: str) -> Path:
    """Map an MLS source name to a photo directory."""
    key = (mls_source or "").lower().replace(" ", "")
    subdir = SOURCE_DIRS.get(key, key)
    path = _get_base() / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def primary_filename(mls_number: str, ext: str = ".jpg") -> str:
    return f"{mls_number}{ext}"


def gallery_filename(mls_number: str, index: int, ext: str = ".jpg") -> str:
    return f"{mls_number}_{index:02d}{ext}"


def primary_path(mls_source: str, mls_number: str) -> Path:
    """Full path to the primary photo file."""
    return get_source_dir(mls_source) / primary_filename(mls_number)


def primary_exists(mls_source: str, mls_number: str) -> bool:
    """Check if primary photo exists on disk (any extension)."""
    d = get_source_dir(mls_source)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if (d / f"{mls_number}{ext}").exists():
            return True
    return False


def primary_url(mls_source: str, mls_number: str) -> Optional[str]:
    """Return the serving URL if primary photo exists, else None."""
    d = get_source_dir(mls_source)
    key = (mls_source or "").lower().replace(" ", "")
    source_name = SOURCE_DIRS.get(key, key)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if (d / f"{mls_number}{ext}").exists():
            return f"/api/public/photos/{source_name}/{mls_number}{ext}"
    return None


def gallery_urls(mls_source: str, mls_number: str) -> List[str]:
    """Scan disk for all gallery photos, return serving URLs."""
    d = get_source_dir(mls_source)
    key = (mls_source or "").lower().replace(" ", "")
    source_name = SOURCE_DIRS.get(key, key)
    urls = []

    # Primary first
    p_url = primary_url(mls_source, mls_number)
    if p_url:
        urls.append(p_url)

    # Gallery files: _01, _02, ...
    consecutive_misses = 0
    for i in range(1, 100):
        found = False
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            fname = gallery_filename(mls_number, i, ext)
            if (d / fname).exists():
                urls.append(f"/api/public/photos/{source_name}/{fname}")
                found = True
                break
        if not found:
            consecutive_misses += 1
            if consecutive_misses >= 5:
                break
        else:
            consecutive_misses = 0

    return urls


def save_atomic(directory: Path, filename: str, data: bytes) -> Path:
    """Write photo bytes to disk atomically (temp file + rename).

    Prevents serving partial downloads. See docs/DECISIONS.md D2.
    """
    filepath = directory / filename
    try:
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            os.write(fd, data)
            os.close(fd)
            os.chmod(tmp_path, 0o644)  # World-readable (API serves as different user)
            os.rename(tmp_path, filepath)
            return filepath
        except Exception:
            os.close(fd) if not os.get_inheritable(fd) else None
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception as e:
        logger.warning(f"Atomic write failed for {filename}: {e}")
        # Fallback: direct write (better than no photo)
        with open(filepath, "wb") as f:
            f.write(data)
        return filepath
