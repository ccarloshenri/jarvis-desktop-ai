<div align="center">

# Jarvis

**A premium voice-first desktop assistant for Windows. Talks, thinks with cloud-grade AI, runs on your PC, talks back.**

[![Build Windows EXE](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ccarloshenri/jarvis-desktop-ai/actions/workflows/build-windows.yml)
[![Latest Release](https://img.shields.io/github/v/release/ccarloshenri/jarvis-desktop-ai?label=download)](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## What it is

Jarvis listens for the wake word, transcribes what you said, reasons about it with an LLM, and either runs the command or talks back — with a real voice, through a live HUD that shows every stage of the pipeline in motion.

End-to-end latency from "end of speech" to "first spoken word" lands around **1 second** with the recommended cloud stack (Groq Whisper → Groq Llama 3.3 70B → ElevenLabs Daniel). All local is also supported but slower.

## Download

1. Grab the latest **[Release](https://github.com/ccarloshenri/jarvis-desktop-ai/releases/latest)**.
2. Download `Jarvis-Windows.zip`, extract it anywhere.
3. Run **`Jarvis.exe`**.

No Python install, no environment variables, no manual config files.

## Quick configure

Click the ⚙ icon in the top bar. You get three tabs:

| Tab | What it sets |
|---|---|
| **Intelligence** | The AI brain. **Groq** (Llama 3.3 70B) is the default — free tier, sub-300ms TTFB. |
| **Voice** | The speech synthesiser. **ElevenLabs** (Daniel voice) is recommended for near-human output. |
| **Music** | The music service Jarvis controls. **Spotify** (Web API via OAuth PKCE) is supported. |

Each provider card shows what it's good at, a usage example, and a **CONFIGURE** button that opens a detail screen with the API-key input and a one-click link to the provider's key-management page. Keys are stored in the OS keyring — never in files.

Restart Jarvis after saving a new provider or credential so the audio pipeline picks it up.

## How to talk to it

Just say **"Jarvis"** followed by whatever you want:

| You say | It does |
|---|---|
| "Jarvis, play Lana Del Rey on Spotify" | Searches + plays the track via the Spotify API |
| "Jarvis, open Spotify" / "close Spotify" | Launches or kills the desktop app |
| "Jarvis, send a hi to Renan on Discord" | Opens the DM and sends the message |
| "Jarvis, open a new tab" / "close this tab" / "next tab" | Drives the browser with keyboard shortcuts |
| "Jarvis, search a Neymar video on YouTube" | Opens the search in your default browser |
| "Jarvis, open my email" | Opens Gmail inbox |
| "Jarvis, what time is it" / "what's twelve times eight" | Speaks the answer back |
| "Jarvis, show off" | Puts on a hacker-style window show with AC/DC for a soundtrack |

Each wake also plays a soft two-note chime so you know Jarvis heard you before it starts thinking.

## What's under the hood

```
 ┌──────────────┐      ┌────────────┐      ┌──────────────┐      ┌──────────────┐
 │ openwakeword │ →    │ Silero VAD │ →    │ Groq Whisper │ →    │ Groq Llama   │
 │ always-on    │      │ endpointing│      │ large-v3-    │      │ 3.3 70B      │
 │ wake-word    │      │ ~350ms end │      │ turbo        │      │ streaming    │
 │ detector     │      │ of speech  │      │ ~400ms       │      │ JSON parser  │
 └──────────────┘      └────────────┘      └──────────────┘      └──────────────┘
                                                                          │
                                     ┌────────────────────────────────────┤
                                     ▼                                     ▼
                              ┌──────────────┐                     ┌──────────────┐
                              │ ElevenLabs   │                     │ Action       │
                              │ Daniel voice │                     │ executor     │
                              │ streaming    │                     │ (Spotify /   │
                              │ PCM 22050    │                     │  Discord /   │
                              └──────────────┘                     │  Browser /   │
                                                                    │  Apps)      │
                                                                    └──────────────┘
```

- **Wake word**: [openwakeword](https://github.com/dscripka/openWakeWord) hey-jarvis ONNX model, always running, near-zero CPU.
- **VAD**: [Silero VAD](https://github.com/snakers4/silero-vad) replaces RMS silence detection — ~500ms tighter end-of-speech without clipping.
- **STT**: [Groq Whisper](https://console.groq.com/) `large-v3-turbo` for multilingual accuracy at cloud latency. Falls back to local `faster-whisper` when no key is set.
- **LLM**: [Groq Llama 3.3 70B](https://console.groq.com/) via an OpenAI-compatible client with streaming JSON decisions. Action commands can start executing while the LLM is still producing tokens. Also works against local [LM Studio](https://lmstudio.ai/).
- **TTS**: [ElevenLabs `eleven_multilingual_v2`](https://elevenlabs.io/) for near-human quality. Local [Piper](https://github.com/rhasspy/piper) pre-warmed pool when you want offline.

## Live HUD

The main window is a full dashboard you can leave open on a second monitor:

- **Status strip**: AI Brain / Voice Engine / Music / Pipeline state cards with live accent dots.
- **Providers + System**: current provider names, uptime, turns, success rate (donut), wake fires, errors.
- **Telemetry**: STT / LLM / TTS latencies — current and rolling average over the last 20 turns.
- **Latency History**: per-turn stacked bars (STT + LLM) so you can see *where* each turn's budget went.
- **Connections**: pulsing live-state indicators for each subsystem (AI, STT, TTS, wake word, music).
- **Event Timeline**: scrolling dot-ribbon of recent wake fires, turns, errors.
- **Centre stage**: J.A.R.V.I.S title → animated orb → state strip (LISTENING / THINKING / SPEAKING) → VU meter → scrolling waveform → last transcript / last response banners.
- **Live clock** + session log at the bottom.

The whole HUD runs in a single strict palette (cyan / amber / teal) — no stray pinks or branding clashes.

## For developers

```bash
git clone https://github.com/ccarloshenri/jarvis-desktop-ai.git
cd jarvis-desktop-ai
pip install -r requirements.txt

# download the Silero VAD model (~2.3 MB)
powershell -ExecutionPolicy Bypass -File scripts/fetch_silero_vad.ps1

python -m app.main
```

```bash
pytest           # 80/80 green
```

### Configuration without the UI

Every setting is also an environment variable — drop them in a `.env` file next to the project (see `.env.example`):

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq key for LLM + Whisper STT |
| `ELEVENLABS_API_KEY` | ElevenLabs key for cloud TTS |
| `JARVIS_LLM_PROVIDER` | `groq` / `lm_studio` |
| `JARVIS_STT_PROVIDER` | `groq` / `whisper` |
| `JARVIS_TTS_PROVIDER` | `elevenlabs` / `groq` / `piper` |
| `JARVIS_LANGUAGE` | `en-US` / `pt-BR` (ack phrases + prompts switch accordingly) |
| `SPOTIFY_CLIENT_ID` | Spotify Web API (PKCE, no secret) |

Any key set via the UI is stored in the OS keyring and read back on the next launch — you don't need to mirror it into `.env`.

### Build the Windows executable

```powershell
pip install -r requirements-build.txt
.\scripts\build_windows.ps1 -Clean
```

### Automated release

Pushing a `v*` tag fires the CI workflow: runs tests, packages with PyInstaller, publishes the zip to Releases.

```bash
git tag v1.1.0
git push origin v1.1.0
```

## Roadmap

- [x] Local STT (faster-whisper) — works without internet
- [x] Cloud STT (Groq Whisper large-v3-turbo)
- [x] Streaming TTS pipeline (chunk-as-it-speaks)
- [x] Neural endpointing (Silero VAD)
- [x] Multi-provider settings dialog with provider cards
- [ ] OpenAI / Anthropic / Gemini LLM integration (UI scaffolding ready)
- [ ] SoundCloud music provider
- [ ] Streamlabs TTS integration
- [ ] Gmail API for reading + summarising emails
- [ ] Discord RPC for status + voice without stealing focus
- [ ] Reminders + tasks
- [ ] Persistent memory across sessions
- [ ] Linux and macOS packaging

## Contributing

Pull requests are welcome. For large changes, please open an issue first so we can align on direction.

## License

[MIT](LICENSE)
