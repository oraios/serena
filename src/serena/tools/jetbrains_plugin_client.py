"""
Client for the Serena JetBrains Plugin
"""

import json
from typing import Any, Optional, Self

import requests


class SerenaClientError(Exception):
    """Base exception for Serena client errors."""


class ConnectionError(SerenaClientError):
    """Raised when connection to the service fails."""


class APIError(SerenaClientError):
    """Raised when the API returns an error response."""


class JetBrainsPluginClient:
    """
    Python client for the Serena Backend Service.

    Provides simple methods to interact with all available endpoints.
    """

    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

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
                return response.json()
            except json.JSONDecodeError:
                # If response is not JSON, return raw text
                return {"response": response.text}

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Serena service at {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise ConnectionError(f"Request to {url} timed out: {e}")
        except requests.exceptions.HTTPError:
            raise APIError(f"API request failed with status {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            raise SerenaClientError(f"Request failed: {e}")

    def heartbeat(self) -> dict[str, Any]:
        return self._make_request("GET", "/heartbeat")

    def find_symbol(self, name_path: str, relative_path: str | None = None, include_body: bool = False, depth: int = 0) -> dict[str, Any]:
        """
        Find symbols by name.

        :param name_path: the name path to match
        :param relative_path: the relative path to which to restrict the search
        :param include_body: whether to include symbol body content
        :param depth: depth of children to include (0 = no children)

        :return: Dictionary containing 'symbols' list with matching symbols
        """
        request_data = {"namePath": name_path, "relativePath": relative_path, "includeBody": include_body, "depth": depth}

        return self._make_request("POST", "/findSymbol", request_data)

    def find_references(self, name_path: str, relative_path: str) -> dict[str, Any]:
        """
        Find references to a symbol.

        :param name_path: the name path of the symbol
        :param relative_path: the relative path
        :return: dictionary containing 'symbols' list with symbol references
        """
        request_data = {"namePath": name_path, "relativePath": relative_path}

        return self._make_request("POST", "/findReferences", request_data)

    def is_service_available(self) -> bool:
        try:
            response = self.heartbeat()
            return response.get("status") == "OK"
        except (ConnectionError, APIError):
            return False

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        self.close()


if __name__ == "__main__":
    with JetBrainsPluginClient() as client:
        # check heartbeat
        heartbeat_response = client.heartbeat()
        print(f"Heartbeat: {heartbeat_response}")

        # find symbol
        symbols_response = client.find_symbol("DQN", include_body=False, depth=1)
        symbols = symbols_response.get("symbols", [])
        print(f"Found {len(symbols)} symbols")
        from pprint import pprint

        pprint(symbols_response)

        # find references
        if symbols:
            first_symbol = symbols[0]
            refs_response = client.find_references(name_path=first_symbol["namePath"], relative_path=first_symbol["relativePath"])
            pprint(refs_response)
