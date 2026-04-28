# 🔧 DROID SYSTEM - TROUBLESHOOTING GUIDE

## Problem: System Hangs on Ctrl+C

### Symptoms
- Pressing Ctrl+C doesn't immediately shutdown
- Takes 30+ seconds to stop
- Appears frozen

### Root Causes
1. **TTS Engine Blocking** - pyttsx3 `runAndWait()` can hang on some systems
2. **Thread Joins Timeout** - Waiting for threads to finish cleanup
3. **Unresponsive Hardware** - Serial communication timeout

### Solutions

#### ✅ Quick Fix (Already Applied)
The new Droid v3.0 includes fixes:
- **Non-blocking TTS** - Runs in background thread
- **Forced timeout** - 3-second max shutdown time
- **Better signal handling** - Immediate Ctrl+C response

#### Manual Fix (If using older version)
```python
# In main.py, replace signal handler with:

def signal_handler(sig, frame):
    print("\n\n[!] Shutting down...")
    
    # Force exit after 3 seconds
    import threading
    def force_exit():
        time.sleep(3)
        print("[!] Force exit - timeout")
        os._exit(1)  # Force immediate exit
    
    force_thread = threading.Thread(target=force_exit, daemon=True)
    force_thread.start()
    
    if droid:
        try:
            droid.stop()
        except:
            pass
    
    sys.exit(0)
```

---

## Problem: MediaPipe Import Error

### Symptoms
```
ERROR: module 'mediapipe' has no attribute 'solutions'
```

### Root Causes
1. **Incompatible MediaPipe version** - Old version doesn't have solutions
2. **Incomplete installation** - Missing submodules
3. **Import order issue** - Not importing solutions submodule

### Solutions

#### ✅ Fix (Applied in v3.0)
```python
# Wrapped in try-except with proper error handling
try:
    mp_pose = mp.solutions.pose
    mp_face = mp.solutions.face_detection
except Exception as e:
    logger.warning(f"MediaPipe error: {e}")
    # Falls back to cascade detection
```

#### Manual Fix
```bash
# Reinstall MediaPipe
pip uninstall -y mediapipe
pip install --upgrade mediapipe

# Or use a known working version
pip install mediapipe==0.10.0
```

---

## Problem: System Won't Start

### Symptoms
```
Error during initialization
No output after running main.py
```

### Solutions

#### 1. Run Diagnostics First
```bash
python diagnostic.py
```

This tests:
- ✓ All imports
- ✓ Configuration loading
- ✓ Logger system
- ✓ State machine
- ✓ Command queue
- ✓ Module loading
- ✓ Controller initialization

#### 2. Check Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Enable Debug Output
```bash
# Run with verbose output
python -u main.py 2>&1 | more
```

---

## Problem: Missing Dependencies

### Symptoms
```
ImportError: No module named 'cv2'
ModuleNotFoundError: No module named 'speech_recognition'
```

### Solutions

#### Install All Requirements
```bash
pip install -r requirements.txt
```

#### Install Individual Package
```bash
# OpenCV
pip install opencv-python

# Speech Recognition
pip install SpeechRecognition

# Text-to-Speech
pip install pyttsx3

# Ollama (optional but recommended)
pip install ollama

# MediaPipe (optional)
pip install mediapipe
```

#### Using Virtual Environment
```bash
# Windows
python -m venv droid_env
droid_env\Scripts\activate
pip install -r requirements.txt

# Linux/Mac
python3 -m venv droid_env
source droid_env/bin/activate
pip install -r requirements.txt
```

---

## Problem: Roomba Not Connecting

### Symptoms
```
✗ Failed to connect to Roomba on COM7
Roomba not available - continuing anyway
```

### Solutions

#### 1. Check USB Connection
- Ensure USB cable is properly connected
- Check device manager for COM port
- Try different USB ports

#### 2. Find Correct COM Port
```bash
# Windows - Check Device Manager
# Look for "USB Serial Port" or "Arduino" devices

# Linux
ls -la /dev/ttyUSB* /dev/ttyACM*

# Mac
ls -la /dev/tty.* /dev/cu.*
```

#### 3. Update config.json
```json
{
  "roomba": {
    "uart_port": "COM7"  // Change this to your COM port
  }
}
```

#### 4. Test Connection
```python
from modules.roomba_interface import RoombaInterface

roomba = RoombaInterface()
print(f"Connected: {roomba.connected}")
```

---

## Problem: Camera Not Working

### Symptoms
```
✗ Camera failed to open
Vision not available
```

### Solutions

#### 1. Check Camera Connection
- Ensure webcam is plugged in
- Check if camera is already in use by other app
- Try different USB port

#### 2. Test Camera Index
```python
import cv2

# Try different indices
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Camera found at index {i}")
        cap.release()
```

#### 3. Update config.json
```json
{
  "vision": {
    "camera_index": 0  // Try 1, 2, 3 if 0 doesn't work
  }
}
```

