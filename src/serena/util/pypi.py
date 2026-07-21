"""Utilities for querying package information from the Python Package Index (PyPI)."""

import requests


class PyPIPackageInfo:
    """Provider of information on a package hosted on the Python Package Index (PyPI).

    Information is retrieved on demand via PyPI's JSON API.
    """

    JSON_API_URL_TEMPLATE = "https://pypi.org/pypi/%s/json"

    def __init__(self, package_name: str) -> None:
        """
        :param package_name: the name of the package on PyPI (e.g. "requests")
        """
        self.package_name = package_name

    def get_latest_version(self, timeout_secs: int = 5) -> str:
        """Retrieves the latest released version of the package from PyPI.

        :return: the latest version string (e.g. "2.33.0")
        :raises requests.RequestException: if the HTTP request fails or PyPI responds with an error status
        """
        # query PyPI's JSON API for the package metadata
        url = self.JSON_API_URL_TEMPLATE % self.package_name
        response = requests.get(url, timeout=timeout_secs)
        response.raise_for_status()

        # extract the latest version from the metadata
        return response.json()["info"]["version"]
