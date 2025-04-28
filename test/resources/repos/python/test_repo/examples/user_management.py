"""
Example demonstrating user management with the test_repo module.

This example showcases:
- Creating and managing users
- Using various object types and relationships
- Type annotations and complex Python patterns
"""

import logging
from dataclasses import dataclass
from typing import Any

from test_repo.models import User, create_user_object
from test_repo.services import UserService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class UserStats:
    """Statistics about user activity."""

    user_id: str
    login_count: int = 0
    last_active_days: int = 0
    engagement_score: float = 0.0

    def is_active(self) -> bool:
        """Check if the user is considered active."""
        return self.last_active_days < 30


class UserManager:
    """Example class demonstrating complex user management."""

    def __init__(self, service: UserService):
        self.service = service
        self.active_users: dict[str, User] = {}
        self.user_stats: dict[str, UserStats] = {}

    def register_user(self, name: str, email: str, roles: list[str] | None = None) -> User:
        """Register a new user."""
        logger.info(f"Registering new user: {name} ({email})")
        user = self.service.create_user(name=name, email=email, roles=roles)
        self.active_users[user.id] = user
        self.user_stats[user.id] = UserStats(user_id=user.id)
        return user

    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        if user_id in self.active_users:
            return self.active_users[user_id]

        # Try to fetch from service
        user = self.service.get_user(user_id)
        if user:
            self.active_users[user.id] = user
        return user

    def update_user_stats(self, user_id: str, login_count: int, days_since_active: int) -> None:
        """Update statistics for a user."""
        if user_id not in self.user_stats:
            self.user_stats[user_id] = UserStats(user_id=user_id)

        stats = self.user_stats[user_id]
        stats.login_count = login_count
        stats.last_active_days = days_since_active

        # Calculate engagement score based on activity
        engagement = (100 - min(days_since_active, 100)) * 0.8
        engagement += min(login_count, 20) * 0.2
        stats.engagement_score = engagement

    def get_active_users(self) -> list[User]:
        """Get all active users."""
        active_user_ids = [user_id for user_id, stats in self.user_stats.items() if stats.is_active()]
        return [self.active_users[user_id] for user_id in active_user_ids if user_id in self.active_users]

    def get_user_by_email(self, email: str) -> User | None:
        """Find a user by their email address."""
        for user in self.active_users.values():
            if user.email == email:
                return user
        return None


# Example function demonstrating type annotations
def process_user_data(users: list[User], include_inactive: bool = False, transform_func: callable | None = None) -> dict[str, Any]:
    """Process user data with optional transformations."""
    result: dict[str, Any] = {"users": [], "total": 0, "admin_count": 0}

    for user in users:
        if transform_func:
            user_data = transform_func(user.to_dict())
        else:
            user_data = user.to_dict()

        result["users"].append(user_data)
        result["total"] += 1

        if "admin" in user.roles:
            result["admin_count"] += 1

    return result


def main():
    """Main function demonstrating the usage of UserManager."""
    # Initialize service and manager
    service = UserService()
    manager = UserManager(service)

    # Register some users
    admin = manager.register_user("Admin User", "admin@example.com", ["admin"])
    user1 = manager.register_user("Regular User", "user@example.com", ["user"])
    user2 = manager.register_user("Another User", "another@example.com", ["user"])

    # Update some stats
    manager.update_user_stats(admin.id, 100, 5)
    manager.update_user_stats(user1.id, 50, 10)
    manager.update_user_stats(user2.id, 10, 45)  # Inactive user

    # Get active users
    active_users = manager.get_active_users()
    logger.info(f"Active users: {len(active_users)}")

    # Process user data
    user_data = process_user_data(active_users, transform_func=lambda u: {**u, "full_name": u.get("name", "")})

    logger.info(f"Processed {user_data['total']} users, {user_data['admin_count']} admins")

    # Example of calling create_user directly
    external_user = create_user_object(id="ext123", name="External User", email="external@example.org", roles=["external"])
    logger.info(f"Created external user: {external_user.name}")


if __name__ == "__main__":
    main()
