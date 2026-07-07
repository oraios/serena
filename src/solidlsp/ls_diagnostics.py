"""PublishedDiagnosticsHub: deep module for LSP publishDiagnostics storage and coordination.

Extracted from SolidLanguageServer in ls.py (Phase 1 of the Ousterhout deep-module refactor).
This module owns the volatile decisions around:
- URI canonicalization (Windows drive-letter case / %3A normalization)
- Generation counters and per-URI generation tracking
- Thread-safe storage of the latest published diagnostics payload
- Condition-variable based waiting for "newer than X" publications

The hub is intentionally not a full LSP client; it is a narrow state machine that
the SolidLanguageServer facade wires into via:
- record(params) from the generic notification observer
- generation/cached/wait APIs from the public diagnostics request paths
- policy hooks that remain on the facade (_supports_pull_diagnostics, _accept_*, etc.)

Backward-compatibility note:
- No public names from this module are currently imported by adapters or serena.
- If any consumer begins importing from here, add a re-export shim in solidlsp/ls.py.
"""

from __future__ import annotations

import os
import threading
from time import perf_counter
from typing import Any

from solidlsp import ls_types


class PublishedDiagnosticsHub:
    """Thread-safe store + waiter for diagnostics received via textDocument/publishDiagnostics.

    Responsibilities (and only these):
    - Store normalized Diagnostic dicts keyed by a canonical URI
    - Maintain a monotonically increasing generation counter
    - Track per-URI generation so waiters can say "after N"
    - Provide canonicalization so pathlib.Path(...).as_uri() lookups match server publications
    - Expose wait / cached / generation queries behind the condition variable

    The hub does not know about:
    - Pull diagnostics (textDocument/diagnostic)
    - Range/severity filtering (done by the facade after retrieval)
    - "Relevant payload" acceptance policy (_accept_published_diagnostics)
    - Per-language URI rewriting (_get_published_diagnostics_uri)
    - Timeouts or open-file bracketing

    Those remain policy/behavior on SolidLanguageServer so subclasses can override them
    without touching the hub.
    """

    def __init__(self) -> None:
        # Latest published diagnostics by canonical URI
        self._diagnostics: dict[str, list[ls_types.Diagnostic]] = {}
        # Per-URI generation (strictly increasing within a given URI's key)
        self._generation_by_uri: dict[str, int] = {}
        # Global generation used to hand out "after this" tokens
        self._generation: int = 0
        # Single condition variable guarding all three maps above
        self._condition = threading.Condition()

    # ------------------------------------------------------------------
    # Recording path (called from _observe_server_notification on publishDiagnostics)
    # ------------------------------------------------------------------

    def record(self, params: Any) -> None:
        """Record a publishDiagnostics notification payload.

        Safe to call with any value; non-conforming payloads are ignored.
        Normalizes the diagnostics into ls_types.Diagnostic dicts and updates
        generation counters under the condition variable, then notifies waiters.
        """
        if not isinstance(params, dict):
            return

        uri = params.get("uri")
        diagnostics = params.get("diagnostics")
        if not isinstance(uri, str) or not isinstance(diagnostics, list):
            return

        normalized: list[ls_types.Diagnostic] = []
        for d in diagnostics:
            if not isinstance(d, dict):
                continue
            if "message" not in d or "range" not in d:
                continue

            nd: ls_types.Diagnostic = {
                "uri": uri,
                "message": d["message"],
                "range": d["range"],
            }
            sev = d.get("severity")
            if isinstance(sev, int):
                nd["severity"] = ls_types.DiagnosticSeverity(sev)
            code = d.get("code")
            if isinstance(code, int | str):
                nd["code"] = code
            if "source" in d:
                nd["source"] = d["source"]
            normalized.append(ls_types.Diagnostic(**nd))

        key = self._canonicalize_uri(uri)

        with self._condition:
            self._generation += 1
            self._diagnostics[key] = normalized
            self._generation_by_uri[key] = self._generation
            self._condition.notify_all()

    # ------------------------------------------------------------------
    # Public-ish queries used by the facade
    # ------------------------------------------------------------------

    def get_generation(self, uri: str) -> int:
        """Return the latest generation for a URI, or -1 if never seen."""
        key = self._canonicalize_uri(uri)
        with self._condition:
            return self._generation_by_uri.get(key, -1)

    def wait_for(
        self,
        uri: str,
        after_generation: int,
        timeout: float,
    ) -> list[ls_types.Diagnostic] | None:
        """Wait until a publication with generation > after_generation arrives for uri.

        Returns a shallow copy of the diagnostics list on success, or None on timeout.
        """
        key = self._canonicalize_uri(uri)
        deadline = perf_counter() + timeout
        with self._condition:
            while True:
                current = self._generation_by_uri.get(key, -1)
                if current > after_generation:
                    return list(self._diagnostics.get(key, []))
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)

    def get_cached(self, uri: str) -> list[ls_types.Diagnostic] | None:
        """Return a shallow copy of the latest diagnostics for uri, or None if none stored."""
        key = self._canonicalize_uri(uri)
        with self._condition:
            diags = self._diagnostics.get(key)
            if diags is None:
                return None
            return list(diags)

    # ------------------------------------------------------------------
    # Canonicalization (matches the original behavior exactly)
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize_uri(uri: str) -> str:
        """Canonicalize a file:// URI for cross-platform key stability.

        On Windows, servers may publish under file:///c%3A/... or file:///c:/... while
        pathlib.Path(...).as_uri() produces file:///C:/.... We normalize to an
        upper-case drive letter and a plain colon.
        """
        if os.name != "nt" or not uri.startswith("file:///"):
            return uri

        prefix = "file:///"
        rest = uri[len(prefix) :]
        slash = rest.find("/")
        head = rest if slash < 0 else rest[:slash]
        tail = "" if slash < 0 else rest[slash:]

        # Accept either "c:" or "c%3a" (case-insensitive for the %3a form)
        if (len(head) >= 2 and head[0].isalpha() and head[1] == ":") or (
            len(head) >= 4 and head[0].isalpha() and head[1:4].lower() == "%3a"
        ):
            head = head[0].upper() + ":"
        else:
            return uri

        return prefix + head + tail
