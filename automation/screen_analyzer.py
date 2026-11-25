"""Optional screen awareness: capture, local OCR and AI explanation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from ai.ollama_client import OllamaClient, OllamaError
from automation.screenshot import ScreenshotService
from core.logging import get_logger


class ScreenAnalyzer:
    """Describe a captured screen using offline OCR plus the local LLM."""

    def __init__(self, screenshot: ScreenshotService, ollama: OllamaClient) -> None:
        self._screenshot = screenshot
        self._ollama = ollama
        self._log = get_logger("screen")
        self._ocr: Any | None = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr

    def analyse(self, question: str = "What is on the screen?") -> str:
        """Capture the screen, run OCR and let the local model explain the text."""
        success, path = self._screenshot.capture()
        if not success:
            return f"I could not capture the screen: {path}"

        try:
            engine = self._get_ocr()
            result, _elapsed = engine(path)
            texts: list[str] = []
            if result:
                for item in result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text = item[1]
                        if isinstance(text, str) and text.strip():
                            texts.append(text.strip())
            with Image.open(path) as image:
                size = f"{image.width}x{image.height}"
        except Exception as exc:
            self._log.warning("OCR failed: %s", exc)
            texts = []
            size = "unknown"

        visible = "\n".join(texts[:80]) or "(no text was detected)"
        if not self._ollama.is_available():
            return f"Screen capture saved to {path} ({size}). Local AI is unavailable, so I can only report the detected text:\n{visible}"

        messages = [
            {
                "role": "system",
                "content": "You describe what is visible on a computer screen using only the OCR text supplied. Do not invent details. Be concise.",
            },
            {
                "role": "user",
                "content": f"Question: {question}\nScreen resolution: {size}\nDetected text:\n{visible}",
            },
        ]
        try:
            response = self._ollama.chat(messages, retries=1)
            return self._ollama.extract_content(response) or f"Detected text:\n{visible}"
        except OllamaError as exc:
            return f"Screen saved to {path}. AI explanation failed ({exc}). Detected text:\n{visible}"
