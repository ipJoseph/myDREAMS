import json
import time
from pathlib import Path
from typing import Any, Optional

from .exceptions import FUBError, FUBAPIError, RateLimitExceeded, DataValidationError



class DataCache:
    def __init__(self, cache_dir: Path, enabled: bool = True, max_age_minutes: int = 30, logger=None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = enabled
        self.max_age_minutes = max_age_minutes
        self.logger = logger

    def _safe_key(self, key: str) -> str:
        return "".join(c if c.isalnum() or c in "._-()" else "_" for c in key)

    def get(self, key: str, max_age_minutes: int = None) -> Optional[Any]:
        if not self.enabled:
            return None

        max_age = max_age_minutes or self.max_age_minutes
        safe_key = self._safe_key(key)
        cache_file = self.cache_dir / f"{safe_key}.json"

        if not cache_file.exists():
            return None

        age_minutes = (time.time() - cache_file.stat().st_mtime) / 60
        if age_minutes > max_age:
            if self.logger:
                self.logger.debug(f"Cache expired for {key} (age: {age_minutes:.1f}m)")
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if self.logger:
                self.logger.debug(f"Cache hit for {key} (age: {age_minutes:.1f}m)")
            return data
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Cache read error for {key}: {e}")
            return None

    def set(self, key: str, data: Any):
        if not self.enabled:
            return

        safe_key = self._safe_key(key)
        cache_file = self.cache_dir / f"{safe_key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            if self.logger:
                self.logger.debug(f"Cached {key}")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Cache write error for {key}: {e}")
