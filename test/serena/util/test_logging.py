# SPDX-License-Identifier: GPL-3.0-or-later

import gc
import logging
import weakref

from serena.util.logging import MemoryLogHandler


def test_memory_log_handler_close_drains_queue_and_releases_worker() -> None:
    handler = MemoryLogHandler()
    worker = handler.worker_thread
    handler_reference = weakref.ref(handler)
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "queued message", (), None)

    handler.emit(record)
    handler.close()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert handler.get_log_messages().messages[0].endswith("queued message")

    del handler
    gc.collect()
    assert handler_reference() is None


def test_memory_log_handler_can_close_from_emit_callback() -> None:
    handler = MemoryLogHandler()
    worker = handler.worker_thread
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "close handler", (), None)

    def close_handler(_: str) -> None:
        handler.close()

    handler.add_emit_callback(close_handler)
    handler.emit(record)
    worker.join(timeout=2)

    assert not worker.is_alive()
