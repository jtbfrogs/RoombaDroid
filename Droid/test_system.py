"""Test suite for droid system components."""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.logger import logger
from core.controller import DroidController
from core.state_machine import DroidState
from utils.config import config
from utils.command_queue import Command, CommandQueue

def test_logger():
    """Test logging system."""
    print("\n[TEST] Logger System")
    logger.init("logs")
    log = logger.get_logger("test")
    
    log.debug("Debug message")
    log.info("Info message")
    log.warning("Warning message")
    log.error("Error message")
    
    print("[OK] Logging works")

def test_config():
    """Test configuration management."""
    print("\n[TEST] Configuration")
    
    val1 = config.get("roomba.uart_port")
    print(f"  Roomba port: {val1}")
    
    val2 = config.get("vision.frame_skip")
    print(f"  Frame skip: {val2}")
    
    val3 = config.get("nonexistent.value", "default")
    print(f"  Missing value: {val3}")
    
    print("[OK] Config works")

def test_state_machine():
    """Test state machine."""
    print("\n[TEST] State Machine")
    from core.state_machine import StateMachine, DroidState
    
    sm = StateMachine()
    
    # Valid transition
    assert sm.transition(DroidState.LISTENING)
    print(f"  State: {sm.current_state.value}")
    
    # Valid transition
    assert sm.transition(DroidState.THINKING)
    print(f"  State: {sm.current_state.value}")
    
    # Invalid transition (can't go from THINKING to TRACKING)
    assert not sm.transition(DroidState.TRACKING)
    print(f"  State: {sm.current_state.value} (invalid transition rejected)")
    
    print("[OK] State machine works")

def test_command_queue():
    """Test command queue."""
    print("\n[TEST] Command Queue")
    
    queue = CommandQueue(max_size=10)
    
    # Add commands
    cmd1 = Command("move", {"direction": "FORWARD"}, priority=0)
    cmd2 = Command("speak", {"text": "hello"}, priority=5)
    cmd3 = Command("stop", {}, priority=10)
    
    assert queue.put(cmd1)
    assert queue.put(cmd2)
    assert queue.put(cmd3)
    
    print(f"  Queue size: {queue.size()}")
    
    # Get commands (should be in priority order: 3, 2, 1)
    assert queue.get() == cmd3
    print(f"  Got priority 10 command")
    
    assert queue.get() == cmd2
    print(f"  Got priority 5 command")
    
    assert queue.get() == cmd1
    print(f"  Got priority 0 command")
    
    print("[OK] Command queue works")

def test_controller_init():
    """Test controller initialization."""
    print("\n[TEST] DroidController Initialization")
    
    droid = DroidController()
    print(f"  State: {droid.state_machine.current_state.value}")
    print(f"  Running: {droid.running}")
    
    droid.start()
    print(f"  Started")
    print(f"  Running: {droid.running}")
    
    droid.stop()
    print(f"  Stopped")
    
    print("[OK] Controller works")

def test_command_queueing():
    """Test command queueing."""
    print("\n[TEST] Command Queueing")
    
    droid = DroidController()
    droid.start()
    
    # Queue commands
    assert droid.queue_command("move", {"direction": "FORWARD"})
    assert droid.queue_command("speak", {"text": "hello"})
    assert droid.queue_command("stop")
    
    print(f"  Queue size: {droid.command_queue.size()}")
    
    # Process commands
    processed = droid.process_commands()
    print(f"  Processed {processed} commands")
    
    droid.stop()
    print("[OK] Command queueing works")

def test_roomba_interface():
    """Test Roomba interface (dry run)."""
    print("\n[TEST] Roomba Interface")
    
    try:
        from modules.roomba_interface import RoombaInterface
        
        # This will fail if no Roomba connected, which is expected
        print("  Attempting connection...")
        roomba = RoombaInterface()
        
        if roomba.connected:
            print("  [OK] Roomba connected")
            roomba.stop()
        else:
            print("  [FAIL] Roomba not connected (this is OK in test environment)")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        print("  (This is OK - Roomba hardware may not be available)")

def test_audio_output():
    """Test audio output device directly via winsound (bypasses pyttsx3)."""
    print("\n[TEST] Audio Output (winsound)")
    try:
        import winsound
        print("  Playing startup beep sequence...")
        beeps = [(1047, 120), (1319, 120), (1568, 120), (2093, 250)]
        for freq, duration in beeps:
            winsound.Beep(freq, duration)
        print("  [OK] Beep sequence played - did you hear 4 ascending tones?")
    except ImportError:
        print("  [--] winsound not available (non-Windows platform)")
    except Exception as e:
        print(f"  [FAIL] Beep error: {e}")
        print("  Check: Control Panel -> Sound -> Playback devices")


def test_voice_processor():
    """Test voice processor and microphone availability."""
    print("\n[TEST] Voice Processor")

    try:
        from modules.voice_processor import VoiceProcessor

        print("  Initializing...")
        voice = VoiceProcessor()
        print("  [OK] Voice processor initialized")
    except Exception as e:
        print(f"  [FAIL] Voice processor init error: {e}")
        return

    # Check TTS engine
    if voice._engine:
        print("  [OK] TTS engine available")
    else:
        print("  [FAIL] TTS engine not available")

    # Check speech recognizer
    if voice._recognizer:
        print("  [OK] Speech recognizer available")
    else:
        print("  [FAIL] Speech recognizer not available")

    # Check microphone
    print("  Checking microphone...")
    try:
        import speech_recognition as sr
        mics = sr.Microphone.list_microphone_names()
        if mics:
            print(f"  [OK] {len(mics)} microphone(s) found:")
            for i, name in enumerate(mics):
                print(f"    [{i}] {name}")
        else:
            print("  [FAIL] No microphones detected")
    except Exception as e:
        print(f"  [FAIL] Microphone check error: {e}")

    # Check LLM
    if voice._llm:
        print("  [OK] Ollama LLM available")
    else:
        print("  [WARN] Ollama LLM not available (optional)")

    print("  (Live listen test skipped - run manually to test audio capture)")

def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DROID SYSTEM TEST SUITE")
    print("=" * 60)
    
    try:
        test_logger()
        test_config()
        test_state_machine()
        test_command_queue()
        test_controller_init()
        test_command_queueing()
        test_roomba_interface()
        test_audio_output()
        test_voice_processor()
        
        print("\n" + "=" * 60)
        print("[OK] TESTS COMPLETE")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()
