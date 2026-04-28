"""Main droid controller - orchestrates all systems."""
import time
import signal
import sys
from typing import Optional
from core.logger import logger
from core.state_machine import StateMachine, DroidState
from core.worker_pool import WorkerPool
from utils.command_queue import CommandQueue, Command
from modules.roomba_interface import RoombaInterface
from modules.vision_processor import VisionProcessor
from modules.voice_processor import VoiceProcessor
from utils.config import config

class DroidController:
    """Central command orchestrator."""
    
    def __init__(self):
        self.log = logger.get_logger("DroidController")
        self.log.info("=" * 60)
        self.log.info("DROID SYSTEM v3.0 STARTING")
        self.log.info("=" * 60)
        
        # Core systems
        self.state_machine = StateMachine()
        self.command_queue = CommandQueue(max_size=config.get("performance.command_queue_size", 50))
        self.worker_pool = WorkerPool(num_workers=config.get("performance.worker_threads", 3))
        
        # Hardware (lazy-loaded)
        self._roomba: Optional[RoombaInterface] = None
        self._vision: Optional[VisionProcessor] = None
        self._voice: Optional[VoiceProcessor] = None
        
        # State
        self.running = False
        
        # Register handlers
        self._register_handlers()
        self._register_callbacks()
        
        self.log.info("✓ DroidController ready")
    
    @property
    def roomba(self) -> Optional[RoombaInterface]:
        """Lazy load Roomba."""
        if self._roomba is None:
            try:
                self._roomba = RoombaInterface()
            except Exception as e:
                self.log.error(f"Roomba load error: {e}")
        return self._roomba if self._roomba and self._roomba.connected else None
    
    @property
    def vision(self) -> Optional[VisionProcessor]:
        """Lazy load Vision."""
        if self._vision is None:
            try:
                self._vision = VisionProcessor()
                self._vision.start()
            except Exception as e:
                self.log.error(f"Vision load error: {e}")
        return self._vision
    
    @property
    def voice(self) -> Optional[VoiceProcessor]:
        """Lazy load Voice."""
        if self._voice is None:
            try:
                self._voice = VoiceProcessor()
            except Exception as e:
                self.log.error(f"Voice load error: {e}")
        return self._voice
    

    
    def _register_handlers(self):
        """Register command handlers."""
        self.command_queue.register_handler("move", self._handle_move)
        self.command_queue.register_handler("speak", self._handle_speak)
        self.command_queue.register_handler("listen", self._handle_listen)
        self.command_queue.register_handler("stop", self._handle_stop)
    
    def _register_callbacks(self):
        """Register state callbacks."""
        self.state_machine.register_callback(DroidState.IDLE, self._on_idle)
        self.state_machine.register_callback(DroidState.LISTENING, self._on_listening)
        self.state_machine.register_callback(DroidState.MOVING, self._on_moving)
        self.state_machine.register_callback(DroidState.ERROR, self._on_error)
    
    def _on_idle(self, prev, new):
        """Entering IDLE state."""
        pass
    
    def _on_listening(self, prev, new):
        """Entering LISTENING state."""
        pass
    
    def _on_moving(self, prev, new):
        """Entering MOVING state."""
        pass
    
    def _on_error(self, prev, new):
        """Entering ERROR state."""
        if self.roomba:
            self.roomba.send_command("STOP")
    
    def _handle_move(self, data: dict):
        """Process movement command."""
        if not self.roomba or not self.state_machine.can_accept_commands():
            return
        
        direction = data.get("direction", "STOP").upper()
        self.state_machine.transition(DroidState.MOVING)
        self.roomba.send_command(direction)
        
        # Auto-return to idle after move
        self.worker_pool.submit(self._delay_idle, 0.5)
    
    def _handle_speak(self, data: dict):
        """Process speak command."""
        text = data.get("text", "")
        if self.voice:
            self.voice.speak(text)
    
    def _handle_listen(self, data: dict):
        """Process listen command."""
        if not self.voice:
            return
        
        self.state_machine.transition(DroidState.LISTENING)
        text = self.voice.listen(timeout=data.get("timeout", 5))
        
        if text:
            self.state_machine.transition(DroidState.THINKING)
            response = self.voice.get_response(text)
            self.voice.speak(response)
        
        self.state_machine.transition(DroidState.IDLE)
    
    def _handle_stop(self, data: dict):
        """Process stop command."""
        if self.roomba:
            self.roomba.send_command("STOP")
        self.state_machine.transition(DroidState.IDLE)
    
    def _delay_idle(self, delay: float):
        """Return to idle after delay."""
        time.sleep(delay)
        self.state_machine.transition(DroidState.IDLE)
    
    def start(self):
        """Start the droid system."""
        if self.running:
            return
        
        self.running = True
        self.worker_pool.start()
        
        self.log.info("✓ Droid started")
        
        # Initial greeting
        if self.voice:
            self.voice.speak("Hello, I am awake.")
    
    def stop(self):
        """Shutdown the droid system with timeout."""
        if not self.running:
            return
        
        self.running = False
        self.state_machine.transition(DroidState.SHUTDOWN)
        
        self.log.info("Shutting down...")
        
        # Cleanup with timeouts
        try:
            # Stop with short timeout (1 second each)
            if self._roomba:
                try:
                    self._roomba.stop()
                except Exception as e:
                    self.log.warning(f"Roomba stop error: {e}")
            
            if self._vision:
                try:
                    self._vision.stop()
                except Exception as e:
                    self.log.warning(f"Vision stop error: {e}")
            
            # Stop worker pool (1 second timeout)
            self.worker_pool.stop()
        
        except Exception as e:
            self.log.error(f"Cleanup error: {e}")
        
        self.log.info("✓ Droid shutdown complete")
    
    def queue_command(self, command_type: str, data: dict = None, priority: int = 0) -> bool:
        """Queue a command for execution."""
        cmd = Command(command_type, data, priority)
        return self.command_queue.put(cmd)
    
    def move(self, direction: str):
        """Queue movement command."""
        return self.queue_command("move", {"direction": direction})
    
    def speak(self, text: str):
        """Queue speak command."""
        return self.queue_command("speak", {"text": text})
    
    def listen(self, timeout: float = 5.0):
        """Queue listen command."""
        return self.queue_command("listen", {"timeout": timeout})
    
    def process_commands(self, timeout: float = 0.1) -> int:
        """Process queued commands. Returns number processed."""
        count = 0
        while True:
            cmd = self.command_queue.get(timeout=timeout)
            if not cmd:
                break
            
            self.command_queue.execute(cmd)
            count += 1
        
        return count
