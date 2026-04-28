#!/usr/bin/env python3
"""
DROID SYSTEM v3.0
Improved Star Wars-like Droid on Roomba with optimizations for performance and maintainability.
"""

import sys
import time
import signal
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from core.logger import logger as logger_manager
from core.controller import DroidController

def print_banner():
    """Display welcome banner."""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                  DROID SYSTEM v3.0                         ║
    ║          Star Wars-like Roomba Droid (Enhanced)            ║
    ║                                                            ║
    ║  Features:                                                ║
    ║  • Async command processing  • Lazy module loading       ║
    ║  • Frame skipping vision     • Optimized Roomba I/O      ║
    ║  • Worker pool threading     • Better error recovery     ║
    ╚════════════════════════════════════════════════════════════╝
    """)

def main():
    """Main entry point."""
    global droid
    droid = None
    
    print_banner()
    
    # Initialize logging
    logger_manager.init("logs")
    log = logger_manager.get_logger("main")
    
    # Shutdown flag for signal handler
    shutdown_event = []
    
    # Signal handler - quick exit
    def signal_handler(sig, frame):
        print("\n\n[!] Ctrl+C received - shutting down...")
        shutdown_event.append(True)
        
        # Give shutdown 3 seconds max
        if droid:
            import threading
            def force_stop():
                time.sleep(3)
                if droid and droid.running:
                    print("[!] Force-stopping unresponsive components...")
                    # Force set running to False to exit main loop
                    droid.running = False
            
            stopper = threading.Thread(target=force_stop, daemon=True)
            stopper.start()
            
            try:
                droid.stop()
            except Exception as e:
                log.error(f"Error during shutdown: {e}")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Initialize controller
        droid = DroidController()
        droid.start()
        
        log.info("Droid ready! Press Ctrl+C to shutdown")
        
        # Main loop
        while droid.running and not shutdown_event:
            try:
                # Process queued commands
                droid.process_commands(timeout=0.1)
                time.sleep(0.05)
            except KeyboardInterrupt:
                signal_handler(None, None)
                break
            except Exception as e:
                log.error(f"Loop error: {e}")
    
    except Exception as e:
        log.critical(f"Fatal error: {e}", exc_info=True)
        if droid:
            try:
                droid.stop()
            except:
                pass
        sys.exit(1)

if __name__ == "__main__":
    main()
