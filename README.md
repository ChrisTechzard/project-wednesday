# Wednesday

A voice-enabled desktop assistant for Linux that keeps the interesting parts on your machine.

I built Wednesday because I wanted to talk to my laptop without sending every sentence to somebody else's server. The microphone, webcam and screen frames stay local, replies come from an Ollama model running on the same box, and anything that touches the desktop has to pass through a safety check first.

## What it does

- **Voice without the cloud.** ONNX wake word, faster-whisper for speech to text, Piper for speech output. Say "Jarvis, ..." to wake it, then speak a command. Typing in the Conversation panel uses the same AI and skips the audio step.
- **Local AI.** Ollama with `llama3.2:latest` answers questions and picks actions from a small allowlist. The model has to emit `ACTION: <tool> <json>`; free-form tool calls are not trusted.
- **Desktop control.** Launch apps, open a configured project folder, search the web, take a screenshot through the GNOME portal, and optionally move the pointer or send keys through the RemoteDesktop portal. Every action is recorded in `logs/actions.jsonl`.
- **Webcam tracking.** Face, head and coarse gaze tracking with a 9-point calibration and dwell selection. Blink click exists but is off by default and I would not rely on it.
- **Local memory.** SQLite-backed facts and recent conversation context, with a filter that refuses passwords, tokens and API keys.
- **A GUI you can actually stop.** Dashboard, Conversation, Vision & Tracking and Settings panels, plus an EMERGENCY STOP button that blocks automation and quits the app.

It is a personal project, not a product. It assumes one user on one machine.

## Requirements

- Linux with Python 3.10+ (developed on Ubuntu 24.04, GNOME on Wayland, Python 3.12)
- [Ollama](https://ollama.com) with `llama3.2:latest` pulled
- A microphone; a webcam is optional
- GNOME/Freedesktop portals for screenshots and input injection. Without them those two features stay unavailable, but chat and voice still work.
- About 150 MB of local voice/vision model files, downloaded separately (see [docs/MODELS.md](docs/MODELS.md))

No sudo is needed. The installer uses a virtual environment inside the project and a user-level systemd unit.

## Install

```bash
git clone https://github.com/ChrisTechzard/project-wednesday.git
cd project-wednesday
./scripts/install.sh
```

Then download the model files listed in [docs/MODELS.md](docs/MODELS.md) into `models/` and run the health check:

```bash
./scripts/launch.sh doctor
```

`install.sh` will tell you which model files are missing. It deliberately does not download them: a few have non-commercial licences, so they should not be redistributed with the source.

Full details are in [docs/INSTALL.md](docs/INSTALL.md).

## Run

```bash
./scripts/on.sh                    # start the GUI in the background
./scripts/off.sh                   # stop the GUI and the headless service
./scripts/toggle.sh                # flip between the two

./scripts/launch.sh                # GUI in the foreground
./scripts/launch.sh chat           # terminal chat
./scripts/launch.sh listen         # one spoken command
./scripts/launch.sh say "Hello"    # offline text-to-speech
./scripts/launch.sh voice          # headless wake-word listener
./scripts/launch.sh doctor         # diagnostics as JSON
./scripts/launch.sh status         # one-line status
./scripts/launch.sh test           # offline tests
```

The desktop launcher appears as "Wednesday" in the Activities overview. The headless service is installed as `jarvis.service` — an older name that stuck — and is **not** enabled at login unless you pass `--enable` to `scripts/install-service.sh`.

See [docs/USAGE.md](docs/USAGE.md) for the command list, GUI panels and calibration steps.

## Layout

```
app/          CLI entry point and orchestrator
core/         config, events, models, safety, portals, logging
ai/           brain, Ollama client, memory, tool registry
voice/        microphone, wake word, STT, TTS, voice engine
vision/       camera, face tracker, gaze calibration, dwell, engine
automation/   launcher, screenshots, input, screen analysis, monitoring
ui/           CustomTkinter dashboard and panels
tests/        offline unit tests and opt-in live hardware tests
docs/         installation, usage, models, troubleshooting, architecture
scripts/      install, launch, on/off, service installer
assets/       launcher icon
```

Runtime directories (`models/`, `logs/`, `screenshots/`, `.venv/`) are ignored by Git and stay on your machine.

## Safety and privacy

- Cloud AI is off by default and no API key is configured. Nothing is uploaded for speech, faces or screen content.
- The AI cannot run shell commands, delete files, install packages, change system settings, send messages or buy things. Those tools are always blocked by policy.
- Mouse and key injection through the RemoteDesktop portal needs a consent dialog. Wednesday cannot approve it for you.
- High-risk user actions need explicit confirmation; medium-risk ones prompt when `require_confirmation` is on.
- Settings and memory live under `~/.config/Jarvis/`. Use Settings → Clear Memory to wipe them.

The honest list of limits is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). If something behaves oddly, start with [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Tests

```bash
./scripts/launch.sh test
```

That runs the offline suite. Live hardware tests are opt-in:

```bash
JARVIS_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_integration_live.py -q
```

More detail in [docs/TESTING.md](docs/TESTING.md).

## License

The source is MIT licensed; see [LICENSE](LICENSE). The third-party models are not included in this repository and keep their own upstream licences — check [docs/MODELS.md](docs/MODELS.md) before using Wednesday commercially.
