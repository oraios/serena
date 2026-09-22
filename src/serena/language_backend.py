# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING

from serena.util.file_proxy import FileProxy

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import CodeEditor
    from serena.project import Project
    from serena.repl.facade import ApiScope, Facade
    from serena.tools import Tool


class LanguageBackend(ABC):
    def __init__(self, key: str):
        """
        :param key: the key by which the backend is identified in the registry and in configuration
        """
        self._key = key

    def __str__(self):
        return self._key

    def get_key(self) -> str:
        """
        :return: the key by which the backend is identified in the registry and in configuration
        """
        return self._key

    def is_lsp(self):
        return self.get_key() == BuiltinLanguageBackend.LSP.value

    def is_jetbrains(self):
        return self.get_key() == BuiltinLanguageBackend.JETBRAINS.value

    @property
    def name(self):
        return self.get_key()

    @abstractmethod
    def get_lsp_tool_class_replacements(self) -> "dict[type[Tool], type[Tool]]":
        """
        :return: mapping from LSP tool classes to replacement tool classes (functional replacements)
        """

    @abstractmethod
    def create_facades(self, agent: "SerenaAgent", api_scope: "ApiScope") -> list["Facade"]:
        """
        Creates backend-specific facades for the given agent and API scope.

        :param agent: the agent
        :param api_scope: the API scope defining active facade methods
        :return: the list of facades to be used by the agent for this backend
        """

    @abstractmethod
    def init_active_project(self, agent: "SerenaAgent") -> None:
        """
        Initialises the backend for the given agent's newly activated project.

        :param agent: the agent, which has just set a new active project
        """

    @abstractmethod
    def shutdown_active_project(self, project: "Project", timeout: float) -> None:
        """
        Cleans up, freeing resources, after a project has been deactivated.

        :param project: the project
        :param timeout: the timeout, in seconds, after which to give up on graceful shutdown
        """

    def get_project_activation_statement(self, project: "Project") -> str:
        """
        :return: a statement to add to the project activation message
        """
        return ""

    def get_config_overview_statement(self, project: "Project") -> str:
        """
        :return: a statement to add to the project configuration overview
        """
        return ""

    @abstractmethod
    def create_code_editor(self, project: "Project") -> "CodeEditor":
        pass

    @abstractmethod
    def is_source_file(self, abs_path: str, project: "Project") -> bool:
        """
        Determines whether the given absolute path corresponds to a source file that can (potentially) be processed/understood by the backend.

        :param abs_path: the absolute path to an existing file
        :param project: the project in which the file is located
        :return: True if the file is a source file for this backend (or the backend does not specifically make distinctions),
            False otherwise
        """

    @abstractmethod
    def is_external_path(self, relative_path: str) -> bool:
        """
        Determines whether the given relative path corresponds to a file that is external to the project (e.g. a dependency file).
        Virtually all of Serena's interfaces use `relative_path` (relative to the project root) to refer to files, but some backends
        may need to support project-external files. In this case, the external path should be encoded in the `relative_path` parameter
        (e.g. "<ext:/path/to/whatever>") rather than this being an actual relative path that points outside the project root.
        Therefore, information about the project in question is deliberately not provided to this method.

        :param relative_path: the relative path to a file within the project or an encoded external path.
            The path can be assumed to have been provided by the backend itself.
        :return: whether the file is considered external to the project by this backend
        """

    @abstractmethod
    def create_file_proxy(self, relative_path: str, project: "Project") -> FileProxy:
        """
        Creates a file proxy for the given relative path in the given project.

        :param relative_path: the relative path to a file within the project or an encoded external path.
        :param project: the project
        :return: a file proxy for the given file
        """


class BuiltinLanguageBackend(Enum):
    LSP = "LSP"
    """
    Use the language server protocol (LSP), spawning freely available language servers
    via the SolidLSP library that is part of Serena
    """
    JETBRAINS = "JetBrains"
    """
    Use the Serena plugin in your JetBrains IDE.
    (requires the plugin to be installed and the project being worked on to be open in your IDE)
    """

    @staticmethod
    def from_str(backend_str: str) -> "BuiltinLanguageBackend":
        for backend in BuiltinLanguageBackend:
            if backend.value.lower() == backend_str.lower():
                return backend
        raise ValueError(f"Unknown language backend '{backend_str}': valid values are {[b.value for b in BuiltinLanguageBackend]}")

    @cache
    def get_instance(self) -> LanguageBackend:
        if self == BuiltinLanguageBackend.LSP:
            from .lsp.lsp_backend import LanguageBackendLSP

            return LanguageBackendLSP()
        elif self == BuiltinLanguageBackend.JETBRAINS:
            from .jetbrains.jetbrains_backend import LanguageBackendJetBrains

            return LanguageBackendJetBrains()
        else:
            raise NotImplementedError


class LanguageBackendRegistry:
    """
    Registry of language backends
    """

    REGISTRATION_ENTRY_POINT_GROUP = "serena.language_backend_registration"
    """
    entry point group for language backend registration functions; each function should call use 
    `LanguageBackendRegistry.get_instance().register(...)` to register a backend
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls(True)
                    cls._discover_backends_from_entry_points()
        return cls._instance

    def __init__(self, _singleton: bool):
        if not _singleton:
            raise RuntimeError("LanguageServerRegistry is a singleton. Use get_instance() to access it.")
        self._registered_backends: dict[str, LanguageBackend] = {}

        # auto-register built-in language backends
        for builtin_backend in BuiltinLanguageBackend:
            self._registered_backends[builtin_backend.value] = builtin_backend.get_instance()

    @classmethod
    def _discover_backends_from_entry_points(cls) -> None:
        """
        Discover and execute language server adapter registration functions from entry points.
        """
        log.debug("Discovering language backend registration entry points ...")
        try:
            entry_points = importlib.metadata.entry_points(group=cls.REGISTRATION_ENTRY_POINT_GROUP)
        except Exception as error:
            log.exception("Failed to discover language server registration entry points: %s", error)
            return

        def get_distribution_name(ep: importlib.metadata.EntryPoint) -> str:
            distribution = getattr(ep, "dist", None)
            if distribution is None:
                return "unknown distribution"
            return distribution.name or "unknown distribution"

        log.debug("Found %d language server registration entry points", len(entry_points))
        for entry_point in entry_points:
            try:
                registration = entry_point.load()
                if not callable(registration):
                    raise TypeError("Entry point must resolve to a callable registration function")
                registration()
            except Exception as error:
                log.exception(
                    "Failed to load language backend entry point '%s' from %s: %s",
                    entry_point.name,
                    get_distribution_name(entry_point),
                    error,
                )

    def resolve(self, key: str) -> LanguageBackend:
        if key in self._registered_backends:
            return self._registered_backends[key]
        raise ValueError(f"Unknown language backend key: '{key}'; Valid keys: {self.get_keys()}")

    def register(self, backend: LanguageBackend, allow_override: bool = False) -> None:
        """
        :param backend: the backend to register
        :param allow_override: whether to allow overriding an existing registration with the same key
        """
        key = backend.get_key()
        log.info("Registering language backend: %s (class=%s)", key, backend.__class__.__name__)
        if backend.get_key() in self._registered_backends and not allow_override:
            raise ValueError(f"Language backend already registered: {key}")
        self._registered_backends[key] = backend

    def get_keys(self) -> list[str]:
        """
        :return: the sorted list of all registered string keys
        """
        return sorted(self._registered_backends.keys())
