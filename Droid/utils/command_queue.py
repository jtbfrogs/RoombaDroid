"""Optimized command queue with priority and batching."""
import queue
import threading
from typing import Callable, Dict, List, Optional
from core.logger import logger

class Command:
    """Immutable command object."""
    
    __slots__ = ('command_type', 'data', 'priority', 'timestamp')
    
    def __init__(self, command_type: str, data: Optional[Dict] = None, priority: int = 0):
        self.command_type = command_type
        self.data = data or {}
        self.priority = priority
        self.timestamp = threading.current_thread().ident
    
    def __lt__(self, other):
        return self.priority > other.priority
    
    def __repr__(self):
        return f"Cmd({self.command_type}:p{self.priority})"

class CommandQueue:
    """Fast thread-safe command queue with handlers."""
    
    def __init__(self, max_size: int = 50):
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._handlers: Dict[str, List[Callable]] = {}
        self.log = logger.get_logger("CommandQueue")
        self._stats = {"processed": 0, "dropped": 0}
    
    def put(self, command: Command, timeout: float = None) -> bool:
        """Add command to queue."""
        try:
            self._queue.put((command.priority, command), timeout=timeout)
            return True
        except queue.Full:
            self._stats["dropped"] += 1
            self.log.warning(f"Queue full, dropped: {command}")
            return False
    
    def get(self, timeout: float = 0.1) -> Optional[Command]:
        """Get next command."""
        try:
            _, command = self._queue.get(timeout=timeout)
            return command
        except queue.Empty:
            return None
    
    def register_handler(self, command_type: str, handler: Callable):
        """Register handler for command type."""
        if command_type not in self._handlers:
            self._handlers[command_type] = []
        self._handlers[command_type].append(handler)
    
    def execute(self, command: Command) -> bool:
        """Execute command handlers."""
        handlers = self._handlers.get(command.command_type)
        if not handlers:
            self.log.warning(f"No handler: {command.command_type}")
            return False
        
        for handler in handlers:
            try:
                handler(command.data)
                self._stats["processed"] += 1
            except Exception as e:
                self.log.error(f"Handler error: {e}")
                return False
        
        return True
    
    def size(self) -> int:
        """Get queue size."""
        return self._queue.qsize()
    
    def stats(self) -> Dict:
        """Get statistics."""
        return self._stats.copy()
