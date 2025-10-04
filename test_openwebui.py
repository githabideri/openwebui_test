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
import random
import mimetypes
from typing import Dict, Optional, Tuple, List, Any
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
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self.follow_up_enabled = os.getenv("FOLLOW_UP_TEST", "0") == "1"
        
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
        
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        json_payload: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Tuple[str, bytes, str]]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Dict:
        """Make an HTTP request and return the JSON response."""

        url = f"{self.base_url}{endpoint}"
        request_headers = dict(self.session.headers)
        if headers:
            request_headers.update(headers)

        try:
            method_upper = method.upper()
            if method_upper == "GET":
                response = self.session.get(
                    url, headers=request_headers, params=params, timeout=timeout
                )
            elif method_upper == "POST":
                if files:
                    response = self.session.post(
                        url,
                        headers={k: v for k, v in request_headers.items() if k.lower() != "content-type"},
                        files=files,
                        data=data,
                        params=params,
                        timeout=timeout,
                    )
                elif json_payload is not None:
                    response = self.session.post(
                        url,
                        headers=request_headers,
                        json=json_payload,
                        params=params,
                        timeout=timeout,
                    )
                else:
                    response = self.session.post(
                        url,
                        headers=request_headers,
                        json=data,
                        params=params,
                        timeout=timeout,
                    )
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except requests.exceptions.RequestException as e:
            self._log(f"Request failed: {str(e)}", "ERROR")
            if hasattr(e, "response") and e.response is not None:
                self._log(f"Response: {e.response.text[:500]}", "ERROR")
            raise

    @staticmethod
    def _extract_first_id(payload: Any) -> Optional[str]:
        """Extract the first identifier found in a nested payload."""

        if isinstance(payload, dict):
            for key in ("id", "_id", "knowledge_id", "file_id"):
                value = payload.get(key)
                if value:
                    return str(value)
            for value in payload.values():
                found = OpenWebUITester._extract_first_id(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = OpenWebUITester._extract_first_id(item)
                if found:
                    return found
        elif isinstance(payload, (str, int)):
            return str(payload)
        return None

    def _upload_artifact_file(self, path: Path) -> Dict[str, Any]:
        """Upload a local artifact to OpenWebUI and return metadata."""

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size_bytes = path.stat().st_size
        self._log(
            f"  Uploading {path.name} ({size_bytes} bytes, {mime_type})...",
            "DETAIL",
        )

        endpoints = [
            "/api/v1/files/",
            "/api/v1/files",
            "/api/v1/files/upload",
        ]
        params = {"process": "true", "process_in_background": "false"}
        last_error: Optional[Exception] = None

        for index, endpoint in enumerate(endpoints):
            url = f"{self.base_url}{endpoint}"
            try:
                with path.open("rb") as handle:
                    response = self.session.post(
                        url,
                        headers={
                            k: v
                            for k, v in self.session.headers.items()
                            if k.lower() != "content-type"
                        },
                        files={"file": (path.name, handle, mime_type)},
                        params=params,
                        timeout=180,
                    )
                status_code = response.status_code
                if status_code in (404, 405) and index < len(endpoints) - 1:
                    self._log(
                        f"    Endpoint {endpoint} unavailable ({status_code}); trying fallback",
                        "DETAIL",
                    )
                    continue
                if status_code >= 400:
                    response.raise_for_status()
                data = response.json() if response.content else {}
                file_id = self._extract_first_id(data)
                if not file_id:
                    raise RuntimeError("OpenWebUI upload did not return an id")
                self._log(f"    File uploaded with id {file_id}", "SUCCESS")
                return {
                    "path": str(path),
                    "id": file_id,
                    "size": size_bytes,
                    "mime_type": mime_type,
                    "response": data,
                }
            except Exception as exc:
                last_error = exc
                self._log(f"    Upload attempt via {endpoint} failed: {exc}", "WARNING")

        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to upload artifact {path}")

    def _wait_for_file_processing(
        self,
        file_id: str,
        label: str,
        timeout: float = 180.0,
        poll_interval: float = 1.0,
    ) -> Dict[str, Any]:
        """Poll until OpenWebUI finishes processing an uploaded file."""

        deadline = time.time() + timeout
        last_status: Optional[str] = None
        status_payload: Dict[str, Any] = {}

        while time.time() < deadline:
            try:
                status_payload = self._make_request(
                    "GET",
                    f"/api/v1/files/{file_id}/process/status",
                    timeout=30,
                )
            except Exception as exc:
                self._log(
                    f"    Could not fetch processing status for {label}: {exc}",
                    "WARNING",
                )
                time.sleep(poll_interval)
                continue

            status = ""
            if isinstance(status_payload, dict):
                status = str(status_payload.get("status", ""))

            if status and status != last_status:
                self._log(
                    f"    Processing status for {label}: {status}",
                    "DETAIL",
                )
                last_status = status

            if status.lower() == "completed":
                try:
                    file_details = self._make_request(
                        "GET", f"/api/v1/files/{file_id}", timeout=30
                    )
                except Exception:
                    file_details = {}
                return {"status": status, "details": file_details}
            if status.lower() == "failed":
                raise RuntimeError(
                    f"File {file_id} processing failed: {status_payload}"
                )

            time.sleep(poll_interval)

        raise TimeoutError(
            f"File {file_id} did not finish processing after {timeout} seconds"
        )

    def _create_knowledge_collection(self, name: str, description: str) -> Dict[str, Any]:
        """Create an OpenWebUI knowledge collection and return metadata."""

        endpoints = [
            "/api/v1/knowledge/create",
            "/api/v1/knowledge",
        ]
        payload = {"name": name, "description": description}
        last_error: Optional[Exception] = None

        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = self.session.post(url, json=payload, timeout=60)
                if response.status_code >= 400:
                    response.raise_for_status()
                data = response.json() if response.content else {}
                knowledge_id = self._extract_first_id(data)
                if not knowledge_id:
                    raise RuntimeError("Knowledge creation response did not include an id")
                self._log(
                    f"  Knowledge collection created with id {knowledge_id}", "SUCCESS"
                )
                data.setdefault("id", knowledge_id)
                return data
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response else None
                if status in (404, 405) and endpoint != endpoints[-1]:
                    self._log(
                        f"    Knowledge endpoint {endpoint} unavailable ({status}); retrying fallback",
                        "DETAIL",
                    )
                    last_error = exc
                    continue
                raise
            except Exception as exc:
                last_error = exc
                self._log(f"    Knowledge creation via {endpoint} failed: {exc}", "WARNING")

        if last_error:
            raise last_error
        raise RuntimeError("Failed to create knowledge collection")

    def _attach_files_to_knowledge(self, knowledge_id: str, file_ids: List[str]) -> None:
        """Attach uploaded files to the target knowledge collection."""

        endpoint = f"/api/v1/knowledge/{knowledge_id}/file/add"
        url = f"{self.base_url}{endpoint}"
        for file_id in file_ids:
            payload = {"file_id": file_id}
            retries = 5
            for attempt in range(retries):
                try:
                    response = self.session.post(url, json=payload, timeout=60)
                    if response.status_code >= 400:
                        response.raise_for_status()
                    self._log(
                        f"    Attached file {file_id} to knowledge {knowledge_id}",
                        "SUCCESS",
                    )
                    break
                except requests.exceptions.HTTPError as exc:
                    status = exc.response.status_code if exc.response else None
                    if status in (409, 422, 425, 503) and attempt < retries - 1:
                        wait = 0.4 + random.random() * 0.4
                        self._log(
                            f"    Attachment returned {status}; retrying in {wait:.2f}s",
                            "WARNING",
                        )
                        time.sleep(wait)
                        continue
                    raise
                except Exception as exc:
                    if attempt < retries - 1:
                        wait = 0.4 + random.random() * 0.4
                        self._log(
                            f"    Attachment error {exc}; retrying in {wait:.2f}s",
                            "WARNING",
                        )
                        time.sleep(wait)
                        continue
                    raise

    def step7_publish_artifacts(
        self,
        chat_id: str,
        artifact_paths: List[Path],
        user_message: str,
        assistant_response: str,
    ) -> Dict[str, Any]:
        """Upload artifacts and bind them to a fresh knowledge collection."""

        self._log("STEP 7: Publishing artifacts to OpenWebUI knowledge...", "INFO")

        uploaded: List[Dict[str, Any]] = []
        for path in artifact_paths:
            upload_info = self._upload_artifact_file(path)
            file_id = upload_info["id"]
            processing_info = self._wait_for_file_processing(
                file_id, label=path.name
            )
            upload_info["processing"] = processing_info
            uploaded.append(upload_info)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        name = f"OpenWebUI Test Artifacts {datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        description = (
            f"Automated test artifacts for chat {chat_id}. "
            f"User prompt: {user_message[:180]}. Generated at {timestamp}."
        )

        knowledge_info = self._create_knowledge_collection(name, description)
        knowledge_id = knowledge_info.get("id") or self._extract_first_id(knowledge_info)
        if not knowledge_id:
            raise RuntimeError("Knowledge creation succeeded but no id was captured")

        file_ids = [entry["id"] for entry in uploaded]
        self._attach_files_to_knowledge(knowledge_id, file_ids)

        try:
            knowledge_details = self._make_request(
                "GET", f"/api/v1/knowledge/{knowledge_id}"
            )
        except Exception:
            knowledge_details = {}

        knowledge_snapshot_path = None
        try:
            artifacts_dir = Path("artifacts")
            artifacts_dir.mkdir(exist_ok=True)
            snapshot_path = artifacts_dir / f"knowledge_snapshot_{knowledge_id}.json"
            with snapshot_path.open("w", encoding="utf-8") as handle:
                json.dump(knowledge_details, handle, indent=2)
                handle.write("\n")
            knowledge_snapshot_path = snapshot_path
        except Exception as exc:
            self._log(
                f"    Could not write knowledge snapshot: {exc}",
                "WARNING",
            )

        ui_url = f"{self.base_url}/workspace/knowledge/{knowledge_id}"
        api_url = f"{self.base_url}/api/v1/knowledge/{knowledge_id}"

        self._log(
            f"Knowledge collection ready for review: {ui_url}",
            "SUCCESS",
        )

        updated_chat_state = self._bind_knowledge_to_chat(
            chat_id, knowledge_id, knowledge_details or knowledge_info
        )

        return {
            "knowledge_id": knowledge_id,
            "knowledge_name": knowledge_info.get("name", name),
            "knowledge_api_url": api_url,
            "knowledge_ui_url": ui_url,
            "uploads": uploaded,
            "knowledge_details": knowledge_details,
            "knowledge_snapshot": str(knowledge_snapshot_path)
            if knowledge_snapshot_path
            else None,
            "chat": updated_chat_state,
            "assistant_response": assistant_response,
        }

    def _bind_knowledge_to_chat(
        self,
        chat_id: str,
        knowledge_id: str,
        knowledge_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Link the created knowledge collection to the chat for immediate use."""

        try:
            raw_chat = self._make_request("GET", f"/api/v1/chats/{chat_id}")
        except Exception as exc:
            self._log(f"    Could not read chat while binding knowledge: {exc}", "WARNING")
            return None

        working_chat = (
            json.loads(json.dumps(raw_chat.get("chat")))
            if isinstance(raw_chat, dict) and isinstance(raw_chat.get("chat"), dict)
            else json.loads(json.dumps(raw_chat))
            if isinstance(raw_chat, dict)
            else None
        )

        if not isinstance(working_chat, dict):
            self._log("    Chat payload missing or malformed; skipping knowledge link", "WARNING")
            return None

        working_chat.setdefault("id", chat_id)

        knowledge_entry: Dict[str, Any] = {"id": knowledge_id}
        if isinstance(knowledge_details, dict):
            knowledge_entry.update(json.loads(json.dumps(knowledge_details)))
        knowledge_entry.setdefault("id", knowledge_id)
        knowledge_entry.setdefault("type", "collection")
        knowledge_entry.setdefault("status", knowledge_entry.get("status", "processed"))

        def merge_entry(collection: List[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
            merged: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for existing in collection + [entry]:
                if not isinstance(existing, dict):
                    continue
                entry_id = str(existing.get("id")) if existing.get("id") else None
                if not entry_id or entry_id in seen:
                    continue
                seen.add(entry_id)
                merged.append(existing)
            return merged

        files = working_chat.setdefault("files", [])
        if isinstance(files, list):
            working_chat["files"] = merge_entry(files, knowledge_entry)
        else:
            working_chat["files"] = [knowledge_entry]

        knowledge_ids = working_chat.setdefault("knowledge_ids", [])
        if isinstance(knowledge_ids, list):
            knowledge_ids.append(knowledge_id)
            ordered = []
            for kid in knowledge_ids:
                if kid not in ordered:
                    ordered.append(kid)
            working_chat["knowledge_ids"] = ordered
        else:
            working_chat["knowledge_ids"] = [knowledge_id]

        for message in working_chat.get("messages", []) or []:
            if isinstance(message, dict) and message.get("role") == "user":
                existing_files = message.setdefault("files", [])
                if isinstance(existing_files, list):
                    message["files"] = merge_entry(existing_files, knowledge_entry)
                else:
                    message["files"] = [knowledge_entry]
                break

        history = working_chat.get("history")
        if isinstance(history, dict):
            history_messages = history.setdefault("messages", {})
            if isinstance(history_messages, dict):
                for msg in history_messages.values():
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        existing_files = msg.setdefault("files", [])
                        if isinstance(existing_files, list):
                            msg["files"] = merge_entry(existing_files, knowledge_entry)
                        else:
                            msg["files"] = [knowledge_entry]
                        break

        payload = {"chat": working_chat}

        try:
            self._make_request(
                "POST",
                f"/api/v1/chats/{chat_id}",
                json_payload=payload,
                timeout=60,
            )
            self._log(
                f"  Knowledge collection linked to chat {chat_id}",
                "SUCCESS",
            )
            try:
                refreshed = self._make_request("GET", f"/api/v1/chats/{chat_id}")
                if (
                    isinstance(refreshed, dict)
                    and isinstance(refreshed.get("chat"), dict)
                ):
                    return refreshed["chat"]
                if isinstance(refreshed, dict):
                    return refreshed
            except Exception:
                pass
        except Exception as exc:
            self._log(
                f"    Failed to link knowledge to chat: {exc}",
                "WARNING",
            )

        return working_chat

    def _get_task_ids(self, chat_id: str) -> List[str]:
        """Fetch active task IDs for a chat."""
        try:
            result = self._make_request("GET", f"/api/tasks/chat/{chat_id}")
            task_ids = result.get("task_ids") if isinstance(result, dict) else []
            if not isinstance(task_ids, list):
                return []
            return [str(task) for task in task_ids]
        except Exception as exc:
            self._log(f"Could not retrieve task list: {exc}", "WARNING")
            return []

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
                "childrenIds": [],
            }
            messages.append(assistant_entry)
        else:
            assistant_entry["content"] = content
            assistant_entry["done"] = True
            assistant_entry.setdefault("statusHistory", [])
            assistant_entry.setdefault("childrenIds", [])

        parent_id = assistant_entry.get("parentId")
        if parent_id:
            for message in messages:
                if message.get("id") == parent_id:
                    children = message.setdefault("childrenIds", [])
                    if assistant_msg_id not in children:
                        children.append(assistant_msg_id)
                    break

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
                "childrenIds": [],
            }
        history_entry["content"] = content
        history_entry["done"] = True
        history_entry.setdefault("childrenIds", [])
        history_messages[assistant_msg_id] = history_entry

        if parent_id:
            parent_history = history_messages.get(parent_id)
            if isinstance(parent_history, dict):
                children = parent_history.setdefault("childrenIds", [])
                if assistant_msg_id not in children:
                    children.append(assistant_msg_id)

        history["current_id"] = assistant_msg_id
        history["currentId"] = assistant_msg_id
        updated_chat["currentId"] = assistant_msg_id

        try:
            response = self._make_request("POST", f"/api/v1/chats/{chat_id}", {"chat": updated_chat})
            preview = json.dumps(response, indent=2)[:200] if isinstance(response, dict) else str(response)[:200]
            self._log(f"Chat update response: {preview}", "DETAIL")
            if isinstance(response, dict):
                updated_payload = response.get("chat")
                if isinstance(updated_payload, dict):
                    updated_payload.setdefault("history", {}).setdefault("messages", {})
                    return updated_payload
            self._log("Assistant content synchronized with chat state", "DETAIL")
            return updated_chat
        except Exception as sync_error:
            self._log(f"Failed to synchronize assistant content: {sync_error}", "WARNING")
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

    def step6_generate_test_artifacts(
        self,
        chat_id: str,
        user_message: str,
        assistant_response: str,
    ) -> List[Path]:
        """Create representative files that can be uploaded to OpenWebUI."""
        self._log("STEP 6: Generating test artifacts for upload validation...")

        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(exist_ok=True)

        timestamp_utc = datetime.now(timezone.utc)
        stamp = timestamp_utc.strftime("%Y%m%d_%H%M%S")
        session_stub = self.session_id.split("-")[0]
        prefix = f"openwebui_test_load_{stamp}_{session_stub}"

        assistant_preview = (assistant_response or "").strip()
        if len(assistant_preview) > 220:
            assistant_preview = assistant_preview[:220] + "…"

        iso_timestamp = timestamp_utc.isoformat()
        txt_path = artifacts_dir / f"{prefix}.txt"
        md_path = artifacts_dir / f"{prefix}.md"
        json_path = artifacts_dir / f"{prefix}.json"

        artifacts: List[Path] = []

        txt_lines = [
            "OpenWebUI verification test artifact",
            f"Generated: {iso_timestamp}",
            f"Base URL: {self.base_url}",
            f"Model: {self.model}",
            f"Chat ID: {chat_id}",
            f"Session ID: {self.session_id}",
            "",
            "This plain-text payload is produced by the automated backend flow test.",
            "Use it to confirm file uploads succeed within OpenWebUI.",
            "",
            "User message:",
            user_message,
        ]
        if assistant_preview:
            txt_lines.extend([
                "",
                "Assistant reply preview:",
                assistant_preview,
            ])
        txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
        artifacts.append(txt_path)
        self._log(
            f"  Created text artifact: {txt_path} ({txt_path.stat().st_size} bytes)",
            "SUCCESS",
        )

        md_lines = [
            "# OpenWebUI Test Artifact",
            "",
            f"- **Generated**: {iso_timestamp}",
            f"- **Base URL**: {self.base_url}",
            f"- **Model**: {self.model}",
            f"- **Chat ID**: {chat_id}",
            f"- **Session ID**: {self.session_id}",
            "",
            "## Scenario",
            "This Markdown file accompanies automated regression checks. Attach it to a knowledge collection to validate uploads.",
            "",
            "### User Prompt",
            "```",
            user_message,
            "```",
            "",
        ]
        if assistant_preview:
            md_lines.extend([
                "### Assistant Reply Preview",
                "```",
                assistant_preview,
                "```",
            ])
        else:
            md_lines.extend([
                "### Assistant Reply Preview",
                "_Not captured during this run._",
            ])
        md_content = "\n".join(md_lines) + "\n"
        md_path.write_text(md_content, encoding="utf-8")
        artifacts.append(md_path)
        self._log(
            f"  Created markdown artifact: {md_path} ({md_path.stat().st_size} bytes)",
            "SUCCESS",
        )

        json_payload = {
            "artifact": "openwebui-test",
            "generated_at": iso_timestamp,
            "session_id": self.session_id,
            "chat_id": chat_id,
            "model": self.model,
            "user_message": user_message,
            "assistant_preview": assistant_preview,
            "notes": "Use this JSON payload to exercise knowledge uploads in OpenWebUI.",
        }
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(json_payload, handle, indent=2)
            handle.write("\n")
        artifacts.append(json_path)
        self._log(
            f"  Created JSON artifact: {json_path} ({json_path.stat().st_size} bytes)",
            "SUCCESS",
        )

        self._log("Test artifacts ready in ./artifacts", "DETAIL")
        return artifacts

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
                        "models": [self.model],
                        "parentId": None,
                        "childrenIds": [],
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
                            "models": [self.model],
                            "parentId": None,
                            "childrenIds": [],
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
            "childrenIds": [],
        }

        updated_chat = json.loads(json.dumps(chat_payload))
        messages = updated_chat.setdefault("messages", [])
        messages.append(assistant_message)

        for message in messages:
            if message.get("id") == user_msg_id:
                children = message.setdefault("childrenIds", [])
                if assistant_msg_id not in children:
                    children.append(assistant_msg_id)
                break

        history = updated_chat.setdefault("history", {})
        history_messages = history.setdefault("messages", {})
        history_messages[assistant_msg_id] = dict(assistant_message)
        parent_entry = history_messages.get(user_msg_id)
        if isinstance(parent_entry, dict):
            children = parent_entry.setdefault("childrenIds", [])
            if assistant_msg_id not in children:
                children.append(assistant_msg_id)
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
            
        result = self._make_request(
            "POST", "/api/chat/completions", payload, timeout=180
        )
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
            task_ids = self._get_task_ids(chat_id)
            if task_ids:
                self._log(f"  Active tasks: {', '.join(task_ids)}", "DETAIL")
            else:
                self._log("  No active tasks reported", "DETAIL")

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
                synced_view = self._sync_assistant_content(chat_id, chat_view, assistant_msg_id, history_content)
                if isinstance(synced_view, dict):
                    chat_view = synced_view
                    messages = chat_view.get("messages", []) or []
                    for message in messages:
                        if (
                            message.get("id") == assistant_msg_id
                            and message.get("role") == "assistant"
                            and (message.get("content", "") or "").strip()
                        ):
                            self._log(f"Response ready after {attempt + 1} attempts", "SUCCESS")
                            return chat_view
                else:
                    self._log("Content sync returned unexpected payload", "WARNING")
            
            self._log(f"  Attempt {attempt + 1}/{max_attempts}: Waiting for response...")
            time.sleep(interval)
        self._log("Polling timed out; capturing final chat snapshot for analysis", "WARNING")
        self._save_chat_snapshot(chat_id)
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

            artifact_paths = self.step6_generate_test_artifacts(
                chat_id=chat_id,
                user_message=user_message,
                assistant_response=assistant_response,
            )

            if not artifact_paths:
                raise RuntimeError("No artifacts were generated for upload validation")

            publish_result = self.step7_publish_artifacts(
                chat_id=chat_id,
                artifact_paths=artifact_paths,
                user_message=user_message,
                assistant_response=assistant_response,
            )

            if isinstance(publish_result.get("chat"), dict):
                final_chat = publish_result["chat"]

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

            self._log("Artifacts generated for manual upload checks:", "DETAIL")
            for artifact in artifact_paths:
                self._log(f"  {artifact}", "DETAIL")
            self._log("Uploaded to knowledge collection:", "DETAIL")
            self._log(
                f"  Collection: {publish_result.get('knowledge_name')} "
                f"({publish_result.get('knowledge_id')})",
                "DETAIL",
            )
            self._log(f"  API: {publish_result.get('knowledge_api_url')}", "DETAIL")
            self._log(f"  UI:  {publish_result.get('knowledge_ui_url')}", "DETAIL")
            snapshot_path = publish_result.get("knowledge_snapshot")
            if snapshot_path:
                self._log(f"  Snapshot: {snapshot_path}", "DETAIL")
            for item in publish_result.get("uploads", []):
                status = (
                    item.get("processing", {}).get("status")
                    if isinstance(item.get("processing"), dict)
                    else None
                )
                self._log(
                    f"    ↳ {item.get('path')} → file_id={item.get('id')}"
                    + (f" (status: {status})" if status else ""),
                    "DETAIL",
                )

            # Optional: Test if chat is continuable
            if self.follow_up_enabled:
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
                "continuable": True,
                "artifacts": [str(path) for path in artifact_paths],
                "artifact_count": len(artifact_paths),
                "knowledge": publish_result,
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
