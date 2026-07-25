# Repo Setup

## Status: Implementation

## Problem statement

This repo was generated from a template (`geo-builder`'s `tpl-py`). It still contains
placeholder tokens that need to be replaced with real values before the repo is usable, and
this file itself needs to be retired once that's done.

## Placeholder tokens

| Token | Meaning | Appears in |
|---|---|---|
| `__package_name__` | Importable package identifier (snake_case, e.g. `my_project`) | `src/__package_name__/` directory name, all internal imports, `pyproject.toml`'s `[project.scripts]` target |
| `__project_name__` | Distribution / CLI command name (e.g. `my-project`) | `pyproject.toml`'s `[project.scripts]` key, `README.md`, `.vscode/launch.json` |
| `__description__` | One-line description | `pyproject.toml`'s `description`, `README.md` tagline |
| `__mission__` | A paragraph describing what this repo builds and why | `CLAUDE.md`'s `## Mission` section |

**One exception**: `pyproject.toml`'s `[project].name` field is written as `x__project_name__x`
(padded with a leading/trailing `x`), not the bare token — PEP 508 requires a distribution name
to start and end with an alphanumeric character, and setuptools hard-errors on `project.name`
otherwise (confirmed by actually running `pip install -e ".[dev]"` against the raw
`__project_name__` value). `[project.scripts]` keys have no such restriction, so that one stays
unpadded. When replacing, strip the padding `x`s along with the token there.

## Implementation plan

0. **If this folder is not already a git repo** (e.g. it was unzipped from the template rather
   than created via GitHub's "Use this template" button): ask the user for the SSH endpoint of
   the destination repo (their private git server). Also confirm whether the remote repo itself
   already exists there — it may not. If it doesn't exist yet, ask the user how repos get
   provisioned on their server (a bare `git init --bare <path>.git` over SSH, a Gitea/GitLab/etc.
   web UI or API, or something else) rather than assuming; don't guess at server-specific
   tooling. Once the remote exists, `git init`, `git remote add origin <ssh-endpoint>`, and push
   once the placeholder replacement below is done and committed. Skip this step entirely if
   `.git/` already exists — the GitHub-template path already has one.
1. Ask the user for the real values of `__package_name__`, `__project_name__`, `__description__`, and `__mission__` if they weren't already given.
2. Grep the whole repo case-sensitively for `__` to find every occurrence (this also catches any spot missed by the table above).
3. Replace each token with its real value. Also remove `README.md`'s `## Setup` section (the
   paragraph pointing at this file) — it becomes stale once the tokens are gone.
4. Rename the `src/__package_name__/` directory to `src/<package_name>/` (`git mv` if the repo
   is already tracked, to preserve history).
5. Run `pip install -e ".[dev]"`, then `ruff check src/ tests/`, `ruff format src/ tests/`, and `pytest` — all should pass clean on the renamed package. Optionally sanity-run the CLI itself (`python -m <package_name>.cli` or the installed console script) to confirm it exits 0.
6. Set the initial `Synced to` timestamp in `CLAUDE.md`'s `## Template Sync` section: fetch
   `tpl-py`'s `ADDENDUM.md` (plain HTTPS, e.g. `WebFetch`) and use its latest entry's timestamp,
   or the current time if the addendum is empty — otherwise a brand-new instance would look
   "behind" on history that predates it.
7. If the GitHub issue-based task workflow in `CLAUDE.md` will be used, create the `status:brainstorm` / `status:implementation` / `status:testing` / `status:ready-to-submit` labels on the new repo (`gh label create`) — they don't exist on a fresh repo.
8. Delete this file (`tasks/repo_setup.md`) and its entry in `CLAUDE.md`'s `## Pending Tasks` section.

## Test results

Dry-run test-drive (2026-07-25): instantiated as `quant-scratch` via `gh repo create --template
--clone` (repo later discarded — the run was a drill, not a real project). Every step worked
first try with no template changes needed: `.git/` already present so step 0 was skipped, the
grep in step 2 caught every occurrence, `git mv` on the package directory preserved history
cleanly, and `pip install -e ".[dev]"` / `ruff check` / `ruff format --check` / `pytest` / a
direct CLI run all passed clean immediately after. Two small process gaps found and folded back
into steps 3 and 5 above: the README's `## Setup` blurb isn't covered by the token-replacement
steps and was left stale until removed by hand, and step 5 didn't call out actually running the
CLI as a sanity check.
