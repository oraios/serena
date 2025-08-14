"""Improvements to Lean 4 language server symbol extraction."""

import json
import logging
import os
import re
import time
from dataclasses import dataclass

from solidlsp import ls_types
from solidlsp.lsp_protocol_handler.lsp_types import Position, Range


@dataclass
class IleanCacheEntry:
    """Cache entry for parsed .ilean file."""

    symbols: tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]
    mtime: float
    parse_time: float


class ImprovedIleanParser:
    """Improved .ilean file parser with better heuristics and error handling."""

    # Symbol patterns for better type detection
    PATTERNS = {
        "instance": re.compile(r"^inst[A-Z]"),
        "class": re.compile(r"^[A-Z][a-zA-Z]*$"),
        "structure": re.compile(r"^[A-Z][a-zA-Z]*$"),
        "inductive": re.compile(r"^[A-Z][a-zA-Z]*$"),
        "constructor": re.compile(r"\.(mk|cons|nil|some|none|left|right|inl|inr)$"),
        "field": re.compile(r"^[a-z][a-zA-Z]*$"),
        "theorem": re.compile(r"^[a-z_][a-zA-Z0-9_]*$"),
        "definition": re.compile(r"^[a-z_][a-zA-Z0-9_]*$"),
        "axiom": re.compile(r"^[a-z_][a-zA-Z0-9_]*$"),
        "opaque": re.compile(r"^[a-z_][a-zA-Z0-9_]*$"),
    }

    # Known theorem/lemma keywords
    THEOREM_KEYWORDS = {"theorem", "lemma", "proposition", "corollary"}

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._cache: dict[str, IleanCacheEntry] = {}

    def clear_cache(self):
        """Clear the .ilean cache."""
        self._cache.clear()

    def parse_ilean_file(
        self, ilean_path: str, relative_file_path: str, max_parse_time: float = 0.1  # 100ms max parse time
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        Parse .ilean file with improved error handling and caching.

        Returns (top_level_symbols, all_symbols)
        """
        # Check cache first
        if ilean_path in self._cache:
            cached = self._cache[ilean_path]
            try:
                current_mtime = os.path.getmtime(ilean_path)
                if current_mtime == cached.mtime:
                    self.logger.debug(f"Using cached .ilean data for {ilean_path}")
                    return cached.symbols
            except OSError:
                # File might have been deleted, remove from cache
                del self._cache[ilean_path]

        start_time = time.time()

        try:
            # Check file size first
            file_size = os.path.getsize(ilean_path)
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                self.logger.warning(f".ilean file too large ({file_size} bytes): {ilean_path}")
                return ([], [])

            with open(ilean_path, encoding="utf-8") as f:
                data = json.load(f)

            parse_time = time.time() - start_time
            if parse_time > max_parse_time:
                self.logger.warning(f".ilean parse took {parse_time:.3f}s (>{max_parse_time}s): {ilean_path}")

            # Version check
            version = data.get("version")
            if version not in [3, 4]:
                self.logger.error(f"Unsupported .ilean version {version} in {ilean_path}")
                return ([], [])

            references = data.get("references", {})
            if not references:
                self.logger.debug(f"No references found in {ilean_path}")
                return ([], [])

            top_level_symbols = []
            all_symbols = []

            # Expected module name from file path
            expected_module = relative_file_path.replace("/", ".").replace("\\", ".").replace(".lean", "")

            for ref_key, ref_data in references.items():
                try:
                    symbol_info = self._parse_reference(ref_key, ref_data, expected_module, relative_file_path)
                    if symbol_info:
                        all_symbols.append(symbol_info)
                        if self._is_top_level_symbol(symbol_info.name, expected_module):
                            top_level_symbols.append(symbol_info)

                except Exception as e:
                    self.logger.debug(f"Error parsing reference {ref_key}: {e}")
                    continue

            result = (top_level_symbols, all_symbols)

            # Cache the result
            try:
                mtime = os.path.getmtime(ilean_path)
                self._cache[ilean_path] = IleanCacheEntry(result, mtime, parse_time)
            except OSError:
                pass  # Don't cache if we can't get mtime

            return result

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in .ilean file {ilean_path}: {e}")
            return ([], [])
        except OSError as e:
            self.logger.error(f"Error reading .ilean file {ilean_path}: {e}")
            return ([], [])
        except Exception as e:
            self.logger.error(f"Unexpected error parsing .ilean file {ilean_path}: {e}")
            return ([], [])

    def _parse_reference(
        self, ref_key: str, ref_data: dict, expected_module: str, relative_file_path: str
    ) -> ls_types.UnifiedSymbolInformation | None:
        """Parse a single reference entry."""
        ref_obj = json.loads(ref_key)

        if "c" not in ref_obj or "n" not in ref_obj["c"]:
            return None

        symbol_name = ref_obj["c"]["n"]
        module_name = ref_obj["c"]["m"]

        # Only process symbols from the current module
        if module_name != expected_module:
            return None

        definition = ref_data.get("definition")
        if not definition or len(definition) < 4:
            return None

        # Convert 1-based to 0-based indexing
        start_line = definition[0] - 1
        start_char = definition[1]
        end_line = definition[2] - 1
        end_char = definition[3]

        # Determine symbol kind with improved heuristics
        kind = self._infer_symbol_kind(symbol_name, ref_data)

        return ls_types.UnifiedSymbolInformation(
            name=symbol_name,
            name_path=symbol_name,
            kind=kind,
            range=Range(start=Position(line=start_line, character=start_char), end=Position(line=end_line, character=end_char)),
            relative_path=relative_file_path,
            children=[],
        )

    def _infer_symbol_kind(self, symbol_name: str, ref_data: dict) -> ls_types.SymbolKind:
        """
        Infer symbol kind using improved heuristics.
        """
        # Split the symbol name into parts
        parts = symbol_name.split(".")
        last_part = parts[-1]

        # Check for instance pattern
        if self.PATTERNS["instance"].match(last_part):
            return ls_types.SymbolKind.Variable  # Instances are like special variables

        # Check for constructor pattern
        if self.PATTERNS["constructor"].match(symbol_name):
            return ls_types.SymbolKind.Constructor

        # Check if it's a field (has parent structure)
        if len(parts) > 1 and self.PATTERNS["field"].match(last_part):
            parent = parts[-2]
            if parent[0].isupper():  # Parent is likely a structure/class
                return ls_types.SymbolKind.Field

        # Check if it's a method (lowercase in a capitalized parent)
        if len(parts) > 1 and parts[-2][0].isupper() and last_part[0].islower():
            return ls_types.SymbolKind.Method

        # Check for type-like names (capitalized)
        if last_part[0].isupper():
            # Could be Class, Struct, Enum, or Interface
            # Default to Class for now (most common in Lean)
            return ls_types.SymbolKind.Class

        # Check for theorem-like names
        if any(keyword in symbol_name.lower() for keyword in self.THEOREM_KEYWORDS):
            return ls_types.SymbolKind.Property  # Using Property for theorems

        # Default to Function for lowercase symbols
        return ls_types.SymbolKind.Function

    def _is_top_level_symbol(self, symbol_name: str, expected_module: str) -> bool:
        """
        Determine if a symbol is top-level with improved logic.
        """
        # Remove module prefix if present
        module_parts = expected_module.split(".")
        namespace = module_parts[-1] if module_parts else ""

        if symbol_name.startswith(namespace + "."):
            relative_name = symbol_name[len(namespace) + 1 :]
            # Top-level if no dots, or if it's a constructor/field of a top-level type
            if "." not in relative_name:
                return True
            # Also consider Foo.mk as top-level if Foo is top-level
            parts = relative_name.split(".")
            if len(parts) == 2 and parts[1] in ["mk", "rec", "recOn", "casesOn"]:
                return True
            return False
        elif "." not in symbol_name:
            # No dots means top-level
            return True

        return False


def add_performance_assertions(test_func):
    """Decorator to add performance assertions to test functions."""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = test_func(*args, **kwargs)
        elapsed = time.time() - start_time

        # Assert performance bounds
        max_time = kwargs.get("max_time", 0.1)  # 100ms default
        assert elapsed < max_time, f"Test took {elapsed:.3f}s, exceeding limit of {max_time}s"

        return result

    return wrapper
