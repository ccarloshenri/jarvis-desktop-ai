from __future__ import annotations

from openai import OpenAI

from jarvis.interfaces.illm import ILLM
from jarvis.implementations.llm.assistant_prompt_builder import AssistantPromptBuilder


class GPTLLM(ILLM):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._prompt_builder = AssistantPromptBuilder()

    def interpret(self, text: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=self._prompt_builder.build(text),
            temperature=0,
        )
        return response.output_text.strip()
