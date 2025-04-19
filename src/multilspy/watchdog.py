import logging
import os.path
import threading
import time
from pathlib import Path

from multilspy import SyncLanguageServer
from multilspy.lsp_protocol_handler.lsp_types import DidChangeWatchedFilesParams, FileEvent, FileChangeType
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

log = logging.getLogger(__name__)


class ProjectFolderWatchdog:
    def __init__(self, sync_language_server: SyncLanguageServer):
        language_server = sync_language_server.language_server
        project_root = language_server.repository_root_path
        self.observer = Observer()
        self.observer.schedule(self.Handler(sync_language_server), project_root, recursive=True)
        log.info(f"Starting watchdog for {project_root}")
        self.observer.start()

    class Handler(FileSystemEventHandler):
        def __init__(self, sync_language_server: SyncLanguageServer):
            super().__init__()
            self.sync_language_server = sync_language_server
            self.language_server = sync_language_server.language_server
            self.last_event = None
            self.last_event_time = None
            self.lock = threading.Lock()

        def on_modified(self, event):
            self._notify(event, FileChangeType.Changed)

        def on_created(self, event):
            self._notify(event, FileChangeType.Created)

        def on_deleted(self, event):
            self._notify(event, FileChangeType.Deleted)

        def _notify(self, event: FileSystemEvent, change_type: FileChangeType):
            if event.is_directory:
                return
            with self.lock:
                rel_path = os.path.relpath(event.src_path, self.language_server.repository_root_path)
                if self.sync_language_server.is_ignored_path(rel_path, check_existence=False):
                    return
                if self.last_event is None or event.src_path != self.last_event.src_path or time.time() - self.last_event_time > 0.1:
                    log.info(f"External file change event: {rel_path}; change type: {change_type.name}")
                self.last_event = event
                self.last_event_time = time.time()
                file_event: FileEvent = {
                    "uri": Path(event.src_path).as_uri(),
                    "type": change_type
                }
                params: DidChangeWatchedFilesParams = {
                    "changes": [file_event]
                }
                self.language_server.server.notify.did_change_watched_files(params)

    def __del__(self):
        log.info("Stopping watchdog")
        self.observer.stop()
        self.observer.join()
