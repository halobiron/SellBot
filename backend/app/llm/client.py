from __future__ import annotations
import json
import re
import ssl
from typing import Iterator, Protocol
import httpx
from app.config import get_settings


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema_hint: str = "",
                      timeout: float | None = None, max_tokens: int | None = None,
                      reasoning_effort: str = "low") -> dict: ...
    def complete_text(self, system: str, user: str) -> str: ...
    def stream_text(self, system: str, user: str) -> Iterator[str]: ...


class DeepSeekClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 60.0, max_tokens: int = 4096,
                 json_endpoint: str = "responses", enable_thinking: bool | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.json_endpoint = json_endpoint
        self.enable_thinking = enable_thinking
        # Do not use ssl.create_default_context(): Python automatically honors
        # SSLKEYLOGFILE there. A stale/unwritable key-log path then prevents any
        # HTTPS request from being established. This context still uses the OS
        # trust store and requires valid server certificates.
        self._tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._tls_context.load_default_certs()

    def _http_client(self, timeout: float | None) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout if timeout is None else timeout,
            verify=self._tls_context,
        )

    def _post(self, messages: list[dict], timeout: float | None = None,
              max_tokens: int | None = None) -> str:
        # The client deliberately avoids response_format={"type":"json_object"}:
        # prompting plus _extract_json works across OpenAI-compatible gateways.
        # Reasoning-capable models may emit reasoning_content separately; it is ignored.
        payload = {"model": self.model, "messages": messages,
                   "temperature": 0.2, "max_tokens": self.max_tokens if max_tokens is None else max_tokens}
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with self._http_client(timeout) as c:
            r = c.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(
                    "LLM trả về content rỗng. Kiểm tra endpoint/model, "
                    "hoặc tăng max_tokens nếu reasoning model dùng hết token.")
            return content

    @staticmethod
    def _response_output_text(response: dict) -> str:
        """Read all visible text blocks from a B.AI/OpenAI Responses response."""
        parts: list[str] = []
        for item in response.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "output_text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts)

    def _post_responses_json(self, instructions: str, user: str, timeout: float | None,
                             max_tokens: int | None, reasoning_effort: str) -> str:
        """Use B.AI's Responses API for structured, low-reasoning JSON work.

        The Chat Completions compatibility endpoint can return a completed
        DeepSeek reasoning turn with `content: null`. Responses exposes a
        supported reasoning-effort control and separates reasoning from visible
        message text, which is the appropriate API for agent JSON calls.
        """
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": user}],
            "max_output_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "reasoning": {"effort": reasoning_effort},
            # Enforced by the provider, rather than relying on a prompt-only
            # request for JSON that can be malformed by a natural-language model.
            "text": {"format": {"type": "json_object"}},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with self._http_client(timeout) as c:
            r = c.post(f"{self.base_url}/responses", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        text = self._response_output_text(data)
        if text.strip():
            return text
        usage = data.get("usage") or {}
        reasoning_tokens = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
        raise ValueError(
            "LLM Responses không có visible text "
            f"(status={data.get('status')!r}, reasoning_tokens={reasoning_tokens!r}).")

    @staticmethod
    def _extract_json(raw: str) -> dict:
        raw = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence:
            raw = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", raw, re.DOTALL)
            if brace:
                raw = brace.group(0)
        return json.loads(raw)

    def complete_json(self, system: str, user: str, schema_hint: str = "",
                      timeout: float | None = None, max_tokens: int | None = None,
                      reasoning_effort: str = "low") -> dict:
        sys = system + ("\n\nCHỈ trả về một object JSON hợp lệ, không kèm giải thích hay văn bản thừa."
                        + (f" Schema:\n{schema_hint}" if schema_hint else ""))
        if self.json_endpoint == "chat_completions":
            return self._extract_json(self._post(
                [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                timeout=timeout, max_tokens=max_tokens,
            ))
        return self._extract_json(
            self._post_responses_json(sys, user, timeout, max_tokens, reasoning_effort))

    def complete_text(self, system: str, user: str) -> str:
        return self._post(
            [{"role": "system", "content": system}, {"role": "user", "content": user}])

    def stream_text(self, system: str, user: str) -> Iterator[str]:
        # SSE stream (stream:true). Yields only `content` tokens — reasoning models
        # also emit `reasoning_content` deltas, which we intentionally skip.
        payload = {"model": self.model,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}],
                   "temperature": 0.2, "max_tokens": self.max_tokens, "stream": True}
        if self.enable_thinking is not None:
            payload["enable_thinking"] = self.enable_thinking
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout) as c:
            with c.stream("POST", f"{self.base_url}/chat/completions",
                          json=payload, headers=headers) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices") or []
                    if not choices:
                        continue
                    token = (choices[0].get("delta") or {}).get("content")
                    if token:
                        yield token


class FakeLLM:
    def __init__(self, json_responses: list[dict] | None = None, text_responses: list[str] | None = None):
        self._json = list(json_responses or [])
        self._text = list(text_responses or [])
        self.calls: list[tuple[str, str]] = []
        self.json_options: list[dict] = []

    def complete_json(self, system: str, user: str, schema_hint: str = "",
                      timeout: float | None = None, max_tokens: int | None = None,
                      reasoning_effort: str = "low") -> dict:
        self.calls.append((system, user))
        self.json_options.append({"timeout": timeout, "max_tokens": max_tokens,
                                  "reasoning_effort": reasoning_effort})
        return self._json.pop(0) if self._json else {}

    def complete_text(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._text.pop(0) if self._text else ""

    def stream_text(self, system: str, user: str) -> Iterator[str]:
        # Yields the canned text in small slices to exercise line-buffering in callers.
        text = self.complete_text(system, user)
        for i in range(0, len(text), 10):
            yield text[i:i + 10]


def get_llm() -> LLMClient:
    s = get_settings()
    return DeepSeekClient(s.llm_base_url, s.llm_api_key, s.llm_model,
                          json_endpoint=s.llm_json_endpoint,
                          enable_thinking=s.llm_enable_thinking)
