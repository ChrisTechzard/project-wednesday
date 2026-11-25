"""Resilient HTTP client for a local Ollama server."""

from __future__ import annotations

import time
from typing import Any

import requests

from core.config import AIConfig
from core.logging import get_logger


class OllamaError(RuntimeError):
    """Raised when Ollama cannot be reached or returns an invalid response."""


class OllamaClient:
    """Thin typed wrapper around the Ollama REST API."""

    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._log = get_logger("ollama")

    def is_available(self) -> bool:
        """Return True when the Ollama server responds."""
        try:
            response = self._session.get(f"{self._config.ollama_host}/api/tags", timeout=3)
            return response.ok
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """List locally installed model names."""
        try:
            response = self._session.get(f"{self._config.ollama_host}/api/tags", timeout=10)
            response.raise_for_status()
            return [str(model["name"]) for model in response.json().get("models", [])]
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise OllamaError(f"Could not list Ollama models: {exc}") from exc

    def ensure_model(self, model: str | None = None) -> str:
        """Return the configured model if installed, otherwise the first available one."""
        target = model or self._config.model
        models = self.list_models()
        if not models:
            raise OllamaError("No Ollama models are installed.")
        if any(target == name or target.split(":")[0] == name.split(":")[0] for name in models):
            return target
        self._log.warning("Model %s not found; falling back to %s", target, models[0])
        return models[0]

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        """Send a chat request and return the parsed message object.

        Retries transient connection failures with exponential backoff. All
        callers must handle OllamaError rather than assuming a response.
        """
        model = self.ensure_model()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "num_ctx": 8192,
            },
        }
        if tools:
            payload["tools"] = tools

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._session.post(
                    f"{self._config.ollama_host}/api/chat",
                    json=payload,
                    timeout=self._config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or "message" not in data:
                    raise OllamaError("Ollama returned an unexpected response shape.")
                return dict(data["message"])
            except (requests.RequestException, ValueError, OllamaError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.5 * (2**attempt))
        raise OllamaError(f"Ollama request failed after {retries + 1} attempts: {last_error}")

    @staticmethod
    def extract_content(message: dict[str, Any]) -> str:
        """Safely extract assistant text from an Ollama message."""
        content = message.get("content", "")
        return content.strip() if isinstance(content, str) else ""
