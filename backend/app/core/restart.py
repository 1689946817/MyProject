"""
Backend process restart helpers.

The admin restart endpoint schedules a delayed process replacement so the HTTP
response can be delivered before the server restarts.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def restart_current_process() -> None:
    """Replace the current Python process with the same command line."""
    executable = sys.executable
    argv = [executable, *sys.argv]
    logger.warning("Restarting backend process: %s", " ".join(argv))
    os.execv(executable, argv)


def schedule_backend_restart(
    delay_seconds: float = 1.0,
    restart_func: Callable[[], None] | None = None,
) -> None:
    """Schedule a delayed backend restart in a daemon thread."""

    def delayed_restart() -> None:
        time.sleep(delay_seconds)
        try:
            (restart_func or restart_current_process)()
        except Exception:
            logger.exception("Failed to restart backend process")

    thread = threading.Thread(
        target=delayed_restart,
        name="backend-restart",
        daemon=True,
    )
    thread.start()
