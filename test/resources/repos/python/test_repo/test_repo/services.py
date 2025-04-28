"""
Services module demonstrating function usage and dependencies.
"""

from typing import Any

from .models import Item, User


class UserService:
    """Service for user-related operations"""

    def __init__(self, user_db: dict[str, User] | None = None):
        self.users = user_db or {}

    def create_user(self, id: str, name: str, email: str) -> User:
        """Create a new user and store it"""
        if id in self.users:
            raise ValueError(f"User with ID {id} already exists")

        user = User(id=id, name=name, email=email)
        self.users[id] = user
        return user

    def get_user(self, id: str) -> User | None:
        """Get a user by ID"""
        return self.users.get(id)

    def list_users(self) -> list[User]:
        """Get a list of all users"""
        return list(self.users.values())

    def delete_user(self, id: str) -> bool:
        """Delete a user by ID"""
        if id in self.users:
            del self.users[id]
            return True
        return False


class ItemService:
    """Service for item-related operations"""

    def __init__(self, item_db: dict[str, Item] | None = None):
        self.items = item_db or {}

    def create_item(self, id: str, name: str, price: float, category: str) -> Item:
        """Create a new item and store it"""
        if id in self.items:
            raise ValueError(f"Item with ID {id} already exists")

        item = Item(id=id, name=name, price=price, category=category)
        self.items[id] = item
        return item

    def get_item(self, id: str) -> Item | None:
        """Get an item by ID"""
        return self.items.get(id)

    def list_items(self, category: str | None = None) -> list[Item]:
        """List all items, optionally filtered by category"""
        if category:
            return [item for item in self.items.values() if item.category == category]
        return list(self.items.values())


# Factory function for services
def create_service_container() -> dict[str, Any]:
    """Create a container with all services"""
    container = {"user_service": UserService(), "item_service": ItemService()}
    return container


user_var_str = "user_var"


user_service = UserService()
user_service.create_user("1", "Alice", "alice@example.com")
