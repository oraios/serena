"""
Module demonstrating function and method overloading with typing.overload
"""

from typing import Any, overload


# Example of function overloading
@overload
def process_data(data: str) -> dict[str, str]: ...


@overload
def process_data(data: int) -> dict[str, int]: ...


@overload
def process_data(data: list[str | int]) -> dict[str, list[str | int]]: ...


def process_data(data: str | int | list[str | int]) -> dict[str, Any]:
    """
    Process data based on its type.

    - If string: returns a dict with 'value': <string>
    - If int: returns a dict with 'value': <int>
    - If list: returns a dict with 'value': <list>
    """
    return {"value": data}


# Class with overloaded methods
class DataProcessor:
    """
    A class demonstrating method overloading.
    """

    @overload
    def transform(self, input_value: str) -> str: ...

    @overload
    def transform(self, input_value: int) -> int: ...

    @overload
    def transform(self, input_value: list[Any]) -> list[Any]: ...

    def transform(self, input_value: str | int | list[Any]) -> str | int | list[Any]:
        """
        Transform input based on its type.

        - If string: returns the string in uppercase
        - If int: returns the int multiplied by 2
        - If list: returns the list sorted
        """
        if isinstance(input_value, str):
            return input_value.upper()
        elif isinstance(input_value, int):
            return input_value * 2
        elif isinstance(input_value, list):
            try:
                return sorted(input_value)
            except TypeError:
                return input_value
        return input_value

    @overload
    def fetch(self, id: int) -> dict[str, Any]: ...

    @overload
    def fetch(self, id: str, cache: bool = False) -> dict[str, Any] | None: ...

    def fetch(self, id: int | str, cache: bool = False) -> dict[str, Any] | None:
        """
        Fetch data for a given ID.

        Args:
            id: The ID to fetch, either numeric or string
            cache: Whether to use cache for string IDs

        Returns:
            Data dictionary or None if not found

        """
        # Implementation would actually fetch data
        if isinstance(id, int):
            return {"id": id, "type": "numeric"}
        else:
            return {"id": id, "type": "string", "cached": cache}
