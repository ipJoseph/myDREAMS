"""Async polling service for continuous Linear ↔ FUB sync."""

import asyncio
import logging
import signal
from datetime import datetime

from .config import config
from .sync_engine import sync_engine
from .db import db

logger = logging.getLogger(__name__)


class Poller:
    """Async polling service for bidirectional sync."""

    def __init__(self):
        self.running = False
        self.linear_poll_interval = config.LINEAR_POLL_INTERVAL
        self.fub_poll_interval = config.FUB_POLL_INTERVAL
        self.deal_cache_refresh = config.DEAL_CACHE_REFRESH

        # Stats
        self._fub_synced = 0
        self._linear_synced = 0
        self._errors = 0
        self._last_fub_poll = None
        self._last_linear_poll = None

    async def poll_fub(self):
        """Poll FUB for task changes."""
        while self.running:
            try:
                loop = asyncio.get_event_loop()
                synced = await loop.run_in_executor(
                    None, sync_engine.poll_fub_changes
                )
                self._fub_synced += synced
                self._last_fub_poll = datetime.now()

                if synced > 0:
                    logger.info(f"FUB poll: synced {synced} tasks")

            except Exception as e:
                self._errors += 1
                logger.error(f"FUB poll error: {e}")

            await asyncio.sleep(self.fub_poll_interval)

    async def poll_linear(self):
        """Poll Linear for issue changes."""
        while self.running:
            try:
                loop = asyncio.get_event_loop()
                synced = await loop.run_in_executor(
                    None, sync_engine.poll_linear_changes
                )
                self._linear_synced += synced
                self._last_linear_poll = datetime.now()

                if synced > 0:
                    logger.info(f"Linear poll: synced {synced} issues")

            except Exception as e:
                self._errors += 1
                logger.error(f"Linear poll error: {e}")

            await asyncio.sleep(self.linear_poll_interval)

    async def refresh_deal_cache(self):
        """Periodically refresh deal cache."""
        from .fub_client import fub_client

        while self.running:
            try:
                # Get all mapped person IDs
                mappings = db.get_all_mappings()
                person_ids = set(m['fub_person_id'] for m in mappings if m['fub_person_id'])

                loop = asyncio.get_event_loop()
                for person_id in person_ids:
                    deals = await loop.run_in_executor(
                        None, fub_client.get_deals_for_person, person_id
                    )
                    for deal in deals:
                        db.cache_deal(deal)

                logger.debug(f"Refreshed deal cache for {len(person_ids)} people")

            except Exception as e:
                logger.error(f"Deal cache refresh error: {e}")

            await asyncio.sleep(self.deal_cache_refresh)

    def get_status(self) -> dict:
        """Get poller status."""
        return {
            'running': self.running,
            'fub_poll_interval': self.fub_poll_interval,
            'linear_poll_interval': self.linear_poll_interval,
            'stats': {
                'fub_synced': self._fub_synced,
                'linear_synced': self._linear_synced,
                'errors': self._errors,
                'last_fub_poll': self._last_fub_poll.isoformat() if self._last_fub_poll else None,
                'last_linear_poll': self._last_linear_poll.isoformat() if self._last_linear_poll else None,
            }
        }

    async def run(self):
        """Start all polling loops."""
        self.running = True
        logger.info("Starting Linear sync poller...")
        logger.info(f"  FUB poll interval: {self.fub_poll_interval}s")
        logger.info(f"  Linear poll interval: {self.linear_poll_interval}s")
        logger.info(f"  Deal cache refresh: {self.deal_cache_refresh}s")

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)

        # Start polling tasks
        tasks = [
            asyncio.create_task(self.poll_fub()),
            asyncio.create_task(self.poll_linear()),
            asyncio.create_task(self.refresh_deal_cache()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Poller tasks cancelled")

    def stop(self):
        """Stop the poller."""
        logger.info("Stopping poller...")
        self.running = False


def run_poller():
    """Run the poller (blocking)."""
    poller = Poller()

    try:
        asyncio.run(poller.run())
    except KeyboardInterrupt:
        logger.info("Poller stopped by user")


# Module-level instance
poller = Poller()
