"""
Poller Service - Continuous sync polling.

Runs async loops to:
- Poll FUB for task changes
- Poll Todoist for changes (dev mode)
- Refresh deal cache periodically
"""

import asyncio
import logging
import signal
from datetime import datetime, timedelta
from typing import Optional

from .config import config
from .db import db
from .sync_engine import sync_engine
from .todoist_client import todoist_client

logger = logging.getLogger(__name__)


class Poller:
    """Async polling service for task sync."""

    def __init__(self):
        self.running = False
        self.fub_poll_interval = config.FUB_POLL_INTERVAL
        self.todoist_poll_interval = config.TODOIST_POLL_INTERVAL
        self.deal_cache_refresh = config.DEAL_CACHE_REFRESH

        # Track last poll times
        self._last_fub_poll: Optional[datetime] = None
        self._last_todoist_poll: Optional[datetime] = None
        self._last_deal_refresh: Optional[datetime] = None

        # Stats
        self._fub_polls = 0
        self._todoist_polls = 0
        self._tasks_synced = 0
        self._errors = 0

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        def shutdown_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.running = False

        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)

    async def poll_fub(self):
        """Poll FUB for task changes."""
        while self.running:
            try:
                logger.debug(f"Polling FUB (interval: {self.fub_poll_interval}s)")

                # Run sync in thread pool to not block async loop
                loop = asyncio.get_event_loop()
                synced = await loop.run_in_executor(None, sync_engine.poll_fub_changes)

                self._fub_polls += 1
                self._tasks_synced += len(synced)
                self._last_fub_poll = datetime.now()

                if synced:
                    logger.info(f"FUB poll: synced {len(synced)} tasks")

            except Exception as e:
                self._errors += 1
                logger.error(f"FUB poll error: {e}")
                db.log_sync(
                    direction='fub_to_todoist',
                    action='error',
                    details=f"Poll error: {str(e)}",
                    status='error',
                )

            await asyncio.sleep(self.fub_poll_interval)

    async def poll_todoist(self):
        """Poll Todoist for task changes (dev mode only)."""
        if config.TODOIST_USE_WEBHOOKS:
            logger.info("Todoist webhooks enabled, skipping poll loop")
            return

        # Get or initialize sync token
        sync_token = db.get_state('todoist_sync_token') or '*'

        while self.running:
            try:
                logger.debug(f"Polling Todoist (interval: {self.todoist_poll_interval}s)")

                # Run sync in thread pool
                loop = asyncio.get_event_loop()

                def do_todoist_sync():
                    nonlocal sync_token
                    response = todoist_client.incremental_sync(
                        sync_token=sync_token,
                        resource_types=['items']
                    )

                    # Update sync token
                    new_token = response.get('sync_token')
                    if new_token:
                        sync_token = new_token
                        db.set_state('todoist_sync_token', new_token)

                    # Process changed items
                    items = response.get('items', [])
                    synced_count = 0

                    for item in items:
                        # Skip deleted items
                        if item.get('is_deleted'):
                            continue

                        # Check if we have a mapping for this task
                        from .models import TodoistTask
                        todoist_task = TodoistTask.from_api(item)

                        result = sync_engine.sync_todoist_task_to_fub(todoist_task)
                        if result:
                            synced_count += 1

                    return synced_count, len(items)

                synced_count, total_items = await loop.run_in_executor(None, do_todoist_sync)

                self._todoist_polls += 1
                self._tasks_synced += synced_count
                self._last_todoist_poll = datetime.now()

                if synced_count > 0:
                    logger.info(f"Todoist poll: synced {synced_count}/{total_items} tasks")

            except Exception as e:
                self._errors += 1
                logger.error(f"Todoist poll error: {e}")
                db.log_sync(
                    direction='todoist_to_fub',
                    action='error',
                    details=f"Poll error: {str(e)}",
                    status='error',
                )

            await asyncio.sleep(self.todoist_poll_interval)

    async def refresh_deal_cache(self):
        """Periodically refresh the deal cache."""
        while self.running:
            try:
                logger.debug(f"Refreshing deal cache (interval: {self.deal_cache_refresh}s)")

                # TODO: Implement deal cache refresh
                # This will be implemented when we add deal enrichment

                self._last_deal_refresh = datetime.now()

            except Exception as e:
                logger.error(f"Deal cache refresh error: {e}")

            await asyncio.sleep(self.deal_cache_refresh)

    def get_status(self) -> dict:
        """Get current poller status."""
        return {
            'running': self.running,
            'config': {
                'fub_poll_interval': self.fub_poll_interval,
                'todoist_poll_interval': self.todoist_poll_interval,
                'deal_cache_refresh': self.deal_cache_refresh,
                'todoist_webhooks': config.TODOIST_USE_WEBHOOKS,
            },
            'stats': {
                'fub_polls': self._fub_polls,
                'todoist_polls': self._todoist_polls,
                'tasks_synced': self._tasks_synced,
                'errors': self._errors,
            },
            'last_poll': {
                'fub': self._last_fub_poll.isoformat() if self._last_fub_poll else None,
                'todoist': self._last_todoist_poll.isoformat() if self._last_todoist_poll else None,
                'deal_cache': self._last_deal_refresh.isoformat() if self._last_deal_refresh else None,
            },
        }

    async def run(self):
        """Start all polling loops."""
        self.running = True
        self._setup_signal_handlers()

        logger.info("=" * 60)
        logger.info("Task Sync Poller Starting")
        logger.info("=" * 60)
        logger.info(f"  FUB poll interval: {self.fub_poll_interval}s")
        logger.info(f"  Todoist poll interval: {self.todoist_poll_interval}s")
        logger.info(f"  Deal cache refresh: {self.deal_cache_refresh}s")
        logger.info(f"  Todoist webhooks: {config.TODOIST_USE_WEBHOOKS}")
        logger.info("=" * 60)

        # Create tasks for each polling loop
        tasks = [
            asyncio.create_task(self.poll_fub()),
            asyncio.create_task(self.poll_todoist()),
            asyncio.create_task(self.refresh_deal_cache()),
        ]

        # Wait for shutdown signal
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        # Cancel all tasks
        logger.info("Shutting down polling loops...")
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Poller stopped")
        logger.info(f"Final stats: {self._fub_polls} FUB polls, {self._todoist_polls} Todoist polls, {self._tasks_synced} synced, {self._errors} errors")

    def start(self):
        """Start the poller (blocking)."""
        asyncio.run(self.run())


# Module-level instance
poller = Poller()


def run_poller():
    """Entry point for running the poller."""
    poller.start()
