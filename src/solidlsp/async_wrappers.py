"""
Async wrappers for SolidLanguageServer to enable parallel LSP operations.

This module provides async-friendly wrappers around synchronous LSP operations,
allowing multiple requests to execute concurrently using asyncio.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger(__name__)

# Global thread pool for LSP operations (shared across all language servers)
# Using 10 workers allows up to 10 concurrent LSP requests
_lsp_thread_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="LSPAsync")


async def run_in_executor(func: Any, *args: Any) -> Any:
    """
    Run a synchronous function in the thread pool executor.

    This allows blocking LSP operations to run concurrently without
    blocking the async event loop.

    Args:
        func: The synchronous function to execute
        *args: Arguments to pass to the function

    Returns:
        The result of the function call

    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_lsp_thread_pool, func, *args)


def shutdown_executor() -> None:
    """
    Shutdown the thread pool executor.

    Should be called on application shutdown to clean up resources.
    """
    _lsp_thread_pool.shutdown(wait=True, cancel_futures=False)
    log.debug("LSP thread pool executor shut down")
