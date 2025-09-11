"""
Android-specific test configuration with optimized fixtures for better performance.

This module implements:
1. Session-scoped language server fixtures to avoid repeated startup costs
2. Language server pooling to reuse instances across tests
3. Proper cleanup and isolation between test runs
"""

import logging
import threading
from pathlib import Path
from typing import Optional

import pytest

from serena.constants import SERENA_MANAGED_DIR_IN_HOME, SERENA_MANAGED_DIR_NAME
from solidlsp.language_servers.android_language_server import AndroidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


class AndroidLanguageServerPool:
    """
    Pool of AndroidLanguageServer instances for test reuse.
    
    Manages a pool of initialized language servers that can be shared across
    tests to avoid the expensive startup cost of Eclipse JDTLS and Kotlin LS.
    """
    
    def __init__(self, max_pool_size: int = 2):
        self.max_pool_size = max_pool_size
        self.available_servers: list[AndroidLanguageServer] = []
        self.in_use_servers: set[AndroidLanguageServer] = set()
        self.lock = threading.Lock()
        self.logger = LanguageServerLogger(log_level=logging.ERROR)
        
    def get_server(self, repository_root_path: str) -> AndroidLanguageServer:
        """Get an available server from the pool or create a new one."""
        with self.lock:
            # Try to reuse an existing server
            if self.available_servers:
                server = self.available_servers.pop()
                self.in_use_servers.add(server)
                self.logger.log(f"Reusing Android LS from pool ({len(self.available_servers)} remaining)", logging.DEBUG)
                return server
            
            # Create a new server if pool isn't at capacity
            if len(self.in_use_servers) < self.max_pool_size:
                server = self._create_server(repository_root_path)
                self.in_use_servers.add(server)
                self.logger.log(f"Created new Android LS for pool ({len(self.in_use_servers)}/{self.max_pool_size})", logging.DEBUG)
                return server
            
            # Pool is at capacity, wait or create temporary server
            # For now, create a temporary server (could implement waiting/blocking here)
            return self._create_server(repository_root_path)
    
    def return_server(self, server: AndroidLanguageServer) -> None:
        """Return a server to the pool for reuse."""
        with self.lock:
            if server in self.in_use_servers:
                self.in_use_servers.remove(server)
                
                # Only keep servers that are still healthy
                if self._is_server_healthy(server):
                    self.available_servers.append(server)
                    self.logger.log(f"Returned Android LS to pool ({len(self.available_servers)} available)", logging.DEBUG)
                else:
                    self.logger.log("Android LS unhealthy, not returning to pool", logging.DEBUG)
                    self._cleanup_server(server)
    
    def cleanup_all(self) -> None:
        """Clean up all servers in the pool."""
        with self.lock:
            all_servers = list(self.available_servers) + list(self.in_use_servers)
            for server in all_servers:
                self._cleanup_server(server)
            
            self.available_servers.clear()
            self.in_use_servers.clear()
            self.logger.log("Cleaned up all Android LS instances in pool", logging.DEBUG)
    
    def _create_server(self, repository_root_path: str) -> AndroidLanguageServer:
        """Create and start a new AndroidLanguageServer instance."""
        config = LanguageServerConfig(
            code_language=Language.ANDROID,
            trace_lsp_communication=False,  # Disable tracing for performance
            start_independent_lsp_process=True,
            ignored_paths=[]
        )
        
        solidlsp_settings = SolidLSPSettings(
            solidlsp_dir=SERENA_MANAGED_DIR_IN_HOME, 
            project_data_relative_path=SERENA_MANAGED_DIR_NAME
        )
        
        server = AndroidLanguageServer(config, self.logger, repository_root_path, solidlsp_settings)
        
        try:
            server.start()
            self.logger.log("Started new Android LS instance", logging.DEBUG)
            return server
        except Exception as e:
            self.logger.log(f"Failed to start Android LS: {e}", logging.ERROR)
            raise
    
    def _is_server_healthy(self, server: AndroidLanguageServer) -> bool:
        """Check if a server is still healthy and can be reused."""
        try:
            # Basic health check - ensure delegates are still running
            if not hasattr(server, 'java_ls') or not hasattr(server, 'kotlin_ls'):
                return False
                
            # Could add more sophisticated health checks here
            # For now, assume server is healthy if it has delegates
            return True
            
        except Exception:
            return False
    
    def _cleanup_server(self, server: AndroidLanguageServer) -> None:
        """Clean up a server instance."""
        try:
            server.shutdown()
        except Exception as e:
            self.logger.log(f"Error shutting down Android LS: {e}", logging.WARNING)


