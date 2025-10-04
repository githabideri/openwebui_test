# OpenWebUI Backend API Flow (v0.6.32)

The commands below recreate the automation performed by `test_openwebui.py`. Each step shows:
- **API reference:** a curl pattern with placeholders such as `<CHAT_ID>`.
- **Shell snippet:** copy/paste-ready commands that persist results under `artifacts/api-flow-demo/`.

> Run everything from the repository root. Required tools: `curl`, `jq`, `uuidgen`.

---

## 0. Prerequisites

```bash
set -a
source .env        # provides BASE, TOKEN, MODEL
set +a

WORKDIR=./artifacts/api-flow-demo
mkdir -p "$WORKDIR"

echo "BASE=$BASE"
command -v curl jq uuidgen
```

---

## 1. Create the chat skeleton

**API reference**
```bash
curl -X POST "$BASE/api/v1/chats/new" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {...}}'
```

**Shell snippet**
```bash
USER_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
CHAT_TITLE="CLI Verification $(date +%H:%M:%S)"
PIVOT_TS=$(date +%s)

cat <<'PAYLOAD' > "$WORKDIR/01-create-chat.json"
{
  "chat": {
    "title": "REPLACE_TITLE",
    "models": ["REPLACE_MODEL"],
    "messages": [
      {
        "id": "REPLACE_USER",
        "role": "user",
        "content": "Health check: say pong.",
        "timestamp": REPLACE_TS,
        "models": ["REPLACE_MODEL"],
        "parentId": null,
        "childrenIds": []
      }
    ],
    "history": {
      "current_id": "REPLACE_USER",
      "messages": {
        "REPLACE_USER": {
          "id": "REPLACE_USER",
          "role": "user",
          "content": "Health check: say pong.",
          "timestamp": REPLACE_TS,
          "models": ["REPLACE_MODEL"],
          "parentId": null,
          "childrenIds": []
        }
      }
    }
  }
}
PAYLOAD

perl -0pi -e "s/REPLACE_TITLE/$CHAT_TITLE/g; s/REPLACE_MODEL/$MODEL/g; s/REPLACE_USER/$USER_ID/g; s/REPLACE_TS/$PIVOT_TS/g" "$WORKDIR/01-create-chat.json"

curl -sS -X POST "$BASE/api/v1/chats/new" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$WORKDIR/01-create-chat.json" \
  | tee "$WORKDIR/01-create-response.json" | jq '.'

CHAT_ID=$(jq -r '.chat.id // .id' "$WORKDIR/01-create-response.json")
if [ -z "$CHAT_ID" ]; then echo "chat id not returned" >&2; exit 1; fi
jq '.chat // .' "$WORKDIR/01-create-response.json" > "$WORKDIR/chat_state.json"
echo "CHAT_ID=$CHAT_ID"
```

---

## 2. Insert the assistant placeholder

**API reference**
```bash
curl -X POST "$BASE/api/v1/chats/<CHAT_ID>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {...}}'
```

**Shell snippet**
```bash
ASSISTANT_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
NOW_TS=$(date +%s)

jq --arg assistant "$ASSISTANT_ID"    --arg user "$USER_ID"    --arg model "$MODEL"    --argjson ts "$NOW_TS" '
  .messages += [{
    id: $assistant,
    role: "assistant",
    content: "",
    parentId: $user,
    modelName: $model,
    modelIdx: 0,
    timestamp: $ts,
    done: false,
    statusHistory: [],
    childrenIds: []
  }]
  | .messages = (.messages | map(if .id == $user then .childrenIds = ((.childrenIds // []) + [$assistant] | unique) else . end))
  | .history.messages[$assistant] = {
      id: $assistant,
      role: "assistant",
      content: "",
      parentId: $user,
      modelName: $model,
      modelIdx: 0,
      timestamp: $ts,
      done: false,
      childrenIds: []
    }
  | .history.current_id = $assistant
  | .history.currentId = $assistant
  | .currentId = $assistant
' "$WORKDIR/chat_state.json" > "$WORKDIR/chat_with_placeholder.json"

curl -sS -X POST "$BASE/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<<"{\"chat\": $(cat "$WORKDIR/chat_with_placeholder.json") }" >/dev/null

cp "$WORKDIR/chat_with_placeholder.json" "$WORKDIR/chat_state.json"
```

---

## 3. Trigger the completion

**API reference**
```bash
curl -X POST "$BASE/api/chat/completions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"<CHAT_ID>","id":"<ASSISTANT_ID>",...}'
```

