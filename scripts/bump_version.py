# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

import click

from serena.constants import REPO_ROOT
from serena.util.git import get_git_status

log = logging.getLogger(__name__)

VersionPart = Literal["major", "minor", "patch"]
#: a version part to bump or, in the case of "current", the version already reserved by the current .dev version
VersionTarget = Literal["major", "minor", "patch", "current"]
_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(\.\w+)?$")
_INIT_VERSION_PATTERN = re.compile(r'^(?P<before>__version__\s*=\s*")(?P<version>\d+\.\d+\.\d+(?:\.\w+)?)(?P<after>"\s*)$', re.MULTILINE)
_PYPROJECT_VERSION_PATTERN = re.compile(
    r'(?m)^(?P<before>\[project\]\n(?:.*\n)*?^version\s*=\s*")(?P<version>\d+\.\d+\.\d+(?:\.\w+)?)(?P<after>"\s*)$'
)
_VERSION_SUFFIX_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.(?P<suffix>\w+)$")
_UNRELEASED_HEADER = "# Unreleased (main)\n"


_version_target_argument = click.argument("version_target", type=click.Choice(["current", "major", "minor", "patch"]))
_version_part_argument = click.argument("version_part", type=click.Choice(["major", "minor", "patch"]))
_dry_run_option = click.option("--dry-run", is_flag=True, help="Show what would change without writing any files.")


@click.group()
def cli() -> None:
    """Manages the Serena version."""


@cli.command()
@_version_target_argument
@_dry_run_option
def release(version_target: VersionTarget, dry_run: bool) -> None:
    """Bumps the version for a release and starts the next dev iteration.

    Bumps the version, updates the changelog, commits and tags the release, and then commits
    the subsequent .dev0 version.

    VERSION_TARGET is either "current", releasing the version already reserved by the current .dev version
    (the usual case), or the part of the version to bump beyond it (major, minor or patch).
    """
    require_clean_working_directory()
    log.info("release called: version_target=%s", version_target)

    repo_root = find_repo_root()
    log.info("Repo root: %s", repo_root)

    # bump to the release version
    new_version = bump_repo_version(repo_root, version_target=version_target, dry_run=dry_run)
    log.info("New version: %s", new_version)
    if dry_run:
        click.echo(f"Dry run complete. Version would be bumped to {new_version}")
        return

    # commit and tag the release version
    commit_version_change(new_version, message=f"Release v{new_version}")
    os.system(f"git tag v{new_version}")

    # bump patch and add the suffix for the next dev iteration
    new_snapshot_version = bump_repo_version(repo_root, version_target="patch", dry_run=dry_run, target_version_suffix=".dev0")
    log.info("New snapshot version: %s", new_snapshot_version)
    commit_version_change(new_snapshot_version, message=f"Set version to v{new_snapshot_version}")


@cli.command()
@_version_part_argument
@_dry_run_option
def dev(version_part: VersionPart, dry_run: bool) -> None:
    """Bumps the development version without creating a release.

    Sets the version to a new .dev0 version and commits it; no tag is created and the changelog
    is not modified.

    VERSION_PART is the part of the version to bump (major, minor or patch).
    """
    require_clean_working_directory()
    log.info("dev called: version_part=%s", version_part)

    repo_root = find_repo_root()
    log.info("Repo root: %s", repo_root)

    new_version = bump_repo_version(repo_root, version_target=version_part, dry_run=dry_run, target_version_suffix=".dev0")
    log.info("New version: %s", new_version)
    if dry_run:
        click.echo(f"Dry run complete. Version would be bumped to {new_version}")
        return

    commit_version_change(new_version, message=f"Set version to v{new_version}")


def require_clean_working_directory() -> None:
    if not get_git_status().is_clean:
        raise click.ClickException("Working directory is not clean. Please commit or stash your changes first.")


def commit_version_change(new_version: str, *, message: str) -> None:
    os.system("uv lock")
    click.echo(f"Bumped version to {new_version}")
    os.system("git add -u")
    os.system(f'git commit -m "{message}"')


def find_repo_root() -> Path:
    return Path(REPO_ROOT)


