from __future__ import annotations

import re

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.icommand_interpreter import ICommandInterpreter
from jarvis.utils.llm_response_parser import LLMResponseParser


class RuleBasedCommandInterpreter(ICommandInterpreter):
    def __init__(self) -> None:
        self._parser = LLMResponseParser()

    def interpret(self, text: str) -> dict[str, str] | None:
        cleaned = text.strip().lower()
        cleaned = re.sub(r"^jarvis[,\s]+", "", cleaned)
        cleaned = re.sub(r"\bplease\b", "", cleaned).strip()

        open_match = re.search(r"\b(open|start|launch)\s+(.+)$", cleaned)
        if open_match:
            return self._parser.normalize_payload(
                {"action": ActionType.OPEN_APP.value, "target": self._clean_target(open_match.group(2))}
            )

        close_match = re.search(r"\b(close|stop|quit|exit)\s+(.+)$", cleaned)
        if close_match:
            return self._parser.normalize_payload(
                {"action": ActionType.CLOSE_APP.value, "target": self._clean_target(close_match.group(2))}
            )
        return None

    def _clean_target(self, target: str) -> str:
        value = re.sub(r"\b(app|application|program)\b", "", target)
        value = re.sub(r"[^\w\s\-.]", "", value)
        return re.sub(r"\s+", " ", value).strip().lower()
