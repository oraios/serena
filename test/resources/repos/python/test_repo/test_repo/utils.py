"""
Utility functions and classes demonstrating various Python features.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

# Type variables for generic functions
T = TypeVar("T")
U = TypeVar("U")


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up and return a configured logger"""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    logger = logging.getLogger("test_repo")
    logger.setLevel(levels.get(level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Decorator example
def log_execution(func: Callable) -> Callable:
    """Decorator to log function execution"""

    def wrapper(*args, **kwargs):
        logger = logging.getLogger("test_repo")
        logger.info(f"Executing function: {func.__name__}")
        result = func(*args, **kwargs)
        logger.info(f"Completed function: {func.__name__}")
        return result

    return wrapper


# Higher-order function
def map_list(items: list[T], mapper: Callable[[T], U]) -> list[U]:
    """Map a function over a list of items"""
    return [mapper(item) for item in items]


# Class with various Python features
class ConfigManager:
    """Manages configuration with various access patterns"""

    _instance = None

    # Singleton pattern
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, initial_config: dict[str, Any] | None = None):
        if not hasattr(self, "initialized"):
            self.config = initial_config or {}
            self.initialized = True

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-like access"""
        return self.config.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dictionary-like setting"""
        self.config[key] = value

    @property
    def debug_mode(self) -> bool:
        """Property example"""
        return self.config.get("debug", False)

    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        self.config["debug"] = value


# Context manager example
class Timer:
    """Context manager for timing code execution"""

    def __init__(self, name: str = "Timer"):
        self.name = name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        import time

        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time

        self.end_time = time.time()
        print(f"{self.name} took {self.end_time - self.start_time:.6f} seconds")


# Functions with default arguments
def retry(func: Callable, max_attempts: int = 3, delay: float = 1.0) -> Any:
    """Retry a function with backoff"""
    import time

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise e
            time.sleep(delay * (2**attempt))