def bump_repo_version(
    repo_root: Path,
    *,
    version_target: VersionTarget,
    dry_run: bool = False,
    target_version_suffix: str | None = None,
) -> str:
    pyproject_path = repo_root / "pyproject.toml"
    init_path = repo_root / "src" / "serena" / "__init__.py"
    changelog_path = repo_root / "CHANGELOG.md"

    log.info("Reading pyproject.toml from %s", pyproject_path)
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    log.info("Reading __init__.py from %s", init_path)
    init_text = init_path.read_text(encoding="utf-8")
    log.info("Reading CHANGELOG.md from %s", changelog_path)
    changelog_text = changelog_path.read_text(encoding="utf-8")

    log.info("Extracting versions")
    current_version = extract_version(pyproject_text, _PYPROJECT_VERSION_PATTERN, "pyproject.toml")
    init_version = extract_version(init_text, _INIT_VERSION_PATTERN, "src/serena/__init__.py")
    log.info("pyproject.toml version: %s, __init__.py version: %s", current_version, init_version)
    if current_version != init_version:
        raise click.ClickException(
            f"Version mismatch between pyproject.toml and src/serena/__init__.py: {current_version} != {init_version}"
        )

    if version_target == "current" and _VERSION_SUFFIX_PATTERN.search(current_version) is None:
        raise click.ClickException(
            f"The current version {current_version} is not a development version, so there is no reserved version to release. "
            f"Use major, minor or patch to bump the version instead."
        )
    new_version = increment_version(current_version, version_target)
    if target_version_suffix is not None:
        new_version += target_version_suffix
    log.info("New version will be: %s", new_version)

    new_pyproject_text = replace_version(pyproject_text, _PYPROJECT_VERSION_PATTERN, new_version, "pyproject.toml")
    new_init_text = replace_version(init_text, _INIT_VERSION_PATTERN, new_version, "src/serena/__init__.py")

    file_changes: list[tuple[Path, str, str]] = [
        (pyproject_path, pyproject_text, new_pyproject_text),
        (init_path, init_text, new_init_text),
    ]

    # update changelog only for actual releases (not -dev versions with suffixes)
    if target_version_suffix is None:
        new_changelog_text = update_changelog(changelog_text, new_version)
        file_changes.append((changelog_path, changelog_text, new_changelog_text))

    if dry_run:
        for path, old, new in file_changes:
            if old != new:
                rel = path.relative_to(repo_root)
                click.echo(f"\n--- {rel}")
                _print_diff(old, new)
    else:
        for path, _old, new in file_changes:
            log.info("Writing %s", path)
            path.write_text(new, encoding="utf-8")
        log.info("All files written successfully")

    return new_version


def _print_diff(old: str, new: str) -> None:
    import difflib

    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")
    # Skip the --- / +++ header lines from unified_diff
    lines = list(diff)
    for line in lines[2:]:
        click.echo(line)


def extract_version(text: str, pattern: re.Pattern[str], file_label: str) -> str:
    """
    Extracts the core version Major.Minor.Patch in the given text
    :param text:
    :param pattern: the pattern to search for
    :param file_label: file reference for error messages
    :return: the core version
    """
    match = pattern.search(text)
    if match is None:
        raise click.ClickException(f"Could not find version in {file_label}.")
    return match.group("version")


def replace_version(text: str, pattern: re.Pattern[str], new_version: str, file_label: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise click.ClickException(f"Could not update version in {file_label}.")
    return f"{text[: match.start('version')]}{new_version}{text[match.end('version') :]}"


def increment_version(version: str, version_target: VersionTarget) -> str:
    """
    Computes the new version, dropping any development suffix of the given version.

    :param version: the current version
    :param version_target: the part of the version to bump or "current" to keep the version as is
    :return: the new version
    """
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise click.ClickException(f"Unsupported version format: {version}")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))

    match version_target:
        case "major":
            return f"{major + 1}.0.0"
        case "minor":
            return f"{major}.{minor + 1}.0"
        case "patch":
            return f"{major}.{minor}.{patch + 1}"
        case "current":
            return f"{major}.{minor}.{patch}"
        case _:
            raise ValueError(version_target)


def update_changelog(changelog_text: str, new_version: str) -> str:
    if not changelog_text.startswith(_UNRELEASED_HEADER):
        raise click.ClickException("CHANGELOG.md must start with '# Unreleased (main)'.")

    next_header_index = changelog_text.find("\n# ", len(_UNRELEASED_HEADER))
    unreleased_section_end = len(changelog_text) if next_header_index == -1 else next_header_index + 1

    unreleased_section = changelog_text[:unreleased_section_end]
    remaining_text = changelog_text[unreleased_section_end:]
    unreleased_body = unreleased_section[len(_UNRELEASED_HEADER) :]
    intro, unreleased_entries = split_unreleased_body(unreleased_body)

    date_str = datetime.now().strftime("%Y-%m-%d")
    updated_section = _UNRELEASED_HEADER + intro + f"# v{new_version} ({date_str})\n"

    if unreleased_entries.strip():
        updated_section += "\n" + unreleased_entries.lstrip("\n")
    else:
        updated_section += "\n"

    if remaining_text:
        updated_section += remaining_text.lstrip("\n")

    return updated_section


def split_unreleased_body(unreleased_body: str) -> tuple[str, str]:
    """Go until first line with content, the intro will be until the end of that line.

    :return: changelog_intro, changelog_body
    """
    lines = unreleased_body.splitlines(keepends=True)
    intro_end = 0
    seen_content = False

    for index, line in enumerate(lines):
        intro_end = index + 1
        if line.strip():
            seen_content = True
            continue
        if seen_content:
            break

    if not seen_content:
        raise click.ClickException("Could not determine the introduction paragraph in CHANGELOG.md.")

    return "".join(lines[:intro_end]), "".join(lines[intro_end:])


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    log.info("Script starting")
    cli()
