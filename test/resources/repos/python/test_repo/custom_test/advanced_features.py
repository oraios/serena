"""
Advanced Python features for testing code parsing capabilities.

This module contains various advanced Python code patterns to ensure
that the code parser can correctly handle them.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, Flag, IntEnum, auto
from functools import wraps
from typing import (
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    Literal,
    NewType,
    Protocol,
    TypedDict,
    TypeVar,
)

# Type variables for generics
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# Custom types using NewType
UserId = NewType("UserId", str)
ItemId = NewType("ItemId", int)

# Type aliases
PathLike = str | os.PathLike
JsonDict = dict[str, Any]


# TypedDict
class UserDict(TypedDict):
    """TypedDict representing user data."""

    id: str
    name: str
    email: str
    age: int
    roles: list[str]


# Enums
class Status(Enum):
    """Status enum for process states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Priority(IntEnum):
    """Priority levels for tasks."""

    LOW = 0
    MEDIUM = 5
    HIGH = 10
    CRITICAL = auto()


class Permissions(Flag):
    """Permission flags for access control."""

    NONE = 0
    READ = 1
    WRITE = 2
    EXECUTE = 4
    ALL = READ | WRITE | EXECUTE


# Abstract class with various method types
class BaseProcessor(ABC):
    """Abstract base class for processors with various method patterns."""

    # Class variable with type annotation
    DEFAULT_TIMEOUT: ClassVar[int] = 30
    MAX_RETRIES: Final[int] = 3

    def __init__(self, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}
        self._status = Status.PENDING

    @property
    def status(self) -> Status:
        """Status property getter."""
        return self._status

    @status.setter
    def status(self, value: Status) -> None:
        """Status property setter."""
        if not isinstance(value, Status):
            raise TypeError(f"Expected Status enum, got {type(value)}")
        self._status = value

    @abstractmethod
    def process(self, data: Any) -> Any:
        """Process the input data."""

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> BaseProcessor:
        """Factory classmethod."""
        name = config.get("name", "default")
        return cls(name=name, config=config)

    @staticmethod
    def validate_config(config: dict[str, Any]) -> bool:
        """Static method for config validation."""
        return "name" in config

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"


# Concrete implementation of abstract class
class DataProcessor(BaseProcessor):
    """Concrete implementation of BaseProcessor."""

    def __init__(self, name: str, config: dict[str, Any] | None = None, priority: Priority = Priority.MEDIUM):
        super().__init__(name, config)
        self.priority = priority
        self.processed_count = 0

    def process(self, data: Any) -> Any:
        """Process the data."""

        # Nested function definition
        def transform(item: Any) -> Any:
            # Nested function within a nested function
            def apply_rules(x: Any) -> Any:
                return x

            return apply_rules(item)

        # Lambda function
        normalize = lambda x: x / max(x) if hasattr(x, "__iter__") and len(x) > 0 else x  # noqa: F841

        result = transform(data)
        self.processed_count += 1
        return result

    # Method with complex type hints
    def batch_process(self, items: list[str | dict[str, Any] | tuple[Any, ...]]) -> dict[str, list[Any]]:
        """Process multiple items in a batch."""
        results: dict[str, list[Any]] = {"success": [], "error": []}

        for item in items:
            try:
                result = self.process(item)
                results["success"].append(result)
            except Exception as e:
                results["error"].append((item, str(e)))

        return results

    # Generator method
    def process_stream(self, data_stream: Iterable[T]) -> Iterable[T]:
        """Process a stream of data, yielding results as they're processed."""
        for item in data_stream:
            yield self.process(item)

    # Async method
    async def async_process(self, data: Any) -> Any:
        """Process data asynchronously."""
        await asyncio.sleep(0.1)
        return self.process(data)

    # Method with function parameters
    def apply_transform(self, data: Any, transform_func: Callable[[Any], Any]) -> Any:
        """Apply a custom transform function to the data."""
        return transform_func(data)


# Dataclass
@dataclass
class Task:
    """Task dataclass for tracking work items."""

    id: str
    name: str
    status: Status = Status.PENDING
    priority: Priority = Priority.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    created_at: float | None = None

    def __post_init__(self):
        if self.created_at is None:
            import time

            self.created_at = time.time()

    def has_dependencies(self) -> bool:
        """Check if task has dependencies."""
        return len(self.dependencies) > 0


# Generic class
class Repository(Generic[T]):
    """Generic repository for managing collections of items."""

    def __init__(self):
        self.items: dict[str, T] = {}

    def add(self, id: str, item: T) -> None:
        """Add an item to the repository."""
        self.items[id] = item

    def get(self, id: str) -> T | None:
        """Get an item by id."""
        return self.items.get(id)

    def remove(self, id: str) -> bool:
        """Remove an item by id."""
        if id in self.items:
            del self.items[id]
            return True
        return False

    def list_all(self) -> list[T]:
        """List all items."""
        return list(self.items.values())


# Type with Protocol (structural subtyping)
class Serializable(Protocol):
    """Protocol for objects that can be serialized to dict."""

    def to_dict(self) -> dict[str, Any]: ...


