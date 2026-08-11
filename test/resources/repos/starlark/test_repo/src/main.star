"""A standalone Starlark module in the standard dialect."""

GREETING_PREFIX = "Hello, "

def greet(name):
    """Build a greeting for the given name."""
    return GREETING_PREFIX + name
