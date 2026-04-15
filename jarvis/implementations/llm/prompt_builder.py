from __future__ import annotations


class IntentPromptBuilder:
    def build(self, text: str) -> str:
        return (
            "You are an intent extraction system for a desktop assistant.\n"
            "Return only valid JSON with this exact schema:\n"
            '{"action":"open_app"|"close_app","target":"app_name"}\n\n'
            f"User request: {text}"
        )
