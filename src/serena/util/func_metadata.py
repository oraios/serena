"""
Function metadata utilities - replacement for mcp.server.fastmcp.utilities.func_metadata
that was removed in FastMCP 2.0.
"""

import inspect
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from pydantic import create_model


@dataclass
class FuncMetadata:
    """Metadata about a function's arguments."""

    arg_model: type
    """Pydantic model representing the function's arguments."""


def func_metadata(func: Callable[..., Any], skip_names: list[str] | None = None) -> FuncMetadata:
    """
    Extract metadata from a function to create a Pydantic model of its arguments.

    :param func: The function to extract metadata from.
    :param skip_names: List of parameter names to skip (e.g., 'self', 'cls', 'context').
    :return: FuncMetadata containing a Pydantic model of the function's arguments.
    """
    skip_names = skip_names or []

    # Get the function signature
    sig = inspect.signature(func)

    # Get type hints
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    # Build the fields for the Pydantic model
    fields = {}
    for param_name, param in sig.parameters.items():
        # Skip parameters in the skip list
        if param_name in skip_names:
            continue

        # Get the type annotation
        param_type = hints.get(param_name, Any)

        # Handle default values
        if param.default is inspect.Parameter.empty:
            # Required parameter
            fields[param_name] = (param_type, ...)
        else:
            # Optional parameter with default
            fields[param_name] = (param_type, param.default)

    # Create a Pydantic model dynamically
    model_name = f"{func.__name__}_Args"
    arg_model = create_model(model_name, **fields)

    return FuncMetadata(arg_model=arg_model)