#### 4. Debug Camera
```bash
python diagnostic.py
# Check VisionProcessor section
```

---

## Problem: Voice Input Not Working

### Symptoms
```
Could not understand audio
Microphone error
```

### Solutions

#### 1. Check Microphone
- Ensure microphone is connected
- Test volume levels
- Check privacy settings allow microphone access

#### 2. Test Microphone
```python
import speech_recognition as sr

recognizer = sr.Recognizer()
with sr.Microphone() as source:
    print("Listening...")
    audio = recognizer.listen(source, timeout=5)

try:
    text = recognizer.recognize_google(audio)
    print(f"You said: {text}")
except Exception as e:
    print(f"Error: {e}")
```

#### 3. Adjust Settings
```json
{
  "voice": {
    "recognizer_energy_threshold": 300,  // Increase if too quiet
    "recognizer_pause_threshold": 2.3    // Adjust pause detection
  }
}
```

---

## Problem: Voice Output (TTS) Not Working

### Symptoms
```
TTS engine error
No audio output
```

### Solutions

#### 1. Check Speaker Volume
- Verify system volume is not muted
- Check app volume settings

#### 2. Fix pyttsx3
```bash
# Reinstall
pip uninstall -y pyttsx3
pip install pyttsx3

# Or specify version
pip install pyttsx3==2.90
```

#### 3. Test TTS
```python
import pyttsx3

engine = pyttsx3.init()
engine.say("Hello world")
engine.runAndWait()
```

#### 4. Non-blocking TTS (Recommended)
The v3.0 system runs TTS in background thread automatically.

---

## Problem: LLM Not Responding

### Symptoms
```
Ollama unavailable
LLM error: connection refused
```

### Solutions

#### 1. Install Ollama
Download from: https://ollama.ai

#### 2. Start Ollama Server
```bash
# Windows/Mac - Already running if installed

# Linux
ollama serve
```

#### 3. Pull Model
```bash
ollama pull neural-chat
```

#### 4. Test Connection
```python
from ollama import Client

client = Client()
response = client.chat(
    model="neural-chat",
    messages=[{"role": "user", "content": "Hello"}],
    stream=False
)
print(response['message']['content'])
```

#### 5. Verify in Config
```json
{
  "llm": {
    "model": "neural-chat"  // Must match pulled model
  }
}
```

---

## Problem: High Memory Usage

### Symptoms
- System using 150MB+ RAM
- Stuttering/lag during operation

### Solutions

#### 1. Reduce Frame Size
```json
{
  "vision": {
    "frame_width": 480,     // Was 640
    "frame_height": 360,    // Was 480
    "frame_skip": 3         // Skip more frames
  }
}
```

#### 2. Reduce FPS
```json
{
  "vision": {
    "fps": 15  // Was 30
  }
}
```

#### 3. Monitor Memory
```bash
# During operation, check logs:
ls -lh logs/
# Monitor system resources
```

---

## Problem: Slow Command Response

### Symptoms
- Commands take 100ms+ to execute
- Laggy movement

### Solutions

#### 1. Increase Worker Threads
```json
{
  "performance": {
    "worker_threads": 5  // Was 3
  }
}
```

#### 2. Reduce Command Queue Size
```json
{
  "performance": {
    "command_queue_size": 100  // Increase if dropping commands
  }
}
```

#### 3. Monitor Performance
```python
droid = DroidController()

# Check queue stats
stats = droid.command_queue.stats()
print(f"Processed: {stats['processed']}")
print(f"Dropped: {stats['dropped']}")
```

---

## Quick Diagnostic Command

Run all checks at once:
```bash
python diagnostic.py
```

Output shows:
- ✓ All imports working
- ✓ Configuration loaded
- ✓ Logger ready
- ✓ All systems initialized

---

## Emergency Reset

If system is completely broken:

```bash
# 1. Clear any corrupted cache
rm -rf __pycache__ .pytest_cache

# 2. Reinstall everything
pip uninstall -y -r requirements.txt
pip install -r requirements.txt

# 3. Test diagnostics
python diagnostic.py

# 4. Try main.py
python main.py
```

---

## Getting Help

### Check These First
1. Run `python diagnostic.py`
2. Check `logs/` directory for errors
3. Review this troubleshooting guide
4. Check `QUICK_START.md` for setup

### Common Quick Fixes
- Reinstall requirements: `pip install -r requirements.txt`
- Update config.json for your hardware
- Run diagnostic: `python diagnostic.py`
- Check logs: `cat logs/*.log`

### Performance Tuning
- Increase `frame_skip` for slow camera
- Reduce `fps` if CPU loaded
- Adjust `worker_threads` for CPU cores

---

**Version**: DROID v3.0
**Last Updated**: April 2026

All fixes are included in the new Droid system. Use `python diagnostic.py` to verify your setup!
