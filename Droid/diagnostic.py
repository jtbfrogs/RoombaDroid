#!/usr/bin/env python3
"""
Quick diagnostic script to test Droid system components.
Run this to identify any issues before starting main.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test if all dependencies can be imported."""
    print("\n[TEST] Checking imports...")
    
    deps = {
        "numpy": "numpy",
        "cv2": "opencv-python",
        "pyaudio": "pyaudio",
        "speech_recognition": "SpeechRecognition",
        "pyttsx3": "pyttsx3",
        "requests": "requests",
        "serial": "pyserial",
    }
    
    missing = []
    for module, package in deps.items():
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError as e:
            print(f"  ✗ {module}")
            print(f"    └─ Error: {e}")
            print(f"    └─ Fix: pip install {package}")
            missing.append(package)
        except Exception as e:
            print(f"  ✗ {module} - unexpected error")
            print(f"    └─ Error: {type(e).__name__}: {e}")
            missing.append(package)
    
    # Optional but recommended
    optional = {
        "mediapipe": "mediapipe",
        "ollama": "ollama",
    }
    
    for module, package in optional.items():
        try:
            __import__(module)
            print(f"  ✓ {module} (optional)")
        except ImportError:
            print(f"  ○ {module} (optional) - not installed")
        except Exception as e:
            print(f"  ⚠ {module} (optional) - error: {type(e).__name__}")
    
    if missing:
        print(f"\n  Action required: pip install {' '.join(missing)}")
        return False
    
    return True

def test_config():
    """Test configuration loading."""
    print("\n[TEST] Configuration...")
    try:
        from utils.config import config
        
        # Test getting values
        roomba_port = config.get("roomba.uart_port")
        vision_fps = config.get("vision.fps")
        
        print(f"  ✓ Config loaded")
        print(f"    ├─ Roomba port: {roomba_port}")
        print(f"    └─ Vision FPS: {vision_fps}")
        return True
    except FileNotFoundError as e:
        print(f"  ✗ Config file not found")
        print(f"    └─ Expected: {e}")
        print(f"    └─ Fix: Ensure config.json exists in the Droid directory")
        return False
    except Exception as e:
        print(f"  ✗ Config error")
        print(f"    └─ Error: {type(e).__name__}: {e}")
        print(f"    └─ Fix: Check config.json syntax and values")
        return False

def test_logger():
    """Test logging system."""
    print("\n[TEST] Logger...")
    try:
        from core.logger import logger
        
        logger.init("logs")
        log = logger.get_logger("diagnostic")
        log.info("✓ Logging works")
        print(f"  ✓ Logger initialized")
        print(f"    └─ Logs location: logs/")
        return True
    except PermissionError as e:
        print(f"  ✗ Logger initialization failed - permission denied")
        print(f"    └─ Error: {e}")
        print(f"    └─ Fix: Check write permissions for logs/ directory")
        return False
    except Exception as e:
        print(f"  ✗ Logger error")
        print(f"    └─ Error: {type(e).__name__}: {e}")
        import traceback
        print(f"    └─ Traceback: {traceback.format_exc()}")
        return False

def test_state_machine():
    """Test state machine."""
    print("\n[TEST] State Machine...")
    try:
        from core.state_machine import StateMachine, DroidState
        
        sm = StateMachine()
        
        # Try a transition
        sm.transition(DroidState.LISTENING)
        print(f"  ✓ State machine works")
        print(f"    └─ Current state: {sm.current_state.value}")
        return True
    except Exception as e:
        print(f"  ✗ State machine error")
        print(f"    └─ Error: {type(e).__name__}: {e}")
        print(f"    └─ Fix: Check core/state_machine.py for issues")
        return False

def test_command_queue():
    """Test command queue."""
    print("\n[TEST] Command Queue...")
    try:
        from utils.command_queue import Command, CommandQueue
        
        queue = CommandQueue()
        
        cmd = Command("move", {"direction": "FORWARD"})
        queue.put(cmd)
        
        retrieved = queue.get()
        if retrieved:
            print(f"  ✓ Command queue works")
            print(f"    - Queue size: {queue.size()}")
            return True
        else:
            print(f"  ✗ Could not retrieve command")
            return False
    except Exception as e:
        print(f"  ✗ Command queue error: {e}")
        return False

def test_controller():
    """Test controller initialization."""
    print("\n[TEST] DroidController...")
    try:
        from core.controller import DroidController
        
        print("  Initializing (this may take 1-2 seconds)...")
        droid = DroidController()
        
        print(f"  ✓ Controller initialized")
        print(f"    - State: {droid.state_machine.current_state.value}")
        
        # Don't start, just test init
        return True
    except Exception as e:
        print(f"  ✗ Controller error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_modules():
    """Test module loading."""
    print("\n[TEST] Hardware Modules...")
    
    results = []
    
    # Test each module individually
    try:
        from modules.voice_processor import VoiceProcessor
        print("  ✓ VoiceProcessor imports")
        results.append(True)
    except Exception as e:
        print(f"  ✗ VoiceProcessor error: {e}")
        results.append(False)
    
    try:
        from modules.vision_processor import VisionProcessor
        print("  ✓ VisionProcessor imports")
        results.append(True)
    except Exception as e:
        print(f"  ✗ VisionProcessor error: {e}")
        results.append(False)
    
    try:
        from modules.roomba_interface import RoombaInterface
        print("  ✓ RoombaInterface imports")
        results.append(True)
    except Exception as e:
        print(f"  ✗ RoombaInterface error: {e}")
        results.append(False)
    

    
    return all(results)

def main():
    """Run all diagnostics."""
    print("\n" + "=" * 60)
    print("DROID SYSTEM DIAGNOSTIC")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Config", test_config()))
    results.append(("Logger", test_logger()))
    results.append(("State Machine", test_state_machine()))
    results.append(("Command Queue", test_command_queue()))
    results.append(("Modules", test_modules()))
    results.append(("Controller", test_controller()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All systems ready! You can now run: python main.py")
    else:
        print(f"\n✗ {total - passed} issue(s) found. Check above for details.")
        print("\nCommon fixes:")
        print("  1. Install missing packages: pip install -r requirements.txt")
        print("  2. Check config.json for correct settings")
        print("  3. Ensure camera is connected (if using vision)")
        print("  4. Check USB cable for Roomba (if using Roomba)")
    
    print("\n" + "=" * 60 + "\n")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
