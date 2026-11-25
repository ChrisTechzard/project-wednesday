# Troubleshooting

## Diagnostics

```bash
./scripts/launch.sh doctor > doctor.json
tail -f logs/jarvis.log
tail -f logs/actions.jsonl
journalctl --user -u jarvis.service -f
```

`doctor` reports Ollama state, microphones, cameras, model presence, session type and memory counts. If a subsystem is unavailable, it says so there before you go digging.

## Ollama is offline or the first answer is slow

- Check `ollama list` and `curl http://127.0.0.1:11434/api/tags`.
- Start it with `systemctl start ollama` if it is installed but not running.
- The first request after a reload can take 25–40 s while `llama3.2:latest` loads. Warm answers are usually 1–3 s.
- If answers mention tools that do not exist, check that `ai/brain.py` still uses the validated `ACTION:` protocol rather than native `tools=` calls.

## Camera / face tracking

- Check the physical privacy shutter and whether another app holds the webcam.
- `doctor` lists available camera indices. A near-black frame usually means the shutter is closed or the lens is covered.
- Change the index in Settings if the default is wrong (`vision.camera_index`).
- "No face detected" means the tracker is running but sees no face. Check lighting and framing.
- Gaze control needs calibration; head control is a coarse fallback. Blink click is experimental and off by default.

## Screenshots and desktop input

Screenshots and pointer/keyboard injection go through the GNOME/Freedesktop portals. On first use a consent dialog appears:

- Allow the request from Wednesday/the launcher. Without approval the call times out and you get `Screen capture is unavailable` or `Mode unavailable (permission?)`.
- The supported path is the portal. Do not try to bypass the consent prompt.
- If a request hangs, cancel the dialog and retry.
- The screenshot portal timeout is 90 s, and the code subscribes to the Response signal before making the call so a remembered permission is not missed.
- If screenshots still time out, check `logs/jarvis.log` for portal parsing errors.
- Screen text extraction needs `requirements-optional.txt`; screenshots and AI descriptions work without it.

## Audio pipeline

The mic path is local:

1. `sounddevice` streams 16 kHz mono audio from the mic into a queue.
2. A wake-word thread scores each frame with a local ONNX model. It runs continuously while the app is on.
3. On detection, Piper says "Yes?" and `listen_once()` records up to 12 s.
4. `faster-whisper tiny.en` transcribes on CPU.
5. Ollama returns a validated action or a plain reply, which Piper speaks.

Things to check:

- No wake response: verify the mic in Settings/`doctor`, adjust the wake threshold, and make sure the input is not muted in GNOME Sound settings.
- Slow replies are expected: STT is about 2× realtime and the first Ollama answer after a reload can take 25–40 s.
- False wake triggers: raise `voice.wake_word_threshold` in `~/.config/Jarvis/config.json` from `0.5` to `0.6–0.7`, or disable the wake word and use typed input / push-to-talk.
- Recording froze the desktop: this was traced to opening a second blocking `sd.rec()` stream while the wake-word stream was live. Recording now drains the existing stream and is cancellable.
- STOP did not cancel an answer: a request generation counter now discards late replies.
- No spoken output: check `models/en_US-lessac-medium.onnx`, system volume, and run `./scripts/launch.sh say "test"`.

## Lag / responsiveness

- The vision engine starts with the camera on by default. Turn it off in Settings → "Enable camera/vision engine at startup", or from the Vision & Tracking panel.
- If the UI feels slow, lower `vision.target_fps`, set `vision.show_preview = false`, or disable the camera in `~/.config/Jarvis/config.json`.
- The event bus replaces stale queued events instead of flooding the log when frames arrive faster than the UI can draw them.
- `doctor()` is refreshed in the dashboard every 30 s. Do not call it in a tight loop.

## Turning Wednesday off

- `./scripts/off.sh` or `./scripts/toggle.sh`: SIGTERM first, up to 5 s to release the mic/camera, then SIGKILL if needed.
- **EMERGENCY STOP** in the GUI blocks actions and quits the app.
- Closing the window stops all subsystems. Dismiss any open confirmation dialog first.

## Install / dependencies

- Core install skips `rapidocr-onnxruntime` because it adds extra wheels. Install it separately if you want OCR.
- `requirements-optional.txt` pins NumPy/OpenCV so MediaPipe and RapidOCR coexist.
- If pip was interrupted, re-run `scripts/install.sh`.
- `openwakeword` itself cannot be installed on Python 3.12 (`tflite-runtime` has no wheel). Wednesday uses the local ONNX port instead.
- No apt/sudo packages are required by the project itself.

## GUI issues

- A `Given image is not CTkImage` warning means the webcam preview needs `ctk.CTkImage`.
- `AttributeError` about `TrackingState` fields means the vision thread is out of sync with `core/models.py`; the correct field is `face_detected`.
- Settings live in `~/.config/Jarvis/config.json`, memory in `~/.config/Jarvis/memory.sqlite3`. Prefer Settings → Reset Defaults / Clear Memory over deleting those files by hand.

## Background service

```bash
systemctl --user status jarvis.service
journalctl --user -u jarvis.service -n 50 --no-pager
./scripts/install-service.sh --enable --start
systemctl --user disable --now jarvis.service
```

The service is user-level only and never uses sudo. It runs `launch.sh voice`, so mic and camera permissions follow the same GNOME grants as the GUI.
