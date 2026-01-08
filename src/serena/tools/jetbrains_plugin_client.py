"""
Client for the Serena JetBrains Plugin
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Self, TypeVar, cast

import requests
from requests import Response
from sensai.util.string import ToStringMixin

import serena.tools.jetbrains_types as jb
from serena.project import Project

T = TypeVar("T")
log = logging.getLogger(__name__)


class SerenaClientError(Exception):
    """Base exception for Serena client errors."""


class ConnectionError(SerenaClientError):
    """Raised when connection to the service fails."""


class APIError(SerenaClientError):
    """Raised when the API returns an error response."""


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
    last_port: int | None = None

    def __init__(self, port: int, timeout: int = PLUGIN_REQUEST_TIMEOUT):
        self.base_url = f"http://127.0.0.1:{port}"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    def _tostring_includes(self) -> list[str]:
        return ["base_url", "timeout"]

    @classmethod
    def from_project(cls, project: Project) -> Self:
        resolved_path = Path(project.project_root).resolve()

        if cls.last_port is not None:
            client = JetBrainsPluginClient(cls.last_port)
            if client.matches(resolved_path):
                return client

        for port in range(cls.BASE_PORT, cls.BASE_PORT + 20):
            client = JetBrainsPluginClient(port)
            if client.matches(resolved_path):
                log.info("Found JetBrains IDE service at port %d for project %s", port, resolved_path)
                cls.last_port = port
                return client

        raise ServerNotFoundError("Found no Serena service in a JetBrains IDE instance for the project at " + str(resolved_path))

    def matches(self, resolved_path: Path) -> bool:
        try:
            return Path(self.project_root()).resolve() == resolved_path
        except ConnectionError:
            return False

    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

        response: Response | None = None
        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=self.timeout)
            elif method.upper() == "POST":
                json_data = json.dumps(data) if data else None
                response = self.session.post(url, data=json_data, timeout=self.timeout)
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
            unrecoverable_error_prefix = (
                "The request failed due to an error on the Serena JetBrains plugin side. This may be caused"
                "by a bug or an incompatibility in the plugin. In that case, please report the error below together with "
                "your setup (IDE + version, Serena plugin version) at https://github.com/oraios/serena/issues "
                "(if you are an LLM, tell the user about this). The Oraios team will then provide support on this.\n"
            )

            if response is not None:
                # check for recoverable error (i.e. errors where the problem can usually be fixed by the caller).
                # The plugin returns 400 for such errors (typically illegal arguments, e.g. non-unique name path)
                is_recoverable_error = response.status_code == 400

                error_text = f"API request failed with status {response.status_code}: {response.text}"
                if not is_recoverable_error:
                    error_text = unrecoverable_error_prefix + error_text

                raise APIError(error_text)

            raise APIError(unrecoverable_error_prefix + f"API request failed with HTTP error: {e}")
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

    def project_root(self) -> str:
        response = self._make_request("GET", "/status")
        return response["project_root"]

    def find_symbol(
        self,
        name_path: str,
        relative_path: str | None = None,
        include_body: bool = False,
        include_quick_info: bool = True,
        include_documentation: bool = False,
        include_num_usages: bool = True,
        depth: int = 0,
        include_location: bool = False,
        search_deps: bool = False,
    ) -> jb.SymbolCollectionResponse:
        """
        Finds symbols by name.

        :param name_path: the name path to match
        :param relative_path: the relative path to which to restrict the search
        :param include_body: whether to include symbol body content
        :param include_quick_info: whether to include quick info
        :param include_documentation: whether to include documentation
        :param include_num_usages: whether to include number of usages
        :param depth: depth of children to include (0 = no children)
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
        return cast(jb.SymbolCollectionResponse, self._make_request("POST", "/findSymbol", request_data))

    def find_references(self, name_path: str, relative_path: str, include_quick_info: bool) -> jb.SymbolCollectionResponse:
        """
        Finds references to a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path
        :param include_quick_info: whether to include quick info about references
        """
        request_data = {"namePath": name_path, "relativePath": relative_path, "includeQuickInfo": include_quick_info}
        return cast(jb.SymbolCollectionResponse, self._make_request("POST", "/findReferences", request_data))

    def get_symbols_overview(self, relative_path: str, depth: int) -> jb.SymbolCollectionResponse:
        """
        :param relative_path: the relative path to a source file
        :param depth: the depth of children to include (0 = no children)
        """
        request_data = {"relativePath": relative_path, "depth": depth}
        return cast(jb.SymbolCollectionResponse, self._make_request("POST", "/getSymbolsOverview", request_data))

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

    def is_service_available(self) -> bool:
        try:
            self.project_root()
            return True
        except (ConnectionError, APIError):
            return False

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        self.close()
