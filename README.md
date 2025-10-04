# Preface
I wanted to create chat sessions (with attachments) in OpenWebUI from the CLI via API calls as outlined [here]([url](https://docs.openwebui.com/tutorials/integrations/backend-controlled-ui-compatible-flow/)). But it did not work out, I was not able to get it fully working, the chat window in OpenWebUI would constantly show a spinner and saying "Loading...". That's why I created this repo and I tried out how LLMs (from OpenAI, Anthropic and a bit of unsuccessful Google) in their new CLI variants could handle it. GPT-Codex was ultimately able to crack the nut, but only after I gave it git cloned open-webui/open-webui and open-webui/docs and more importantly two json exports from OpenWebUI itself, one broken chat (via API call) and one working (manually). OpenWebUI allows you to download chats not only in text and PDF but also in json - That's great! And then it was able to figure it out. The following is the result and summarization of my endavour. Maybe useful to somebody :)

Tested with OpenWebUI v6.32.

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

## API Flow Reference
The OpenWebUI backend expects the same data shape the web client produces. The harness shows the exact sequence; the outline below is safe to reuse in other tooling.

1. **Create the chat** – `POST /api/v1/chats/new`
   ```jsonc
   {
     "chat": {
       "title": "Test Chat",
       "models": ["gemma3:4b"],
       "messages": [
         {
           "id": "<user-id>",
           "role": "user",
           "content": "Health check: say pong.",
           "timestamp": 1710000000,
           "models": ["gemma3:4b"],
           "parentId": null,
           "childrenIds": []
         }
       ],
       "history": {
         "current_id": "<user-id>",
         "messages": {
           "<user-id>": {
             "id": "<user-id>",
             "role": "user",
             "content": "Health check: say pong.",
             "timestamp": 1710000000,
             "models": ["gemma3:4b"],
             "parentId": null,
             "childrenIds": []
           }
         }
       }
     }
   }
   ```

2. **Insert an assistant placeholder** – enrich the response locally and `POST /api/v1/chats/{chat_id}` with:
   - An empty assistant message in both `chat.messages[]` and `chat.history.messages{}`.
   - `parentId` set to the user message ID.
   - `done: false`, `childrenIds: []`, and the parent’s `childrenIds` updated to include the assistant ID.

3. **Trigger the completion** – `POST /api/chat/completions` with:
   ```jsonc
   {
     "chat_id": "<chat-id>",
     "id": "<assistant-id>",
     "messages": [{"role": "user", "content": "Health check: say pong."}],
     "model": "gemma3:4b",
     "stream": false,
     "background_tasks": {"title_generation": false, "tags_generation": false, "follow_up_generation": false},
     "features": {"code_interpreter": false, "web_search": false, "image_generation": false, "memory": false},
     "session_id": "<uuid>"
   }
   ```
   The response usually contains `{ "status": true, "task_id": "..." }`. You can monitor active work with `GET /api/tasks/chat/<chat_id>`; if it ever lists IDs, the UI will keep showing the stop button.

4. **Wait for the assistant content** – poll `GET /api/v1/chats/<chat_id>` until the assistant message in `messages[]` has non-empty `content`. If the text only turns up under `history.messages`, re‑post the enriched chat (Step 2) with `done: true` so both structures match.

5. **Mark the completion** – `POST /api/chat/completed` with `{ "chat_id": "...", "id": "<assistant-id>", "session_id": "<uuid>", "model": "gemma3:4b" }` to clear the frontend spinner.

6. *(Optional)* **Continue the chat** – subsequent turns reuse the same pattern: add a user message (update `childrenIds`), inject a blank assistant placeholder, trigger `/api/chat/completions`, and poll until the UI fields are populated.

Always keep `messages[]` and `history.messages{}` in sync—especially `childrenIds`, `parentId`, and `done`. The web client relies on those fields to decide when to stop showing the spinner.

## Extending the Workflow
- Add new verification steps by following the existing `stepN_action` naming pattern so logs stay consistent.
- When testing new OpenWebUI builds, duplicate transcripts to compare payload changes between versions.
- Treat tokens as disposable; rotate them when sharing artifacts externally.

## Contributing
See `AGENTS.md` for house coding standards, testing expectations, and pull-request guidelines tailored to this project.
