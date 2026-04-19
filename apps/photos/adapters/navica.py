"""
Navica (Carolina Smokies + Mountain Lakes) photo adapter.

Key facts:
- CDN URLs are STABLE (CloudFront, no expiring tokens)
- Photos CAN be served from CDN as fallback (see docs/DECISIONS.md D2)
- Local download still preferred for performance
- Both NavicaMLS and MountainLakesMLS use the same adapter
"""

from typing import Dict, List, Optional, Tuple

from .base import PhotoAdapter


class NavicaPhotoAdapter(PhotoAdapter):
    name = "navica"
    source_dir = "navica"
    cdn_urls_expire = False  # CloudFront URLs are stable

    def extract_media_from_response(self, prop: Dict) -> Tuple[Optional[str], List[str], int]:
        """Extract photo URLs from a Navica API response.

        Navica embeds photos directly in the listing response as CloudFront URLs.
        """
        media = prop.get("Media", [])
        if not media:
            # Navica sometimes puts the primary photo in a different field
            primary = prop.get("PrimaryPhoto") or prop.get("primary_photo")
            if primary:
                return primary, [primary], 1
            return None, [], 0

        photos = [m for m in media if isinstance(m, dict) and m.get("MediaURL")]
        photos.sort(key=lambda m: m.get("Order", 999))

        urls = [m["MediaURL"] for m in photos]
        primary = urls[0] if urls else None
        return primary, urls, len(urls)

    def get_fresh_urls(self, mls_number: str) -> List[str]:
        """Return CDN URLs from the database — they don't expire."""
        # CDN URLs for Navica are stable, so whatever's in the database works
        # The caller should read from the DB photos/primary_photo columns
        return []
