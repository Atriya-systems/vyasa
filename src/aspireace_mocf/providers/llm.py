from __future__ import annotations

import json
from typing import Any
from openai import OpenAI
from aspireace_mocf.settings import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.provider == "lmstudio":
            self.client = OpenAI(base_url=settings.lmstudio_base_url, api_key=settings.lmstudio_api_key)
        elif settings.provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is missing")
            self.client = OpenAI(base_url=settings.openai_base_url, api_key=settings.openai_api_key)
        else:
            raise ValueError(f"Unsupported provider: {settings.provider}")

    def chat_json(self, prompt: str, schema: dict[str, Any] | None = None, *, temperature: float | None = None, max_tokens: int | None = None) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No markdown. No prose outside JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": self.settings.max_tokens if max_tokens is None else max_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_response", "schema": schema, "strict": True},
            }
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception:
            kwargs.pop("response_format", None)
            response = self.client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        return json.loads(strip_json_fences(text))


def strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text
