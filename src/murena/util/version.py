class Version:
    """
    Represents a version, specifically the numeric components of a version string.

    Suffixes like "rc1" or "-dev" are ignored, i.e. for a version string like "1.2.3rc1",
    the components are [1, 2, 3].
    """

    def __init__(self, package_or_version: object | str):
        """
        :param package_or_version: a package object (with a `__version__` attribute) or a version string like "1.2.3".
            If a version contains a suffix (like "1.2.3rc1" or "1.2.3-dev"), the suffix is ignored.
        """
        if isinstance(package_or_version, str):
            version_string = package_or_version
        elif hasattr(package_or_version, "__version__"):
            package_version_string = getattr(package_or_version, "__version__", None)
            if package_version_string is None:
                raise ValueError(f"The given package object {package_or_version} has no __version__ attribute")
            version_string = package_version_string
        else:
            raise ValueError("The given argument must be either a version string or a package object with a __version__ attribute")
        self.version_string = version_string
        self.components = self._get_version_components(version_string)

    def __str__(self) -> str:
        return self.version_string

    @staticmethod
    def _get_version_components(version_string: str) -> list[int]:
        components = version_string.split(".")
        int_components = []
        for c in components:
            num_str = ""
            for ch in c:
                if ch.isdigit():
                    num_str += ch
                else:
                    break
            if num_str == "":
                break
            int_components.append(int(num_str))
        return int_components

    def is_at_least(self, *components: int) -> bool:
        """
        Checks this version against the given version components.
        This version object must contain at least the respective number of components

        :param components: version components in order (i.e. major, minor, patch, etc.)
        :return: True if the version is at least the given version, False otherwise
        """
        for i, desired_min_version in enumerate(components):
            actual_version = self.components[i]
            if actual_version < desired_min_version:
                return False
            elif actual_version > desired_min_version:
                return True
        return True

    def is_at_most(self, *components: int) -> bool:
        """
        Checks this version against the given version components.
        This version object must contain at least the respective number of components

        :param components: version components in order (i.e. major, minor, patch, etc.)
        :return: True if the version is at most the given version, False otherwise
        """
        for i, desired_max_version in enumerate(components):
            actual_version = self.components[i]
            if actual_version > desired_max_version:
                return False
            elif actual_version < desired_max_version:
                return True
        return True

    def is_equal(self, *components: int) -> bool:
        """
        Checks this version against the given version components.
        This version object must contain at least the respective number of components

        :param components: version components in order (i.e. major, minor, patch, etc.)
        :return: True if the version is the given version, False otherwise
        """
        return self.components[: len(components)] == list(components)
