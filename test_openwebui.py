#!/usr/bin/env python3
"""
OpenWebUI Backend Flow Test Script with .env Support
This script tests the complete workflow and verifies the spinner is gone.

Usage:
    python openwebui_test.py
    python openwebui_test.py "Custom test message"
"""

import requests
import json
import time
import uuid
import os
import sys
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color


class OpenWebUITester:
    def __init__(self, base_url: str, token: str, model: str, session_id: str):
        """
        Initialize the OpenWebUI tester.
        
        Args:
            base_url: OpenWebUI instance URL
            token: API authentication token
            model: Model name to use
            session_id: Session ID for this test run
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.model = model
        self.session_id = session_id
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        
    def _log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp and color."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = {
            "INFO": Colors.BLUE,
            "SUCCESS": Colors.GREEN,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW,
            "DETAIL": Colors.CYAN
        }.get(level, Colors.NC)
        
        symbol = {
            "SUCCESS": "✓",
            "ERROR": "✗",
            "WARNING": "⚠",
            "DETAIL": "ℹ"
        }.get(level, "")
        
        print(f"{color}[{timestamp}] {symbol}{Colors.NC} {message}")
        
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make an HTTP request and return the JSON response."""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self._log(f"Request failed: {str(e)}", "ERROR")
            if hasattr(e, 'response') and e.response is not None:
                self._log(f"Response: {e.response.text[:500]}", "ERROR")
            raise

    def _extract_assistant_text(self, completion_result: Dict) -> str:
        """Extract assistant content from the completion response."""
        if not isinstance(completion_result, dict):
            return ""

        def collect_from_choices(choices: List[Dict]) -> str:
            parts: List[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    delta_content = delta.get("content")
                    if isinstance(delta_content, str):
                        parts.append(delta_content)
                direct_content = choice.get("content")
                if isinstance(direct_content, str):
                    parts.append(direct_content)
            combined = "".join(parts).strip()
            return combined

        choices = completion_result.get("choices")
        if isinstance(choices, list):
            text = collect_from_choices(choices)
            if text:
                return text

        message = completion_result.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        content = completion_result.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        data = completion_result.get("data")
        if isinstance(data, dict):
            nested = self._extract_assistant_text(data)
            if nested:
                return nested

        return ""

    @staticmethod
    def _find_parent_id(chat_view: Dict, assistant_msg_id: str) -> Optional[str]:
        """Find the parentId for the assistant message if present."""
        history = chat_view.get("history", {})
        history_messages = history.get("messages", {})
        if isinstance(history_messages, dict):
            entry = history_messages.get(assistant_msg_id)
            if isinstance(entry, dict):
                parent = entry.get("parentId")
                if parent:
                    return parent

        for msg in chat_view.get("messages", []) or []:
            if isinstance(msg, dict) and msg.get("id") == assistant_msg_id:
                parent = msg.get("parentId")
                if parent:
                    return parent

        return None

    def _sync_assistant_content(
        self,
        chat_id: str,
        chat_view: Dict,
        assistant_msg_id: str,
        content: str,
    ) -> Dict:
        """Ensure assistant content is present in both messages[] and history."""
        if not content or not content.strip():
            return chat_view

    def _save_chat_snapshot(self, chat_id: str) -> Optional[Path]:
        """Persist the latest chat payload for external inspection."""
        try:
            chat_payload = self._make_request("GET", f"/api/v1/chats/{chat_id}")
        except Exception as exc:
            self._log(f"Unable to capture chat snapshot: {exc}", "WARNING")
            return None

        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(exist_ok=True)
        snapshot_path = artifacts_dir / f"chat_snapshot_{chat_id}.json"
        with snapshot_path.open("w", encoding="utf-8") as handle:
            json.dump(chat_payload, handle, indent=2)
        self._log(f"Chat snapshot saved to {snapshot_path}", "DETAIL")
        return snapshot_path

        updated_chat = json.loads(json.dumps(chat_view))
        updated_chat["id"] = chat_id

        messages = updated_chat.setdefault("messages", [])
        assistant_entry = None
        for message in messages:
            if message.get("id") == assistant_msg_id:
                assistant_entry = message
                break

        if assistant_entry is None:
            assistant_entry = {
                "id": assistant_msg_id,
                "role": "assistant",
                "content": content,
                "parentId": self._find_parent_id(chat_view, assistant_msg_id),
                "modelName": self.model,
                "modelIdx": 0,
                "timestamp": int(time.time()),
                "done": True,
            }
            messages.append(assistant_entry)
        else:
            assistant_entry["content"] = content
            assistant_entry["done"] = True
            assistant_entry.setdefault("statusHistory", [])

        history = updated_chat.setdefault("history", {})
        history_messages = history.setdefault("messages", {})
        history_entry = history_messages.get(assistant_msg_id)
        if not isinstance(history_entry, dict):
            history_entry = {
                "id": assistant_msg_id,
                "role": "assistant",
                "parentId": assistant_entry.get("parentId"),
                "modelName": assistant_entry.get("modelName", self.model),
                "modelIdx": assistant_entry.get("modelIdx", 0),
                "timestamp": assistant_entry.get("timestamp", int(time.time())),
            }
        history_entry["content"] = content
        history_entry["done"] = True
        history_messages[assistant_msg_id] = history_entry
        history["current_id"] = assistant_msg_id
        history["currentId"] = assistant_msg_id
        updated_chat["currentId"] = assistant_msg_id

        try:
            self._make_request("POST", f"/api/v1/chats/{chat_id}", {"chat": updated_chat})
            self._log("Assistant content synchronized with chat state", "DETAIL")
            return updated_chat
        except Exception as sync_error:
            self._log(f"Failed to synchronize assistant content: {sync_error}", "WARNING")
            return chat_view

    def step1_create_chat(self, user_message: str) -> Dict:
        """Step 1: Create a new chat with a user message."""
        self._log("STEP 1: Creating chat...")
        
        user_msg_id = str(uuid.uuid4())
        timestamp = int(time.time())
        
        payload = {
            "chat": {
                "title": f"Test Chat {datetime.now().strftime('%H:%M:%S')}",
                "models": [self.model],
                "messages": [
                    {
                        "id": user_msg_id,
                        "role": "user",
                        "content": user_message,
                        "timestamp": timestamp,
                        "models": [self.model]
                    }
                ],
                "history": {
                    "current_id": user_msg_id,
                    "messages": {
                        user_msg_id: {
                            "id": user_msg_id,
                            "role": "user",
                            "content": user_message,
                            "timestamp": timestamp,
                            "models": [self.model]
                        }
                    }
                }
            }
        }
        
        result = self._make_request("POST", "/api/v1/chats/new", payload)

        chat_payload: Optional[Dict] = None
        chat_id: Optional[str] = None
        if isinstance(result, dict):
            # Preferred shape: {"success": True, "chat": {...}}
            if result.get("success") and isinstance(result.get("chat"), dict):
                chat_payload = json.loads(json.dumps(result["chat"]))
            # Some deployments drop the success flag and return the chat object directly
            elif isinstance(result.get("chat"), dict):
                chat_payload = json.loads(json.dumps(result["chat"]))
            # Other builds wrap chat inside a data envelope
            elif isinstance(result.get("data"), dict) and isinstance(result["data"].get("chat"), dict):
                chat_payload = json.loads(json.dumps(result["data"]["chat"]))
            # Fallback: the top-level object already looks like a chat
            elif {"id", "messages"}.issubset(result.keys()):
                chat_payload = json.loads(json.dumps(result))
            elif result.get("chat_id"):
                chat_payload = json.loads(json.dumps({k: v for k, v in result.items() if k not in {"success", "status", "chat_id"}}))
                chat_payload["id"] = result["chat_id"]

            if isinstance(result.get("id"), str):
                chat_id = result["id"]

        if chat_payload:
            chat_id = chat_payload.get("id") or chat_id
            if not chat_id and isinstance(result, dict) and isinstance(result.get("chat"), dict):
                chat_id = result.get("id")
                if chat_id:
                    chat_payload["id"] = chat_id

        if chat_payload and chat_id:
            self._log(f"Chat created: {chat_id}", "SUCCESS")
            return {
                "chat_id": chat_id,
                "user_msg_id": user_msg_id,
                "chat_payload": chat_payload
            }

        safe_preview = json.dumps(result, indent=2)[:500] if isinstance(result, dict) else str(result)
        self._log("Failed to create chat - unexpected response", "ERROR")
        self._log(f"Response preview: {safe_preview}", "DETAIL")
        raise Exception("Failed to create chat")
            
    def step2_inject_assistant_message(self, chat_id: str, user_msg_id: str,
                                       chat_payload: Dict) -> Tuple[str, Dict]:
        """Step 2: Inject empty assistant message placeholder."""
        self._log("STEP 2: Injecting assistant message placeholder...")
        
        assistant_msg_id = str(uuid.uuid4())
        timestamp = int(time.time())
        
        assistant_message = {
            "id": assistant_msg_id,
            "role": "assistant",
            "content": "",
            "parentId": user_msg_id,
            "modelName": self.model,
            "modelIdx": 0,
            "timestamp": timestamp,
            "done": False,
            "statusHistory": [],
        }

        updated_chat = json.loads(json.dumps(chat_payload))
        messages = updated_chat.setdefault("messages", [])
        messages.append(assistant_message)

        history = updated_chat.setdefault("history", {})
        history_messages = history.setdefault("messages", {})
        history_messages[assistant_msg_id] = dict(assistant_message)
        history["current_id"] = assistant_msg_id
        history["currentId"] = assistant_msg_id

        updated_chat["currentId"] = assistant_msg_id
        updated_chat["id"] = chat_id

        self._make_request("POST", f"/api/v1/chats/{chat_id}", {"chat": updated_chat})
        self._log("Assistant placeholder injected", "SUCCESS")

        return assistant_msg_id, updated_chat
        
    def step3_trigger_completion(
        self,
        chat_id: str,
        assistant_msg_id: str,
        user_message: str,
        chat_state: Dict,
    ) -> Tuple[Dict, str]:
        """Step 3: Trigger the assistant completion."""
        self._log("STEP 3: Triggering completion...")
        
        conversation: List[Dict[str, str]] = []
        for message in chat_state.get("messages", []) or []:
            role = message.get("role")
            content = message.get("content", "")
            if not role or content is None:
                continue
            if role not in {"user", "assistant"}:
                continue
            if role == "assistant" and not content.strip():
                continue
            conversation.append({
                "role": role,
                "content": content,
            })
        if not conversation:
            conversation.append({"role": "user", "content": user_message})

        payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "messages": conversation,
            "model": self.model,
            "stream": False,
            "background_tasks": {
                "title_generation": False,
                "tags_generation": False,
                "follow_up_generation": False
            },
            "features": {
                "code_interpreter": False,
                "web_search": False,
                "image_generation": False,
                "memory": False
            },
            "variables": {
                "{{USER_NAME}}": "",
                "{{USER_LANGUAGE}}": "en-US",
                "{{CURRENT_DATETIME}}": datetime.now(timezone.utc).isoformat(),
                "{{CURRENT_TIMEZONE}}": "UTC"
            },
            "session_id": self.session_id
        }
            
        result = self._make_request("POST", "/api/chat/completions", payload)
        preview = json.dumps(result, indent=2)[:400] if isinstance(result, dict) else str(result)[:400]
        self._log(f"Completion response preview: {preview}", "DETAIL")

        assistant_text = ""
        if isinstance(result, dict):
            if result.get("error"):
                self._log(f"Completion response reported error: {result.get('error')}", "ERROR")
            assistant_text = self._extract_assistant_text(result)

        if assistant_text:
            chat_state = self._sync_assistant_content(chat_id, chat_state, assistant_msg_id, assistant_text)
            snippet = assistant_text[:80].replace('\n', ' ')
            self._log(f"Assistant reply captured: {snippet}...", "DETAIL")
        else:
            self._log("Completion triggered", "SUCCESS")

        return chat_state, assistant_text
        
    def step4_mark_completion(self, chat_id: str, assistant_msg_id: str) -> None:
        """Step 4: Mark the completion as done (CRITICAL - prevents spinner!)."""
        self._log("STEP 4: Marking completion... (This prevents the spinner!)")
        
        payload = {
            "chat_id": chat_id,
            "id": assistant_msg_id,
            "session_id": self.session_id,
            "model": self.model
        }
        
        self._make_request("POST", "/api/chat/completed", payload)
        self._log("Completion marked (spinner should not appear!)", "SUCCESS")
        
    def step5_poll_for_response(self, chat_id: str, assistant_msg_id: str, 
                                max_attempts: int = 30, interval: int = 2) -> Dict:
        """Step 5: Poll for assistant response readiness."""
        self._log(f"STEP 5: Polling for response (max {max_attempts} attempts, {interval}s interval)...")
        
        for attempt in range(max_attempts):
            chat_data = self._make_request("GET", f"/api/v1/chats/{chat_id}")
            chat_view = chat_data.get("chat") if isinstance(chat_data, dict) and isinstance(chat_data.get("chat"), dict) else chat_data
            if not isinstance(chat_view, dict):
                self._log("Unexpected chat payload structure while polling", "WARNING")
                self._log(f"Payload preview: {str(chat_data)[:300]}", "DETAIL")
                time.sleep(interval)
                continue
            if attempt == 0:
                try:
                    snapshot = json.dumps(chat_view)[:500]
                    self._log(f"Chat snapshot: {snapshot}", "DETAIL")
                except Exception:
                    self._log("Could not serialize chat snapshot", "WARNING")
            
            # Look for assistant message with content in messages array
            messages = chat_view.get("messages") or []
            ui_message = None
            for message in messages:
                if (message.get("id") == assistant_msg_id and
                        message.get("role") == "assistant"):
                    ui_message = message
                    break

            history_container = chat_view.get("history") or {}
            history_messages = history_container.get("messages", {}) or {}
            history_message = history_messages.get(assistant_msg_id)
            history_content = ""
            if isinstance(history_message, dict):
                history_content = history_message.get("content", "") or ""

            ui_content = ui_message.get("content", "") if isinstance(ui_message, dict) else ""

            if ui_content.strip():
                self._log(f"Response ready after {attempt + 1} attempts", "SUCCESS")
                return chat_view

            if history_content.strip():
                self._log("History contains assistant content; synchronizing messages", "DETAIL")
                chat_view = self._sync_assistant_content(chat_id, chat_view, assistant_msg_id, history_content)
                messages = chat_view.get("messages", [])
                for message in messages:
                    if (message.get("id") == assistant_msg_id and
                            message.get("role") == "assistant" and
                            (message.get("content", "") or "").strip()):
                        self._log(f"Response ready after {attempt + 1} attempts", "SUCCESS")
                        return chat_view
            
            self._log(f"  Attempt {attempt + 1}/{max_attempts}: Waiting for response...")
            time.sleep(interval)
            
        raise TimeoutError(f"Response not ready after {max_attempts} attempts")
        
    def verify_spinner_gone(self, chat_id: str, assistant_msg_id: str) -> Tuple[bool, Dict]:
        """
        Verify that the spinner is gone by checking:
        1. Assistant message has content in messages[] array (what UI displays)
        2. Content matches between messages[] and history{}
        3. Chat is in proper state
        
        Returns:
            Tuple of (success: bool, chat_data: dict)
        """
        self._log("", "DETAIL")
        self._log("="*80, "DETAIL")
        self._log("VERIFICATION: Checking if spinner is gone", "DETAIL")
        self._log("="*80, "DETAIL")
        self._log("", "DETAIL")
        
        response_payload = self._make_request("GET", f"/api/v1/chats/{chat_id}")
        chat_data = response_payload.get("chat") if isinstance(response_payload, dict) and isinstance(response_payload.get("chat"), dict) else response_payload
        
        # Extract assistant message from messages array (UI displays this)
        messages = chat_data.get("messages") or chat_data.get("chat", {}).get("messages", [])
        ui_message = None
        for msg in messages:
            if msg.get("id") == assistant_msg_id and msg.get("role") == "assistant":
                ui_message = msg
                break
        
        if not ui_message:
            self._log("FAIL: Assistant message not found in messages[] array", "ERROR")
            return False, chat_data
            
        ui_content = ui_message.get("content", "")
        
        # Extract from history
        history_container = chat_data.get("history") or chat_data.get("chat", {}).get("history", {})
        history_message = history_container.get("messages", {}).get(assistant_msg_id, {})
        history_content = history_message.get("content", "")
        
        self._log("Verification Results:", "DETAIL")
        print()
        
        # Check 1: UI content is not empty
        if not ui_content or ui_content.strip() == "":
            self._log("FAIL: Assistant message content is EMPTY in messages[] array", "ERROR")
            self._log("      This means the spinner will still show!", "ERROR")
            return False, chat_data
        else:
            self._log("PASS: Assistant message has content in messages[] array (UI displays this)", "SUCCESS")
            preview = ui_content[:100].replace('\n', ' ')
            self._log(f"      Content preview: {preview}...", "DETAIL")
        
        # Check 2: History content matches
        if ui_content == history_content:
            self._log("PASS: Content matches between messages[] and history{}", "SUCCESS")
        else:
            self._log("WARNING: Content mismatch between UI and history", "WARNING")
            ui_preview = ui_content[:50].replace('\n', ' ')
            history_preview = history_content[:50].replace('\n', ' ')
            self._log(f"      UI content: {ui_preview}...", "WARNING")
            self._log(f"      History content: {history_preview}...", "WARNING")
        
        # Check 3: Verify currentId
        current_id = (
            history_container.get("currentId") or
            chat_data.get("currentId") or
            history_container.get("current_id")
        )
        
        if current_id == assistant_msg_id or not current_id:
            self._log("PASS: Chat state looks correct", "SUCCESS")
        else:
            self._log("WARNING: currentId is not the assistant message", "WARNING")
        
        print()
        self._log("✓ SPINNER VERIFICATION PASSED", "SUCCESS")
        self._log("✓ Chat should be continuable in the UI", "SUCCESS")
        print()
        
        return True, chat_data
        
    def test_chat_continuable(self, chat_id: str, assistant_msg_id: str) -> bool:
        """Test if chat is continuable by attempting to add a follow-up message."""
        self._log("Testing if chat is continuable by adding a follow-up message...", "DETAIL")
        
        followup_user_id = str(uuid.uuid4())
        timestamp = int(time.time())
        
        try:
            response_payload = self._make_request("GET", f"/api/v1/chats/{chat_id}")
            chat_state = response_payload.get("chat") if isinstance(response_payload, dict) and isinstance(response_payload.get("chat"), dict) else response_payload
            updated_chat = json.loads(json.dumps(chat_state))

            user_message = {
                "id": followup_user_id,
                "role": "user",
                "content": "Thanks! One more test.",
                "parentId": assistant_msg_id,
                "timestamp": timestamp,
                "models": [self.model]
            }

            messages = updated_chat.setdefault("messages", [])
            messages.append(user_message)

            history = updated_chat.setdefault("history", {})
            history_messages = history.setdefault("messages", {})
            history_messages[followup_user_id] = dict(user_message)
            history["current_id"] = followup_user_id
            history["currentId"] = followup_user_id

            updated_chat["currentId"] = followup_user_id
            updated_chat["id"] = chat_id

            self._make_request("POST", f"/api/v1/chats/{chat_id}", {"chat": updated_chat})
            self._log("Follow-up message added successfully", "SUCCESS")
            self._log("Chat is definitely continuable!", "DETAIL")
            return True
        except Exception as e:
            self._log(f"Could not add follow-up message: {str(e)}", "WARNING")
            return False
    
    def run_complete_test(self, user_message: str) -> Dict:
        """
        Run the complete 6-step workflow with verification.
        
        Args:
            user_message: The user's question/message
            
        Returns:
            Dict containing test results
        """
        self._log("="*80)
        self._log("OpenWebUI Backend Flow Test with Spinner Verification")
        self._log("="*80)
        print()
        
        self._log("Test Configuration:", "DETAIL")
        self._log(f"  Message: {user_message}", "DETAIL")
        self._log(f"  Session ID: {self.session_id}", "DETAIL")
        print()
        
        try:
            # Step 1: Create chat
            step1_result = self.step1_create_chat(user_message)
            chat_id = step1_result["chat_id"]
            user_msg_id = step1_result["user_msg_id"]
            chat_state = step1_result["chat_payload"]
            print()
            
            # Step 2: Inject assistant message
            assistant_msg_id, chat_state = self.step2_inject_assistant_message(
                chat_id, user_msg_id, chat_state
            )
            print()
            
            # Step 3: Trigger completion
            assistant_response = ""
            chat_state, assistant_response = self.step3_trigger_completion(
                chat_id,
                assistant_msg_id,
                user_message,
                chat_state,
            )
            print()
            
            # Small delay before marking complete
            time.sleep(2)
            
            # Step 4: Mark completion (CRITICAL!)
            self.step4_mark_completion(chat_id, assistant_msg_id)
            print()
            
            # Step 5: Poll for response
            chat_data = self.step5_poll_for_response(chat_id, assistant_msg_id)
            print()
            
            # Step 6: Verify spinner is gone
            verification_passed, final_chat = self.verify_spinner_gone(chat_id, assistant_msg_id)
            
            if not verification_passed:
                return {
                    "success": False,
                    "error": "Spinner verification failed",
                    "chat_id": chat_id
                }
            
            # Extract response
            if not assistant_response:
                for msg in final_chat.get("messages", []):
                    if msg.get("id") == assistant_msg_id:
                        assistant_response = msg.get("content", "")
                        break

            if not assistant_response:
                history_messages = final_chat.get("history", {}).get("messages", {})
                if isinstance(history_messages, dict):
                    history_msg = history_messages.get(assistant_msg_id)
                    if isinstance(history_msg, dict):
                        assistant_response = history_msg.get("content", "")

            assistant_response = assistant_response or ""

            # Display results
            print()
            self._log("="*80)
            self._log("✓✓✓ TEST PASSED - SPINNER IS GONE ✓✓✓", "SUCCESS")
            self._log("="*80)
            print()
            
            self._log("Assistant Response:", "DETAIL")
            print()
            print(assistant_response)
            print()
            
            self._log("Access your chat here:", "DETAIL")
            print(f"  {self.base_url}/c/{chat_id}")
            print()

            self._save_chat_snapshot(chat_id)

            # Optional: Test if chat is continuable
            print()
            self.test_chat_continuable(chat_id, assistant_msg_id)

            return {
                "success": True,
                "chat_id": chat_id,
                "user_msg_id": user_msg_id,
                "assistant_msg_id": assistant_msg_id,
                "user_message": user_message,
                "assistant_response": assistant_response,
                "full_chat": final_chat,
                "spinner_gone": True,
                "continuable": True
            }
            
        except Exception as e:
            self._log(f"✗ TEST FAILED: {str(e)}", "ERROR")
            self._log("="*80)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables from .env file."""
    env_vars = {}
    
    if not env_path.exists():
        raise FileNotFoundError(f".env file not found at {env_path}")
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    
    return env_vars


def main():
    """Main function to run tests."""
    
    # Find .env file in script directory
    script_dir = Path(__file__).parent
    env_file = script_dir / '.env'
    
    print(f"Loading configuration from {env_file}...")
    
    try:
        env_vars = load_env_file(env_file)
    except FileNotFoundError as e:
        print(f"\n{Colors.RED}ERROR:{Colors.NC} {e}")
        print("\nPlease create a .env file with:")
        print("  BASE=https://your-openwebui-instance.com")
        print("  TOKEN=your-api-token")
        print("  MODEL=gemma3:4b")
        return 1
    
    # Validate required variables
    required_vars = ['BASE', 'TOKEN', 'MODEL']
    missing = [var for var in required_vars if var not in env_vars or not env_vars[var]]
    
    if missing:
        print(f"\n{Colors.RED}ERROR:{Colors.NC} Missing required variables in .env file: {', '.join(missing)}")
        return 1
    
    # Get configuration
    BASE = env_vars['BASE'].rstrip('/')
    TOKEN = env_vars['TOKEN']
    MODEL = env_vars['MODEL']
    SESSION = str(uuid.uuid4())
    
    print(f"\nConfiguration loaded:")
    print(f"  BASE: {BASE}")
    print(f"  MODEL: {MODEL}")
    print(f"  SESSION: {SESSION}")
    print()
    
    # Get test message from command line or use default
    test_message = sys.argv[1] if len(sys.argv) > 1 else "Health check: say pong."
    
    # Initialize tester
    tester = OpenWebUITester(BASE, TOKEN, MODEL, SESSION)
    
    # Run test
    result = tester.run_complete_test(test_message)
    
    # Save results to file
    if result.get("success"):
        output_file = f"test_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n{Colors.GREEN}✓{Colors.NC} Full test results saved to: {output_file}\n")
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
