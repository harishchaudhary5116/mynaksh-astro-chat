"""Google Gemini implementation of LLMClient.

Model routing: LLM_EXTRACTION_MODEL (flash-lite, cheap) pulls facts out of a
message; LLM_CHAT_MODEL (flash) writes the reply. Extraction uses Gemini's
structured-output mode so the JSON is schema-valid without parsing tricks.

Called over plain REST with httpx, which is already a dependency. The Gemini
SDK would add a package for roughly forty lines of HTTP, and the whole point
of LLMClient is that this file is small enough to replace.

One provider quirk is contained here: Gemini's `responseSchema` has no
`additionalProperties`, so it cannot express a free-form string map. The
`attributes` map therefore travels as a key/value array and is folded back
into a dict before it leaves this class. The rest of the app never learns
that this happened.
"""
import logging
from typing import Any

import httpx

from ..config import Settings
from .base import LLMClient, LLMError

log = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 30.0

# Gemini wants OpenAPI-style upper-case type names.
_TYPES = {"object": "OBJECT", "array": "ARRAY", "string": "STRING",
          "number": "NUMBER", "integer": "INTEGER", "boolean": "BOOLEAN"}

_KEY_VALUE_ITEM = {
    "type": "OBJECT",
    "properties": {"key": {"type": "STRING"}, "value": {"type": "STRING"}},
    "required": ["key", "value"],
}


def _base_type(node: dict[str, Any]) -> str | None:
    """JSON Schema allows ["string", "null"]; Gemini wants one type + nullable."""
    declared = node.get("type")
    if isinstance(declared, list):
        return next((t for t in declared if t != "null"), None)
    return declared


def _is_free_form_map(node: dict[str, Any]) -> bool:
    return (
        _base_type(node) == "object"
        and "properties" not in node
        and "additionalProperties" in node
    )


def to_gemini_schema(node: Any) -> Any:
    """Translate canonical JSON Schema into what Gemini accepts."""
    if not isinstance(node, dict):
        return node
    if _is_free_form_map(node):
        return {"type": "ARRAY", "items": _KEY_VALUE_ITEM}

    out: dict[str, Any] = {}
    base = _base_type(node)
    if base:
        out["type"] = _TYPES.get(base, base.upper())
    if isinstance(node.get("type"), list) and "null" in node["type"]:
        out["nullable"] = True
    for passthrough in ("enum", "required"):
        if passthrough in node:
            out[passthrough] = node[passthrough]
    if "properties" in node:
        out["properties"] = {k: to_gemini_schema(v) for k, v in node["properties"].items()}
    if "items" in node:
        out["items"] = to_gemini_schema(node["items"])
    return out


def restore_maps(value: Any, node: Any) -> Any:
    """Undo `to_gemini_schema`: fold key/value arrays back into dicts."""
    if not isinstance(node, dict):
        return value
    if _is_free_form_map(node):
        if isinstance(value, list):
            return {
                item["key"]: item["value"]
                for item in value
                if isinstance(item, dict) and "key" in item and "value" in item
            }
        return value if isinstance(value, dict) else {}
    base = _base_type(node)
    if base == "object" and isinstance(value, dict):
        properties = node.get("properties", {})
        return {k: restore_maps(v, properties.get(k, {})) for k, v in value.items()}
    if base == "array" and isinstance(value, list):
        return [restore_maps(v, node.get("items", {})) for v in value]
    return value


class GeminiLLM(LLMClient):
    """One attempt per call; retries and fallbacks are the caller's policy."""

    def __init__(self, settings: Settings) -> None:
        if not settings.google_api_key:
            raise LLMError("GOOGLE_API_KEY is not set")
        self._key = settings.google_api_key
        self._chat_model = settings.llm_chat_model
        self._extraction_model = settings.llm_extraction_model

    # --------------------------------------------------------------------- chat

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [
                # Gemini calls the assistant "model"; everything else is "user".
                {"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]}
                for m in messages
            ],
        }
        return self._text(self._post(self._chat_model, body))

    # ------------------------------------------------------------------ extract

    def extract_json(
        self, system: str, user_text: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": to_gemini_schema(schema),
                "temperature": 0,  # extraction is not a creative task
            },
        }
        import json

        raw = self._text(self._post(self._extraction_model, body))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            # Structured output makes this near-impossible, but a malformed
            # payload must not take the user's reply down with it.
            raise LLMError(f"Gemini returned non-JSON: {raw[:120]}") from exc
        return restore_maps(payload, schema)

    # ---------------------------------------------------------------- internals

    def _post(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE_URL}/{model}:generateContent"
        try:
            # The key goes in a header, never in the query string: httpx logs
            # request URLs at INFO, so ?key=... would end up in the app logs
            # (and in any proxy or APM in front of it).
            response = httpx.post(
                url,
                headers={"x-goog-api-key": self._key},
                json=body,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200]
            log.warning("Gemini %s returned %s: %s", model, exc.response.status_code, detail)
            raise LLMError(f"Gemini HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini unreachable: {exc}") from exc

    @staticmethod
    def _text(payload: dict[str, Any]) -> str:
        """Pull the text out, and treat a blocked or empty response as a failure."""
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError) as exc:
            reason = payload.get("promptFeedback", {}).get("blockReason")
            raise LLMError(f"Gemini returned no usable candidate (reason={reason})") from exc
        if not text:
            raise LLMError("Gemini returned an empty response")
        return text
