"""Thread pool for async command processing."""
import threading
import queue
from typing import Callable, Any
from core.logger import logger

class WorkerPool:
    """Lightweight thread pool for task distribution."""
    
    def __init__(self, num_workers: int = 3):
        self.log = logger.get_logger("WorkerPool")
        self.task_queue: queue.Queue = queue.Queue()
        self.workers = []
        self.running = False
        self.num_workers = num_workers
    
    def start(self):
        """Start worker threads."""
        if self.running:
            return
        
        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)
        
        self.log.info(f"Started {self.num_workers} workers")
    
    def stop(self):
        """Stop all workers."""
        self.running = False
        for _ in self.workers:
            self.task_queue.put(None)  # Sentinel
        
        for worker in self.workers:
            worker.join(timeout=1)
        
        self.log.info("Workers stopped")
    
    def submit(self, func: Callable, *args, **kwargs) -> bool:
        """Submit task to pool."""
        try:
            self.task_queue.put((func, args, kwargs), timeout=1)
            return True
        except queue.Full:
            self.log.warning("Task queue full")
            return False
    
    def _worker_loop(self):
        """Worker thread main loop."""
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.5)
                if task is None:  # Shutdown signal
                    break
                
                func, args, kwargs = task
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    self.log.error(f"Task error: {e}")
            except queue.Empty:
                continue
