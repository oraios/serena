#!/usr/bin/env python
"""
Main entry point script for the test_repo application.

This script demonstrates how a typical application entry point would be structured,
with command-line arguments, configuration loading, and service initialization.
"""

import argparse
import json
import logging
import os
import sys
from typing import Any

# Add parent directory to path to make imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_repo.models import Item, User
from test_repo.services import ItemService, UserService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test Repo Application")

    parser.add_argument("--config", type=str, default="config.json", help="Path to configuration file")

    parser.add_argument("--mode", choices=["user", "item", "both"], default="both", help="Operation mode")

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    """Load configuration from a JSON file."""
    if not os.path.exists(config_path):
        logger.warning(f"Configuration file not found: {config_path}")
        return {}

    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in configuration file: {config_path}")
        return {}
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return {}


def create_sample_users(service: UserService, count: int = 3) -> list[User]:
    """Create sample users for demonstration."""
    users = []

    # Create admin user
    admin = service.create_user(name="Admin User", email="admin@example.com", roles=["admin"])
    users.append(admin)

    # Create regular users
    for i in range(count - 1):
        user = service.create_user(name=f"User {i + 1}", email=f"user{i + 1}@example.com", roles=["user"])
        users.append(user)

    return users


def create_sample_items(service: ItemService, count: int = 5) -> list[Item]:
    """Create sample items for demonstration."""
    categories = ["Electronics", "Books", "Clothing", "Food", "Other"]
    items = []

    for i in range(count):
        category = categories[i % len(categories)]
        item = service.create_item(name=f"Item {i + 1}", price=10.0 * (i + 1), category=category)
        items.append(item)

    return items


def run_user_operations(service: UserService, config: dict[str, Any]) -> None:
    """Run operations related to users."""
    logger.info("Running user operations")

    # Get configuration
    user_count = config.get("user_count", 3)

    # Create users
    users = create_sample_users(service, user_count)
    logger.info(f"Created {len(users)} users")

    # Demonstrate some operations
    for user in users:
        logger.info(f"User: {user.name} (ID: {user.id})")

        # Access a method to demonstrate method calls
        if user.has_role("admin"):
            logger.info(f"{user.name} is an admin")

    # Lookup a user
    found_user = service.get_user(users[0].id)
    if found_user:
        logger.info(f"Found user: {found_user.name}")


def run_item_operations(service: ItemService, config: dict[str, Any]) -> None:
    """Run operations related to items."""
    logger.info("Running item operations")

    # Get configuration
    item_count = config.get("item_count", 5)

    # Create items
    items = create_sample_items(service, item_count)
    logger.info(f"Created {len(items)} items")

    # Demonstrate some operations
    total_price = 0.0
    for item in items:
        price_display = item.get_display_price()
        logger.info(f"Item: {item.name}, Price: {price_display}")
        total_price += item.price

    logger.info(f"Total price of all items: ${total_price:.2f}")


def main():
    """Main entry point for the application."""
    # Parse command line arguments
    args = parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Test Repo Application")

    # Load configuration
    config = load_config(args.config)
    logger.debug(f"Loaded configuration: {config}")

    # Initialize services
    user_service = UserService()
    item_service = ItemService()

    # Run operations based on mode
    if args.mode in ("user", "both"):
        run_user_operations(user_service, config)

    if args.mode in ("item", "both"):
        run_item_operations(item_service, config)

    logger.info("Application completed successfully")


item_reference = Item(id="1", name="Item 1", price=10.0, category="Electronics")

if __name__ == "__main__":
    main()
