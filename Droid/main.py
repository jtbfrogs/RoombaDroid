#!/usr/bin/env python3
"""DROID SYSTEM v3.0  -  entry point."""
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.logger import logger as log_manager
from core.controller import DroidController
from core.state_machine import DroidState

_BANNER = """
+------------------------------------------------------------+
|                  DROID SYSTEM v3.0                         |
|          Star Wars-like Roomba Droid (Enhanced)            |
|                                                            |
|  * Async command processing    * Lazy module loading       |
|  * Frame-skipping vision       * Optimised Roomba I/O      |
|  * Worker-pool threading       * Graceful error recovery   |
+------------------------------------------------------------+
"""


def main() -> None:
    print(_BANNER)

    log_manager.init("logs")
    log = log_manager.get_logger("main")

    droid: DroidController | None = None
    shutdown_requested = threading.Event()

    def shutdown(sig=None, frame=None) -> None:
        """Handle Ctrl-C / SIGINT cleanly."""
        if shutdown_requested.is_set():
            return
        shutdown_requested.set()
        print("\n[!] Shutting down...")

        if droid:
            def force_exit() -> None:
                time.sleep(3)
                print("[!] Force exit triggered")
                sys.exit(1)

            threading.Thread(target=force_exit, daemon=True).start()

            try:
                droid.stop()
            except Exception as exc:
                log.error("Error during shutdown: %s", exc)

        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    try:
        # --- Boot sequence ---
        droid = DroidController()
        droid.start()           # starts worker pool, loads voice, greets
        droid.initialize()      # eagerly loads roomba + vision, logs status

        log.info("Droid ready. Press Ctrl+C to shut down.")

        # --- Main loop ---
        # The droid listens for voice commands when idle.  listen() is a
        # blocking call (up to the configured timeout) so the loop sleeps
        # naturally while waiting for speech rather than busy-spinning.
        while droid.running and not shutdown_requested.is_set():
            try:
                # Drain any pending commands first (movement, speak, etc.)
                droid.process_commands(timeout=0.05)

                # When idle with nothing queued, listen for a voice command.
                if (
                    droid.voice
                    and droid.state_machine.is_in_state(DroidState.IDLE)
                    and droid.command_queue.size() == 0
                ):
                    droid.listen(timeout=5.0)

                time.sleep(0.05)

            except Exception as exc:
                log.error("Main loop error: %s", exc)

    except Exception as exc:
        log.critical("Fatal error: %s", exc, exc_info=True)
        if droid:
            try:
                droid.stop()
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
