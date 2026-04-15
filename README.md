<div align="center">

# Jarvis Desktop AI

**Um assistente de voz para Windows com HUD animado, múltiplos provedores de LLM e comandos do sistema.**

[![Build Windows EXE](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml)
[![Latest Release](https://img.shields.io/github/v/release/ccarloshenri/jarvis-desktop-ai?label=download)](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## Download

### Windows (recomendado)

1. Acesse a página de [**Releases**](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest).
2. Baixe `Jarvis-Windows.zip`.
3. Extraia o arquivo em qualquer pasta.
4. Dê duplo clique em **`Jarvis.exe`**.

> Não precisa instalar Python, nem rodar comandos no terminal.

---

## Configuração das chaves de API (opcional)

O Jarvis funciona em modo offline por padrão. Para habilitar provedores de LLM na nuvem:

1. Na pasta extraída, copie `.env.example` para `.env`.
2. Edite `.env` e preencha as chaves que quiser usar:

```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

3. Reabra o `Jarvis.exe`.

---

## Recursos

- Assistente de voz com HUD animado em PySide6
- Reconhecimento de fala (speech-to-text)
- Síntese de voz offline (pyttsx3)
- Suporte a múltiplos provedores de LLM:
  - OpenAI (GPT)
  - Google (Gemini)
  - Anthropic (Claude)
  - Fallback baseado em regras (100% offline)
- Comandos do sistema: abrir e fechar aplicativos
- Áudios pré-gravados de inicialização e confirmação
- Logging estruturado
- Processamento de voz em thread dedicada

---

## Como usar

1. Abra o `Jarvis.exe` — você verá o HUD animado do Jarvis.
2. Aguarde o som de inicialização.
3. Fale seu comando naturalmente. Exemplos:
   - *"Abre o Chrome"*
   - *"Fecha o Spotify"*
   - *"Que horas são?"*
   - *"Me explica o que é inteligência artificial"*

---

## Para desenvolvedores

### Rodando a partir do código-fonte

```bash
git clone https://github.com/ccarloshenri/jarvis-desktop-ai.git
cd jarvis-desktop-ai

python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
python -m app.main
```

### Testes

```bash
pytest
```

### Build local do executável (Windows)

```powershell
.\scripts\build_windows.ps1 -Clean
```

O executável é gerado em `dist/Jarvis.exe`.

### Release automatizado

Todo push de tag `v*` dispara o workflow do GitHub Actions, que:

1. Roda os testes.
2. Empacota o `.exe` via PyInstaller.
3. Publica automaticamente em **Releases** com o `.zip` e o `.exe`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Arquitetura

```text
jarvis-desktop-ai/
├── app/                 # Entry point (main.py)
├── assets/              # Ícones e recursos visuais
├── speechs/             # Áudios pré-gravados
├── jarvis/
│   ├── models/          # Dataclasses puras
│   ├── interfaces/      # Contratos abstratos
│   ├── implementations/
│   │   ├── llm/         # GPT, Gemini, Claude, rule-based
│   │   ├── audio/
│   │   ├── speech/
│   │   ├── system/
│   │   └── tts/
│   ├── factories/       # ApplicationFactory, LLMFactory
│   ├── services/        # Orquestração
│   ├── ui/              # Qt / PySide6
│   ├── config/
│   ├── enums/
│   └── utils/
└── tests/
```

Princípios:

- `models/` — apenas dataclasses puras.
- `interfaces/` — apenas contratos abstratos.
- `implementations/` — integrações externas e comportamento concreto.
- `factories/` — criação e composição de objetos.
- `services/` — lógica de aplicação e orquestração.
- `ui/` — renderização e Qt event wiring.
- `enums/` — centraliza provedores e ações (sem magic strings).

---

## Contribuindo

Pull requests são bem-vindos. Para mudanças maiores, abra uma issue antes discutindo a proposta.

## Licença

[MIT](LICENSE)
