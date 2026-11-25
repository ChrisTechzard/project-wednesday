# Model files

Wednesday does not ship model weights. They are too large for a source repo, and some of them carry non-commercial terms. Download them yourself into `models/` before running the voice features.

Text chat and `doctor` work without any of these files. Speech input/output and the wake word need them.

## Wake word and VAD

From the [openWakeWord v0.5.1 release](https://github.com/dscripka/openWakeWord/releases/tag/v0.5.1):

```bash
mkdir -p models
BASE=https://github.com/dscripka/openWakeWord/releases/download/v0.5.1
for file in hey_jarvis_v0.1.onnx embedding_model.onnx melspectrogram.onnx silero_vad.onnx; do
  curl -fL -o "models/$file" "$BASE/$file"
done
```

`hey_jarvis_v0.1.onnx` is the model that listens for the spoken "Jarvis" trigger. The two feature models are required; `silero_vad.onnx` is a helper and can be left out if you do not need voice activity detection.

The wake-word models are published by openWakeWord under **CC BY-NC-SA 4.0**. Read the upstream terms before using them in anything commercial.

## Offline speech output

Piper voice `en_US-lessac-medium`:

```bash
curl -fL -o models/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -fL -o models/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Check the [piper-voices repository](https://huggingface.co/rhasspy/piper-voices) for the voice's current licence.

## Offline speech recognition

`faster-whisper` fetches `tiny.en` on first use:

```bash
./scripts/launch.sh listen
```

The cache lands in `models/whisper/`. Set `voice.stt_model` in `~/.config/Jarvis/config.json` if you want a different model. Larger models are slower on CPU.

## Ollama

Wednesday talks to `http://127.0.0.1:11434` and expects `llama3.2:latest`:

```bash
ollama pull llama3.2:latest
```

The Ollama model is managed by Ollama itself, outside this repo.

## Verify

```bash
./scripts/install.sh
./scripts/launch.sh doctor
```

`install.sh` prints `MISSING:` lines for any required wake-word or TTS file it cannot find. `doctor` reports whether the detectors actually load.
