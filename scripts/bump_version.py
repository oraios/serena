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
_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
_INIT_VERSION_PATTERN = re.compile(r'^(?P<before>__version__\s*=\s*")(?P<version>\d+\.\d+\.\d+)(?P<after>"\s*)$', re.MULTILINE)
_PYPROJECT_VERSION_PATTERN = re.compile(
    r'(?m)^(?P<before>\[project\]\n(?:.*\n)*?^version\s*=\s*")(?P<version>\d+\.\d+\.\d+)(?P<after>"\s*)$'
)
_UNRELEASED_HEADER = "# Unreleased (main)\n"


@click.command()
@click.option("--major", "major", is_flag=True, help="Bump the major version and reset minor and patch to 0.")
@click.option("--minor", "minor", is_flag=True, help="Bump the minor version and reset patch to 0.")
@click.option("--patch", "patch", is_flag=True, help="Bump the patch version.")
@click.option("--version", "-v", "target_version", metavar="X.Y.Z", help="Set an explicit version instead of bumping.")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing any files.")
def bump_version(major: bool, minor: bool, patch: bool, target_version: str | None, dry_run: bool) -> None:
    git_status = get_git_status()
    if not git_status.is_clean:
        raise click.ClickException("Working directory is not clean. Please commit or stash your changes first.")

    log.info("bump_version called: major=%s, minor=%s, patch=%s, target_version=%s", major, minor, patch, target_version)
    version_part = resolve_version_selection(major=major, minor=minor, patch=patch, target_version=target_version)
    log.info("Resolved version_part=%s", version_part)

    repo_root = find_repo_root()
    log.info("Repo root: %s", repo_root)
    new_version = bump_repo_version(repo_root, version_part=version_part, target_version=target_version, dry_run=dry_run)
    log.info("New version: %s", new_version)
    if dry_run:
        click.echo(f"Dry run complete. Version would be bumped to {new_version}")
    else:
        os.system("uv lock")
        click.echo(f"Bumped version to {new_version}")
        os.system("git add -u")
        os.system(f'git commit -m "Release v{new_version}"')
        os.system(f"git tag v{new_version}")


def find_repo_root() -> Path:
    return Path(REPO_ROOT)


def resolve_version_selection(*, major: bool, minor: bool, patch: bool, target_version: str | None) -> VersionPart | None:
    bump_flags_selected = sum([major, minor, patch])
    if target_version is not None and bump_flags_selected > 0:
        raise click.ClickException("Use either --version or one of --major/--minor/--patch, not both.")
    if bump_flags_selected > 1:
        raise click.ClickException("Use only one of --major, --minor, or --patch.")
    if target_version is not None:
        validate_version_string(target_version)
        return None
    if major:
        return "major"
    if minor:
        return "minor"
    if patch:
        return "patch"
    raise click.ClickException("No version bump selected. Use --major, --minor, --patch or --version.")


def bump_repo_version(repo_root: Path, *, version_part: VersionPart | None, target_version: str | None, dry_run: bool = False) -> str:
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

    if target_version is not None:
        new_version = validate_version_string(target_version)
    else:
        if version_part is None:
            raise click.ClickException("No version target specified.")
        new_version = increment_version(current_version, version_part)
    log.info("New version will be: %s", new_version)

    new_pyproject_text = replace_version(pyproject_text, _PYPROJECT_VERSION_PATTERN, new_version, "pyproject.toml")
    new_init_text = replace_version(init_text, _INIT_VERSION_PATTERN, new_version, "src/serena/__init__.py")
    new_changelog_text = update_changelog(changelog_text, new_version)

    file_changes: list[tuple[Path, str, str]] = [
        (pyproject_path, pyproject_text, new_pyproject_text),
        (init_path, init_text, new_init_text),
        (changelog_path, changelog_text, new_changelog_text),
    ]

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
    match = pattern.search(text)
    if match is None:
        raise click.ClickException(f"Could not find version in {file_label}.")
    return match.group("version")


def replace_version(text: str, pattern: re.Pattern[str], new_version: str, file_label: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise click.ClickException(f"Could not update version in {file_label}.")
    return f"{text[: match.start('version')]}{new_version}{text[match.end('version') :]}"


def increment_version(version: str, version_part: VersionPart) -> str:
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise click.ClickException(f"Unsupported version format: {version}")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))

    if version_part == "major":
        return f"{major + 1}.0.0"
    if version_part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def validate_version_string(version: str) -> str:
    if _VERSION_PATTERN.fullmatch(version) is None:
        raise click.ClickException(f"Unsupported version format: {version}")
    return version


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
    bump_version()
