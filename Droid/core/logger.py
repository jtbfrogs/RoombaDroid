"""Optimized logging system with rotation and caching."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

class LoggerManager:
    """Centralized logger management with caching."""
    
    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False
    
    @classmethod
    def init(cls, log_dir: str = "logs"):
        """Initialize logging once."""
        if cls._initialized:
            return
        
        Path(log_dir).mkdir(exist_ok=True)
        cls._log_dir = log_dir
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get cached logger or create new one."""
        if name in cls._loggers:
            return cls._loggers[name]
        
        if not cls._initialized:
            cls.init()
        
        logger = logging.getLogger(name)
        
        if not logger.handlers:
            logger.setLevel(logging.DEBUG)
            
            # Console handler
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            
            # File handler with rotation
            log_file = os.path.join(cls._log_dir, f"{name}.log")
            fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
            fh.setLevel(logging.DEBUG)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            ch.setFormatter(formatter)
            fh.setFormatter(formatter)
            
            logger.addHandler(ch)
            logger.addHandler(fh)
        
        cls._loggers[name] = logger
        return logger

# Singleton instance
logger = LoggerManager
