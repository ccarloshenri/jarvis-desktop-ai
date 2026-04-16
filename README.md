<div align="center">

# Jarvis

**Assistente pessoal de voz para Windows. Fala, interpreta com IA, executa no seu PC e responde de volta.**

[![Build Windows EXE](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml)
[![Latest Release](https://img.shields.io/github/v/release/ccarloshenri/jarvis-desktop-ai?label=download)](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-119%20passing-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<br>

[Download](#download) &bull; [Como usar](#como-usar) &bull; [Funcionalidades](#funcionalidades) &bull; [Para desenvolvedores](#para-desenvolvedores)

</div>

---

## Demo

> Em breve: gif/video demonstrando o Jarvis em acao.

---

## Download

### Windows (recomendado)

1. Acesse a pagina de [**Releases**](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest).
2. Baixe `Jarvis-Windows.zip`.
3. Extraia em qualquer pasta.
4. Execute **`Jarvis.exe`**.

Nao precisa instalar Python nem rodar comandos no terminal.

### Primeira execucao

Na primeira vez, o Jarvis abre um dialog pra voce escolher o provedor de IA:

| Provedor | O que precisa | Custo |
|---|---|---|
| **Google Gemini** (recomendado) | Chave de API do [AI Studio](https://aistudio.google.com/apikey) | Gratis (free tier generoso) |
| OpenAI GPT | Chave de API da [OpenAI](https://platform.openai.com/api-keys) | Pago (pay-per-use) |
| Anthropic Claude | Chave de API da [Anthropic](https://console.anthropic.com/settings/keys) | Pago |
| Modo Offline | Nada | Gratis (comandos basicos apenas) |

A chave e armazenada com seguranca no Windows Credential Manager. Voce pode trocar de provedor a qualquer momento pelo botao de engrenagem na interface.

---

## Como usar

Fale **"Jarvis"** seguido do que voce quer fazer:

```
"Jarvis, abre o Spotify"
"Jarvis, toca Coldplay"
"Jarvis, manda um oi pro Renan no Discord"
"Jarvis, abre o GitHub"
"Jarvis, pesquisa o que e BPMN"
"Jarvis, abre meu email"
"Jarvis, muta"
"Jarvis, que dia e hoje?"
"Jarvis, fecha essa aba"
```

O "Jarvis" no comeco e obrigatorio. Se voce nao falar, ele ignora a frase (pra nao responder conversa alheia).

---

## Funcionalidades

### Conversa com IA
- Perguntas em linguagem natural com resposta por voz
- Contexto conversacional entre turnos (lembra o que voce falou antes)
- Suporte a referencias implicitas: "ele", "isso", "aquela musica"

### Discord
- Mandar mensagem pra alguem: "manda um oi pro Renan"
- Abrir DM, servidor ou canal por nome
- Entrar/sair de calls de voz
- Mutar e ensurdecer
- Referencia por contexto: "manda pra ele: ja vou"

### Navegacao Web
- Abrir 30+ sites por nome: GitHub, Gmail, YouTube, LinkedIn, WhatsApp, Netflix, etc.
- Pesquisar no Google, YouTube, imagens e noticias
- Gerenciar abas: nova, fechar, trocar, voltar, avancar, recarregar
- Email: abrir inbox, filtrar nao-lidos, buscar por remetente ou assunto

### Apps e Midia
- Abrir e fechar qualquer aplicativo instalado
- Tocar musica no Spotify por voz
- Pesquisar na web

### Voz
- Reconhecimento de fala (Google Speech) em portugues e ingles
- Sintese de voz neural offline (Piper) com fallback pra SAPI5
- O Jarvis fala antes de executar, pra voce saber que entendeu

---

## Arquitetura

```text
jarvis-desktop-ai/
├── app/                     # Entry point
├── jarvis/
│   ├── apps/                # Integracoes de apps (pattern BaseApp)
│   │   ├── browser/         # BrowserApp: navegacao, busca, email
│   │   └── discord/         # DiscordApp: mensagens, voz, navegacao
│   ├── models/              # Dataclasses puras (Command, ChatTurn, etc.)
│   ├── interfaces/          # Contratos abstratos (ILLM, ISpeechToText, etc.)
│   ├── implementations/
│   │   ├── llm/             # GPT, Gemini, Claude, Ollama, Fallback, rule-based
│   │   ├── speech/          # Google STT
│   │   ├── system/          # SystemActionExecutor, WindowsApplicationFinder
│   │   └── tts/             # SAPI5 fallback
│   ├── factories/           # ApplicationFactory, LLMFactory
│   ├── services/            # AssistantService, ConversationMemory, VoiceService
│   ├── ui/                  # PySide6: MainWindow, orbe animado, worker thread
│   ├── config/              # Strings (i18n), SettingsLoader
│   └── enums/               # ActionType, LLMProvider
└── tests/                   # 119 testes automatizados
```

### Principios

- **`models/`** — dataclasses puras, sem logica.
- **`interfaces/`** — contratos abstratos. Nenhuma implementacao.
- **`apps/`** — cada integracao (Discord, browser) e um `BaseApp` com facade + context + services.
- **`implementations/`** — codigo concreto que toca o mundo externo.
- **`services/`** — orquestracao. `AssistantService` e o coracao: wake word gate -> rule-based -> LLM -> executor -> TTS.
- **`factories/`** — montagem e injecao de dependencias.
- **`ui/`** — renderizacao Qt e event wiring. Zero logica de negocio.

### Fluxo de um comando

```
Fala -> STT -> Wake word gate -> Strip "Jarvis"
  -> Rule-based match? -> Sim: Command -> Executor -> TTS ack (paralelo)
  -> Nao: LLM decide -> action ou chat
       -> action: Command -> Executor -> TTS ack
       -> chat: TTS fala a resposta
  -> Grava no ConversationMemory
```

---

## Para desenvolvedores

### Rodando a partir do codigo-fonte

```bash
git clone https://github.com/ccarloshenri/jarvis-desktop-ai.git
cd jarvis-desktop-ai

python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt

cp .env.example .env           # edite com suas chaves

python -m app.main
```

### Testes

```bash
pytest
```

### Build do executavel

```powershell
pip install -r requirements-build.txt
.\scripts\build_windows.ps1 -Clean
```

Gera `dist/Jarvis.exe`.

### Release automatizado

Push de tag `v*` dispara GitHub Actions: roda testes, empacota com PyInstaller, publica em Releases.

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Roadmap

- [ ] STT local (Whisper) pra funcionar sem internet
- [ ] Gmail API pra ler e resumir emails
- [ ] Discord RPC pra status e voz sem roubar foco
- [ ] Lembretes e tarefas com agenda
- [ ] Memoria persistente entre sessoes
- [ ] TTS streaming (falar enquanto gera)
- [ ] Suporte a Linux e macOS

---

## Contribuindo

Pull requests sao bem-vindos. Pra mudancas grandes, abra uma issue antes discutindo a proposta.

## Licenca

[MIT](LICENSE)
