from __future__ import annotations

from anthropic import Anthropic

from jarvis.interfaces.illm import ILLM
from jarvis.implementations.llm.assistant_prompt_builder import AssistantPromptBuilder


class ClaudeLLM(ILLM):
    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-latest") -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._prompt_builder = AssistantPromptBuilder()

    def interpret(self, text: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            temperature=0,
            messages=[{"role": "user", "content": self._prompt_builder.build(text)}],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "\n".join(text_blocks).strip()
