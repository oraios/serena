"""
Client for the Serena JetBrains Plugin
"""

import json
import logging
import posixpath
import re
from pathlib import Path
from typing import Any, Literal, Optional, Self, TypeVar, cast

import requests
from requests import Response
from sensai.util.string import ToStringMixin

import serena.tools.jetbrains_types as jb
from serena.project import Project
from serena.text_utils import render_html
from serena.tools.jetbrains_types import PluginStatusDTO
from serena.util.version import Version

T = TypeVar("T")
log = logging.getLogger(__name__)


class SerenaClientError(Exception):
    """Base exception for Serena client errors."""


class ConnectionError(SerenaClientError):
    """Raised when connection to the service fails."""


class APIError(SerenaClientError):
    """Raised when the API returns an error response that shall be reported on the caller/LLM."""

    def __init__(self, response: Response):
        try:
            error_data = response.json()
            message = error_data.get("error", response.text)
        except:
            message = response.text
        super().__init__(message)


class PluginServerError(SerenaClientError):
    """Raised when the plugin's service encounters an internal error (which may need to be reported)."""

    def __init__(self, message: str):
        unrecoverable_error_prefix = (
            "The request failed due to an error on the Serena JetBrains plugin side. This may be caused "
            "by a bug or an incompatibility in the plugin. In that case, please report the error below together with "
            "your setup (IDE + version, Serena plugin version) at https://github.com/oraios/serena/issues "
            "(if you are an LLM, tell the user about this). The Oraios team will then provide support on this.\n"
        )
        super().__init__(unrecoverable_error_prefix + message)


class ServerNotFoundError(Exception):
    """Raised when the plugin's service is not found."""


