"""
Time-bounded matching for regular expressions that originate from the agent.

Several tools accept a regular expression written by the agent (`search_for_pattern`,
`replace_content`, `replace_in_files`, `find_declaration`, `find_implementations`), and such an
expression can backtrack catastrophically. The standard library's `re` module offers no way out of
it: it neither releases the GIL nor runs signal handlers while matching. A single pathological
expression therefore freezes the entire Serena process rather than just the tool application that
issued it - tools are executed one at a time, so every subsequent tool application waits behind the
runaway match, and the tool timeout can report a failure to the client but cannot stop a match that
is already running. Killing the process is the only remedy left.

The `regex` module (already a dependency) checks the clock while matching and can therefore be
interrupted, so agent-supplied expressions are matched through the helpers below, which abort the
match and explain the likely cause instead of taking the process down with them.
"""

import logging
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeAlias

import regex

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
"""
The time limit for a single matching operation. Well-formed expressions match in milliseconds even
across large repositories, so the limit only has to be small enough to keep the server responsive
and large enough not to interfere with legitimate work.
"""

TIMEOUT_ENV_VAR = "SERENA_REGEX_TIMEOUT_SECONDS"

# The `regex` module ships no type information. Its match objects are structurally identical to
# those of `re` and are described accordingly; its compiled patterns are not, because they accept
# the `timeout` argument that `re.Pattern` does not have.
Match: TypeAlias = re.Match[str]


def get_timeout_seconds() -> float:
    """
    :return: the time limit for a single matching operation, which is `DEFAULT_TIMEOUT_SECONDS`
        unless the environment variable `SERENA_REGEX_TIMEOUT_SECONDS` provides a positive number.
    """
    raw_value = os.environ.get(TIMEOUT_ENV_VAR, "").strip()
    if not raw_value:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout_seconds = float(raw_value)
    except ValueError:
        log.warning("Ignoring %s=%r: not a number", TIMEOUT_ENV_VAR, raw_value)
        return DEFAULT_TIMEOUT_SECONDS
    if timeout_seconds <= 0:
        log.warning("Ignoring %s=%r: must be positive", TIMEOUT_ENV_VAR, raw_value)
        return DEFAULT_TIMEOUT_SECONDS
    return timeout_seconds


class RegexTimeoutError(ValueError):
    """
    Raised when matching an agent-supplied regular expression exceeded the time limit, which
    virtually always means that the expression backtracks catastrophically rather than that the
    input is large.
    """

    def __init__(self, pattern: str, timeout_seconds: float) -> None:
        super().__init__(
            f"The regular expression did not complete within {timeout_seconds:g} seconds and was aborted: {pattern!r}. "
            "This indicates catastrophic backtracking rather than a large amount of input. "
            "Note that '.' matches newlines as well, because the DOTALL flag is enabled by default: "
            r"write '[^\n]*' where you mean 'the remainder of the line', and do not apply a quantifier to a group "
            r"that can span newlines (e.g. '(?:.*\n){0,40}'), because the number of ways in which such an "
            "expression can match grows exponentially with the size of the input. "
            "To include a few lines around a match, use the context parameters of the tool rather than encoding "
            "the window in the expression itself."
        )
        self.pattern = pattern
        self.timeout_seconds = timeout_seconds


class TimeLimitedPattern:
    """
    A compiled regular expression whose matching operations are aborted with a
    :class:`RegexTimeoutError` when they exceed the given time limit.
    """

    def __init__(self, compiled_pattern: Any, pattern: str, timeout_seconds: float) -> None:
        """
        :param compiled_pattern: the expression as compiled by the `regex` module
        :param pattern: the expression as written by the agent, for use in error messages
        :param timeout_seconds: the time limit for a single matching operation
        """
        self._compiled_pattern = compiled_pattern
        self._pattern = pattern
        self._timeout_seconds = timeout_seconds

    @property
    def pattern(self) -> str:
        return self._pattern

    def finditer(self, content: str) -> list[Match]:
        """
        :param content: the text to search
        :return: all non-overlapping matches; a list rather than a lazy iterator, such that the time
            limit covers the entire scan instead of a single step of it
        """
        with self._time_limit():
            return list(self._compiled_pattern.finditer(content, timeout=self._timeout_seconds))

    def search(self, content: str) -> Match | None:
        """
        :param content: the text to search
        :return: the first match or None
        """
        with self._time_limit():
            return self._compiled_pattern.search(content, timeout=self._timeout_seconds)

    def subn(self, repl: Callable[[Match], str], content: str) -> tuple[str, int]:
        """
        :param repl: the replacement function
        :param content: the text in which to perform the replacement
        :return: the updated text and the number of replacements performed
        """
        with self._time_limit():
            return self._compiled_pattern.subn(repl, content, timeout=self._timeout_seconds)

    @contextmanager
    def _time_limit(self) -> Iterator[None]:
        try:
            yield
        except TimeoutError as e:
            raise RegexTimeoutError(self._pattern, self._timeout_seconds) from e


def compile_pattern(pattern: str, flags: int = 0, timeout_seconds: float | None = None) -> TimeLimitedPattern:
    """
    Compiles an agent-supplied regular expression for time-bounded matching.

    :param pattern: the regular expression
    :param flags: the flags to compile it with
    :param timeout_seconds: the time limit for a single matching operation; the configured default
        applies if this is None
    :return: the compiled expression
    """
    return TimeLimitedPattern(
        regex.compile(pattern, flags),
        pattern,
        get_timeout_seconds() if timeout_seconds is None else timeout_seconds,
    )
