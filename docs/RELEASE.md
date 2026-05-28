# Release Checklist

1. Full test suite green locally:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pytest -m "not live"
   ```
2. Run live integration tests at least once (requires real credentials):
   ```bash
   uv run pytest -m live
   ```
3. Update `CHANGELOG.md` with the new version section.
4. Bump `src/gangtise_openapi/__about__.py` (`__version__`).
5. Commit: `git commit -am "release: vX.Y.Z"`.
6. Tag: `git tag vX.Y.Z && git push --follow-tags`.
7. CI workflow `.github/workflows/release.yml` runs build + publish + GitHub Release.
8. Verify on PyPI: `pip install gangtise-openapi==X.Y.Z` in a clean venv.

## Initial setup

Before the first release, configure PyPI Trusted Publishing for the `gangtise-openapi` project:

1. Claim the `gangtise-openapi` name on PyPI (verified free as of 2026-05-27).
2. Add a Trusted Publisher in PyPI project settings:
   - Owner: `gangtiser`
   - Repository: `gangtise-python`
   - Workflow: `release.yml`
   - Environment: (leave blank)
3. Run the workflow once via TestPyPI by temporarily pointing `pypa/gh-action-pypi-publish@release/v1` at `repository-url: https://test.pypi.org/legacy/`. Revert before tagging the real `v0.1.0`.