class JetBrainsPluginClient(ToStringMixin):
    """
    Python client for the Serena Backend Service.

    Provides simple methods to interact with all available endpoints.
    """

    BASE_PORT = 0x5EA2
    PLUGIN_REQUEST_TIMEOUT = 300
    """
    the timeout used for request handling within the plugin (a constant in the plugin)
    """
    _last_port: int | None = None
    """
    the last port that was successfully used to connect to a plugin instance in the current session
    """
    _server_address: str = "127.0.0.1"
    """
    the server address where to connect to the plugin service
    """

    def __init__(self, port: int, timeout: int = PLUGIN_REQUEST_TIMEOUT):
        self._port = port
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

        # connect and obtain status
        self._project_root: str | None = None
        self._plugin_version: Version | None = None
        try:
            status_response: PluginStatusDTO = cast(jb.PluginStatusDTO, self._make_request("GET", "/status"))
            self._project_root = status_response["project_root"]
            self._plugin_version = Version(status_response["plugin_version"])
        except ConnectionError:  # expected if no server is running at the port
            pass
        except Exception as e:
            log.warning("Failed to obtain status from JetBrains plugin service at port %d: %s", port, e, exc_info=e)

    @property
    def _base_url(self) -> str:
        return f"http://{self._server_address}:{self._port}"

    @classmethod
    def set_server_address(cls, address: str) -> None:
        cls._server_address = address

    def _tostring_includes(self) -> list[str]:
        return ["_port", "_project_root", "_plugin_version"]

    @classmethod
    def from_project(cls, project: Project) -> Self:
        resolved_path = Path(project.project_root).resolve()

        if cls._last_port is not None:
            client = JetBrainsPluginClient(cls._last_port)
            if client.matches(resolved_path):
                return client

        for port in range(cls.BASE_PORT, cls.BASE_PORT + 20):
            client = JetBrainsPluginClient(port)
            if client.matches(resolved_path):
                log.info("Found matching %s", client)
                cls._last_port = port
                return client

        raise ServerNotFoundError("Found no Serena service in a JetBrains IDE instance for the project at " + str(resolved_path))

    @staticmethod
    def _normalize_wsl_path(path_str: str) -> Path:
        """
        Normalize WSL UNC paths to Linux paths for comparison.

        When JetBrains IDE runs on Windows with a project opened from WSL,
        it returns paths like `//wsl.localhost/Ubuntu-24.04/home/user/project`
        or `//wsl$/Ubuntu/home/user/project`. This method converts such paths
        to standard Linux format `/home/user/project` for proper matching.

        :param path_str: Path string that may be a WSL UNC path
        :return: Normalized Path object
        """
        path_str = str(path_str)
        # Match //wsl.localhost/<distro>/... or //wsl$/<distro>/...
        match = re.match(r"^//wsl(?:\.localhost|\$)/[^/]+(.*)$", path_str, re.IGNORECASE)
        if match:
            return Path(match.group(1))
        return Path(path_str)

    @staticmethod
    def _canonicalize_path(path_str: str) -> str:
        """
        Convert a variety of path strings to a canonical, lowercase POSIX-like path for comparison.
        - preserves existing WSL UNC normalization
        - converts Windows drive paths (C:/...) to /mnt/c/... form
        - strips container/workspace prefixes like /workspaces/.../C:/... by extracting the first Windows drive occurrence
        - normalizes '..' and duplicate slashes
        - lowercases for case-insensitive Windows paths
        """
        s = str(path_str).replace("\\", "/")

        # First apply existing WSL UNC normalization
        s = str(JetBrainsPluginClient._normalize_wsl_path(s)).replace("\\", "/")

        # Extract embedded Windows drive (may appear after container prefixes)
        m = re.search(r"([A-Za-z]:/.*)", s)
        if m:
            drive_path = m.group(1)
            drive_letter = drive_path[0].lower()
            rest = drive_path[2:].lstrip("/")
            s = f"/mnt/{drive_letter}/{rest}"

        # Normalize using POSIX semantics
        s = posixpath.normpath(s)

        # Case-insensitive comparison for Windows-like paths
        return s.lower()

    def matches(self, resolved_path: Path) -> bool:
        if self._project_root is None:
            log.debug("matches(): _project_root is None -> False")
            return False

        try:
            plugin_raw = self._project_root
            local_raw = resolved_path.as_posix()

            # Best-effort logging of original behavior
            original_match = False
            try:
                plugin_root_path = self._normalize_wsl_path(plugin_raw)
                try:
                    original_match = plugin_root_path.resolve() == resolved_path
                except Exception:
                    original_match = False
            except Exception:
                original_match = False

            can_plugin = self._canonicalize_path(plugin_raw)
            can_local = self._canonicalize_path(local_raw)

            log.debug("Serena matches(): plugin raw: %s", plugin_raw)
            log.debug("Serena matches(): local  raw: %s", local_raw)
            log.debug("Serena matches(): original comparison: %s", original_match)
            log.debug("Serena matches(): plugin canonical: %s", can_plugin)
            log.debug("Serena matches(): local  canonical: %s", can_local)

            # Exact canonical match
            if can_plugin == can_local:
                log.debug("Serena matches(): exact canonical match -> True")
                return True

            plugin_parts = [p for p in can_plugin.split("/") if p]
            local_parts = [p for p in can_local.split("/") if p]

            if plugin_parts and local_parts:
                # Suffix match (container / namespace prefixes)
                if len(plugin_parts) <= len(local_parts):
                    if plugin_parts == local_parts[-len(plugin_parts) :]:
                        log.debug("Serena matches(): plugin is suffix of local -> True")
                        return True

                if len(local_parts) <= len(plugin_parts):
                    if local_parts == plugin_parts[-len(local_parts) :]:
                        log.debug("Serena matches(): local is suffix of plugin -> True")
                        return True

                # Fallback: last N components
                MIN_TAIL = 3
                if len(plugin_parts) >= MIN_TAIL and len(local_parts) >= MIN_TAIL:
                    if plugin_parts[-MIN_TAIL:] == local_parts[-MIN_TAIL:]:
                        log.debug("Serena matches(): last %d components match -> True", MIN_TAIL)
                        return True

            log.debug("Serena matches(): no match -> False")
            return False

        except ConnectionError:
            return False
        except Exception as e:
            log.exception("matches(): unexpected exception -> False: %s", e)
            return False

    def is_version_at_least(self, *version_parts: int) -> bool:
        if self._plugin_version is None:
            return False
        return self._plugin_version.is_at_least(*version_parts)

    def _require_version_at_least(self, *version_parts: int) -> None:
        """
        Ensures that the plugin version is at least the given version and raises an error otherwise.

        :param version_parts: the minimum required version parts (major, minor, patch)
        """
        if not self.is_version_at_least(*version_parts):
            raise SerenaClientError(
                f"This operation requires Serena JetBrains plugin version "
                f"{'.'.join(map(str, version_parts))} or higher, but the installed version is "
                f"{self._plugin_version}. Ask the user to update the plugin!"
            )

    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self._base_url}{endpoint}"

        response: Response | None = None
        try:
            if method.upper() == "GET":
                response = self._session.get(url, timeout=self._timeout)
            elif method.upper() == "POST":
                json_data = json.dumps(data) if data else None
                response = self._session.post(url, data=json_data, timeout=self._timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Try to parse JSON response
            try:
                return self._pythonify_response(response.json())
            except json.JSONDecodeError:
                # If response is not JSON, return raw text
                return {"response": response.text}

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Serena service at {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Request to {url} timed out: {e}")
        except requests.exceptions.HTTPError as e:
            if response is not None:
                # check for recoverable error (i.e. errors where the problem can be resolved by the caller or
                # other errors where the error text shall simply be passed on to the LLM).
                # The plugin returns 400 for such errors (typically illegal arguments, e.g. non-unique name path)
                # but only since version 2023.2.6
                if self.is_version_at_least(2023, 2, 6):
                    is_recoverable_error = response.status_code == 400
                else:
                    is_recoverable_error = True  # assume recoverable for older versions (mix of errors)
                if is_recoverable_error:
                    raise APIError(response)
                raise PluginServerError(f"API request failed with status {response.status_code}: {response.text}")
            raise PluginServerError(f"API request failed with HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            raise SerenaClientError(f"Request failed: {e}")

    @staticmethod
    def _pythonify_response(response: T) -> T:
        """
        Converts dictionary keys from camelCase to snake_case recursively.

        :response: the response in which to convert keys (dictionary or list)
        """
        to_snake_case = lambda s: "".join(["_" + c.lower() if c.isupper() else c for c in s])

        def convert(x):  # type: ignore
            if isinstance(x, dict):
                return {to_snake_case(k): convert(v) for k, v in x.items()}
            elif isinstance(x, list):
                return [convert(item) for item in x]
            else:
                return x

        return convert(response)

    def _postprocess_symbol_collection_response(self, response_dict: jb.SymbolCollectionResponse) -> None:
        """
        Postprocesses a symbol collection response in-place, converting HTML documentation to plain text.

        :param response_dict: the response dictionary
        """

        def convert_html(key: Literal["documentation", "quick_info"], symbol: jb.SymbolDTO) -> None:
            if key in symbol:
                doc_html: str = symbol[key]
                doc_text = render_html(doc_html)
                if doc_text:
                    symbol[key] = doc_text
                else:
                    del symbol[key]

        def convert_symbol_list(l: list) -> None:
            for s in l:
                convert_html("documentation", s)
                convert_html("quick_info", s)
                if "children" in s:
                    convert_symbol_list(s["children"])

        convert_symbol_list(response_dict["symbols"])

    def find_symbol(
        self,
        name_path: str,
        relative_path: str | None = None,
        include_body: bool = False,
        include_quick_info: bool = False,
        include_documentation: bool = False,
        include_num_usages: bool = False,
        depth: int = 0,
        include_location: bool = False,
        search_deps: bool = False,
    ) -> jb.SymbolCollectionResponse:
        """
        Finds symbols by name.

        :param name_path: the name path to match
        :param relative_path: the relative path to which to restrict the search
        :param include_body: whether to include symbol body content (should typically not be combined with `include_quick_info`
            or `include_documentation` because the body includes everything)
        :param include_quick_info: whether to include quick info (typically the signature)
        :param include_documentation: whether to include documentation; note that this includes the quick info, so one should
            not pass both `include_quick_info` and this
        :param include_num_usages: whether to include the number of usages
        :param depth: depth up to which to include children (0 = no children)
        :param include_location: whether to include symbol location information
        :param search_deps: whether to also search in dependencies
        """
        request_data = {
            "namePath": name_path,
            "relativePath": relative_path,
            "includeBody": include_body,
            "depth": depth,
            "includeLocation": include_location,
            "searchDeps": search_deps,
            "includeQuickInfo": include_quick_info,
            "includeDocumentation": include_documentation,
            "includeNumUsages": include_num_usages,
        }
        symbol_collection = cast(jb.SymbolCollectionResponse, self._make_request("POST", "/findSymbol", request_data))
        self._postprocess_symbol_collection_response(symbol_collection)
        return symbol_collection

    def find_references(self, name_path: str, relative_path: str, include_quick_info: bool) -> jb.SymbolCollectionResponse:
        """
        Finds references to a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path
        :param include_quick_info: whether to include quick info about references
        """
        request_data = {"namePath": name_path, "relativePath": relative_path, "includeQuickInfo": include_quick_info}
        symbol_collection = cast(jb.SymbolCollectionResponse, self._make_request("POST", "/findReferences", request_data))
        self._postprocess_symbol_collection_response(symbol_collection)
        return symbol_collection

    def get_symbols_overview(
        self, relative_path: str, depth: int, include_file_documentation: bool = False
    ) -> jb.GetSymbolsOverviewResponse:
        """
        :param relative_path: the relative path to a source file
        :param depth: the depth of children to include (0 = no children)
        :param include_file_documentation: whether to include the file's documentation string (if any)
        """
        request_data = {"relativePath": relative_path, "depth": depth, "includeFileDocumentation": include_file_documentation}
        response = cast(jb.GetSymbolsOverviewResponse, self._make_request("POST", "/getSymbolsOverview", request_data))
        self._postprocess_symbol_collection_response(response)

        # process file documentation
        if "documentation" in response:
            response["documentation"] = render_html(response["documentation"])

        return response

    def get_supertypes(
        self,
        name_path: str,
        relative_path: str,
        depth: int | None = None,
        limit_children: int | None = None,
    ) -> jb.TypeHierarchyResponse:
        """
        Gets the supertypes (parent classes/interfaces) of a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path to the file containing the symbol
        :param depth: depth limit for hierarchy traversal (None or 0 for unlimited)
        :param limit_children: optional limit on children per level
        """
        self._require_version_at_least(2023, 2, 6)
        request_data = {
            "namePath": name_path,
            "relativePath": relative_path,
            "depth": depth,
            "limitChildren": limit_children,
        }
        return cast(jb.TypeHierarchyResponse, self._make_request("POST", "/getSupertypes", request_data))

    def get_subtypes(
        self,
        name_path: str,
        relative_path: str,
        depth: int | None = None,
        limit_children: int | None = None,
    ) -> jb.TypeHierarchyResponse:
        """
        Gets the subtypes (subclasses/implementations) of a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path to the file containing the symbol
        :param depth: depth limit for hierarchy traversal (None or 0 for unlimited)
        :param limit_children: optional limit on children per level
        """
        self._require_version_at_least(2023, 2, 6)
        request_data = {
            "namePath": name_path,
            "relativePath": relative_path,
            "depth": depth,
            "limitChildren": limit_children,
        }
        return cast(jb.TypeHierarchyResponse, self._make_request("POST", "/getSubtypes", request_data))

    def rename_symbol(
        self, name_path: str, relative_path: str, new_name: str, rename_in_comments: bool, rename_in_text_occurrences: bool
    ) -> None:
        """
        Renames a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path
        :param new_name: the new name for the symbol
        :param rename_in_comments: whether to rename in comments
        :param rename_in_text_occurrences: whether to rename in text occurrences
        """
        request_data = {
            "namePath": name_path,
            "relativePath": relative_path,
            "newName": new_name,
            "renameInComments": rename_in_comments,
            "renameInTextOccurrences": rename_in_text_occurrences,
        }
        self._make_request("POST", "/renameSymbol", request_data)

    def refresh_file(self, relative_path: str) -> None:
        """
        Triggers a refresh of the given file in the IDE.

        :param relative_path: the relative path
        """
        request_data = {
            "relativePath": relative_path,
        }
        self._make_request("POST", "/refreshFile", request_data)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        self.close()
