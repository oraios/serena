# Developer Instructions

## Python Environment & Development Tools

See [the contributing guide](CONTRIBUTING.md) for instructions on setting up your development environment
and tools for formatting and type checking.

## Release Process

1. Ensure clean git status.
2. Set the version for release. Normally, the version to be released is the one already reserved by the
   current `.dev0` version (e.g. `1.8.0` when the repository is at `1.8.0.dev0`):

       python scripts/bump_version.py release current

   To release a version beyond the reserved one, name the part to bump instead, e.g.

       python scripts/bump_version.py release patch
       python scripts/bump_version.py release minor

   This updates `CHANGELOG.md`, commits the release version, creates the git tag, and then
   commits the subsequent `.dev0` version for the next iteration.
3. Push to GitHub:

       git push
       git push --tags

   Important: This must push a single tag only!
   Pushing the single tag triggers the `create-release` workflow for the tag, which creates a
   **draft release** on GitHub.
4. Review the draft release on the
   [GitHub Releases page](https://github.com/oraios/serena/releases).
   When ready, publish it (click *Publish release*).
   This triggers the `publish` workflow, which builds and publishes the
   package to PyPI.

### Bumping the Development Version

Independently of a release, the development version can be bumped, e.g. when work on `main`
begins to target a new minor or major version:

    python scripts/bump_version.py dev minor
    python scripts/bump_version.py dev major

This sets the version to the respective new `.dev0` version (e.g. `1.8.0.dev0`) and commits it as
"Set version to vX"; it creates no tag and does not modify `CHANGELOG.md`.

The subsequent release of that version is then performed with `release current`.

Both commands require a clean git status and support `--dry-run` to preview the changes.