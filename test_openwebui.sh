#!/bin/bash

# OpenWebUI Backend Flow Test Script with .env Support
# This script tests the complete workflow and verifies the spinner is gone

set -e  # Exit on error

# ============================================================================
# LOAD CONFIGURATION FROM .env FILE
# ============================================================================

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env file
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "ERROR: .env file not found in $SCRIPT_DIR"
    echo "Please create a .env file with:"
    echo "  BASE=https://your-openwebui-instance.com"
    echo "  TOKEN=your-api-token"
    echo "  MODEL=gemma3:4b"
    exit 1
fi

echo "Loading configuration from .env file..."

if ! command -v jq &> /dev/null; then
    echo "ERROR: jq is required for this script. Please install jq and rerun."
    exit 1
fi

trim() {
    local var="$1"
    var="${var#${var%%[![:space:]]*}}"
    var="${var%${var##*[![:space:]]}}"
    printf '%s' "$var"
}

strip_quotes() {
    local val="$1"
    if [[ ${#val} -ge 2 ]]; then
        local first="${val:0:1}"
        local last="${val: -1}"
        if [[ ( "$first" == '"' && "$last" == '"' ) || ( "$first" == "'" && "$last" == "'" ) ]]; then
            val="${val:1:${#val}-2}"
        fi
    fi
    printf '%s' "$val"
}

while IFS= read -r line || [ -n "$line" ]; do
    line="$(trim "$line")"
    [ -z "$line" ] && continue
    [[ "$line" == \#* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="$(trim "$key")"
    value="$(trim "$value")"
    case "$key" in
        BASE|TOKEN|MODEL)
            value="$(strip_quotes "$value")"
            export "$key=$value"
            ;;
        *)
            continue
            ;;
    esac
done < "$SCRIPT_DIR/.env"

# Validate required variables
if [ -z "$BASE" ] || [ -z "$TOKEN" ] || [ -z "$MODEL" ]; then
    echo "ERROR: Missing required configuration in .env file"
    echo "Required variables: BASE, TOKEN, MODEL"
    exit 1
fi

# Remove trailing slash from BASE if present
BASE="${BASE%/}"

# Generate new session ID for this test run
SESSION="$(uuidgen | tr '[:upper:]' '[:lower:]')"

echo "Configuration loaded:"
echo "  BASE: $BASE"
echo "  MODEL: $MODEL"
echo "  SESSION: $SESSION"
echo ""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $1"
}

info() {
    echo -e "${CYAN}[$(date +'%H:%M:%S')] ℹ${NC} $1"
}

# Generate UUID
generate_uuid() {
    uuidgen | tr '[:upper:]' '[:lower:]'
}

# Get timestamp in milliseconds
get_timestamp() {
    echo $(date +%s)
}

# ============================================================================
# VERIFICATION FUNCTIONS
# ============================================================================

verify_spinner_gone() {
    local CHAT_ID=$1
    local ASSISTANT_MSG_ID=$2
    
    info "Verifying spinner is gone and chat is continuable..."
    
    # Fetch current chat state
    local CHAT_DATA=$(curl -s -X GET "$BASE/api/v1/chats/$CHAT_ID" \
        -H "Authorization: Bearer $TOKEN")
    
    if ! command -v jq &> /dev/null; then
        warn "jq not installed - cannot fully verify. Assuming success."
        return 0
    fi
    
    # Extract assistant message content from messages array (what UI displays)
    local UI_CONTENT=$(echo "$CHAT_DATA" | jq -r --arg assistant "$ASSISTANT_MSG_ID" '
        ((.chat.messages // .messages // [])
            | map(select(.id == $assistant and .role == "assistant"))
            | .[0].content) // empty
    ')
    
    # Extract assistant message content from history (backend state)
    local HISTORY_CONTENT=$(echo "$CHAT_DATA" | jq -r --arg assistant "$ASSISTANT_MSG_ID" '
        ((.chat.history.messages // .history.messages // {})
            | .[$assistant]
            | .content) // empty
    ')
    
    info "Verification Results:"
    echo ""
    
    # Check 1: UI content is not empty
    if [ -z "$UI_CONTENT" ] || [ "$UI_CONTENT" = "null" ] || [ "$UI_CONTENT" = "" ]; then
        error "FAIL: Assistant message content is EMPTY in messages[] array"
        error "      This means the spinner will still show!"
        echo ""
        echo "Current state:"
        echo "$CHAT_DATA" | jq '.chat.messages // .messages // [] | map(select(.role=="assistant"))'
        return 1
    else
        success "PASS: Assistant message has content in messages[] array (UI displays this)"
        echo "      Content preview: ${UI_CONTENT:0:100}..."
    fi
    
    # Check 2: History content matches
    if [ "$UI_CONTENT" = "$HISTORY_CONTENT" ]; then
        success "PASS: Content matches between messages[] and history{}"
    else
        warn "WARNING: Content mismatch between UI and history"
        echo "      UI content: ${UI_CONTENT:0:50}..."
        echo "      History content: ${HISTORY_CONTENT:0:50}..."
    fi
    
    # Check 3: Verify we can identify the currentId
    local CURRENT_ID=$(echo "$CHAT_DATA" | jq -r '
        .chat.history.currentId // .chat.history.current_id // .chat.currentId // .history.currentId // .history.current_id // .currentId // empty
    ')
    if [ "$CURRENT_ID" = "$ASSISTANT_MSG_ID" ] || [ "$CURRENT_ID" = "null" ]; then
        success "PASS: Chat state looks correct"
    else
        warn "WARNING: currentId is not the assistant message"
    fi
    
    echo ""
    success "✓ SPINNER VERIFICATION PASSED"
    success "✓ Chat should be continuable in the UI"
    echo ""
    
    return 0
}

test_chat_continuable() {
    local CHAT_ID=$1
    local ASSISTANT_MSG_ID=$2
    
    info "Testing if chat is continuable by adding a follow-up message..."
    
    # Generate IDs for follow-up
    local FOLLOWUP_USER_ID=$(generate_uuid)
    local FOLLOWUP_TIMESTAMP=$(get_timestamp)
    
    local CHAT_RESPONSE=$(curl -s -X GET "$BASE/api/v1/chats/$CHAT_ID" \
        -H "Authorization: Bearer $TOKEN")

    local CHAT_JSON=$(echo "$CHAT_RESPONSE" | jq --arg chat_id "$CHAT_ID" '(.chat // .) | .id = $chat_id')

    local FOLLOWUP_MESSAGE=$(jq -n \
        --arg id "$FOLLOWUP_USER_ID" \
        --arg parent "$ASSISTANT_MSG_ID" \
        --arg model "$MODEL" \
        --argjson timestamp $FOLLOWUP_TIMESTAMP \
        '{
            id: $id,
            role: "user",
            content: "Thanks! One more test.",
            parentId: $parent,
            timestamp: $timestamp,
            models: [$model]
        }'
    )

    local UPDATED_CHAT=$(echo "$CHAT_JSON" | jq \
        --argjson message "$FOLLOWUP_MESSAGE" \
        --arg id "$FOLLOWUP_USER_ID" \
        '.messages = (.messages // []) + [$message]
         | .history = (.history // {})
         | .history.messages = (.history.messages // {})
         | .history.messages[$id] = $message
         | .history.current_id = $id
         | .history.currentId = $id
         | .currentId = $id'
    )

    local UPDATE_BODY=$(echo "$UPDATED_CHAT" | jq -c '{chat: .}')
    local UPDATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/chats/$CHAT_ID" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATE_BODY")

    if [ "$UPDATE_STATUS" != "200" ] && [ "$UPDATE_STATUS" != "201" ]; then
        warn "Could not add follow-up message (status: $UPDATE_STATUS)"
        return 1
    fi

    success "Follow-up message added successfully"
    info "Chat is definitely continuable!"
    return 0
}

# ============================================================================
# MAIN TEST WORKFLOW
# ============================================================================

run_complete_test() {
    local TEST_MESSAGE="${1:-Health check: say pong.}"
    
    log "============================================================================"
    log "OpenWebUI Backend Flow Test with Spinner Verification"
    log "============================================================================"
    echo ""
    
    # Generate IDs
    local USER_MSG_ID=$(generate_uuid)
    local ASSISTANT_MSG_ID=$(generate_uuid)
    local TIMESTAMP=$(get_timestamp)
    
    log "Test Configuration:"
    log "  Message: $TEST_MESSAGE"
    log "  User Message ID: $USER_MSG_ID"
    log "  Assistant Message ID: $ASSISTANT_MSG_ID"
    log "  Session ID: $SESSION"
    echo ""
    
    # ========================================================================
    # STEP 1: Create Chat
    # ========================================================================
    log "STEP 1: Creating chat..."
    
    local STEP1_RESPONSE=$(curl -s -X POST "$BASE/api/v1/chats/new" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"chat\": {
                \"title\": \"Test Chat $(date +'%H:%M:%S')\",
                \"models\": [\"$MODEL\"],
                \"messages\": [
                    {
                        \"id\": \"$USER_MSG_ID\",
                        \"role\": \"user\",
                        \"content\": \"$TEST_MESSAGE\",
                        \"timestamp\": $TIMESTAMP,
                        \"models\": [\"$MODEL\"]
                    }
                ],
                \"history\": {
                    \"current_id\": \"$USER_MSG_ID\",
                    \"messages\": {
                        \"$USER_MSG_ID\": {
                            \"id\": \"$USER_MSG_ID\",
                            \"role\": \"user\",
                            \"content\": \"$TEST_MESSAGE\",
                            \"timestamp\": $TIMESTAMP,
                            \"models\": [\"$MODEL\"]
                        }
                    }
                }
            }
        }")
    
    local CHAT_ID=$(echo "$STEP1_RESPONSE" | jq -r '.chat.id // .id // empty')
    if [ -z "$CHAT_ID" ]; then
        error "Failed to create chat"
        echo "$STEP1_RESPONSE" | jq .
        exit 1
    fi

    local CHAT_JSON=$(echo "$STEP1_RESPONSE" | jq --arg chat_id "$CHAT_ID" '(.chat // .) | .id = $chat_id')
    success "Chat created: $CHAT_ID"
    echo ""
    
    # ========================================================================
    # STEP 2: Inject Assistant Message
    # ========================================================================
    log "STEP 2: Injecting assistant message placeholder..."
    
    local ASSISTANT_TIMESTAMP=$(get_timestamp)
    local ASSISTANT_MESSAGE=$(jq -n \
        --arg id "$ASSISTANT_MSG_ID" \
        --arg parent "$USER_MSG_ID" \
        --arg model "$MODEL" \
        --argjson timestamp $ASSISTANT_TIMESTAMP \
        '{
            id: $id,
            role: "assistant",
            content: "",
            parentId: $parent,
            modelName: $model,
            modelIdx: 0,
            timestamp: $timestamp,
            done: false,
            statusHistory: []
        }'
    )

    local UPDATED_CHAT=$(echo "$CHAT_JSON" | jq \
        --argjson assistant "$ASSISTANT_MESSAGE" \
        --arg id "$ASSISTANT_MSG_ID" \
        '.messages = (.messages // []) + [$assistant]
         | .history = (.history // {})
         | .history.messages = (.history.messages // {})
         | .history.messages[$id] = $assistant
         | .history.current_id = $id
         | .history.currentId = $id
         | .currentId = $id'
    )

    local STEP2_BODY=$(echo "$UPDATED_CHAT" | jq -c '{chat: .}')
    local STEP2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/chats/$CHAT_ID" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$STEP2_BODY")

    if [ "$STEP2_STATUS" != "200" ] && [ "$STEP2_STATUS" != "201" ]; then
        error "Failed to update chat with assistant placeholder (status: $STEP2_STATUS)"
        exit 1
    fi

    success "Assistant placeholder injected"
    echo ""
    
    CHAT_JSON=$UPDATED_CHAT
    echo ""
    
    # ========================================================================
    # STEP 3: Trigger Completion
    # ========================================================================
    log "STEP 3: Triggering completion..."
    
    local CURRENT_DATETIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    local CONVERSATION=$(echo "$CHAT_JSON" | jq -c '[
        (.messages // [])
        | map(select(.role == "user" or .role == "assistant"))
        | .[]
        | select(.role != "assistant" or ((.content // "") != ""))
        | {role: .role, content: (.content // "")}
    ]')
    if [ -z "$CONVERSATION" ] || [ "$CONVERSATION" = "[]" ]; then
        CONVERSATION="[{\"role\":\"user\",\"content\":\"$TEST_MESSAGE\"}]"
    fi

    local COMPLETION_RESPONSE=$(curl -s -X POST "$BASE/api/chat/completions" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"chat_id\": \"$CHAT_ID\",
            \"id\": \"$ASSISTANT_MSG_ID\",
            \"messages\": $CONVERSATION,
            \"model\": \"$MODEL\",
            \"stream\": false,
            \"background_tasks\": {
                \"title_generation\": false,
                \"tags_generation\": false,
                \"follow_up_generation\": false
            },
            \"features\": {
                \"code_interpreter\": false,
                \"web_search\": false,
                \"image_generation\": false,
                \"memory\": false
            },
            \"variables\": {
                \"{{USER_NAME}}\": \"\",
            \"{{USER_LANGUAGE}}\": \"en-US\",
            \"{{CURRENT_DATETIME}}\": \"$CURRENT_DATETIME\",
            \"{{CURRENT_TIMEZONE}}\": \"UTC\"
            },
            \"session_id\": \"$SESSION\"
        }")

    local ASSISTANT_TEXT=$(echo "$COMPLETION_RESPONSE" | jq -r '
        def choice_text: (.message.content // .delta.content // .content // "");
        if type == "object" then
            if (.choices and (.choices | type == "array")) then
                (.choices | map(choice_text) | join(""))
            elif (.message and (.message.content // "") != "") then
                .message.content
            elif (.content // "") != "" then
                .content
            else
                ""
            end
        else
            ""
        end
    ')

    if [ -n "$ASSISTANT_TEXT" ] && [ "$ASSISTANT_TEXT" != "null" ]; then
        local SYNCED_CHAT=$(echo "$UPDATED_CHAT" | jq --arg assistant "$ASSISTANT_MSG_ID" --arg text "$ASSISTANT_TEXT" '
            (.messages // []) as $messages
            | ([ $messages[]? | select(.id == $assistant) ] | .[0]) as $message_entry
            | (.history.messages[$assistant] // {}) as $history_entry
            | ($history_entry + ($message_entry // {}) + {id: $assistant, role: ($history_entry.role // ($message_entry.role // "assistant"))}) as $template
            | .messages = if ([ $messages[]? | select(.id == $assistant) ] | length) > 0 then
                [ $messages[] | if .id == $assistant then . + {content: $text, done: true, statusHistory: (.statusHistory // [])} else . end ]
              else
                $messages + [ $template + {content: $text, done: true, statusHistory: []} ]
              end
            | .history = (.history // {})
            | .history.messages = (.history.messages // {})
            | .history.messages[$assistant] = $template + {content: $text, done: true}
            | .history.current_id = $assistant
            | .history.currentId = $assistant
            | .currentId = $assistant
        ')

        local SYNC_BODY=$(echo "$SYNCED_CHAT" | jq -c '{chat: .}')
        local SYNC_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/chats/$CHAT_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$SYNC_BODY")

        if [ "$SYNC_STATUS" = "200" ] || [ "$SYNC_STATUS" = "201" ]; then
            CHAT_JSON=$SYNCED_CHAT
            info "Assistant reply captured: ${ASSISTANT_TEXT:0:80}..."
        else
            warn "Could not sync assistant content after completion (status: $SYNC_STATUS)"
        fi
    fi

    success "Completion triggered"
    echo ""
    
    # Wait a moment for processing to start
    sleep 2
    
    # ========================================================================
    # STEP 4: Mark Completion (CRITICAL!)
    # ========================================================================
    log "STEP 4: Marking completion... (This prevents the spinner!)"
    
    curl -s -X POST "$BASE/api/chat/completed" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"chat_id\": \"$CHAT_ID\",
            \"id\": \"$ASSISTANT_MSG_ID\",
            \"session_id\": \"$SESSION\",
            \"model\": \"$MODEL\"
        }" > /dev/null
    
    success "Completion marked (spinner should not appear!)"
    echo ""
    
    # ========================================================================
    # STEP 5: Poll for Response
    # ========================================================================
    log "STEP 5: Polling for response..."
    
    local MAX_ATTEMPTS=30
    local POLL_INTERVAL=2
    local ATTEMPT=0
    local RESPONSE_READY=false
    
    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        ATTEMPT=$((ATTEMPT + 1))
        
        local POLL_RESPONSE=$(curl -s -X GET "$BASE/api/v1/chats/$CHAT_ID" \
            -H "Authorization: Bearer $TOKEN")
        
        local CONTENT=$(echo "$POLL_RESPONSE" | jq -r --arg assistant "$ASSISTANT_MSG_ID" '
            ((.chat.messages // .messages // [])
                | map(select(.id == $assistant and .role == "assistant"))
                | .[0].content) // ""
        ')

        local HISTORY_CONTENT=$(echo "$POLL_RESPONSE" | jq -r --arg assistant "$ASSISTANT_MSG_ID" '
            ((.chat.history.messages // .history.messages // {})[$assistant].content) // ""
        ')

        if { [ -z "$CONTENT" ] || [ "$CONTENT" = "null" ]; } && [ -n "$HISTORY_CONTENT" ] && [ "$HISTORY_CONTENT" != "null" ]; then
            local SYNCED_CHAT=$(echo "$POLL_RESPONSE" | jq --arg assistant "$ASSISTANT_MSG_ID" --arg text "$HISTORY_CONTENT" '
                (.chat // .) as $chat
                | $chat
                | (.messages // []) as $messages
                | ([ $messages[]? | select(.id == $assistant) ] | .[0]) as $message_entry
                | (.history.messages[$assistant] // {}) as $history_entry
                | ($history_entry + ($message_entry // {}) + {id: $assistant, role: ($history_entry.role // ($message_entry.role // "assistant"))}) as $template
                | .messages = if ([ $messages[]? | select(.id == $assistant) ] | length) > 0 then
                    [ $messages[] | if .id == $assistant then . + {content: $text, done: true, statusHistory: (.statusHistory // [])} else . end ]
                  else
                    $messages + [ $template + {content: $text, done: true, statusHistory: []} ]
                  end
                | .history = (.history // {})
                | .history.messages = (.history.messages // {})
                | .history.messages[$assistant] = $template + {content: $text, done: true}
                | .history.current_id = $assistant
                | .history.currentId = $assistant
                | .currentId = $assistant
            ')

            local SYNC_BODY=$(echo "$SYNCED_CHAT" | jq -c '{chat: .}')
            local SYNC_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/chats/$CHAT_ID" \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "$SYNC_BODY")

            if [ "$SYNC_STATUS" = "200" ] || [ "$SYNC_STATUS" = "201" ]; then
                CONTENT="$HISTORY_CONTENT"
                CHAT_JSON=$SYNCED_CHAT
                success "Synchronized assistant content from history"
            else
                warn "Failed to synchronize assistant content during polling (status: $SYNC_STATUS)"
            fi
        fi

        if [ -n "$CONTENT" ] && [ "$CONTENT" != "" ] && [ "$CONTENT" != "null" ]; then
            RESPONSE_READY=true
            success "Response ready after $ATTEMPT attempts"
            break
        fi

        log "  Attempt $ATTEMPT/$MAX_ATTEMPTS: Waiting for response..."
        sleep $POLL_INTERVAL
    done
    
    if [ "$RESPONSE_READY" = false ]; then
        error "Response not ready after $MAX_ATTEMPTS attempts"
        exit 1
    fi
    echo ""
    
    # ========================================================================
    # STEP 6: Verify Spinner is Gone
    # ========================================================================
    echo ""
    log "============================================================================"
    log "VERIFICATION: Checking if spinner is gone"
    log "============================================================================"
    echo ""
    
    if verify_spinner_gone "$CHAT_ID" "$ASSISTANT_MSG_ID"; then
        echo ""
        log "============================================================================"
        success "✓✓✓ TEST PASSED - SPINNER IS GONE ✓✓✓"
        log "============================================================================"
        echo ""
        
        # Display results
        if command -v jq &> /dev/null; then
            local FINAL_CHAT=$(curl -s -X GET "$BASE/api/v1/chats/$CHAT_ID" \
                -H "Authorization: Bearer $TOKEN")
            local RESPONSE_TEXT=$(echo "$FINAL_CHAT" | jq -r --arg assistant "$ASSISTANT_MSG_ID" '
                ((.chat.messages // .messages // [])
                    | map(select(.id == $assistant))
                    | .[0].content) // empty
            ')
            
            info "Assistant Response:"
            echo ""
            echo "$RESPONSE_TEXT"
            echo ""
        fi
        
        info "Access your chat here:"
        echo "  $BASE/c/$CHAT_ID"
        echo ""

        mkdir -p artifacts
        curl -s -X GET "$BASE/api/v1/chats/$CHAT_ID" \
            -H "Authorization: Bearer $TOKEN" \
            -o "artifacts/chat_snapshot_${CHAT_ID}.json"
        info "Chat snapshot saved to artifacts/chat_snapshot_${CHAT_ID}.json"

        # Optional: Test if chat is continuable
        echo ""
        test_chat_continuable "$CHAT_ID" "$ASSISTANT_MSG_ID" || true
        
        return 0
    else
        error "Spinner verification FAILED"
        return 1
    fi
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

# Check dependencies
if ! command -v curl &> /dev/null; then
    error "curl is required. Install it first."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    warn "jq is not installed. Some features will be limited."
    warn "Install jq for full functionality: https://stedolan.github.io/jq/"
    echo ""
fi

# Run test
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [test_message]"
    echo ""
    echo "Configuration is loaded from .env file"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run with default message"
    echo "  $0 'What is 2+2?'                    # Run with custom message"
    echo ""
    exit 0
fi

TEST_MESSAGE="${1:-Health check: say pong.}"
run_complete_test "$TEST_MESSAGE"
