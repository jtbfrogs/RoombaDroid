"""Priority command queue with typed handler registry."""
import queue
import threading
import time
from typing import Callable, Dict, List, Optional

from core.logger import logger


class Command:
    """Immutable command with priority ordering.

    Higher *priority* values are dequeued first.
    Equal-priority commands are served in insertion order (FIFO).
    """

    __slots__ = ("command_type", "data", "priority", "created_at")

    def __init__(
        self,
        command_type: str,
        data: Optional[Dict] = None,
        priority: int = 0,
    ) -> None:
        self.command_type = command_type
        self.data = data or {}
        self.priority = priority
        self.created_at = time.monotonic()

    def __repr__(self) -> str:
        return f"Command({self.command_type!r}, priority={self.priority})"


class CommandQueue:
    """Thread-safe priority queue that dispatches commands to registered handlers.

    PriorityQueue is a min-heap, so we store (-priority, seq, command) to
    ensure that higher-priority commands are dequeued first, with FIFO
    tiebreaking via an auto-incrementing sequence number.
    """

    def __init__(self, max_size: int = 50) -> None:
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._handlers: Dict[str, List[Callable]] = {}
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._stats = {"processed": 0, "dropped": 0}
        self.log = logger.get_logger("CommandQueue")

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def put(self, command: Command, timeout: Optional[float] = None) -> bool:
        """Enqueue a command. Returns False if the queue is full."""
        with self._seq_lock:
            seq = self._seq
            self._seq += 1

        entry = (-command.priority, seq, command)
        try:
            self._queue.put(entry, timeout=timeout)
            return True
        except queue.Full:
            self._stats["dropped"] += 1
            self.log.warning("Queue full — dropped: %s", command)
            return False

    def get(self, timeout: float = 0.1) -> Optional[Command]:
        """Return the next command, or None if empty within *timeout*."""
        try:
            _neg_priority, _seq, command = self._queue.get(timeout=timeout)
            return command
        except queue.Empty:
            return None

    def size(self) -> int:
        return self._queue.qsize()

    def stats(self) -> Dict:
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Handler registry
    # ------------------------------------------------------------------

    def register_handler(self, command_type: str, handler: Callable) -> None:
        """Register a callable to handle commands of *command_type*."""
        self._handlers.setdefault(command_type, []).append(handler)

    def execute(self, command: Command) -> bool:
        """Dispatch *command* to all registered handlers.

        Returns False if no handler exists or a handler raises.
        """
        handlers = self._handlers.get(command.command_type)
        if not handlers:
            self.log.warning("No handler registered for: %s", command.command_type)
            return False

        for handler in handlers:
            try:
                handler(command.data)
                self._stats["processed"] += 1
            except Exception as exc:
                self.log.error(
                    "Handler error for %s: %s", command.command_type, exc
                )
                return False

        return True
