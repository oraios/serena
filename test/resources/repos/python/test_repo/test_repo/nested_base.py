"""
Module to test parsing of classes with nested module paths in base classes.
"""

from typing import Generic, TypeVar

T = TypeVar("T")


class BaseModule:
    """Base module class for nested module tests."""


class SubModule:
    """Sub-module class for nested paths."""

    class NestedBase:
        """Nested base class."""

        def base_method(self):
            """Base method."""
            return "base"

        class NestedLevel2:
            """Nested level 2."""

            def nested_level_2_method(self):
                """Nested level 2 method."""
                return "nested_level_2"

    class GenericBase(Generic[T]):
        """Generic nested base class."""

        def generic_method(self, value: T) -> T:
            """Generic method."""
            return value


# Classes extending base classes with single-level nesting
class FirstLevel(SubModule):
    """Class extending a class from a nested module path."""

    def first_level_method(self):
        """First level method."""
        return "first"


# Classes extending base classes with multi-level nesting
class TwoLevel(SubModule.NestedBase):
    """Class extending a doubly-nested base class."""

    def multi_level_method(self):
        """Multi-level method."""
        return "multi"

    def base_method(self):
        """Override of base method."""
        return "overridden"


class ThreeLevel(SubModule.NestedBase.NestedLevel2):
    """Class extending a triply-nested base class."""

    def three_level_method(self):
        """Three-level method."""
        return "three"


# Class extending a generic base class with nesting
class GenericExtension(SubModule.GenericBase[str]):
    """Class extending a generic nested base class."""

    def generic_extension_method(self, text: str) -> str:
        """Extension method."""
        return f"Extended: {text}"
