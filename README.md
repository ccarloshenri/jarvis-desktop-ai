<div align="center">

# Jarvis

**Assistente pessoal de voz para Windows. Fala, interpreta com IA, executa no seu PC e responde de volta.**

[![Build Windows EXE](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml)
[![Latest Release](https://img.shields.io/github/v/release/ccarloshenri/jarvis-desktop-ai?label=download)](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## Download

1. Acesse a pagina de [**Releases**](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest).
2. Baixe `Jarvis-Windows.zip`.
3. Extraia em qualquer pasta.
4. Execute **`Jarvis.exe`**.

Nao precisa instalar Python, configurar variavel de ambiente nem editar arquivo nenhum.

Na primeira execucao, o Jarvis abre uma tela pra voce escolher o provedor de IA e colar sua chave. Tudo pela interface.

| Provedor | Custo |
|---|---|
| **Google Gemini** (recomendado) | Gratis — [pegar chave](https://aistudio.google.com/apikey) |
| OpenAI GPT | Pago — [pegar chave](https://platform.openai.com/api-keys) |
| Anthropic Claude | Pago — [pegar chave](https://console.anthropic.com/settings/keys) |
| Modo Offline | Gratis (comandos basicos) |

Voce pode trocar de provedor a qualquer momento clicando no botao de engrenagem na interface.

---

## Como usar

Fale **"Jarvis"** seguido do que voce quer:

| Voce fala | O que acontece |
|---|---|
| "Jarvis, abre o Spotify" | Abre o Spotify desktop |
| "Jarvis, toca Coldplay" | Pesquisa e toca no Spotify |
| "Jarvis, manda um oi pro Renan" | Abre DM no Discord e envia |
| "Jarvis, abre o GitHub" | Abre github.com no navegador |
| "Jarvis, pesquisa o que e BPMN" | Abre busca no Google |
| "Jarvis, abre meu email" | Abre Gmail no navegador |
| "Jarvis, procura email do Joao" | Filtra emails no Gmail |
| "Jarvis, muta" | Muta mic no Discord |
| "Jarvis, que dia e hoje?" | Responde por voz com a data |
| "Jarvis, fecha essa aba" | Fecha a aba ativa do navegador |

O "Jarvis" antes e obrigatorio — sem ele, o assistente ignora a frase.

---

## Funcionalidades

**Conversa com IA** — perguntas em linguagem natural, contexto entre turnos, referencias implicitas ("ele", "isso", "aquela musica").

**Discord** — mandar mensagem por nome ou pronome, abrir DM/servidor/canal, entrar/sair de call, mutar/ensurdecer.

**Navegacao Web** — abrir 30+ sites por nome, pesquisar no Google/YouTube/imagens/noticias, gerenciar abas, filtrar emails no Gmail.

**Apps e Midia** — abrir e fechar qualquer app instalado, tocar musica no Spotify por voz.

**Voz** — reconhecimento de fala (Google Speech), sintese neural offline (Piper) com fallback SAPI5, responde antes de executar.

---

## Para desenvolvedores

```bash
git clone https://github.com/ccarloshenri/jarvis-desktop-ai.git
cd jarvis-desktop-ai
pip install -r requirements.txt
python -m app.main
```

```bash
pytest
```

### Build do executavel

```powershell
pip install -r requirements-build.txt
.\scripts\build_windows.ps1 -Clean
```

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
- [ ] Lembretes e tarefas
- [ ] Memoria persistente entre sessoes
- [ ] TTS streaming
- [ ] Linux e macOS

---

## Contribuindo

Pull requests sao bem-vindos. Pra mudancas grandes, abra uma issue antes.

## Licenca

[MIT](LICENSE)
