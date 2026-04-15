from __future__ import annotations

DEFAULT_LANGUAGE = "pt-BR"

_STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "window_title": "Jarvis",
        "title": "JARVIS",
        "subtitle": "assistente pessoal",
        "response_idle": "Sistema online.",
        "system_online": "Sistema online. Em que posso ajudar, senhor?",
        "debug_user_prefix": "você",
        "debug_jarvis_prefix": "jarvis",
        "ready": "Pronto",
        "listening": "Ouvindo",
        "processing": "Processando",
        "empty_transcript": "Não consegui entender o pedido, senhor.",
        "could_not_catch": "Não consegui ouvir, senhor.",
        "command_ok": "Entendido, senhor.",
        "command_not_found": "Aplicativo não encontrado, senhor.",
        "ack_open_app": "Abrindo {target}, senhor.",
        "ack_close_app": "Fechando {target}, senhor.",
        "ack_play_spotify": "Tocando {target} no Spotify, senhor.",
        "ack_search_web": "Pesquisando {target}, senhor.",
        "no_response": "Não tenho uma resposta para isso agora, senhor.",
        "date_answer": "Hoje é {date}, senhor.",
        "time_answer": "Agora são {time}, senhor.",
        "weather_unavailable": "Não consigo verificar o clima sem acesso à internet, senhor.",
        "greeting": "Olá, senhor. Em que posso ajudar?",
        "how_are_you": "Estou funcional e pronto para servir, senhor.",
        "who_are_you": "Sou o Jarvis, seu assistente pessoal de desktop, senhor.",
        "thanks": "Às ordens, senhor.",
        "goodbye": "Até logo, senhor.",
        "help": "Posso abrir e fechar aplicativos, informar a hora, a data e responder perguntas, senhor.",
        "joke": "Por que o programador confundiu Halloween com Natal? Porque 31 OCT é igual a 25 DEC, senhor.",
        "fallback_unknown": "Às ordens, senhor.",
    },
    "en-US": {
        "window_title": "Jarvis",
        "title": "JARVIS",
        "subtitle": "personal assistant",
        "response_idle": "System online.",
        "system_online": "System online. How may I assist you, sir?",
        "debug_user_prefix": "you",
        "debug_jarvis_prefix": "jarvis",
        "ready": "Ready",
        "listening": "Listening",
        "processing": "Processing",
        "empty_transcript": "I could not understand the request, sir.",
        "could_not_catch": "I couldn't catch that, sir.",
        "command_ok": "Understood, sir.",
        "command_not_found": "Application not found, sir.",
        "ack_open_app": "Opening {target}, sir.",
        "ack_close_app": "Closing {target}, sir.",
        "ack_play_spotify": "Playing {target} on Spotify, sir.",
        "ack_search_web": "Searching {target}, sir.",
        "no_response": "I do not have a response for that right now, sir.",
        "date_answer": "Today is {date}, sir.",
        "time_answer": "It is currently {time}, sir.",
        "weather_unavailable": "I cannot check weather without internet access, sir.",
        "greeting": "Hello, sir. How can I help you?",
        "how_are_you": "I am functional and ready to serve, sir.",
        "who_are_you": "I am Jarvis, your personal desktop assistant, sir.",
        "thanks": "At your service, sir.",
        "goodbye": "Goodbye, sir.",
        "help": "I can open and close applications, tell the time and date, and answer questions, sir.",
        "joke": "Why did the programmer confuse Halloween with Christmas? Because 31 OCT equals 25 DEC, sir.",
        "fallback_unknown": "At your service, sir.",
    },
}


class Strings:
    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self._language = language if language in _STRINGS else DEFAULT_LANGUAGE

    @property
    def language(self) -> str:
        return self._language

    def get(self, key: str, **kwargs: str) -> str:
        template = _STRINGS[self._language].get(key) or _STRINGS[DEFAULT_LANGUAGE].get(key, key)
        return template.format(**kwargs) if kwargs else template
