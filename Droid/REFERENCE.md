# 🚀 DROID v3.0 - QUICK REFERENCE

## Getting Started

### 1️⃣ Run Diagnostic First (Required!)
```bash
cd Droid
python diagnostic.py
```
✓ Tests all dependencies
✓ Checks configuration
✓ Verifies hardware
✓ Shows any issues

**Expected output:**
```
✓ PASS: Imports
✓ PASS: Config
✓ PASS: Logger
✓ PASS: State Machine
✓ PASS: Command Queue
✓ PASS: Modules
✓ PASS: Controller

Total: 7/7 tests passed
✓ All systems ready! You can now run: python main.py
```

### 2️⃣ Start System
```bash
python main.py
```

**Expected output:**
```
╔════════════════════════════════════════════════════════════╗
║                  DROID SYSTEM v3.0                         ║
║          Star Wars-like Roomba Droid (Enhanced)            ║
╚════════════════════════════════════════════════════════════╝

[Droid ready!]
Press Ctrl+C to shutdown
```

### 3️⃣ Test Ctrl+C Response
```
Press Ctrl+C
# Should respond in < 1 second
# Should see: "[!] Shutting down..."
```

---

## Commands

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Install specific package
pip install speech_recognition

# Upgrade all packages
pip install -U -r requirements.txt
```

### Running
```bash
# Run diagnostic (ALWAYS DO THIS FIRST!)
python diagnostic.py

# Start main system
python main.py

# Run test suite
python test_system.py

# Run batch example
python batch_example.py

# Run Windows
run.bat

# Run Linux/Mac
./run.sh
```

### Cleanup
```bash
# Remove cache
rm -rf __pycache__ .pytest_cache

