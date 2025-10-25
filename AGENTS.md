# Repository Guidelines

## Build, Test, and Development Commands
- `python3 -m pip install requests` installs the only dependency required for fresh environments.
- `python3 test_openwebui.py "Health check: say pong."` runs the canonical verification and emits a transcript file on success.
- `python3 test_openwebui.py "Custom prompt"` reuses the workflow for scenario-specific regression checks.
- Manual spot checks: copy/paste the curl itinerary in `API_FLOW.md` to verify payload shapes against a live instance.

### Automation Flags
- `-P/--no-pong` skips the completion request and leaves the UI waiting for an operator.
- `-F/--follow-up` forces the follow-up continuity probe (otherwise honour `FOLLOW_UP_TEST`).
- `-t/--tag <label>` stamps artifacts/metadata for later filtering (e.g., `staging`, `INC-123`).
- `-o/--output-dir <path>` chooses the artifact root (defaults to `./artifacts`).
- `-f/--flat-output` retains the legacy flat layout instead of per-run folders.
- `-i/--poll-interval <seconds>` adjusts the response poll cadence (default `1.0`).
- `-a/--poll-attempts <count>` sets the maximum poll attempts before the test aborts (default `30`).
- `-M/--no-metadata` suppresses the `metadata.json` manifest when not needed.

## Code Style & Naming Conventions
- Use four-space indentation, type hints, docstrings, and f-strings for logging (Python 3.10).
- Preserve the public surface of `OpenWebUITester` and `_log`; new behaviors belong in discrete `stepN_*` helpers.
- Shell helpers should use lowercase_snake_case; emit informative logs and `return 1` on error to respect `set -e`.
- Name new artifacts predictably (e.g., `test_result_{timestamp}.json`).

## Testing Guidelines
- Load credentials from `.env`; trim trailing slashes from `BASE` to avoid doubled separators.
- Prefer staging targets and rotate `TOKEN`s after shared runs; all scripts talk to live APIs.
- Add new assertions after the spinner verification block so failures surface with existing messaging.

## Commit & Pull Request Guidelines
- Format commits as `type: short summary` (e.g., `fix: handle history mismatch logs`). Group by behavior.
- In PRs, describe the scenario, commands, linked issues, and attach anonymized transcript snippets when useful.
- Highlight new configuration requirements and confirm secret values remain outside version control.

## Security & Configuration Tips
- Treat `.env` as sensitive; share tokens via secure channels and rotate them when artifacts leave your control.
- Scrub JSON transcripts before sharing externally if they contain production identifiers.
- Use temporary environment overrides (`BASE=https://staging...`) instead of editing `.env` in place.
