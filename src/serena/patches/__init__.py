"""
Serena patches for external dependencies.

This module contains minimal patches to external packages that need modifications
for Serena's specific requirements. Patches are applied via import hooks to ensure
they survive cache invalidation and environment rebuilds.

Current patches:
- mcp.server.streamable_http_manager: Graceful session handling for invalid/expired session IDs
"""

import importlib
import sys


class _PatchImportHook:
    """
    Import hook to redirect specific mcp modules to patched versions.
    
    This hook intercepts imports of mcp.server.streamable_http_manager and redirects
    them to our patched version in serena.patches.mcp.server.streamable_http_manager.
    
    All other mcp imports use the external mcp package normally.
    """

    def find_module(self, fullname, path=None):
        """Find module if it's one we patch."""
        if fullname == "mcp.server.streamable_http_manager":
            return self
        return None

    def load_module(self, fullname):
        """Load the patched module instead of the original."""
        if fullname in sys.modules:
            return sys.modules[fullname]

        # Load our patched version
        patched_module = importlib.import_module("serena.patches.mcp.server.streamable_http_manager")
        
        # Register it as the mcp module so future imports get our patched version
        sys.modules[fullname] = patched_module
        
        return patched_module


# Install the import hook if not already installed
if not any(isinstance(h, _PatchImportHook) for h in sys.meta_path):
    sys.meta_path.insert(0, _PatchImportHook())

