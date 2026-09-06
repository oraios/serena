"""
The representation protocol through which objects returned from REPL code are rendered for the LLM.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from serena.util.text_utils import TextOutputUtils

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


T = TypeVar("T")


class Renderer(Generic[T], ABC):
    def __init__(self, agent: "SerenaAgent", max_answer_chars: int = -1):
        self._agent = agent
        self._max_answer_chars = max_answer_chars

    def _limit_length(
        self,
        result: str,
        shortened_result_factories: list[Callable[[], str]] | None = None,
    ) -> str:
        """Limit the length of the result string, optionally trying progressively shorter versions.

        :param result: the full result string
        :param max_answer_chars: maximum allowed characters. -1 means use the default from config.
        :param shortened_result_factories: optional list of closures, each producing a progressively shorter
            version of the result. They are tried in order until one fits within ``max_answer_chars``.
        :return: the result string, potentially replaced by a shortened version
        """
        max_answer_chars = self._max_answer_chars
        if max_answer_chars == -1:
            max_answer_chars = self._agent.serena_config.default_max_tool_answer_chars
        return TextOutputUtils.limit_length(
            result=result, max_answer_chars=max_answer_chars, shortened_result_factories=shortened_result_factories
        )

    def _to_json(self, x: Any) -> str:
        return TextOutputUtils.to_json(x)

    @abstractmethod
    def render(self, obj: T) -> str:
        """
        :return: a textual representation of this object for the LLM
        """


class Representable(ABC):
    """
    An object which can render itself as a string suitable for consumption by an LLM.
    """

    @abstractmethod
    def represent(self) -> str:
        """
        :return: a textual representation of this object for the LLM
        """


class RepresentableViaRenderer(Representable):
    """
    A representable object which uses a renderer to render itself.
    """

    def __init__(self, renderer: Renderer):
        self._renderer = renderer

    def represent(self) -> str:
        return self._renderer.render(self)
