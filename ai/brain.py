"""Conversation brain: deterministic command routing plus local LLM reasoning."""

from __future__ import annotations

import re
from typing import Any

from core.config import ConfigManager
from core.events import EventBus
from core.logging import get_logger
from core.models import ChatMessage, EventType, RiskLevel, ToolRequest
from core.safety import EmergencyStop

from ai.memory import MemoryStore
from ai.ollama_client import OllamaClient, OllamaError
from ai.tools import ToolRegistry

SYSTEM_PROMPT = """You are Wednesday, a concise and capable personal AI assistant running locally on the user's Ubuntu laptop.
Be brief, useful and honest. Never claim an action succeeded unless a tool result confirmed it.
The user speaks naturally; interpret commands generously but ask for clarification when ambiguous.
Never reveal passwords, tokens or secrets. Default to local, private operation.

AVAILABLE COMPUTER ACTIONS
If the user explicitly asks you to PERFORM an action on the computer, reply with exactly one line:
ACTION: <tool_name> <json_arguments>
Example: ACTION: open_application {"name": "firefox"}
Valid tool names: get_system_status, get_time, open_application, open_project, close_window, search_web, take_screenshot, describe_screen, remember, recall, list_memories, forget, clear_memory, set_tracking, mouse_move, mouse_click, key_press, stop_speaking, go_to_sleep.
Use NO other tool name and never invent one. Do not put ACTION: in ordinary answers.

CRITICAL: For general knowledge, math, explanations, questions (including 'what is X', 'name X', 'how does X work'), or anything that does not require changing the computer, answer directly in plain text. NEVER output ACTION: for those. Only use ACTION: when the user clearly wants an action performed."""

LLM_ALLOWED_TOOLS = {
    "get_system_status", "get_time", "open_application", "open_project", "close_window",
    "search_web", "take_screenshot", "describe_screen", "remember", "recall",
    "list_memories", "forget", "clear_memory", "set_tracking", "mouse_move",
    "mouse_click", "key_press", "stop_speaking", "go_to_sleep",
}


