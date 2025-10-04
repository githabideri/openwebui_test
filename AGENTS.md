# Repository Guidelines

## Project Structure & Module Organization
- `test_openwebui.py` is the primary Python harness; keep workflow steps in discrete `stepN_*` methods to reuse the logging.
- `test_openwebui.sh` mirrors the flow for bash automation and lightweight CI smoke checks.
- `.env` (next to the scripts) must define `BASE`, `TOKEN`, and `MODEL`; exclude it from commits.
- JSON transcripts such as `test_result_YYYYMMDD_HHMMSS.json` land in the project root; clean or archive them after runs.

## Build, Test, and Development Commands
- `python3 test_openwebui.py` runs the default health check; pass a custom prompt argument for scenario-specific verification.
- `bash test_openwebui.sh` executes the same sequence without Python dependencies and is ideal for cron or container jobs.
- Install dependencies with `python3 -m pip install requests` when bootstrapping fresh environments; no other packages are required today.

## Coding Style & Naming Conventions
- Stick with Python 3.10+ patterns already present: four-space indent, type hints, module/class/method docstrings, and f-strings.
- Preserve the public surface of `OpenWebUITester` and its `_log` helper; new methods should follow the `stepN_action` naming pattern.
- Shell helpers stay lowercase with underscores and return non-zero on failure; wrap complex curls in functions.

## Testing Guidelines
- Populate `.env` before running; trim trailing slashes from `BASE` to avoid double separators in requests.
- Both scripts hit live OpenWebUI APIs, so prefer staging instances and rotate tokens after shared sessions.
- Attach the generated `test_result_*.json` when filing bugs; extend verification by appending new checks after the spinner validation block.

## Commit & Pull Request Guidelines
- Group changes by behavior and title commits `type: short summary` (e.g., `fix: handle history mismatch logs`).
- In PRs, describe the scenario tested, list the command run, and link related issues or support tickets.
- Note any new environment variables, include anonymized output when it aids review, and confirm secrets remain outside version control.
