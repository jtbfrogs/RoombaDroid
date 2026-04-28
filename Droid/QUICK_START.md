# Quick Start Guide

## Installation

1. **Clone/Copy to Droid folder**
```bash
cd Droid
```

2. **Create virtual environment**
```bash
python -m venv droid_env
droid_env\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

## Quick Commands

```python
from core.controller import DroidController

droid = DroidController()
droid.start()

# Move
droid.move("FORWARD")
droid.move("BACKWARD")
droid.move("LEFT")
droid.move("RIGHT")

# Speak
droid.speak("Hello world!")

# Listen and respond
droid.listen()

# Control lights
droid.set_light("cyan", brightness=100)

# Stop everything
droid.stop()
```

## Configuration

Edit `config.json` to customize:
- UART port for Roomba
- Camera settings (frame size, FPS)
- Voice settings (rate, volume)
- Light settings (API key, device ID)
- Performance settings (threads, queue size)

## Troubleshooting

- **ImportError: No module named...** → Run `pip install -r requirements.txt`
- **Cannot open serial port** → Check Roomba USB cable and COM port in config
- **Camera not working** → Verify camera index (0 = default, try 1 if needed)
- **No audio output** → Check speaker volume and TTS engine

## Next Steps

See README.md for full documentation and architecture overview.
