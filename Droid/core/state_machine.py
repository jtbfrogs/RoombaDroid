"""State machine with better transition validation."""
from enum import Enum
from typing import Callable, Dict, List
from core.logger import logger

class DroidState(Enum):
    """Droid operational states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    MOVING = "moving"
    TRACKING = "tracking"
    EXECUTING = "executing"
    ERROR = "error"
    SHUTDOWN = "shutdown"

class StateMachine:
    """Fast state machine with validation."""
    
    # Valid transitions
    VALID_TRANSITIONS = {
        DroidState.IDLE: {DroidState.LISTENING, DroidState.MOVING, DroidState.TRACKING, DroidState.ERROR, DroidState.SHUTDOWN},
        DroidState.LISTENING: {DroidState.THINKING, DroidState.IDLE, DroidState.ERROR},
        DroidState.THINKING: {DroidState.EXECUTING, DroidState.IDLE, DroidState.ERROR},
        DroidState.MOVING: {DroidState.IDLE, DroidState.TRACKING, DroidState.ERROR},
        DroidState.TRACKING: {DroidState.MOVING, DroidState.IDLE, DroidState.ERROR},
        DroidState.EXECUTING: {DroidState.IDLE, DroidState.ERROR},
        DroidState.ERROR: {DroidState.IDLE, DroidState.SHUTDOWN},
        DroidState.SHUTDOWN: set(),
    }
    
    def __init__(self):
        self.current_state = DroidState.IDLE
        self.previous_state = None
        self._callbacks: Dict[DroidState, List[Callable]] = {}
        self.log = logger.get_logger("StateMachine")
    
    def register_callback(self, state: DroidState, callback: Callable):
        """Register transition callback."""
        if state not in self._callbacks:
            self._callbacks[state] = []
        self._callbacks[state].append(callback)
    
    def transition(self, new_state: DroidState) -> bool:
        """Attempt state transition with validation."""
        if new_state == self.current_state:
            return True
        
        # Validate transition
        if new_state not in self.VALID_TRANSITIONS.get(self.current_state, set()):
            self.log.warning(f"Invalid transition: {self.current_state.value} → {new_state.value}")
            return False
        
        self.previous_state = self.current_state
        self.current_state = new_state
        
        self.log.debug(f"{self.previous_state.value} → {new_state.value}")
        
        # Execute callbacks
        if new_state in self._callbacks:
            for callback in self._callbacks[new_state]:
                try:
                    callback(self.previous_state, new_state)
                except Exception as e:
                    self.log.error(f"Callback error: {e}")
        
        return True
    
    def can_transition_to(self, state: DroidState) -> bool:
        """Check if transition is valid."""
        return state in self.VALID_TRANSITIONS.get(self.current_state, set())
    
    def is_in_state(self, state: DroidState) -> bool:
        """Check current state."""
        return self.current_state == state
    
    def can_accept_commands(self) -> bool:
        """Check if droid can accept user commands."""
        return self.current_state not in {DroidState.ERROR, DroidState.SHUTDOWN}