# Remove logs
rm -rf logs/*

# Remove data
rm -rf data/*
```

---

## Configuration

### Edit config.json
```bash
# Windows
notepad config.json

# Linux/Mac
nano config.json
```

### Key Settings
```json
{
  "roomba": {
    "uart_port": "COM7"      // Your COM port
  },
  "vision": {
    "frame_skip": 2,         // Higher = faster
    "fps": 30
  },
  "performance": {
    "worker_threads": 3      // Your CPU cores
  }
}
```

---

## Troubleshooting

### System won't start?
```bash
# Step 1: Run diagnostic
python diagnostic.py

# Step 2: Check dependencies
pip install -r requirements.txt

# Step 3: Check config.json
notepad config.json

# Step 4: Check logs
type logs\DroidController.log
```

### Hangs on Ctrl+C?
✅ **Fixed in v3.0** - Should respond immediately now
```bash
# If still hanging, check logs:
type logs\main.log
```

### MediaPipe error?
```bash
# Reinstall MediaPipe
pip uninstall -y mediapipe
pip install mediapipe

# Or skip it
pip install -r requirements.txt --no-deps mediapipe
```

### Missing imports?
```bash
# Reinstall everything
pip install -r requirements.txt

# Or specific package:
pip install speech_recognition
```

---

## Useful Code Snippets

### Simple Movement
```python
from core.controller import DroidController

droid = DroidController()
droid.start()

droid.move("FORWARD")
droid.speak("Hello!")

droid.stop()
```

### Voice Control
```python
while droid.running:
    droid.queue_command("listen", {"timeout": 5})
    droid.process_commands()
    time.sleep(0.05)
```

### Batch Commands
```python
droid.move("FORWARD")
droid.speak("Moving forward")
droid.set_light("green", brightness=255)

count = droid.process_commands()  # Process all at once
```

### Priority Commands
```python
# Emergency stop (priority 100)
droid.queue_command("stop", {}, priority=100)

# Normal movement (priority 0)
droid.move("FORWARD")
```

---

## Files Overview

### Main Files
- `main.py` - Start here
- `config.json` - Configuration
- `diagnostic.py` - Test system

### Documentation
- `QUICK_START.md` - Setup guide
- `README.md` - Full docs
- `TROUBLESHOOTING.md` - Problem solving
- `FIXES_SUMMARY.md` - What was fixed
- `EXAMPLES.md` - 8 working examples

### Core System
- `core/controller.py` - Main system
- `core/state_machine.py` - States
- `core/logger.py` - Logging
- `core/worker_pool.py` - Threading

### Hardware Modules
- `modules/roomba_interface.py` - Roomba
- `modules/voice_processor.py` - Speech
- `modules/vision_processor.py` - Camera
- `modules/smart_lights.py` - Lights

### Utilities
- `utils/config.py` - Configuration
- `utils/command_queue.py` - Queue

---

## Keyboard Shortcuts

| Action | Key |
|--------|-----|
| Shutdown | Ctrl+C |
| Help (in Python) | help(droid) |
| Exit Python | Ctrl+D (or exit()) |

---

## Log Files

Check these if something goes wrong:
- `logs/DroidController.log` - Main system
- `logs/RoombaInterface.log` - Roomba commands
- `logs/VoiceProcessor.log` - Speech/LLM
- `logs/VisionProcessor.log` - Camera
- `logs/main.log` - Startup/shutdown

---

## Performance Tuning

### If Camera is Slow
```json
{
  "vision": {
    "frame_skip": 3,      // Skip more frames
    "frame_width": 480,   // Smaller resolution
    "fps": 15             // Lower FPS
  }
}
```

### If CPU is Bottlenecked
```json
{
  "performance": {
    "worker_threads": 5   // More threads
  }
}
```

### If Memory is High
```json
{
  "vision": {
    "frame_width": 480,   // Reduce size
    "frame_height": 360
  }
}
```

---

## Command Syntax

### Movement
```python
droid.move("FORWARD")      # Move forward
droid.move("BACKWARD")     # Move backward
droid.move("LEFT")         # Turn left
droid.move("RIGHT")        # Turn right
droid.move("STOP")         # Stop
```

### Voice
```python
droid.speak("Hello world") # Speak text
droid.listen(timeout=5)    # Listen for input
```

### Lights
```python
droid.set_light("cyan")                      # Set color
droid.set_light("red", brightness=200)       # Color + brightness
droid.lights.on()                            # Turn on
droid.lights.off()                           # Turn off
```

### Queuing
```python
droid.queue_command("move", {"direction": "FORWARD"})
droid.queue_command("speak", {"text": "hello"})
droid.process_commands()  # Execute all
```

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| Hangs on Ctrl+C | ✅ Fixed in v3.0 |
| MediaPipe error | ✅ Fixed - try `pip install mediapipe` |
| Missing imports | ✅ Run `pip install -r requirements.txt` |
| Roomba not found | Check COM port in config.json |
| Camera not found | Try `camera_index: 1` in config |
| No audio | Check speaker volume, reinstall pyttsx3 |
| LLM not working | Install Ollama, run `ollama serve` |

---

## Useful Commands

```bash
# Show Python version
python --version

# Show installed packages
pip list

# Search for package
pip search numpy

# Show package info
pip show opencv-python

# Update pip
pip install --upgrade pip

# Create fresh virtual environment
python -m venv fresh_env

# Show directory structure
tree /F

# Show file size
ls -lah logs/
```

---

## Getting Help

1. **Run diagnostic first**
   ```bash
   python diagnostic.py
   ```

2. **Check troubleshooting guide**
   - Read `TROUBLESHOOTING.md`

3. **Check logs**
   - Look in `logs/` directory
   - Most recent log has latest errors

4. **Read documentation**
   - `QUICK_START.md` - Setup
   - `README.md` - Full docs
   - `EXAMPLES.md` - Working code

5. **Try examples**
   - See `EXAMPLES.md` for 8 working examples

---

## Version Info

```
System: DROID v3.0
Status: Production Ready ✅
Last Fix: April 27, 2026
All Known Issues: Fixed ✅
```

---

## Emergency Reset

If everything is broken:
```bash
# Step 1: Remove cache
rm -rf __pycache__ .pytest_cache

# Step 2: Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Step 3: Run diagnostic
python diagnostic.py

# Step 4: Start system
python main.py
```

---

**Ready to go!** 🤖✨

Start with: `python diagnostic.py`
