from __future__ import annotations

import google.generativeai as genai

from jarvis.interfaces.illm import ILLM
from jarvis.implementations.llm.assistant_prompt_builder import AssistantPromptBuilder


class GeminiLLM(ILLM):
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._prompt_builder = AssistantPromptBuilder()

    def interpret(self, text: str) -> str:
        response = self._model.generate_content(
            self._prompt_builder.build(text),
            generation_config={"temperature": 0},
        )
        return response.text.strip()
