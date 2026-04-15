from __future__ import annotations


class AssistantPromptBuilder:
    def build(self, text: str) -> str:
        return (
            "You are Jarvis, an intelligent AI assistant.\n"
            "Respond in a concise, polite, and slightly formal tone.\n"
            "Keep responses short and clear.\n\n"
            f"User request: {text}"
        )
