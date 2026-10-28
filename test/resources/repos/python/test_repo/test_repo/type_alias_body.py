"""
Module with a type alias statement (Python 3.12+), whose symbol body must cover the entire statement.
"""

type StringToInt = dict[
    str,
    int,
]  # trailing comment