class Brain:
    """Routes commands and produces assistant responses."""

    def __init__(
        self,
        config: ConfigManager,
        bus: EventBus,
        memory: MemoryStore,
        ollama: OllamaClient,
        tools: ToolRegistry,
    ) -> None:
        self._config = config
        self._bus = bus
        self._memory = memory
        self._ollama = ollama
        self._tools = tools
        self._log = get_logger("brain")
        self._history: list[ChatMessage] = []
        self._sleeping = False

    @property
    def sleeping(self) -> bool:
        return self._sleeping

    def set_sleeping(self, value: bool) -> None:
        self._sleeping = value
        self._bus.emit(EventType.STATUS, {"sleeping": value}, "brain")

    def reset_conversation(self) -> None:
        self._history.clear()

    def respond(self, text: str) -> str:
        """Process user text and return the assistant's reply."""
        text = text.strip()
        if not text:
            return "I did not catch that."

        self._memory.log_message("user", text)
        try:
            deterministic = self._deterministic(text)
            if deterministic is not None:
                reply = deterministic
            elif self._sleeping and not self._is_wake_phrase(text):
                return ""
            else:
                reply = self._reason(text)
        except EmergencyStop:
            reply = "Emergency stop is active. No actions were performed."
        except Exception as exc:
            self._log.exception("Response failed: %s", exc)
            reply = f"Something went wrong while processing that: {exc}"

        self._history.append(ChatMessage(role="assistant", content=reply))
        self._memory.log_message("assistant", reply)
        self._bus.emit(EventType.RESPONSE, {"text": reply}, "brain")
        return reply

    # ---- deterministic layer ------------------------------------------

    def _is_wake_phrase(self, text: str) -> bool:
        return bool(re.search(r"\b(wake up|wake (?:jarvis|wednesday)|i.m back)\b", text, re.IGNORECASE))

    def _deterministic(self, text: str) -> str | None:
        """Handle core commands without relying on LLM tool-calling accuracy."""
        low = text.lower().strip().rstrip(".")

        if self._is_wake_phrase(low):
            self.set_sleeping(False)
            return "I'm awake and listening."

        patterns: list[tuple[str, str, dict[str, Any] | None, RiskLevel]] = [
            (r"^(stop talking|shut up|be quiet|stop speaking)$", "stop_speaking", None, RiskLevel.LOW),
            (r"^(go to sleep|go to bed|sleep mode)$", "go_to_sleep", None, RiskLevel.LOW),
            (r"^(shut down|shutdown|quit|exit|close (?:jarvis|wednesday))( the assistant)?$", "shutdown_assistant", None, RiskLevel.LOW),
            (r"^(what time is it|what.s the time|the time)$", "get_time", None, RiskLevel.LOW),
            (
                r"^(?:(?:jarvis|wednesday)[, ]+)?(?:(?:check|show|get|report)\s+)?(?:system\s+status|my\s+(?:cpu|ram|memory|disk)(?:\s+usage)?|(?:cpu|ram|memory|disk)\s+(?:usage|status)|how much\s+(?:memory|ram))\??$",
                "get_system_status",
                None,
                RiskLevel.LOW,
            ),
            (r"^(take|get|capture) a? ?screenshot$", "take_screenshot", None, RiskLevel.LOW),
            (r"(what.s on (my |the )?screen|what am i looking at|explain (my |the )?screen|describe (my |the )?screen)", "describe_screen", {"question": text}, RiskLevel.LOW),
            (r"^(what do you remember|list (my )?memories|show (my )?memories)$", "list_memories", None, RiskLevel.LOW),
            (r"^clear (all )?(my )?memories$", "clear_memory", None, RiskLevel.LOW),
        ]
        for pattern, tool, args, risk in patterns:
            if re.search(pattern, low):
                return self._execute(tool, args or {}, risk)

        match = re.search(r"^(?:(?:jarvis|wednesday)[, ]+)?(?:open|launch|start)\s+(?:my\s+)?(.+?)(?:\s+project)?$", low)
        if match:
            target = re.sub(r"\b(please|for me|now|thanks|thank you)\b", "", match.group(1)).strip(" .,")
            if not target:
                return None
            if "project" in low:
                return self._execute("open_project", {"name": target})
            return self._execute("open_application", {"name": target})

        match = re.search(r"^(?:(?:jarvis|wednesday)[, ]+)?(?:search (?:the web|for)|google|look up)\s+(.+)$", low)
        if match:
            return self._execute("search_web", {"query": match.group(1).strip()})

        match = re.search(r"^remember (?:that )?(.+?)\s+(?:is|=|:)\s+(.+)$", low)
        if match:
            return self._execute("remember", {"key": match.group(1), "value": match.group(2)})

        match = re.search(r"^(?:forget|delete memory)\s+(.+)$", low)
        if match:
            return self._execute("forget", {"key": match.group(1)})

        match = re.search(r"^(?:recall|remind me about|what did (?:i|you) (?:tell|say|store about))\s+(.+)$", low)
        if match:
            return self._execute("recall", {"key": match.group(1)})

        match = re.search(r"(enable|turn on|start)\s+(head|gaze|eye)\s*(tracking|control)?", low)
        if match:
            mode = "head" if "head" in match.group(2) else "gaze"
            return self._execute("set_tracking", {"mode": mode, "enabled": True})
        match = re.search(r"(disable|turn off|stop)\s+(head|gaze|eye)\s*(tracking|control)?", low)
        if match:
            mode = "head" if "head" in match.group(2) else "gaze"
            return self._execute("set_tracking", {"mode": mode, "enabled": False})

        match = re.search(r"^move (?:the )?(?:mouse|cursor) to (\d+)\s*,?\s*(\d+)$", low)
        if match:
            return self._execute("mouse_move", {"x": int(match.group(1)), "y": int(match.group(2))}, RiskLevel.MEDIUM)
        if low in {"click", "left click", "right click"}:
            button = "right" if "right" in low else "left"
            return self._execute("mouse_click", {"button": button}, RiskLevel.MEDIUM)
        match = re.search(r"^press\s+([\w+]+)$", low)
        if match:
            return self._execute("key_press", {"keys": match.group(1)}, RiskLevel.MEDIUM)
        return None

    def _execute(self, tool: str, args: dict[str, Any], risk: RiskLevel = RiskLevel.LOW) -> str:
        result = self._tools.execute(ToolRequest(name=tool, arguments=args, risk=risk, reason="voice command"))
        return result.message

    # ---- LLM layer -----------------------------------------------------

    def _reason(self, text: str) -> str:
        """Reason with the local model using a validated text action protocol.

        Native Ollama tool-calling on llama3.2 was observed to hallucinate tool
        names and call apps for factual questions. A strict ACTION: line is
        parsed instead, and only whitelisted, known tools can execute.
        """
        if not self._ollama.is_available():
            return "The local AI server (Ollama) is not running, so I could only process direct commands."

        informational = bool(
            re.match(
                r"^(what is|what are|what does|why\b|how does|how do\b|explain|define|describe|who\b|when\b|where\b|compare)\b",
                text.strip(),
                re.IGNORECASE,
            )
        )
        system_prompt = self._system_prompt()
        if informational:
            system_prompt += "\n\nThis message is an informational question. Answer directly in plain text. Do NOT output ACTION:."
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(msg.to_ollama() for msg in self._history[-self._config.config.ai.max_history_messages :])
        messages.append({"role": "user", "content": text})

        try:
            response = self._ollama.chat(messages)
        except OllamaError as exc:
            self._log.warning("Ollama reasoning failed: %s", exc)
            return "I'm having trouble reaching my local AI model right now."

        content = self._ollama.extract_content(response)
        action = self._parse_action(content)
        if action is None:
            return content or "I understand, but I have no response to give."

        name, args = action
        result = self._tools.execute(ToolRequest(name=name, arguments=args, reason="AI action"))
        return result.message

    @staticmethod
    def _parse_action(content: str) -> tuple[str, dict[str, object]] | None:
        """Parse and validate an ACTION: line; ignore anything unrecognised."""
        import json
        import re

        match = re.search(r"^\s*ACTION:\s*([a-z_]+)\s*(\{.*\})\s*$", content, re.DOTALL)
        if match is None:
            return None
        name, raw_args = match.group(1), match.group(2)
        if name not in LLM_ALLOWED_TOOLS:
            return None
        try:
            parsed = json.loads(raw_args)
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        return name, parsed

    def _system_prompt(self) -> str:
        prompt = SYSTEM_PROMPT
        if self._config.config.memory.memory_enabled:
            lines = self._memory.context_lines(self._config.config.memory.max_context_items)
            if lines:
                prompt += "\n\nWhat I remember about the user:\n" + "\n".join(lines)
        return prompt
