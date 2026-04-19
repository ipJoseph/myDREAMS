"""
MLS Grid (Canopy MLS) photo adapter.

Key facts:
- CDN tokens EXPIRE (see docs/DECISIONS.md D2)
- Photos MUST be downloaded locally — never serve CDN URLs to frontend
- Media URLs come from $expand=Media in the OData response
- Fresh URLs available ONLY during sync (from API response) or via
  the standalone Media endpoint (requires extra API call)
"""

from typing import Dict, List, Optional, Tuple

from .base import PhotoAdapter


class MLSGridPhotoAdapter(PhotoAdapter):
    name = "mlsgrid"
    source_dir = "mlsgrid"
    cdn_urls_expire = True

    def extract_media_from_response(self, prop: Dict) -> Tuple[Optional[str], List[str], int]:
        """Extract photo URLs from an MLS Grid property response.

        The Media array contains objects with MediaURL, MediaCategory, etc.
        We want MediaCategory='Photo' items, ordered by Order field.
        """
        media = prop.get("Media", [])
        if not media:
            return None, [], 0

        # Filter to photos only, sort by Order
        photos = [
            m for m in media
            if isinstance(m, dict) and m.get("MediaCategory", "").lower() == "photo"
        ]
        if not photos:
            # Some listings have Media but no "Photo" category — take all
            photos = [m for m in media if isinstance(m, dict) and m.get("MediaURL")]

        photos.sort(key=lambda m: m.get("Order", 999))

        urls = [m["MediaURL"] for m in photos if m.get("MediaURL")]
        primary = urls[0] if urls else None
        return primary, urls, len(urls)

    def get_fresh_urls(self, mls_number: str) -> List[str]:
        """Fetch fresh Media URLs from MLS Grid API.

        This requires an API call, so use sparingly (hygiene cron only).
        During normal sync, URLs come from $expand=Media in the property response.
        """
        # TODO: implement when we build the hygiene cron
        # For now, the sync-time URLs are the primary path
        return []
