# Architecture, design decisions and limitations

## Data flow

```
Mic ──> wake word (ONNX) ──> STT (faster-whisper) ──┐
Text input ──────────────────────────────────────────┼─> Brain ─> Ollama llama3.2:latest
                                                      │      │
                                                      │      └─> validated ACTION: line
Webcam ─> face/head/gaze (MediaPipe) ─> calibration ─┘             │
                                                                    v
                                                          Tool registry + safety gate
                                                                    │
                                             apps / portals / memory / TTS / GUI log
```

- `app/jarvis.py` is the orchestrator; `app/main.py` is the CLI. The class name is legacy — the assistant is called Wednesday.
- `core/events.py` is a thread-safe event bus. The GUI subscribes and marshals events onto the Tk thread with `after(...)`.
- `core/safety.py` classifies risk, blocks high-risk tools, prompts for medium-risk ones, and implements emergency stop and the JSONL audit log.
- `ai/brain.py` tries deterministic patterns for core commands first, then falls back to the local LLM.

## Why a text action protocol instead of Ollama tool calling

Native Ollama tool calls on `llama3.2:latest` were unreliable in testing: factual questions produced `math`, `open_application {"name": "GNOME"}` and `search_web` calls, plus invented tools. A stronger system prompt did not fix it. The model is now asked to emit exactly:

```
ACTION: <whitelisted_tool> <json_arguments>
```

`Brain._parse_action` accepts only a fixed allowlist and valid JSON. Anything else is treated as an ordinary answer. That keeps useful tool calls without letting a hallucinated call turn into an execution.

## Local-first and privacy

- Ollama runs locally. Cloud AI is `cloud_enabled: false` and has no credentials configured.
- Wake word, STT, TTS, face tracking, optional OCR and memory all use local files.
- The memory store refuses obvious secrets such as passwords, tokens and API keys.
- Microphone, camera and screen data are not uploaded. A short connectivity check does hit `detectportal.firefox.com`, but sends no user data.

## Wayland automation

GNOME Shell's `Eval`, `FocusApp` and screenshot DBus methods were denied in the test session, and X11 capture was unavailable. Wednesday uses `org.freedesktop.portal.Screenshot` and `org.freedesktop.portal.RemoteDesktop` with the required `handle_token` and `session_handle_token` values. Consent is a one-time user action and is never bypassed.

## Honest limitations

- **Gaze/blink**: a normal webcam cannot do precise gaze pointing. Calibration helps with large targets. Blink click is disabled by default because its reliability was not verified with a real face in frame.
- **Camera**: face detection was checked with a real camera during development, but privacy shutters and lighting vary. A black frame usually means the shutter is closed, not a code fault.
- **Screenshots/input**: require portal consent. The assistant cannot approve the dialog itself.
- **STT speed**: `tiny.en` on CPU runs at roughly 2× realtime for short phrases; long dictation is slow.
- **LLM latency**: the first request after an Ollama reload can take 25–40 s while the model loads. Warm requests are usually 1–3 s.
- **Tray icon**: no native tray icon on Wayland GNOME. `tray_enabled` is reserved for future use; headless mode and the user service cover background operation.
- **Emergency hotkey**: `<ctrl>+<shift>+j` is configured but not bound globally. Use the GUI button, voice command or service stop.
- **Shell commands**: deliberately not exposed to the AI (`allow_shell_commands: false`). There is no arbitrary command execution path.
- **OCR**: optional extra, not installed by the core script.
- **Model quality**: `llama3.2:latest` is small. Complex reasoning and long conversations are limited.

## Testing approach

The offline suite covers config, memory, events, safety, the action parser and gaze/dwell logic. Live tests for Ollama, wake-word inference, Piper synthesis and camera capture are opt-in, because they need hardware and network conditions that are not present on every machine. See [TESTING.md](TESTING.md).
