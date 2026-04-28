"""Fixed-size daemon thread pool for background tasks."""
import queue
import threading
from typing import Callable, List

from core.logger import logger


class WorkerPool:
    """Distributes callables across a fixed number of daemon threads."""

    def __init__(self, num_workers: int = 3) -> None:
        self.log = logger.get_logger("WorkerPool")
        self.num_workers = num_workers
        self._queue: queue.Queue = queue.Queue()
        self._workers: List[threading.Thread] = []
        self._running = False

    def start(self) -> None:
        """Spawn worker threads."""
        if self._running:
            return
        self._running = True
        for i in range(self.num_workers):
            t = threading.Thread(
                target=self._loop, daemon=True, name=f"Worker-{i}"
            )
            t.start()
            self._workers.append(t)
        self.log.info("Started %d workers", self.num_workers)

    def stop(self) -> None:
        """Signal all workers to exit and wait for them."""
        self._running = False
        for _ in self._workers:
            self._queue.put(None)  # wake each blocked worker
        for t in self._workers:
            t.join(timeout=1.0)
        self._workers.clear()
        self.log.info("Workers stopped")

    def submit(self, func: Callable, *args, **kwargs) -> bool:
        """Enqueue a callable. Returns False if the queue is full."""
        try:
            self._queue.put((func, args, kwargs), timeout=1.0)
            return True
        except queue.Full:
            self.log.warning("Task queue full — task dropped")
            return False

    def _loop(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:  # shutdown sentinel
                break

            func, args, kwargs = task
            try:
                func(*args, **kwargs)
            except Exception as exc:
                self.log.error("Task error: %s", exc)
