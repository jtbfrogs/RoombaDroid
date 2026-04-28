# Examples and Use Cases

## Example 1: Interactive REPL Mode

```python
#!/usr/bin/env python3
"""Interactive droid control."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

try:
    while True:
        cmd = input("\n> ").strip().lower()
        
        if cmd == "quit":
            break
        elif cmd == "forward":
            droid.move("FORWARD")
        elif cmd == "backward":
            droid.move("BACKWARD")
        elif cmd == "left":
            droid.move("LEFT")
        elif cmd == "right":
            droid.move("RIGHT")
        elif cmd == "stop":
            droid.move("STOP")
        elif cmd == "listen":
            droid.listen()
        elif cmd == "speak":
            text = input("Say: ")
            droid.speak(text)
        elif cmd.startswith("light "):
            color = cmd.split()[1]
            droid.set_light(color)
        else:
            print("Unknown command")
        
        # Process commands
        droid.process_commands(timeout=0.1)

finally:
    droid.stop()
```

## Example 2: Voice Control Loop

```python
"""Continuous voice interaction mode."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

droid.speak("I am listening. Give me commands.")

try:
    while droid.running:
        # Listen for 5 seconds
        droid.queue_command("listen", {"timeout": 5})
        
        # Process the listen command
        for _ in range(50):  # 2.5 seconds with 50ms sleep
            droid.process_commands()
            time.sleep(0.05)
        
except KeyboardInterrupt:
    pass
finally:
    droid.stop()
```

## Example 3: Sequential Movement

```python
"""Choreographed movement sequence."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

# Move in a square
movements = [
    ("FORWARD", 2),
    ("LEFT", 1),
    ("FORWARD", 2),
    ("LEFT", 1),
    ("FORWARD", 2),
    ("LEFT", 1),
    ("FORWARD", 2),
]

for direction, duration in movements:
    droid.move(direction)
    droid.speak(f"Moving {direction}")
    
    # Wait for duration
    start = time.time()
    while time.time() - start < duration:
        droid.process_commands()
        time.sleep(0.05)
    
    droid.move("STOP")

droid.speak("Sequence complete")
droid.stop()
```

## Example 4: High-Priority Emergency Stop

```python
"""Emergency stop with priority queue."""

from core.controller import DroidController
from utils.command_queue import Command

droid = DroidController()
droid.start()

# Start moving
droid.move("FORWARD")

# Simulate some work
import time
time.sleep(1)

# Emergency stop (priority 100, highest)
emergency_stop = Command("stop", {}, priority=100)
droid.command_queue.put(emergency_stop)

# Process immediately
droid.process_commands()

droid.stop()
```

## Example 5: Light Show with Movements

```python
"""Choreographed lights and movement."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

colors = ["cyan", "green", "yellow", "magenta", "blue", "red"]

for color in colors:
    droid.set_light(color, brightness=255)
    droid.speak(color)
    
    droid.move("FORWARD")
    time.sleep(0.5)
    droid.process_commands()
    
    droid.move("STOP")
    time.sleep(0.5)

droid.speak("Light show complete")
droid.stop()
```

## Example 6: Object Tracking

```python
"""Follow detected faces."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

droid.speak("Tracking mode enabled")

try:
    while droid.running:
        # Get current frame
        frame = droid.vision.get_frame() if droid.vision else None
        
        if frame and frame.get("faces"):
            face = frame["faces"][0]
            x, w = face["x"], face["w"]
            frame_center = 640 / 2
            face_center = x + w / 2
            
            # Simple tracking logic
            if face_center < frame_center - 50:
                droid.move("LEFT")
            elif face_center > frame_center + 50:
                droid.move("RIGHT")
            else:
                droid.move("FORWARD")
        else:
            droid.move("STOP")
        
        droid.process_commands()
        time.sleep(0.1)

except KeyboardInterrupt:
    pass
finally:
    droid.stop()
```

## Example 7: Personality Mode

```python
"""Droid with personality - reacting to voice input."""

from core.controller import DroidController
import random

droid = DroidController()
droid.start()

responses = {
    "hello": "H-hello... nice to meet you.",
    "how are you": "I'm... I'm fine. How are you?",
    "dance": "I don't dance, but I can spin...",
    "stop": "O-okay, stopping...",
}

droid.speak("I am ready to chat.")

try:
    while droid.running:
        # Listen
        if droid.voice:
            text = droid.voice.listen(timeout=3)
            
            if text:
                # Get LLM response
                response = droid.voice.get_response(text)
                droid.speak(response)
                
                # Also do physical response
                if "dance" in text.lower():
                    droid.move("LEFT")
                    droid.process_commands()
                    droid.move("RIGHT")
                    droid.process_commands()
                    droid.move("STOP")
                
                droid.process_commands()

except KeyboardInterrupt:
    pass
finally:
    droid.stop()
```

## Example 8: Performance Monitoring

```python
"""Monitor system performance."""

from core.controller import DroidController
import time

droid = DroidController()
droid.start()

start_time = time.time()
command_count = 0

try:
    while droid.running:
        # Queue some commands
        droid.move("FORWARD")
        droid.speak("Test")
        droid.set_light("green")
        
        # Process
        command_count += droid.process_commands()
        
        # Print stats every 10 seconds
        if time.time() - start_time > 10:
            elapsed = time.time() - start_time
            cps = command_count / elapsed
            queue_size = droid.command_queue.size()
            stats = droid.command_queue.stats()
            
            print(f"\n=== STATS ===")
            print(f"Uptime: {elapsed:.1f}s")
            print(f"Commands/sec: {cps:.1f}")
            print(f"Queue size: {queue_size}")
            print(f"Processed: {stats['processed']}")
            print(f"Dropped: {stats['dropped']}")
            
            break
        
        time.sleep(0.05)

finally:
    droid.stop()
```

## Tips

- Always call `droid.process_commands()` in your main loop
- Use high priority (>5) for safety-critical commands
- Lazy loading means first use of a module takes slightly longer
- Check `droid.state_machine.can_accept_commands()` before queuing
- Monitor logs in `logs/` directory for debugging
