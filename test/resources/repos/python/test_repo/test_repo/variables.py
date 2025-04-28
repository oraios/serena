"""
Test module for variable declarations and usage.

This module tests various types of variable declarations and usages including:
- Module-level variables
- Class-level variables
- Instance variables
- Variable reassignments
"""

from dataclasses import dataclass, field

# Module-level variables
module_var = "Initial module value"

reassignable_module_var = 10
reassignable_module_var = 20  # Reassigned

# Module-level variable with type annotation
typed_module_var: int = 42


# Regular class with class and instance variables
class VariableContainer:
    """Class that contains various variables."""

    # Class-level variables
    class_var = "Initial class value"

    reassignable_class_var = True
    reassignable_class_var = False  # Reassigned #noqa: PIE794

    # Class-level variable with type annotation
    typed_class_var: str = "typed value"

    def __init__(self):
        # Instance variables
        self.instance_var = "Initial instance value"
        self.reassignable_instance_var = 100

        # Instance variable with type annotation
        self.typed_instance_var: list[str] = ["item1", "item2"]

    def modify_instance_var(self):
        # Reassign instance variable
        self.instance_var = "Modified instance value"
        self.reassignable_instance_var = 200  # Reassigned

    def use_module_var(self):
        # Use module-level variables
        result = module_var + " used in method"
        other_result = reassignable_module_var + 5
        return result, other_result

    def use_class_var(self):
        # Use class-level variables
        result = VariableContainer.class_var + " used in method"
        other_result = VariableContainer.reassignable_class_var
        return result, other_result


# Dataclass with variables
@dataclass
class VariableDataclass:
    """Dataclass that contains various fields."""

    # Field variables with type annotations
    id: int
    name: str
    items: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    optional_value: float | None = None

    # This will be reassigned in various places
    status: str = "pending"


# Function that uses the module variables
def use_module_variables():
    """Function that uses module-level variables."""
    result = module_var + " used in function"
    other_result = reassignable_module_var * 2
    return result, other_result


# Create instances and use variables
dataclass_instance = VariableDataclass(id=1, name="Test")
dataclass_instance.status = "active"  # Reassign dataclass field

# Use variables at module level
module_result = module_var + " used at module level"
other_module_result = reassignable_module_var + 30

# Create a second dataclass instance with different status
second_dataclass = VariableDataclass(id=2, name="Another Test")
second_dataclass.status = "completed"  # Another reassignment of status
