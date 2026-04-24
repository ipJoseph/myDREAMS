"""
Central MLS Grid API Rate Limiter

ALL MLS Grid API access MUST go through this throttle.
Enforces MLS Grid limits across all processes using a shared lock file.

Limits (from MLS Grid policy):
  - Warning:    2 RPS, 7,200/hr, 3,072 MB/hr, 40,000/day, 40 GB/day
  - Suspension: 6 RPS, 18,000/hr, 4,096 MB/hr, 60,000/day, 60 GB/day

Our targets (stay well under warning thresholds):
  - Max 0.5 RPS (1 request every 2 seconds)
  - Max 3,000 requests per hour
  - Max 20,000 requests per rolling 24 hours
  - Check suspension status before any batch operation

Usage:
    from src.core.mlsgrid_throttle import get_throttle

    throttle = get_throttle()
    throttle.wait()  # blocks until safe to make a request
    response = session.get(...)
    throttle.record()  # log the request

    # Before batch operations:
    if not throttle.can_start_batch(estimated_requests=500):
        print("Too close to limits, aborting")
"""

import fcntl
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = PROJECT_ROOT / 'data' / '.mlsgrid_throttle.json'
LOCK_FILE = PROJECT_ROOT / 'data' / '.mlsgrid_throttle.lock'

# Our conservative limits (well under MLS Grid warning thresholds).
# TEMPORARY grace-period override #2 (2026-04-24, expires 21:00 UTC).
# Hetzner volume resized to 512GB at 14:50 UTC after first drain
# attempt crashed with disk-full. Re-raising to run drain to completion.
# MUST revert to (3.0 / 3000 / 20000) at ramp-down.
MIN_REQUEST_INTERVAL = 0.05   # grace-window value; normal: 3.0
MAX_REQUESTS_PER_HOUR = 150000  # grace-window value; normal: 3000
MAX_REQUESTS_PER_DAY = 1000000  # grace-window value; normal: 20000
BATCH_HEADROOM = 0.7          # only start a batch if under 70% of limits


class MLSGridThrottle:
    """Process-safe rate limiter for MLS Grid API."""

    def __init__(self):
        self._lock_fd = None
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _acquire_lock(self):
        self._lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)

    def _release_lock(self):
        if self._lock_fd:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
        return {'requests': [], 'last_request': 0}

    def _save_state(self, state):
        try:
            STATE_FILE.write_text(json.dumps(state))
        except OSError as e:
            logger.warning(f"Could not save throttle state: {e}")

    def _prune_old_requests(self, state):
        """Remove request timestamps older than 24 hours."""
        cutoff = time.time() - 86400
        state['requests'] = [t for t in state['requests'] if t > cutoff]
        return state

    def _requests_in_window(self, state, seconds):
        """Count requests in the last N seconds."""
        cutoff = time.time() - seconds
        return sum(1 for t in state['requests'] if t > cutoff)

    def wait(self):
        """Block until it's safe to make a request. Call before each API request."""
        self._acquire_lock()
        try:
            state = self._load_state()
            state = self._prune_old_requests(state)

            # Enforce minimum interval
            now = time.time()
            last = state.get('last_request', 0)
            elapsed = now - last
            if elapsed < MIN_REQUEST_INTERVAL:
                wait_time = MIN_REQUEST_INTERVAL - elapsed
                self._release_lock()
                time.sleep(wait_time)
                self._acquire_lock()
                state = self._load_state()

            # Check hourly limit
            hourly = self._requests_in_window(state, 3600)
            if hourly >= MAX_REQUESTS_PER_HOUR:
                wait_until = min(t for t in state['requests'] if t > time.time() - 3600) + 3600
                wait_secs = max(0, wait_until - time.time())
                logger.warning(f"Hourly limit reached ({hourly}/{MAX_REQUESTS_PER_HOUR}). Waiting {wait_secs:.0f}s")
                self._release_lock()
                time.sleep(wait_secs + 1)
                self._acquire_lock()

            # Check daily limit
            daily = self._requests_in_window(state, 86400)
            if daily >= MAX_REQUESTS_PER_DAY:
                logger.error(f"Daily limit reached ({daily}/{MAX_REQUESTS_PER_DAY}). Aborting.")
                self._release_lock()
                raise RuntimeError("MLS Grid daily request limit reached. Try again tomorrow.")

        finally:
            if self._lock_fd:
                self._release_lock()

    def record(self):
        """Record that a request was made. Call after each API request."""
        self._acquire_lock()
        try:
            state = self._load_state()
            now = time.time()
            state['requests'].append(now)
            state['last_request'] = now
            state = self._prune_old_requests(state)
            self._save_state(state)
        finally:
            self._release_lock()

    def can_start_batch(self, estimated_requests):
        """Check if a batch operation is safe to start.

        Returns True only if we have enough headroom for the estimated
        number of requests without hitting limits.
        """
        self._acquire_lock()
        try:
            state = self._load_state()
            state = self._prune_old_requests(state)

            hourly = self._requests_in_window(state, 3600)
            daily = self._requests_in_window(state, 86400)

            hourly_remaining = MAX_REQUESTS_PER_HOUR - hourly
            daily_remaining = MAX_REQUESTS_PER_DAY - daily

            hourly_ok = estimated_requests < (MAX_REQUESTS_PER_HOUR * BATCH_HEADROOM - hourly)
            daily_ok = estimated_requests < (MAX_REQUESTS_PER_DAY * BATCH_HEADROOM - daily)

            logger.info(
                f"Batch check: {estimated_requests} requests needed. "
                f"Hourly: {hourly}/{MAX_REQUESTS_PER_HOUR} used ({hourly_remaining} remaining). "
                f"Daily: {daily}/{MAX_REQUESTS_PER_DAY} used ({daily_remaining} remaining)."
            )

            if not hourly_ok:
                logger.warning(f"Batch rejected: would exceed hourly headroom")
            if not daily_ok:
                logger.warning(f"Batch rejected: would exceed daily headroom")

            return hourly_ok and daily_ok
        finally:
            self._release_lock()

    def get_status(self):
        """Return current usage stats."""
        self._acquire_lock()
        try:
            state = self._load_state()
            state = self._prune_old_requests(state)
            hourly = self._requests_in_window(state, 3600)
            daily = self._requests_in_window(state, 86400)
            last = state.get('last_request', 0)
            last_str = datetime.fromtimestamp(last).strftime('%H:%M:%S') if last else 'never'
            return {
                'hourly_requests': hourly,
                'hourly_limit': MAX_REQUESTS_PER_HOUR,
                'daily_requests': daily,
                'daily_limit': MAX_REQUESTS_PER_DAY,
                'last_request': last_str,
                'rps_limit': 1.0 / MIN_REQUEST_INTERVAL,
            }
        finally:
            self._release_lock()

    def reset(self):
        """Clear all state. Use after confirmed suspension clears."""
        self._acquire_lock()
        try:
            self._save_state({'requests': [], 'last_request': 0})
            logger.info("Throttle state reset.")
        finally:
            self._release_lock()


# Singleton
_throttle = None

def get_throttle():
    global _throttle
    if _throttle is None:
        _throttle = MLSGridThrottle()
    return _throttle
