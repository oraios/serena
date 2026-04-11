# Developer Instructions

## Python Environment & Development Tools

See [the contributing guide](CONTRIBUTING.md) for instructions on setting up your development environment
and tools for formatting and type checking.

## Release Process

1. Ensure clean git status
2. Set version for release, e.g.
   
       python scripts/bump_version.py --patch
       python scripts/bump_version.py --minor

   This also creates the git tag.
3. Push to GitHub, triggering the release process.

       git push
       git push --tags
