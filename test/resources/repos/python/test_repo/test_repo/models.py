"""
Models module that demonstrates various Python class patterns.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class BaseModel(ABC):
    """
    Abstract base class for all models.
    """

    def __init__(self, id: str, name: str | None = None):
        self.id = id
        self.name = name or id

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary representation"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        """Create a model instance from dictionary data"""
        id = data.get("id", "")
        name = data.get("name")
        return cls(id=id, name=name)


class User(BaseModel):
    """
    User model representing a system user.
    """

    def __init__(self, id: str, name: str | None = None, email: str = "", roles: list[str] | None = None):
        super().__init__(id, name)
        self.email = email
        self.roles = roles or []

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "email": self.email, "roles": self.roles}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        instance = super().from_dict(data)
        instance.email = data.get("email", "")
        instance.roles = data.get("roles", [])
        return instance

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role"""
        return role in self.roles


class Item(BaseModel):
    """
    Item model representing a product or service.
    """

    def __init__(self, id: str, name: str | None = None, price: float = 0.0, category: str = ""):
        super().__init__(id, name)
        self.price = price
        self.category = category

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "price": self.price, "category": self.category}

    def get_display_price(self) -> str:
        """Format price for display"""
        return f"${self.price:.2f}"


# Generic type example
class Collection(Generic[T]):
    def __init__(self, items: list[T] | None = None):
        self.items = items or []

    def add(self, item: T) -> None:
        self.items.append(item)

    def get_all(self) -> list[T]:
        return self.items


# Factory function
def create_user_object(id: str, name: str, email: str, roles: list[str] | None = None) -> User:
    """Factory function to create a user"""
    return User(id=id, name=name, email=email, roles=roles)


# Multiple inheritance examples


class Loggable:
    """
    Mixin class that provides logging functionality.
    Example of a common mixin pattern used with multiple inheritance.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log_entries: list[str] = []

    def log(self, message: str) -> None:
        """Add a log entry"""
        self.log_entries.append(message)

    def get_logs(self) -> list[str]:
        """Get all log entries"""
        return self.log_entries


class Serializable:
    """
    Mixin class that provides JSON serialization capabilities.
    Another example of a mixin for multiple inheritance.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary"""
        return self.to_dict() if hasattr(self, "to_dict") else {}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Any:
        """Create instance from JSON data"""
        return cls.from_dict(data) if hasattr(cls, "from_dict") else cls(**data)


class Auditable:
    """
    Mixin for tracking creation and modification timestamps.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.created_at: str = kwargs.get("created_at", "")
        self.updated_at: str = kwargs.get("updated_at", "")

    def update_timestamp(self, timestamp: str) -> None:
        """Update the last modified timestamp"""
        self.updated_at = timestamp


# Diamond inheritance pattern
class BaseService(ABC):
    """
    Base class for service objects - demonstrates diamond inheritance pattern.
    """

    def __init__(self, name: str = "base"):
        self.service_name = name

    @abstractmethod
    def get_service_info(self) -> dict[str, str]:
        """Get service information"""


class DataService(BaseService):
    """
    Data handling service.
    """

    def __init__(self, **kwargs):
        name = kwargs.pop("name", "data")
        super().__init__(name=name)
        self.data_source = kwargs.get("data_source", "default")

    def get_service_info(self) -> dict[str, str]:
        return {"service_type": "data", "service_name": self.service_name, "data_source": self.data_source}


class NetworkService(BaseService):
    """
    Network connectivity service.
    """

    def __init__(self, **kwargs):
        name = kwargs.pop("name", "network")
        super().__init__(name=name)
        self.endpoint = kwargs.get("endpoint", "localhost")

    def get_service_info(self) -> dict[str, str]:
        return {"service_type": "network", "service_name": self.service_name, "endpoint": self.endpoint}


class DataSyncService(DataService, NetworkService):
    """
    Service that syncs data over network - example of diamond inheritance.
    Inherits from both DataService and NetworkService, which both inherit from BaseService.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sync_interval = kwargs.get("sync_interval", 60)

    def get_service_info(self) -> dict[str, str]:
        info = super().get_service_info()
        info.update({"service_type": "data_sync", "sync_interval": str(self.sync_interval)})
        return info


# Multiple inheritance with mixins


class LoggableUser(User, Loggable):
    """
    User class with logging capabilities.
    Example of extending a concrete class with a mixin.
    """

    def __init__(self, id: str, name: str | None = None, email: str = "", roles: list[str] | None = None):
        super().__init__(id=id, name=name, email=email, roles=roles)

    def add_role(self, role: str) -> None:
        """Add a role to the user and log the action"""
        if role not in self.roles:
            self.roles.append(role)
            self.log(f"Added role '{role}' to user {self.id}")


class TrackedItem(Item, Serializable, Auditable):
    """
    Item with serialization and auditing capabilities.
    Example of a class inheriting from a concrete class and multiple mixins.
    """

    def __init__(
        self, id: str, name: str | None = None, price: float = 0.0, category: str = "", created_at: str = "", updated_at: str = ""
    ):
        super().__init__(id=id, name=name, price=price, category=category, created_at=created_at, updated_at=updated_at)
        self.stock_level = 0

    def update_stock(self, quantity: int) -> None:
        """Update stock level and timestamp"""
        self.stock_level = quantity
        self.update_timestamp(f"stock_update_{quantity}")

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({"stock_level": self.stock_level, "created_at": self.created_at, "updated_at": self.updated_at})
        return result
