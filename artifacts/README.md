# Artifacts Overview

This note captures the current organization of automation outputs so future runs follow the same structure and you can quickly locate prior evidence.

## Directory Map
- `runs/<timestamp>/`
  - Created by the Python harness per invocation.
  - Bundles the `test_result_<timestamp>.json` transcript with the corresponding `openwebui_test_load_<timestamp>_<suffix>.{json,md,txt}` payloads for easy diffing.
  - Includes a `metadata.json` manifest summarizing timing, environment, artifact paths, and knowledge uploads.
- `manual/`
  - Keeps ad-hoc curl experiments, the `api-flow-demo/` scaffold, and raw exports that were copied from OpenWebUI without further curation.
- `chat_snapshots/`
  - Stores historical `chat_snapshot_*.json` files downloaded from the UI.
- `knowledge_snapshots/`
  - Stores `knowledge_snapshot_*.json` exports of the RAG collections.
- `reference/`
  - Houses curated exemplars you can reference when diagnosing regressions.
  - Currently contains:
    - `happy_path_manual.json` — clean manual export that proves the fully working flow.
    - `spinner_regression.json` — broken “no pong” variant that surfaced the perpetual spinner bug.
    - `pong_fix_comparison.json` — before/after export highlighting the payload adjustments that fixed the spinner.

## Workflow Tips
- Leave `runs/` as-is after each execution to preserve context; if the directory grows too large, archive old folders (zip or tar) before relocating.
- Drop any new manual investigations into `manual/`, then promote notable cases into `reference/` with descriptive filenames so you remember why they matter.
- When sharing artifacts externally, scrub tokens and instance identifiers before packaging the JSON files.
