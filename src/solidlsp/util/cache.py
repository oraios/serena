# SPDX-License-Identifier: MIT

import contextlib
import logging
import os
import tempfile
from typing import Any, Optional

from sensai.util.pickle import dump_pickle, load_pickle

from solidlsp.util.pickle_util import SafePickleLoader

log = logging.getLogger(__name__)


def load_cache(path: str, version: Any, loader: SafePickleLoader | None = None) -> Optional[Any]:
    if loader is None:
        data = load_pickle(path)
    else:
        data = loader.load(path)
    if not isinstance(data, dict) or "__cache_version" not in data:
        log.info("Cache is outdated (expected version %s). Ignoring cache at %s", version, path)
        return None
    saved_version = data["__cache_version"]
    if saved_version != version:
        log.info("Cache is outdated (expected version %s, got %s). Ignoring cache at %s", version, saved_version, path)
        return None
    return data["obj"]


def save_cache(path: str, version: Any, obj: Any) -> None:
    data = {"__cache_version": version, "obj": obj}
    directory, file_name = os.path.split(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    file_descriptor, temp_path = tempfile.mkstemp(prefix=file_name + ".", suffix=".tmp", dir=directory)
    os.close(file_descriptor)
    try:
        dump_pickle(data, temp_path)
        os.replace(temp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temp_path)
        raise
