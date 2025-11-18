"""
Logging utilities for language server operations.
"""

import logging


def determine_log_level(line: str) -> int:
    """
    Classify a stderr line from the language server to determine appropriate logging level.

    Language servers may emit informational messages to stderr that contain words like "error"
    but are not actual errors. This function provides default classification that can be
    customized by subclasses.

    :param line: The stderr line to classify
    :return: A logging level (logging.DEBUG, logging.INFO, logging.WARNING, or logging.ERROR)
    """
    line_lower = line.lower()

    # Default classification: treat lines with "error" or "exception" as ERROR level
    if "error" in line_lower or "exception" in line_lower or line.startswith("E["):
        return logging.ERROR

    else:
        return logging.INFO
