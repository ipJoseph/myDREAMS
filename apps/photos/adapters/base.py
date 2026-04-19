"""
Base photo adapter interface.

Each MLS source implements this to handle its specific URL format,
authentication, and CDN behavior.
"""

from typing import Dict, List, Optional, Tuple


class PhotoAdapter:
    """Abstract base for per-MLS photo handling."""

    name: str = "base"
    source_dir: str = "base"       # Storage subdirectory name
    cdn_urls_expire: bool = True    # Whether CDN tokens expire

    def extract_media_from_response(self, prop: Dict) -> Tuple[Optional[str], List[str], int]:
        """Extract photo URLs from an API response property dict.

        Returns: (primary_url, all_urls, photo_count)
        """
        raise NotImplementedError

    def get_fresh_urls(self, mls_number: str) -> List[str]:
        """Fetch fresh CDN URLs from the MLS API for a specific listing.

        Used by the hygiene cron when database URLs are expired.
        For MLS Grid: calls the Media endpoint.
        For Navica: CDN URLs don't expire, so returns whatever's in the DB.
        """
        raise NotImplementedError
