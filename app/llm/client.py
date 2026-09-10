from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class CacheMiss(LLMError):
    """Offline mode and this prompt isn't cached."""


def cache_key(model: str, messages: list[dict]) -> str:
    blob = json.dumps({"model": model, "messages": messages}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def _clean(raw: str) -> str:
    """Strip markdown fences some models wrap around JSON."""
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


class LLMClient:
    """OpenAI-compatible chat client with a disk cache.

    - Any /chat/completions provider works: set base_url + model + key.
    - Responses cache by (model, messages): same metadata = same answer,
      free and instant. Cache = deterministic demos + zero-internet replay.
    - METADATA ONLY: callers must only put schema metadata in messages.
    """

    def __init__(self):
        s = get_settings()
        self.model = s.llm_model
        self.base_url = s.llm_base_url.rstrip("/")
        self.api_key = s.llm_api_key
        self.offline = s.llm_offline or not s.llm_api_key
        self.timeout = s.llm_timeout_s
        self.cache_dir = Path(s.llm_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.cache_hits = 0

    def chat_json(self, messages: list[dict], schema: type[T]) -> tuple[T, bool, int]:
        """Returns (parsed, from_cache, latency_ms). Raises LLMError on failure."""
        key = cache_key(self.model, messages)
        cached = self._read_cache(key)
        if cached is not None:
            self.cache_hits += 1
            return schema.model_validate_json(cached), True, 0
        if self.offline:
            raise CacheMiss(
                f"offline mode: no cached response for this prompt (model={self.model}). "
                f"Re-run prewarm with a live key, or set ATLAS_LLM_OFFLINE=0."
            )
        t0 = time.monotonic()
        raw = self._call_api(messages, json_mode=True)
        try:
            parsed = schema.model_validate_json(_clean(raw))
        except Exception:
            raw = self._call_api(
                messages
                + [
                    {
                        "role": "user",
                        "content": "Your previous reply was not valid JSON for the "
                        "requested schema. Reply again with ONLY the JSON object.",
                    }
                ],
                json_mode=True,
            )
            parsed = schema.model_validate_json(_clean(raw))  # raises if still bad
        latency = int((time.monotonic() - t0) * 1000)
        self._write_cache(key, _clean(raw))
        return parsed, False, latency

    def _call_api(self, messages: list[dict], json_mode: bool) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {"model": self.model, "messages": messages, "temperature": 0.1}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = f"{self.base_url}/chat/completions"
        try:
            self.calls += 1
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, headers=headers, json=body)
            if r.status_code == 400 and "response_format" in r.text:
                body.pop("response_format", None)  # provider without JSON mode
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise LLMError(f"LLM request failed ({url}): {e}") from e

    def _read_cache(self, key: str) -> str | None:
        p = self.cache_dir / f"{key}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["response"]

    def _write_cache(self, key: str, response: str) -> None:
        p = self.cache_dir / f"{key}.json"
        p.write_text(
            json.dumps(
                {"model": self.model, "response": response, "cached_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
