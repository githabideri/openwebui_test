# Repository Guidelines

## Project Structure & Module Organization
- `test_openwebui.py` houses the `OpenWebUITester`; extend the flow by adding `stepN_action` methods so logs stay chronological and reusable.
- `test_openwebui.sh` mirrors the Python sequence for cron/CI; keep helper functions lowercase_snake_case and return non-zero on failure to bubble errors.
- Store `.env` beside the scripts with `BASE`, `TOKEN`, `MODEL` (no trailing slash on `BASE`); keep it out of Git.
- JSON transcripts (`test_result_YYYYMMDD_HHMMSS.json`) are saved in the repo root; archive or purge them once tickets are filed.

## Build, Test, and Development Commands
- `python3 -m pip install requests` installs the only dependency required for fresh environments.
- `python3 test_openwebui.py "Health check: say pong."` runs the canonical verification and emits a transcript file on success.
- `python3 test_openwebui.py "Custom prompt"` reuses the workflow for scenario-specific regression checks.
- `bash test_openwebui.sh` exercises the same steps without Python state and is optimized for containers or cron jobs.

## Coding Style & Naming Conventions
- Follow Python 3.10 conventions already present: four-space indent, type hints, docstrings, and f-strings for logging.
- Preserve the public surface of `OpenWebUITester` and `_log`; new behaviors belong in discrete `stepN_*` helpers to stay composable.
- Keep shell helpers in lowercase_snake_case, emit informative logs, and `return 1` on error to respect `set -e`.
- Name new artifacts predictably (e.g., `test_result_{timestamp}.json`) so cleanup scripts remain simple.

## Testing Guidelines
- Load credentials via `.env`; trim trailing slashes from `BASE` before issuing requests to avoid doubled separators.
- Prefer staging OpenWebUI targets and rotate `TOKEN`s after shared runs; every script talks to live APIs.
- Append new assertions immediately after the spinner verification block in each runner so failures surface with existing messaging.

## Commit & Pull Request Guidelines
- Format commits as `type: short summary` (example: `fix: handle history mismatch logs`) and group by behavior.
- In PRs, describe the scenario exercised, commands run, linked issues/tickets, and attach anonymized transcript snippets when useful.
- Highlight any new configuration requirements and confirm secret values remain outside version control.

## Security & Configuration Tips
- Treat `.env` as sensitive; share tokens via secure channels and rotate them whenever artifacts leave your control.
- Scrub JSON transcripts before attaching them externally if they contain production identifiers.
- When debugging, prefer temporary environment overrides (`BASE=https://staging ...`) rather than editing `.env` in place.
