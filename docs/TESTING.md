# Testing

There are two suites: an offline suite that runs anywhere with the virtual environment installed, and a small live suite that needs real hardware and a local Ollama model.

## Offline suite

```bash
./scripts/launch.sh test
```

or directly:

```bash
.venv/bin/python -m pytest tests -q
```

It covers:

- configuration defaults, validation and persistence
- memory storage and the sensitive-data filter
- event bus behaviour
- safety classification and emergency stop
- the `ACTION:` parser, including rejection of unknown tools and malformed JSON
- gaze mapping and dwell logic
- voice stop/cancel behaviour

These tests do not open the microphone or camera and do not need Ollama.

## Live hardware suite

```bash
JARVIS_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_integration_live.py -q
```

Skipped unless `JARVIS_LIVE_TESTS=1`. It exercises Ollama, wake-word inference on generated audio, Piper synthesis and camera capture. It expects the models from [MODELS.md](MODELS.md) to be present.

A quiet or covered camera will make the camera test fail even though the code is fine. Check the shutter and lighting before treating that as a regression.

## Manual checks worth doing

- `./scripts/launch.sh doctor` with the mic and camera connected
- `./scripts/launch.sh say "test"` for audio output
- `./scripts/on.sh` followed by `./scripts/off.sh` to confirm the GUI starts and releases its devices
- Portal consent for a screenshot and for `enable head tracking`

Anything that needs a consent dialog cannot be fully automated, on purpose.
