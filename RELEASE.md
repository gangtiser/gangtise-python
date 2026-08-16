# Release Checklist

1. Full test suite green locally:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pytest -m "not live"
   ```
2. Live integration tests — **required only when the release touches endpoint/API
   surface** (new/changed endpoints, body-field shapes, or error-code handling):
   ```bash
   uv run pytest -m live   # requires real credentials
   ```
   They hit per-call **billed** no-replay endpoints (e.g. `concept_info`), so an
   internal-only patch with no endpoint/API-surface change (e.g. a download-path
   hardening release) may skip them — the enforced gate is step 1
   (`-m "not live"` + ruff + format + mypy + build). Note any skip in the commit body.
3. Update `CHANGELOG.md` with the new version section and `README.md` with the
   matching "最近 5 个版本" entry; release CI checks both before publishing.
4. Bump `src/gangtise_openapi/__about__.py` (`__version__`).

   > ⚠️ **Verify the bump against `__about__.py` and the built filenames in `dist/`,
   > never against `pip list` / `importlib.metadata.version()`.** An editable install
   > records the version it was installed at and does NOT follow later bumps, so
   > `importlib.metadata.version("gangtise-openapi")` can report the OLD number while
   > `__about__.__version__`, `USER_AGENT` and the built artifacts are all correct.
   > Checking the wrong object is how a correct bump gets "confirmed" as broken —
   > or, worse, a missing one gets confirmed as done.
5. Commit: `git add -A && git commit -m "release: vX.Y.Z"`. (Use `git add -A`, **not**
   `git commit -am` — `-am` skips new untracked files, so a release that adds a new
   domain/sample file would ship a tree that fails to import on a clean checkout.)
6. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main vX.Y.Z`. (不要用 `--follow-tags`：它不推 lightweight tag，v0.1.0/v0.1.4 都因此没触发发布 workflow。)
7. CI workflow `.github/workflows/release.yml` runs build + publish + GitHub Release.
8. **Write the GitHub Release notes** — the workflow creates the release with
   `--generate-notes`, which derives from PRs. This repo commits straight to `main`,
   so that produces a body containing nothing but a "Full Changelog" link (v0.1.x
   through v0.3.0 all shipped that way). Someone deciding *whether to upgrade* reads
   that page, not `CHANGELOG.md`, so put the breaking changes and any "this was
   already broken, upgrading is the fix" items at the top:
   ```bash
   gh release edit vX.Y.Z --notes-file <file>
   ```
   Same wording discipline as `README.md`: no absolute platform library sizes, and
   describe server behaviour as observable result + what to do.
9. Verify on PyPI: `pip install gangtise-openapi==X.Y.Z` in a clean venv
   (uv caches metadata — use `uv pip install --refresh-package gangtise-openapi`).

## Known publish failure

`InvalidDistribution: '2.5' is not a valid metadata version` — the pinned
`pypa/gh-action-pypi-publish` bundles a twine older than the metadata version
hatchling emits. **Fix the action pin, do not cap hatchling**: metadata 2.5 is a
standard version PyPI accepts, so capping would be pinning away from the standard
to suit one stale tool. v1.14.2 is the first release whose twine (v7) accepts 2.5;
the pin must stay at or above it. Hit on v0.3.0 — the publish failed, nothing
reached PyPI, and the tag was moved onto the fix commit rather than burning the
version number.

## Initial setup

Before the first release, configure PyPI Trusted Publishing for the `gangtise-openapi` project:

1. Claim the `gangtise-openapi` name on PyPI (verified free as of 2026-05-27).
2. Add a Trusted Publisher in PyPI project settings:
   - Owner: `gangtiser`
   - Repository: `gangtise-python`
   - Workflow: `release.yml`
   - Environment: (leave blank)
3. Run the workflow once via TestPyPI by temporarily adding
   `repository-url: https://test.pypi.org/legacy/` to the pinned
   `pypa/gh-action-pypi-publish` step. Revert before tagging the real `v0.1.0`.
