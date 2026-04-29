"""
Batch processing example - run this after main.py to test command batching.

This demonstrates how to efficiently batch commands and process them
with minimal overhead.
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from core.controller import DroidController
from utils.command_queue import Command

def example_batch_commands():
    """Queue and process multiple commands at once."""
    
    droid = DroidController()
    droid.start()
    
    print("\n=== BATCH COMMAND PROCESSING ===\n")
    
    # Batch 1: Movement
    print("[BATCH 1] Queuing movement commands...")
    droid.queue_command("move", {"direction": "FORWARD"}, priority=5)
    droid.queue_command("speak", {"text": "Moving forward"}, priority=5)
    
    # Process all queued commands at once
    count = droid.process_commands(timeout=0.1)
    print(f"  Processed {count} commands")
    time.sleep(0.5)
    
    # Batch 2: Lights
    print("\n[BATCH 2] Queuing light commands...")
    for color in ["red", "green", "blue"]:
        droid.queue_command("light", {"color": color}, priority=3)
    
    count = droid.process_commands(timeout=0.1)
    print(f"  Processed {count} commands")
    time.sleep(0.5)
    
    # Batch 3: Priority test
    print("\n[BATCH 3] Testing priority queue...")
    droid.queue_command("move", {"direction": "FORWARD"}, priority=0)  # Low
    droid.queue_command("move", {"direction": "STOP"}, priority=100)   # High
    droid.queue_command("move", {"direction": "LEFT"}, priority=50)    # Medium
    
    print("  Commands will process in priority order (100, 50, 0)")
    count = droid.process_commands(timeout=0.2)
    print(f"  Processed {count} commands in priority order")
    
    droid.stop()
    print("\n[OK] Batch processing complete")

if __name__ == "__main__":
    example_batch_commands()
