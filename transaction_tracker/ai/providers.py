from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from transaction_tracker.ai.config import AIConfig, load_ai_config


@dataclass
class ChatCompletionsProvider:
    config: AIConfig

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.api_key:
            raise RuntimeError("AI_API_KEY or AI_API_KEY_FILE must be configured")
        url = f"{self.config.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Budgify/0.1")
        req.add_header("Authorization", f"Bearer {self.config.api_key}")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            try:
                body_json = json.loads(body)
            except json.JSONDecodeError:
                body_json = None
            if isinstance(body_json, dict) and body_json.get("message"):
                body = str(body_json["message"])
            detail = f": {body}" if body else ""
            raise RuntimeError(f"AI provider returned HTTP {exc.code}{detail}") from exc

    def complete_response(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.config.model, "messages": messages}
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return self._post(payload)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self.complete_response(messages, tools=tools, tool_choice=tool_choice)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("AI provider returned no choices")
        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            raise RuntimeError("AI provider returned an invalid message")
        return message

    def generate(self, messages: list[dict[str, Any]]) -> str:
        message = self.complete(messages)
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise RuntimeError("AI provider returned non-text content")
        return content.strip()


class CerebrasProvider(ChatCompletionsProvider):
    pass


def get_chat_provider_from_env() -> ChatCompletionsProvider:
    config = load_ai_config()
    if config.provider == "cerebras":
        return CerebrasProvider(config)
    return ChatCompletionsProvider(config)