**Shell snippet**
```bash
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

cat <<EOF > "$WORKDIR/03-completion.json"
{
  "chat_id": "$CHAT_ID",
  "id": "$ASSISTANT_ID",
  "messages": [
    {"role": "user", "content": "Health check: say pong."}
  ],
  "model": "$MODEL",
  "stream": false,
  "background_tasks": {
    "title_generation": false,
    "tags_generation": false,
    "follow_up_generation": false
  },
  "features": {
    "code_interpreter": false,
    "web_search": false,
    "image_generation": false,
    "memory": false
  },
  "session_id": "$SESSION_ID"
}
EOF

curl -sS -X POST "$BASE/api/chat/completions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$WORKDIR/03-completion.json" \
  | tee "$WORKDIR/03-completion-response.json" | jq '.'
```

(Optional) to monitor background work: `curl -sS "$BASE/api/tasks/chat/$CHAT_ID" -H "Authorization: Bearer $TOKEN" | jq '.'`

---

## 4. Sync the assistant reply and mark completion

**API references**
```bash
curl -X POST "$BASE/api/v1/chats/<CHAT_ID>" ...
curl -X POST "$BASE/api/chat/completed" ...
```

**Shell snippet**
```bash
curl -sS "$BASE/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/04-chat-check.json" | jq '.'

ASSISTANT_TEXT=$(jq -r '.chat.messages[] | select(.id == "'$ASSISTANT_ID'") | .content // ""' "$WORKDIR/04-chat-check.json")

if [ -z "$ASSISTANT_TEXT" ]; then
  jq --arg assistant "$ASSISTANT_ID" '
    (.chat // .) as $chat
    | $chat
    | ($chat.history.messages[$assistant].content // "") as $historyContent
    | .messages = (.messages | map(if .id == $assistant then . + {content: $historyContent, done: true} else . end))
    | .history.messages[$assistant] += {done: true}
    | {chat: .}
  ' "$WORKDIR/04-chat-check.json" > "$WORKDIR/04-sync-payload.json"

  curl -sS -X POST "$BASE/api/v1/chats/$CHAT_ID"   \
  -H "Authorization: Bearer $TOKEN"   \
  -H "Content-Type: application/json"   \
  -d @"$WORKDIR/04-sync-payload.json" >/dev/null
fi

echo "Marking completion"
curl -sS -X POST "$BASE/api/chat/completed" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{"chat_id":"$CHAT_ID","id":"$ASSISTANT_ID","session_id":"$SESSION_ID","model":"$MODEL"}"
```

---

## 5. Generate demo artifacts (local files)

```bash
cat <<EOF > "$WORKDIR/demo.txt"
OpenWebUI verification artifact
Chat ID: $CHAT_ID
Generated: $(date -u)
EOF

cat <<EOF > "$WORKDIR/demo.md"
# OpenWebUI Demo Artifact

- Chat ID: $CHAT_ID
- Generated: $(date -u)
EOF

cat <<EOF > "$WORKDIR/demo.json"
{
  "chat_id": "$CHAT_ID",
  "note": "Demo payload",
  "generated_at": "$(date -u)"
}
EOF
```

Upload each file using `/api/v1/files/`.

**API reference**
```bash
curl -X POST "$BASE/api/v1/files/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -F "file=@<LOCAL_PATH>"   "?process=true&process_in_background=false"
```

**Shell snippet**
```bash
FILE_IDS=()
for path in "$WORKDIR"/demo.*; do
  [ -f "$path" ] || continue

  TMP_JSON=$(mktemp "$WORKDIR/upload_XXXX.json")
  HTTP_CODE=$(curl -sS   \
  -o "$TMP_JSON"   \
  -w '%{http_code}'   \
  -H "Authorization: Bearer $TOKEN"   \
  -H "Accept: application/json"   \
  -F "file=@${path}"     "$BASE/api/v1/files/?process=true&process_in_background=false")

  if [ "${HTTP_CODE:0:1}" != "2" ]; then
    echo "Upload failed for $path (status $HTTP_CODE)" >&2
    cat "$TMP_JSON" >&2
    rm -f "$TMP_JSON"
    exit 1
  fi

  FILE_ID=$(jq -r '[.id, ._id, .file_id, .data.id] | map(select(. != null and . != "")) | first' "$TMP_JSON")
  rm -f "$TMP_JSON"

  if [ -z "$FILE_ID" ]; then
    echo "Could not extract file id for $path" >&2
    exit 1
  fi

  echo "Uploaded $path -> $FILE_ID"
  FILE_IDS+=("$FILE_ID")

  until curl -sS "$BASE/api/v1/files/$FILE_ID/process/status"         \
  -H "Authorization: Bearer $TOKEN" | jq -e '.status == "completed"' >/dev/null; do
    sleep 1
  done
  echo "  status: completed"
done
```

