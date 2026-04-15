from __future__ import annotations

import json
import re
from datetime import datetime

from jarvis.models.llm_decision import LLMDecision


def build_user_message(text: str, now: datetime | None = None) -> str:
    """Prepend current date/time context so the LLM can answer time-sensitive questions."""
    current = now or datetime.now()
    context = f"[Data atual: {current:%Y-%m-%d}. Hora atual: {current:%H:%M}.]"
    return f"{context}\n{text.strip()}"

DECISION_SYSTEM_PROMPT = """Você é o Jarvis, um assistente pessoal em português.

Sua única tarefa é ler a fala do usuário e devolver UM objeto JSON válido no formato exato:
{
  "type": "action" | "chat",
  "app": string | null,
  "action": string | null,
  "parameters": object,
  "spoken_response": string
}

Regras:
- Use "action" apenas quando o usuário pedir para executar algo no computador.
- Use "chat" para conversa, perguntas, saudações ou qualquer coisa que não seja uma ação executável.
- Ações permitidas (campo "action"):
  * "open_app"     -> abrir um aplicativo.      app = nome do app. parameters = {"target": "<nome>"}
  * "close_app"    -> fechar um aplicativo.     app = nome do app. parameters = {"target": "<nome>"}
  * "play_spotify" -> tocar algo no Spotify.    app = "spotify".   parameters = {"target": "<musica ou artista>"}
  * "search_web"   -> pesquisar na internet.    app = "browser".   parameters = {"target": "<consulta>"}
- Em "chat", use app=null, action=null, parameters={}.
- "spoken_response" deve ser curto, natural e em português, como alguém falando.
- NUNCA escreva nada fora do JSON. Sem comentários, sem markdown, sem ```json.

Exemplos:

Usuário: "abre o spotify"
{"type":"action","app":"spotify","action":"open_app","parameters":{"target":"spotify"},"spoken_response":"Abrindo o Spotify."}

Usuário: "toca uma musica do coldplay"
{"type":"action","app":"spotify","action":"play_spotify","parameters":{"target":"coldplay"},"spoken_response":"Tocando Coldplay no Spotify."}

Usuário: "pesquisa receita de bolo de cenoura"
{"type":"action","app":"browser","action":"search_web","parameters":{"target":"receita de bolo de cenoura"},"spoken_response":"Pesquisando receita de bolo de cenoura."}

Usuário: "bom dia jarvis"
{"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"Bom dia! Como posso ajudar?"}

Usuário: "quem descobriu o brasil"
{"type":"chat","app":null,"action":null,"parameters":{},"spoken_response":"A chegada dos portugueses ao Brasil em 1500 é atribuída a Pedro Álvares Cabral."}
"""


def parse_decision(raw: str) -> LLMDecision | None:
    if not raw:
        return None
    candidate = raw.strip()
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if match:
        candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    decision_type = str(data.get("type", "chat")).strip().lower()
    if decision_type not in ("action", "chat"):
        decision_type = "chat"

    spoken = str(data.get("spoken_response") or "").strip()
    if not spoken:
        return None

    app_value = data.get("app")
    app = str(app_value).strip().lower() if isinstance(app_value, str) and app_value.strip() else None

    action_value = data.get("action")
    action = str(action_value).strip().lower() if isinstance(action_value, str) and action_value.strip() else None

    parameters_value = data.get("parameters")
    parameters = parameters_value if isinstance(parameters_value, dict) else {}

    if decision_type == "action" and not action:
        decision_type = "chat"

    return LLMDecision(
        type=decision_type,  # type: ignore[arg-type]
        spoken_response=spoken,
        app=app,
        action=action,
        parameters=parameters,
    )
