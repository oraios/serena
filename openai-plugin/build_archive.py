# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the Serena plugin archive from its portable manifests."""

import argparse
import json
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class PluginArchive:
    """Plugin package builder with generated Codex compatibility manifests."""

    def __init__(self, source: Path) -> None:
        self._source = source.resolve()
        self._manifest = self._read_json("plugin.json")
        self._mcp = self._read_json("mcp.json")

    def _read_json(self, name: str) -> dict[str, Any]:
        """Load a JSON object from the package source."""
        value = json.loads((self._source / name).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{name} must contain a JSON object")
        return value

    @staticmethod
    def _encode(value: dict[str, Any]) -> bytes:
        """Encode a manifest as UTF-8 JSON."""
        return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    def _icon_path(self, archive_path: str) -> Path:
        """Resolve a packaged icon name to its existing repository asset."""
        relative_path = Path(archive_path)
        if len(relative_path.parts) != 2 or relative_path.parts[0] != "assets":
            raise ValueError(f"Icon must reference a file directly inside assets/: {archive_path}")
        directory = self._source.parent / "src/serena/resources/dashboard"
        path = directory / relative_path.name
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError(f"External path or symlink is not allowed: {path}")
        return path

    def _validate(self) -> None:
        """Check package identity, public-upload restrictions, and referenced assets."""
        # validate identity and reject app bindings in the author-supplied upload
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self._manifest["name"]):
            raise ValueError("Plugin name must be lowercase kebab-case")
        if len(self._manifest["name"]) > 64:
            raise ValueError("Plugin name exceeds 64 characters")
        if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", self._manifest["version"]):
            raise ValueError("Use a stable semantic version, such as 0.1.0")
        openai = self._manifest["extensions"]["com.openai"]
        if self._manifest.get("apps") is not None or openai.get("apps") is not None:
            raise ValueError("Public uploads cannot contain app bindings")
        if (self._source / ".app.json").exists():
            raise ValueError("Public uploads cannot include .app.json")

        # validate listing text, links, and real square PNG icons
        interface = openai["interface"]
        for field, limit in {"displayName": 30, "shortDescription": 30, "longDescription": 4000, "developerName": 80}.items():
            value = interface[field]
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f"Invalid {field}; maximum length is {limit}")
        for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
            if field not in interface:
                continue
            url = urlparse(interface[field])
            if url.scheme != "https" or not url.netloc or url.username or url.password or len(interface[field]) > 1024:
                raise ValueError(f"Invalid HTTPS URL: {field}")
        for field, minimum in (("logo", 256), ("composerIcon", 48)):
            data = self._icon_path(interface[field]).read_bytes()
            if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) > 5 * 1024 * 1024:
                raise ValueError(f"{field} must be a PNG no larger than 5 MiB")
            width, height = struct.unpack(">II", data[16:24])
            if width != height or not minimum <= width <= 4096:
                raise ValueError(f"{field} must be square, from {minimum} to 4096 pixels")

        # validate the local process contract without running or modifying the server
        servers = self._mcp["mcpServers"]
        if not isinstance(servers, dict) or not servers:
            raise ValueError("At least one MCP server is required")
        for name, server in servers.items():
            if server.get("type") != "stdio" or not isinstance(server.get("command"), str) or not server["command"]:
                raise ValueError(f"{name} must declare a stdio command")
            if not isinstance(server.get("args"), list) or not all(isinstance(arg, str) for arg in server["args"]):
                raise ValueError(f"{name} must declare a list of string arguments")

    def _members(self) -> dict[str, bytes]:
        """Collect public package files and derive legacy Codex manifests."""
        # collect manifests and the repository's existing license files and icons
        repository = self._source.parent
        members = {
            "plugin.json": self._encode(self._manifest),
            "mcp.json": self._encode(self._mcp),
            "LICENSE": (repository / "LICENSE").read_bytes(),
        }
        directory = repository / "LICENSES"
        if not directory.is_dir():
            raise FileNotFoundError(f"Required package directory is missing: {directory}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.resolve().is_relative_to(directory):
                raise ValueError(f"External path or symlink is not allowed: {path}")
            if path.is_file():
                members[f"LICENSES/{path.relative_to(directory).as_posix()}"] = path.read_bytes()
        interface = self._manifest["extensions"]["com.openai"]["interface"]
        for field in ("logo", "composerIcon"):
            members[Path(interface[field]).as_posix()] = self._icon_path(interface[field]).read_bytes()

        # generate compatibility files from the same canonical configuration
        compatibility = {key: value for key, value in self._manifest.items() if key not in ("$schema", "extensions")}
        interface = dict(self._manifest["extensions"]["com.openai"]["interface"])
        for portable_only in ("supportURL", "composerIconDark", "brandColorDark"):
            interface.pop(portable_only, None)
        compatibility.update(mcpServers="./.mcp.json", interface=interface)
        members[".codex-plugin/plugin.json"] = self._encode(compatibility)
        members[".mcp.json"] = self._encode({"mcpServers": self._mcp["mcpServers"]})
        return members

    def build(self) -> Path:
        """Create and verify the plugin archive."""
        # validate before creating or replacing an output archive
        self._validate()
        members = self._members()
        output = self._source / "dist" / f"{self._manifest['name']}-{self._manifest['version']}.zip"
        output.parent.mkdir(exist_ok=True)

        # write a reproducible archive and verify its contents before replacement
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, content in sorted(members.items()):
                    info = zipfile.ZipInfo(f"{self._manifest['name']}/{name}", date_time=(2000, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, content)
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Archive integrity check failed")
                for name, content in members.items():
                    if archive.read(f"{self._manifest['name']}/{name}") != content:
                        raise ValueError(f"Archive content mismatch: {name}")
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)

        # report the verified output
        print(f"Created and verified: {output}")
        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        PluginArchive(Path(__file__).parent).build()
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
