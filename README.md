# OpenWebUI API Verification

This repository demonstrates how to script OpenWebUI's REST APIs to create full chat sessions, capture the returned artifacts, and validate that conversations remain usable after automation. It ships both Python and Bash harnesses so teams can embed the same workflow in their preferred tooling without manual UI steps.

## What You Can Do Here
- Generate chats end-to-end through `/api/v1/chats/*` endpoints, including message history scaffolding.
- Collect JSON artifacts (e.g., `test_result_YYYYMMDD_HHMMSS.json`) for reproducible debugging and support tickets.
- Confirm completions finish cleanly, including the spinner-free UI experience, before handing sessions back to the web client.
- Optionally continue chats programmatically to ensure follow-up prompts behave like live users.

## Repository Layout
- `test_openwebui.py` — Python 3.10+ runner with structured logging and reusable `stepN_*` helpers.
- `test_openwebui.sh` — Bash equivalent suited to cron jobs or lightweight CI environments.
- `.env` — Environment configuration (not committed) holding `BASE`, `TOKEN`, and `MODEL` values for the target deployment.

## Quick Start
1. Create a `.env` file next to the scripts with `BASE=https://your-openwebui`, `TOKEN=your-api-token`, and `MODEL=gemma3:4b` (or any model your instance supports).
2. Install the only dependency: `python3 -m pip install requests`.
3. Run `python3 test_openwebui.py "Health check: say pong."` for a scripted verification, or `bash test_openwebui.sh` when you prefer shell tooling.
4. Inspect the generated JSON artifact to confirm the assistant response and attach it to bug reports as needed.

## Extending the Workflow
- Add new verification steps by following the existing `stepN_action` naming pattern so logs stay consistent.
- When testing new OpenWebUI builds, duplicate transcripts to compare payload changes between versions.
- Treat tokens as disposable; rotate them when sharing artifacts externally.

## Contributing
See `AGENTS.md` for house coding standards, testing expectations, and pull-request guidelines tailored to this project.
