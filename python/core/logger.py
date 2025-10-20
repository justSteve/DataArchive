"""
Logging configuration for Data Archive System
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

class Logger:
    """Centralized logging configuration"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Create formatters
        self.detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        self.simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Setup loggers
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """Configure root logger"""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Console handler (INFO and above)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(self.simple_formatter)
        root_logger.addHandler(console_handler)
        
        # File handler (DEBUG and above)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_handler = logging.FileHandler(
            self.log_dir / f'archive_{timestamp}.log'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self.detailed_formatter)
        root_logger.addHandler(file_handler)
        
        # Error file handler (ERROR and above)
        error_handler = logging.FileHandler(
            self.log_dir / f'errors_{timestamp}.log'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(self.detailed_formatter)
        root_logger.addHandler(error_handler)
    
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Get a logger instance"""
        return logging.getLogger(name)


# Initialize on import
_logger_instance = Logger()

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return Logger.get_logger(name)
