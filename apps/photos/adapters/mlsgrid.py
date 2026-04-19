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

        Makes ONE API call per listing. Use for hygiene fill, not bulk sync.
        Returns list of fresh CDN URLs with valid tokens.
        """
        import os
        try:
            from apps.mlsgrid.client import MLSGridClient
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv("MLSGRID_TOKEN")
            if not token:
                return []
            client = MLSGridClient(token=token)
            media = client.fetch_media_for_listing(mls_number)
            # Extract photo URLs, sorted by Order
            photos = [
                m for m in media
                if isinstance(m, dict)
                and m.get("MediaCategory", "").lower() == "photo"
            ]
            if not photos:
                photos = [m for m in media if isinstance(m, dict) and m.get("MediaURL")]
            photos.sort(key=lambda m: m.get("Order", 999))
            return [m["MediaURL"] for m in photos if m.get("MediaURL")]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"get_fresh_urls failed for {mls_number}: {e}")
            return []
