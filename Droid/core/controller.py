"""Central droid orchestrator  -  wires together all subsystems."""
import time
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
    """Coordinates the state machine, command queue, worker pool,
    and hardware modules.

    Hardware modules are lazily initialised on first access.  If a module
    fails to initialise, a sentinel flag is set so the failed init is not
    retried on every subsequent access.

    Typical usage::

        droid = DroidController()
        droid.start()

        droid.move("FORWARD")
        droid.speak("Hello!")
        droid.listen()

        while droid.running:
            droid.process_commands()
            time.sleep(0.05)

        droid.stop()
    """

    def __init__(self) -> None:
        self.log = logger.get_logger("DroidController")
        self.log.info("=" * 60)
        self.log.info("DROID SYSTEM v3.0 STARTING")
        self.log.info("=" * 60)

        # Core systems
        self.state_machine = StateMachine()
        self.command_queue = CommandQueue(
            max_size=config.get("performance.command_queue_size", 50)
        )
        self.worker_pool = WorkerPool(
            num_workers=config.get("performance.worker_threads", 3)
        )

        # Hardware module instances (populated lazily)
        self._roomba: Optional[RoombaInterface] = None
        self._vision: Optional[VisionProcessor] = None
        self._voice:  Optional[VoiceProcessor]  = None

        # Failure sentinels  -  prevents re-attempting a broken init every call
        self._roomba_failed = False
        self._vision_failed = False
        self._voice_failed  = False

        self.running = False

        self._register_handlers()
        self._register_callbacks()

        self.log.info("[OK] DroidController ready")

    # ------------------------------------------------------------------
    # Lazy-loaded hardware properties
    # ------------------------------------------------------------------

    @property
    def roomba(self) -> Optional[RoombaInterface]:
        if self._roomba_failed:
            return None
        if self._roomba is None:
            try:
                self._roomba = RoombaInterface()
            except Exception as exc:
                self.log.error("Roomba init failed: %s", exc)
                self._roomba_failed = True
                return None
        return self._roomba if self._roomba.connected else None

    @property
    def vision(self) -> Optional[VisionProcessor]:
        if self._vision_failed:
            return None
        if self._vision is None:
            try:
                self._vision = VisionProcessor()
                self._vision.start()
            except Exception as exc:
                self.log.error("Vision init failed: %s", exc)
                self._vision_failed = True
                return None
        return self._vision

    @property
    def voice(self) -> Optional[VoiceProcessor]:
        if self._voice_failed:
            return None
        if self._voice is None:
            try:
                self._voice = VoiceProcessor()
            except Exception as exc:
                self.log.error("Voice init failed: %s", exc)
                self._voice_failed = True
                return None
        return self._voice

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        reg = self.command_queue.register_handler
        reg("move",   self._handle_move)
        reg("speak",  self._handle_speak)
        reg("listen", self._handle_listen)
        reg("stop",   self._handle_stop)

    def _register_callbacks(self) -> None:
        self.state_machine.register_callback(DroidState.ERROR, self._on_error)

    # ------------------------------------------------------------------
    # State callbacks
    # ------------------------------------------------------------------

    def _on_error(self, prev: DroidState, new: DroidState) -> None:
        """Emergency stop whenever the machine enters the ERROR state."""
        if self.roomba:
            self.roomba.send_command("STOP")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _handle_move(self, data: dict) -> None:
        if not self.roomba or not self.state_machine.can_accept_commands():
            return
        direction = data.get("direction", "STOP").upper()
        self.state_machine.transition(DroidState.MOVING)
        self.roomba.send_command(direction)
        self.worker_pool.submit(self._return_to_idle, delay=0.5)

    def _handle_speak(self, data: dict) -> None:
        if self.voice:
            self.voice.speak(data.get("text", ""))

    def _handle_listen(self, data: dict) -> None:
        if not self.voice:
            return

        self.state_machine.transition(DroidState.LISTENING)
        self.log.info("Listening...")
        text = self.voice.listen(timeout=data.get("timeout", 5.0))

        if not text:
            self.log.debug("Nothing heard")
            self.state_machine.transition(DroidState.IDLE)
            return

        self.log.info("Heard: %s", text)
        self.state_machine.transition(DroidState.THINKING)

        # Check for movement commands before hitting the LLM.
        movement = self.voice.parse_command(text)
        if movement:
            self.log.info("Matched command: %s", movement)
            self.move(movement)
            self.voice.speak("okay")
        else:
            self.log.info("No command match - sending to LLM")
            # Submit to worker pool so the listen loop is not blocked
            # for the duration of the LLM response (~28 s on slow hardware).
            # get_response() streams and speaks internally; we don't wait.
            self.worker_pool.submit(self.voice.get_response, text)

        self.state_machine.transition(DroidState.IDLE)

    def _handle_stop(self, data: dict) -> None:
        if self.roomba:
            self.roomba.send_command("STOP")
        self.state_machine.transition(DroidState.IDLE)

    def _return_to_idle(self, delay: float = 0.5) -> None:
        time.sleep(delay)
        # Guard against the system having shut down during the delay.
        if self.running:
            self.state_machine.transition(DroidState.IDLE)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Eagerly initialize all hardware modules and log their status.

        Call this once after start().  Without it, modules are only
        initialized on first use (lazy), so nothing happens until a
        command references them.
        """
        self.log.info("Initializing hardware...")

        # Roomba
        if self.roomba:
            self.log.info("Roomba : connected on %s", self._roomba.uart_port)
        else:
            self.log.warning("Roomba : not connected  -  movement disabled")

        # Vision - check _cap directly: the VisionProcessor object may
        # exist even if the camera failed to open (no exception is raised,
        # _cap is just set to None).
        if self.vision and self._vision._cap is not None:
            self.log.info("Vision : camera ready")
        else:
            self.log.warning("Vision : camera not available")

        # Voice (already loaded by start())
        if self._voice and self._voice._engine:
            self.log.info("Voice  : TTS + STT ready")
        else:
            self.log.warning("Voice  : TTS or STT not available")

        # Calibrate microphone for current ambient noise level
        if self._voice:
            self._voice.calibrate()

        self.log.info("Hardware initialization complete")

    def start(self) -> None:
        """Start the worker pool and announce readiness."""
        if self.running:
            return
        self.running = True
        self.worker_pool.start()
        self.log.info("[OK] Droid started")
        if self.voice:
            self.voice.speak("Hello, I am awake.")

    def stop(self) -> None:
        """Gracefully shut down all subsystems."""
        if not self.running:
            return
        self.running = False
        self.state_machine.transition(DroidState.SHUTDOWN)
        self.log.info("Shutting down...")

        if self._roomba:
            try:
                self._roomba.stop()
            except Exception as exc:
                self.log.warning("Roomba stop error: %s", exc)

        if self._vision:
            try:
                self._vision.stop()
            except Exception as exc:
                self.log.warning("Vision stop error: %s", exc)

        if self._voice:
            try:
                self._voice.stop()
            except Exception as exc:
                self.log.warning("Voice stop error: %s", exc)

        self.worker_pool.stop()
        self.log.info("[OK] Shutdown complete")

    # ------------------------------------------------------------------
    # Public command API
    # ------------------------------------------------------------------

    def queue_command(
        self, command_type: str, data: dict = None, priority: int = 0
    ) -> bool:
        """Queue any command by type. Returns False if the queue is full."""
        return self.command_queue.put(Command(command_type, data, priority))

    def move(self, direction: str) -> bool:
        return self.queue_command("move", {"direction": direction})

    def speak(self, text: str) -> bool:
        return self.queue_command("speak", {"text": text})

    def listen(self, timeout: float = 5.0) -> bool:
        return self.queue_command("listen", {"timeout": timeout})

    def process_commands(self, timeout: float = 0.1) -> int:
        """Drain the command queue; returns the number of commands executed."""
        count = 0
        while True:
            cmd = self.command_queue.get(timeout=timeout)
            if not cmd:
                break
            self.command_queue.execute(cmd)
            count += 1
        return count
