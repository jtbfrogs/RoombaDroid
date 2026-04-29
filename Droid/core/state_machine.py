"""State machine with validated transitions and state-change callbacks."""
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from core.logger import logger


class DroidState(Enum):
    """Operational states for the droid."""
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    MOVING    = "moving"
    TRACKING  = "tracking"
    EXECUTING = "executing"
    ERROR     = "error"
    SHUTDOWN  = "shutdown"


class StateMachine:
    """Validates and tracks state transitions; fires callbacks on entry."""

    VALID_TRANSITIONS: Dict[DroidState, Set[DroidState]] = {
        DroidState.IDLE:      {DroidState.LISTENING, DroidState.MOVING, DroidState.TRACKING, DroidState.ERROR, DroidState.SHUTDOWN},
        DroidState.LISTENING: {DroidState.THINKING, DroidState.IDLE, DroidState.ERROR},
        DroidState.THINKING:  {DroidState.EXECUTING, DroidState.IDLE, DroidState.ERROR},
        DroidState.MOVING:    {DroidState.IDLE, DroidState.TRACKING, DroidState.ERROR},
        DroidState.TRACKING:  {DroidState.MOVING, DroidState.IDLE, DroidState.ERROR},
        DroidState.EXECUTING: {DroidState.IDLE, DroidState.ERROR},
        DroidState.ERROR:     {DroidState.IDLE, DroidState.SHUTDOWN},
        DroidState.SHUTDOWN:  set(),
    }

    def __init__(self) -> None:
        self.current_state = DroidState.IDLE
        self.previous_state: Optional[DroidState] = None
        self._callbacks: Dict[DroidState, List[Callable]] = {}
        self.log = logger.get_logger("StateMachine")

    def register_callback(self, state: DroidState, callback: Callable) -> None:
        """Register a callback to fire whenever the machine enters *state*."""
        self._callbacks.setdefault(state, []).append(callback)

    def transition(self, new_state: DroidState) -> bool:
        """Attempt a transition; returns True on success, False if invalid."""
        if new_state == self.current_state:
            return True

        if new_state not in self.VALID_TRANSITIONS.get(self.current_state, set()):
            self.log.warning(
                "Invalid transition: %s -> %s",
                self.current_state.value,
                new_state.value,
            )
            return False

        self.previous_state = self.current_state
        self.current_state = new_state
        self.log.debug("%s -> %s", self.previous_state.value, new_state.value)

        for cb in self._callbacks.get(new_state, []):
            try:
                cb(self.previous_state, new_state)
            except Exception as exc:
                self.log.error("Callback error on %s: %s", new_state.value, exc)

        return True

    def can_transition_to(self, state: DroidState) -> bool:
        return state in self.VALID_TRANSITIONS.get(self.current_state, set())

    def is_in_state(self, state: DroidState) -> bool:
        return self.current_state == state

    def can_accept_commands(self) -> bool:
        """True when the droid is not in a terminal or error state."""
        return self.current_state not in {DroidState.ERROR, DroidState.SHUTDOWN}
