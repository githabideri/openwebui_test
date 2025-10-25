# Preface
I wanted to create chat sessions (with attachments) in OpenWebUI from the CLI via API calls as outlined here in the OpenWebUI [Docs](https://docs.openwebui.com/tutorials/integrations/backend-controlled-ui-compatible-flow). But it did not work out, I was not able to get it fully working, the chat window in OpenWebUI would constantly show a spinner and saying "Loading...". That's why I created this repo and I tried out how LLMs (from OpenAI, Anthropic and a bit of unsuccessful Google) in their new CLI variants could handle it. GPT-Codex was ultimately able to crack the nut, but only after I gave it git cloned open-webui/open-webui and open-webui/docs and more importantly two json exports from OpenWebUI itself, one broken chat (via API call) and one working (manually). OpenWebUI allows you to download chats not only in text and PDF but also in json - That's great! And then it was able to figure it out. The following is the result and summarization of my endavour. Maybe useful to somebody :)

Tested with OpenWebUI v0.6.32. CLI release: **v0.2.0**.

# OpenWebUI API Verification

This repository demonstrates how to script OpenWebUI's REST APIs to create full chat sessions, capture the returned artifacts, and validate that conversations remain usable after automation. The Python harness encapsulates the complete flow so teams can reproduce the UI behaviour without manual intervention, and an accompanying manual guide walks you through each HTTP call for debugging or learning purposes.

## What You Can Do Here
- Generate chats end-to-end through `/api/v1/chats/*` endpoints, including message history scaffolding.
- Collect JSON artifacts (e.g., `test_result_YYYYMMDD_HHMMSS.json`) for reproducible debugging and support tickets.
- Confirm completions finish cleanly, including the spinner-free UI experience, before handing sessions back to the web client.
- Optionally continue chats programmatically to ensure follow-up prompts behave like live users.
- Seed prefilled chats that wait for user input by running the CLI with `--no-pong`.

## v0.2.0 Highlights
- Structured run directories are now the default so every execution lands under `artifacts/runs/<timestamp>/`.
- Each run writes a `metadata.json` manifest capturing timing, environment, artifact paths, and knowledge URLs alongside the original transcript.
- Expanded CLI controls let you tag runs, force follow-up tests, tune polling cadence, and toggle between structured/flat layouts.
- The `--no-pong/--prefill-only` flow, version stamping, and manual curl itinerary introduced in v0.1.1 remain available.

## Repository Layout
- `test_openwebui.py` — Python 3.10+ runner with structured logging and reusable `stepN_*` helpers.
- `.env` — Environment configuration holding `BASE`, `TOKEN`, and `MODEL` values for the target deployment.
- `vendor/` — A sandbox copy of upstream projects (OpenWebUI core, UI docs, and the homedoc journal analyzer) retrieved during debugging. The directory is ignored from version control.
- `API_FLOW.md` — Step-by-step curl walkthrough covering every API call required to replicate the automated flow manually.

## Artifacts Layout
Automation outputs stay out of version control, but expect the following structure when you run the tooling:
- `artifacts/runs/<timestamp>/` — per-execution bundles containing `test_result_*.json` plus matching `openwebui_test_load_*` sidecars.
- `artifacts/manual/` — scratch space for manual curl exports and exploratory notes.
- `artifacts/chat_snapshots/` — chat JSON snapshots saved from the UI.
- `artifacts/knowledge_snapshots/` — knowledge-base snapshot exports.
- `artifacts/reference/` — hand-picked exemplars (e.g., `happy_path_manual.json`, `spinner_regression.json`, `pong_fix_comparison.json`) for quick comparisons.

## Quick Start
1. Copy `.env.example` to `.env` and populate `BASE`, `TOKEN`, and `MODEL` (keep the quotes).
2. Install the only dependency: `python3 -m pip install requests`.
3. Automated path: run `python3 test_openwebui.py "Health check: say pong."` and review the generated `test_result_*.json` plus the chat/knowledge snapshots saved under `artifacts/`.
   - Prefer `python3 test_openwebui.py --no-pong "Seed prompt"` when you only need a ready-to-use chat without an assistant response.
4. Manual path: follow the copy/paste-ready curl itinerary in [`API_FLOW.md`](./API_FLOW.md) to exercise every endpoint yourself (both completion and no-completion variants), inspect intermediate payloads, and open the emitted quick links to the chat and knowledge collection.

## CLI Flags
- `-P/--no-pong/--prefill-only` — skip the completion call and leave the chat ready for an operator.
- `-F/--follow-up` — force the follow-up continuity check (overrides the `FOLLOW_UP_TEST` env toggle).
- `-t/--tag <label>` — stamp artifacts and metadata with a label such as `staging` or a ticket ID.
- `-o/--output-dir <path>` — change the root used for structured artifacts (defaults to `./artifacts`).
- `-f/--flat-output` — keep legacy behaviour by writing results to the current directory.
- `-i/--poll-interval <seconds>` — tweak the delay between chat status polls (defaults to `1.0`).
- `-a/--poll-attempts <count>` — cap how many polls to make before timing out (defaults to `30`).
- `-M/--no-metadata` — suppress `metadata.json` if you prefer the lean footprint.

## Manual API Flow
If you need to understand or demonstrate every HTTP request, [`API_FLOW.md`](./API_FLOW.md) documents the entire sequence with placeholder-based curl examples and shell snippets that store each response to disk. It ends with quick links to the generated chat and knowledge collection so you can review them immediately in the browser.

## Extending the Workflow
- Add new verification steps by following the existing `stepN_action` naming pattern so logs stay consistent.
- When testing new OpenWebUI builds, duplicate transcripts to compare payload changes between versions.
- Treat tokens as disposable; rotate them when sharing artifacts externally.

## Contributing
See `AGENTS.md` for house coding standards, testing expectations, and pull-request guidelines tailored to this project.