---

## 6. Create a knowledge collection and attach the files

**API references**
```bash
curl -X POST "$BASE/api/v1/knowledge/create" ...
curl -X POST "$BASE/api/v1/knowledge/<KNOWLEDGE_ID>/file/add" ...
```

**Shell snippet**
```bash
KNOWLEDGE_NAME="CLI Artifacts $(date -u +%Y%m%d_%H%M%S)"
KNOWLEDGE_DESC="Automation demo for chat $CHAT_ID"

KNOWLEDGE_ID=""
for endpoint in /api/v1/knowledge/create /api/v1/knowledge; do
  RESPONSE=$(curl -sS -w '
%{http_code}'   \
  -H "Authorization: Bearer $TOKEN"   \
  -H "Content-Type: application/json"   \
  -d "{"name":"$KNOWLEDGE_NAME","description":"$KNOWLEDGE_DESC"}"     "$BASE$endpoint")
  BODY=${RESPONSE%
*}
  CODE=${RESPONSE##*
}
  if [ "${CODE:0:1}" = "2" ]; then
    KNOWLEDGE_ID=$(printf '%s' "$BODY" | jq -r '[.id, ._id, .knowledge_id] | map(select(. != null and . != "")) | first')
    if [ -n "$KNOWLEDGE_ID" ]; then
      printf '%s' "$BODY" > "$WORKDIR/knowledge_raw.json"
      break
    fi
  fi
  echo "Knowledge creation via $endpoint failed (status $CODE)" >&2
  echo "$BODY" >&2
  KNOWLEDGE_ID=""
done

if [ -z "$KNOWLEDGE_ID" ]; then
  echo "Could not create knowledge collection" >&2
  exit 1
fi

echo "Knowledge collection: $KNOWLEDGE_ID"

for id in "${FILE_IDS[@]}"; do
  curl -sS -X POST "$BASE/api/v1/knowledge/$KNOWLEDGE_ID/file/add"   \
  -H "Authorization: Bearer $TOKEN"   \
  -H "Content-Type: application/json"   \
  -d "{"file_id":"$id"}" | jq '.'
done

curl -sS "$BASE/api/v1/knowledge/$KNOWLEDGE_ID" \
  -H "Authorization: Bearer $TOKEN" | tee "$WORKDIR/knowledge.json" | jq '.'
```

---

## 7. Link the knowledge collection to the chat

**API reference**
```bash
curl -X POST "$BASE/api/v1/chats/<CHAT_ID>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {...}}'
```

**Shell snippet**
```bash
curl -sS "$BASE/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.chat // .' > "$WORKDIR/chat_state.json"

jq --argjson knowledge "$(cat "$WORKDIR/knowledge.json" | jq -c '. + {type: "collection", status: (.status // "processed")}')"    --arg id "$KNOWLEDGE_ID" '
  .files = ((.files // []) + [$knowledge] | unique_by(.id))
  | .knowledge_ids = ((.knowledge_ids // []) + [$id] | unique)
  | .messages = (
      (.messages // []) | map(
        if (.role // "") == "user" then
          .files = ((.files // []) + [$knowledge] | unique_by(.id))
          | .
        else . end
      )
    )
  | .history = (
      (.history // {})
      | .messages = (
          (.messages // {}) | with_entries(
            if (.value.role // "") == "user" then
              .value.files = ((.value.files // []) + [$knowledge] | unique_by(.id))
              | .
            else . end
          )
        )
    )
' "$WORKDIR/chat_state.json" > "$WORKDIR/chat_with_knowledge.json"

curl -sS -X POST "$BASE/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<<"{"chat": $(cat "$WORKDIR/chat_with_knowledge.json")}" >/dev/null

curl -sS "$BASE/api/v1/chats/$CHAT_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.chat.files, .chat.knowledge_ids'
```

**Quick links**
```bash
echo "Chat:      $BASE/c/$CHAT_ID"
echo "Knowledge: $BASE/workspace/knowledge/$KNOWLEDGE_ID"
echo "Artifacts: $WORKDIR"
```

---

## Recap

1. Seed the chat with a user turn in both `messages[]` and `history.messages{}`.
2. Insert an empty assistant message before hitting `/api/chat/completions`.
3. Mirror the assistant content back into `messages[]` and mark the completion.
4. Upload artifacts with `process=true`, wait for `status: completed`, and attach them to a knowledge collection.
5. Link that knowledge collection to the chat so the UI recognises it immediately.

These manual steps match the behaviour of `test_openwebui.py` against OpenWebUI **v0.6.32**.