# Global pool instance
_android_server_pool: Optional[AndroidLanguageServerPool] = None


@pytest.fixture(scope="session")
def android_server_pool():
    """Session-scoped fixture providing the Android language server pool."""
    global _android_server_pool
    
    if _android_server_pool is None:
        _android_server_pool = AndroidLanguageServerPool(max_pool_size=2)
    
    yield _android_server_pool
    
    # Cleanup at end of test session
    if _android_server_pool:
        _android_server_pool.cleanup_all()
        _android_server_pool = None


@pytest.fixture(scope="session")
def android_test_project_path():
    """Get the path to the Android test project."""
    return str(Path(__file__).parent.parent.parent / "resources" / "repos" / "android" / "test_repo")


@pytest.fixture
def android_language_server(android_server_pool: AndroidLanguageServerPool, android_test_project_path: str):
    """
    Provide an AndroidLanguageServer instance from the pool.
    
    This fixture gets a server from the pool, yields it for the test,
    then returns it to the pool for reuse by other tests.
    """
    server = android_server_pool.get_server(android_test_project_path)
    
    try:
        yield server
    finally:
        # Return server to pool for reuse
        android_server_pool.return_server(server)


@pytest.fixture  
def android_language_server_no_pool(android_test_project_path: str):
    """
    Provide a fresh AndroidLanguageServer instance (not from pool).
    
    Use this fixture for tests that need a completely fresh server instance
    or might modify server state in ways that make it unsuitable for reuse.
    """
    config = LanguageServerConfig(
        code_language=Language.ANDROID,
        trace_lsp_communication=False,
        start_independent_lsp_process=True,
        ignored_paths=[]
    )
    
    logger = LanguageServerLogger(log_level=logging.ERROR)
    solidlsp_settings = SolidLSPSettings(
        solidlsp_dir=SERENA_MANAGED_DIR_IN_HOME, 
        project_data_relative_path=SERENA_MANAGED_DIR_NAME
    )
    
    server = AndroidLanguageServer(config, logger, android_test_project_path, solidlsp_settings)
    
    try:
        server.start()
        yield server
    finally:
        server.shutdown()


@pytest.fixture(scope="session") 
def shared_android_server(android_server_pool: AndroidLanguageServerPool, android_test_project_path: str):
    """
    Session-scoped shared AndroidLanguageServer for read-only tests.
    
    This server is initialized once per test session and shared across
    all tests that only read data (symbols, definitions, etc.) without
    modifying server state.
    """
    server = android_server_pool.get_server(android_test_project_path)
    
    try:
        yield server
    finally:
        # Return to pool at end of session
        android_server_pool.return_server(server)


# Pytest configuration for parallelization
def pytest_configure(config):
    """Configure pytest for Android test optimization."""
    # Add custom markers
    config.addinivalue_line("markers", "android_slow: mark test as slow Android test")
    config.addinivalue_line("markers", "android_fast: mark test as fast Android test") 
    config.addinivalue_line("markers", "android_readonly: mark test as read-only Android test")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to optimize Android test execution."""
    for item in items:
        # Add markers based on test patterns
        if "android" in item.keywords:
            if any(keyword in item.name.lower() for keyword in ["startup", "initialization", "crash"]):
                item.add_marker(pytest.mark.android_fast)
            elif any(keyword in item.name.lower() for keyword in ["symbol", "reference", "definition"]):
                item.add_marker(pytest.mark.android_readonly)  
            else:
                item.add_marker(pytest.mark.android_slow)
