# Jarvis v1.0 — Assistente Pessoal Inteligente para Desktop

O Jarvis chegou na v1.0. Assistente de voz para Windows que entende o que voce fala, interpreta com IA, executa no seu computador e responde de volta.

---

## Sobre o Jarvis

O Jarvis e um assistente pessoal que roda no seu desktop e funciona por voz. Voce fala naturalmente o que quer fazer, e ele interpreta, executa e responde.

O problema que ele resolve: voce nao precisa sair do que esta fazendo pra abrir um app, mandar uma mensagem, pesquisar algo ou trocar de aba. Fala com o Jarvis e ele faz.

Funciona com IA na nuvem (Google Gemini, OpenAI GPT, Anthropic Claude) ou 100% offline com comandos por regras. Voce escolhe.

---

## Funcionalidades

### Conversa com IA
- Pergunte qualquer coisa em linguagem natural
- O Jarvis mantem o contexto da conversa entre turnos
- Referencia coisas que voce ja falou: "ele", "isso", "aquela musica"
- Escolha entre Gemini, GPT, Claude ou modo offline

### Controle do Discord
- Abrir, fechar e focar o Discord
- Mandar mensagem para alguem por nome: "manda um oi pro Renan"
- Mandar mensagem usando contexto: "manda pra ele: ja vou"
- Abrir servidor, canal ou DM especificos
- Entrar e sair de calls de voz
- Mutar e ensurdecer
- Navegar entre servidores e canais

### Navegacao Web
- Abrir sites por nome: "abre o GitHub", "abre meu email", "abre o LinkedIn"
- Pesquisar no Google, YouTube, imagens e noticias
- Abrir, fechar e trocar abas
- Voltar, avancar e recarregar pagina
- Verificar emails nao lidos (abre o filtro no Gmail)
- Procurar emails por remetente ou assunto

### Controle de Apps
- Abrir e fechar qualquer aplicativo instalado por nome
- Tocar musica no Spotify por voz: "toca Coldplay no Spotify"
- Pesquisar na web: "pesquisa o que e BPMN"

### Voz
- Reconhecimento de fala em portugues e ingles (Google Speech)
- Sintese de voz neural com Piper (offline, rapido)
- Fallback para SAPI5 do Windows se Piper nao estiver disponivel
- O Jarvis fala antes de executar ("Abrindo o Discord, senhor.") pra voce saber que entendeu

### Interface
- HUD animado estilo sci-fi (orbe pulsante)
- Janela frameless e transparente
- Indicadores visuais: ouvindo, processando, falando
- Botao de engrenagem para trocar de provedor de IA a qualquer momento
- Modo debug que mostra o que foi ouvido e respondido

---

## Como funciona

```
Voce fala  -->  Mic captura  -->  Google STT transcreve
                                       |
                              Rule-based tenta match
                                 |             |
                              Achou?        Nao achou?
                                 |             |
                           Executa acao   Envia pra IA (Gemini/GPT/Claude)
                                 |             |
                           Fala o ack     IA retorna JSON estruturado
                                 |             |
                              Piper TTS   Executa acao ou responde chat
                                 |             |
                           Proximo ciclo  Piper TTS fala a resposta
```

O fluxo completo de "Jarvis abre o GitHub" leva em torno de 4 a 7 segundos (captura + reconhecimento + acao + fala).

---

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Interface | PySide6 (Qt6) |
| Reconhecimento de fala | SpeechRecognition + Google STT |
| Sintese de voz | Piper (neural, offline) / SAPI5 (fallback) |
| IA | Google Gemini, OpenAI GPT, Anthropic Claude, Ollama (local) |
| Automacao | pywin32 (keyboard/window) + webbrowser (URLs) |
| Armazenamento seguro | keyring (Windows Credential Manager) |
| Build | PyInstaller |

---

## Como baixar

### Windows

1. Acesse a pagina de [Releases](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)
2. Baixe `Jarvis-Windows.zip`
3. Extraia em qualquer pasta
4. Execute `Jarvis.exe`

Nao precisa instalar Python.

---

## Como usar

1. Abra o Jarvis. A interface com o orbe animado aparece.
2. Na primeira vez, escolha seu provedor de IA (Gemini recomendado — free tier generoso) e cole a chave de API.
3. Fale "Jarvis" seguido do que voce quer:

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

Voce precisa dizer "Jarvis" antes de cada comando. Se nao disser, ele ignora (de proposito — nao fica respondendo conversa alheia).

---

## Observacoes

- Esta e a primeira versao publica. Funciona, mas tem limitacoes.
- O reconhecimento de fala depende do Google Speech, que precisa de internet e nem sempre acerta.
- Respostas de voz longas (Piper TTS) podem levar 3-5 segundos.
- Automacao do Discord e Spotify usa teclado virtual — funciona bem, mas brevemente rouba o foco da janela.
- A troca de status no Discord ainda nao e suportada (limitacao da automacao por teclado).
- Email funciona via URLs do Gmail — nao leva/resume conteudo, apenas abre filtros.
- So funciona em Windows por enquanto.

---

## Proximos passos

- STT local (Whisper) pra funcionar sem internet e mais rapido
- Integracao com Gmail API pra ler e resumir emails de verdade
- Discord RPC pra status e controle de voz sem roubar foco
- Lembretes e tarefas com agenda
- Memoria persistente do usuario entre sessoes
- Respostas por voz em streaming (falar enquanto gera)
- Suporte a Linux e macOS

---

**119 testes automatizados | 35+ acoes suportadas | 5 provedores de IA | 2 idiomas**
