"""
Serena patches for external dependencies.

This module contains minimal patches to external packages that need modifications
for Serena's specific requirements. Patches are applied via import hooks to ensure
they survive cache invalidation and environment rebuilds.

Current patches:
- mcp.server.streamable_http_manager: Graceful session handling for invalid/expired session IDs
"""

import importlib
import importlib.abc
import importlib.util
import logging
import sys
from collections.abc import Sequence
from typing import Any, Optional

logger = logging.getLogger(__name__)


class _PatchLoader(importlib.abc.Loader):
    """
    Loader for patched modules.

    Implements PEP 451 loader protocol to load patched versions of modules.
    """

    def exec_module(self, module: Any) -> None:
        """
        Execute the patched module in the given namespace.

        Args:
            module: The module object to populate

        """
        try:
            # Load our patched version
            patched_module = importlib.import_module("serena.patches.mcp.server.streamable_http_manager")

            # Copy all attributes from patched module to the target module
            module.__dict__.update(patched_module.__dict__)

            logger.debug("Successfully loaded patched mcp.server.streamable_http_manager")
        except Exception as e:
            logger.exception(f"Failed to load patched module: {e}")
            raise


class _PatchImportHook(importlib.abc.MetaPathFinder):
    """
    Import hook to redirect specific mcp modules to patched versions.

    This hook intercepts imports of mcp.server.streamable_http_manager and redirects
    them to our patched version in serena.patches.mcp.server.streamable_http_manager.

    All other mcp imports use the external mcp package normally.

    Implements PEP 451 import hook protocol (find_spec) instead of deprecated
    find_module/load_module for better compatibility with modern Python.
    """

    def find_spec(
        self, fullname: str, path: Optional[Sequence[str]], target: Optional[Any] = None
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """
        Find module spec if it's one we patch.

        Args:
            fullname: Fully qualified module name
            path: Package path (for submodules)
            target: Target module (for reloading)

        Returns:
            ModuleSpec for patched module, or None if not patched

        """
        if fullname == "mcp.server.streamable_http_manager":
            logger.debug(f"Intercepting import of {fullname}, redirecting to patched version")
            return importlib.util.spec_from_loader(fullname, _PatchLoader(), origin="serena.patches.mcp.server.streamable_http_manager")
        return None


# Install the import hook if not already installed
if not any(isinstance(h, _PatchImportHook) for h in sys.meta_path):
    sys.meta_path.insert(0, _PatchImportHook())
    logger.debug("Installed Serena patch import hook")
