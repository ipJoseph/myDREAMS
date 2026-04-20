"""Sentry initialization helper.

Each app (property-api, property-dashboard, cron scripts) calls
`init_sentry()` during startup. Without SENTRY_DSN in the environment
the call is a no-op, so this is safe to wire in everywhere before the
account is actually provisioned.

Once SENTRY_DSN is set:
  - Unhandled exceptions are captured with context
  - Flask integration attaches request data (URL, method, headers)
  - Traces sample rate defaults to 10% to keep quota in check

Replacing the P0 generic `str(e)` error responses with
`sentry_sdk.capture_exception(e)` + a generic 500 response gives the
operator a tracked error without leaking internals to the user.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def init_sentry(app_name: str) -> bool:
    """Initialize Sentry for this process. Returns True if active.

    Args:
        app_name: Short tag included in every event (e.g. "property-api",
            "property-dashboard", "fub-sync"). Shown in the Sentry UI so
            events from different apps are easy to filter.
    """
    global _initialized
    if _initialized:
        return True

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("SENTRY_DSN not set; skipping Sentry init for %s", app_name)
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed; skipping Sentry init")
        return False

    environment = os.getenv("DREAMS_ENV", "dev").lower()
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=os.getenv("SENTRY_RELEASE") or None,
        integrations=[FlaskIntegration()],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("app", app_name)
    _initialized = True
    logger.info("Sentry initialized for %s (env=%s)", app_name, environment)
    return True


def capture_exception(exc: BaseException) -> None:
    """Send an exception to Sentry if initialized; no-op otherwise.

    Route handlers that want to tell the user "something went wrong"
    without leaking exception text can do:

        except Exception as e:
            capture_exception(e)
            return jsonify(error="internal_error"), 500
    """
    if not _initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
