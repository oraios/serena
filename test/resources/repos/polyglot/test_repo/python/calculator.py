"""Python Calculator implementation for polyglot testing."""


class Calculator:
    """Calculator class with basic arithmetic operations."""

    def __init__(self, initial_value=0):
        """Initialize calculator with optional initial value."""
        self.value = initial_value

    def add(self, x):
        """Add x to current value."""
        self.value += x
        return self.value

    def subtract(self, x):
        """Subtract x from current value."""
        self.value -= x
        return self.value

    def multiply(self, x):
        """Multiply current value by x."""
        self.value *= x
        return self.value

    def divide(self, x):
        """Divide current value by x."""
        if x == 0:
            raise ValueError("Cannot divide by zero")
        self.value /= x
        return self.value

    def reset(self):
        """Reset value to zero."""
        self.value = 0
        return self.value


def helper_double(x):
    """Helper function that doubles a number."""
    return x * 2


def helper_square(x):
    """Helper function that squares a number."""
    return x * x