#
# Decorator function
def log_execution(func: Callable) -> Callable:
    """Decorator to log function execution."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Executing {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Finished {func.__name__}")
        return result

    return wrapper


# Context manager
@contextmanager
def transaction_context(name: str = "default"):
    """Context manager for transaction-like operations."""
    print(f"Starting transaction: {name}")
    try:
        yield name
        print(f"Committing transaction: {name}")
    except Exception as e:
        print(f"Rolling back transaction: {name}, error: {e}")
        raise


# Function with complex parameter annotations
def advanced_search(
    query: str,
    filters: dict[str, Any] | None = None,
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    page: int = 1,
    page_size: int = 10,
    include_metadata: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """
    Advanced search function with many parameters.

    Returns search results and total count.
    """
    results = []
    total = 0
    # Simulating search functionality
    return results, total


# Class with nested classes
class OuterClass:
    """Outer class with nested classes and methods."""

    class NestedClass:
        """Nested class inside OuterClass."""

        def __init__(self, value: Any):
            self.value = value

        def get_value(self) -> Any:
            """Get the stored value."""
            return self.value

        class DeeplyNestedClass:
            """Deeply nested class for testing parser depth capabilities."""

            def deep_method(self) -> str:
                """Method in deeply nested class."""
                return "deep"

    def __init__(self, name: str):
        self.name = name
        self.nested = self.NestedClass(name)

    def get_nested(self) -> NestedClass:
        """Get the nested class instance."""
        return self.nested

    # Method with nested functions
    def process_with_nested(self, data: Any) -> Any:
        """Method demonstrating deeply nested function definitions."""

        def level1(x: Any) -> Any:
            """First level nested function."""

            def level2(y: Any) -> Any:
                """Second level nested function."""

                def level3(z: Any) -> Any:
                    """Third level nested function."""
                    return z

                return level3(y)

            return level2(x)

        return level1(data)


# Metaclass example
class Meta(type):
    """Metaclass example for testing advanced class handling."""

    def __new__(mcs, name, bases, attrs):
        print(f"Creating class: {name}")
        return super().__new__(mcs, name, bases, attrs)

    def __init__(cls, name, bases, attrs):
        print(f"Initializing class: {name}")
        super().__init__(name, bases, attrs)


class WithMeta(metaclass=Meta):
    """Class that uses a metaclass."""

    def __init__(self, value: str):
        self.value = value


# Factory function that creates and returns instances
def create_processor(processor_type: str, name: str, config: dict[str, Any] | None = None) -> BaseProcessor:
    """Factory function that creates and returns processor instances."""
    if processor_type == "data":
        return DataProcessor(name, config)
    else:
        raise ValueError(f"Unknown processor type: {processor_type}")


# Nested decorator example
def with_retry(max_retries: int = 3):
    """Decorator factory that creates a retry decorator."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"Retrying {func.__name__} after error: {e}")
            return None

        return wrapper

    return decorator


@with_retry(max_retries=5)
def unreliable_operation(data: Any) -> Any:
    """Function that might fail and uses the retry decorator."""
    import random

    if random.random() < 0.5:
        raise RuntimeError("Random failure")
    return data


# Complex type annotation with Annotated
ValidatedString = Annotated[str, "A string that has been validated"]
PositiveInt = Annotated[int, lambda x: x > 0]


def process_validated_data(data: ValidatedString, count: PositiveInt) -> list[str]:
    """Process data with Annotated type hints."""
    return [data] * count


# Example of forward references and string literals in type annotations
class TreeNode:
    """Tree node with forward reference to itself in annotations."""

    def __init__(self, value: Any):
        self.value = value
        self.children: list[TreeNode] = []

    def add_child(self, child: TreeNode) -> None:
        """Add a child node."""
        self.children.append(child)

    def traverse(self) -> list[Any]:
        """Traverse the tree and return all values."""
        result = [self.value]
        for child in self.children:
            result.extend(child.traverse())
        return result


# Main entry point for demonstration
def main() -> None:
    """Main function demonstrating the use of various features."""
    # Create processor
    processor = DataProcessor("test-processor", {"debug": True})

    # Create tasks
    task1 = Task(id="task1", name="First Task")
    task2 = Task(id="task2", name="Second Task", dependencies=["task1"])

    # Create repository
    repo: Repository[Task] = Repository()
    repo.add(task1.id, task1)
    repo.add(task2.id, task2)

    # Process some data
    data = [1, 2, 3, 4, 5]
    result = processor.process(data)  # noqa: F841

    # Use context manager
    with transaction_context("main"):
        # Process more data
        for task in repo.list_all():
            processor.process(task.name)

    # Use advanced search
    results, total = advanced_search(query="test", filters={"status": Status.PENDING}, sort_by="priority", page=1, include_metadata=True)

    # Create a tree
    root = TreeNode("root")
    child1 = TreeNode("child1")
    child2 = TreeNode("child2")
    root.add_child(child1)
    root.add_child(child2)
    child1.add_child(TreeNode("grandchild1"))

    print("Done!")


if __name__ == "__main__":
    main()
