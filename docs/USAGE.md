# Usage & command reference

All commands below assume you are in the project root.

## Starting and stopping

```bash
./scripts/on.sh                    # start the GUI in the background
./scripts/off.sh                   # stop the GUI and the background service
./scripts/toggle.sh                # flip between on and off

./scripts/launch.sh                # GUI (default, foreground)
./scripts/launch.sh gui            # same
./scripts/launch.sh chat           # text chat in the terminal
./scripts/launch.sh listen         # record one voice command
./scripts/launch.sh say "text"     # speak with offline TTS
./scripts/launch.sh voice          # headless wake-word listener
./scripts/launch.sh doctor         # diagnostics as JSON
./scripts/launch.sh status         # one-line status
./scripts/launch.sh test           # offline tests
```

Nothing starts at login unless you explicitly enable `jarvis.service`. Headless mode can still be started with `systemctl --user start jarvis.service`.

In the GUI, type into the Conversation panel and press Enter, or click **MIC** to record. Wake-word listening starts with the app; say **"Jarvis, ..."**. Press **F1** any time to see the keyboard shortcuts, or click **Shortcuts** in the top bar.

### Conversation buttons

| Button | What it does |
|---|---|
| **SEND** | Sends typed text; disabled while a reply is being generated so clicks cannot stack up. |
| **MIC** | Records from the already-open mic stream. Becomes **RECORDING** while active; click again to finish early. Disabled while a reply is being generated. |
| **STOP** | Cancels recording, discards a pending reply and stops speech playback. |
| **COPY** | Copies the visible transcript to the clipboard. This does not change stored chat history. |
| **CLEAR** | Empties the visible transcript and starts with a fresh greeting. Stored memory is untouched. |

Transcript lines are timestamped and coloured by speaker. Keyboard focus is shown with a white border on buttons, entries, sliders and check boxes.

Recording reuses the live microphone stream rather than opening a second audio device, which avoids deadlocking PipeWire. Commands are capped at `voice.phrase_time_limit` seconds (default 12) unless you stop sooner.

## GUI panels

- **Dashboard** — status cards, a manual **Refresh** button, quick actions and the action log. **Stop current action** cancels the active request; it does not quit the app.
- **Conversation** — timestamped transcript, text input, MIC/STOP controls, COPY/CLEAR and a live mic meter.
- **Vision & Tracking** — camera on/off, head/gaze/off modes, 9-point calibration with an on-screen target and progress, sensitivity/smoothing/dwell sliders, experimental blink toggle.
- **Settings** — AI model/host, voice devices, vision defaults, automation safety, memory toggles, theme, save/reset/clear memory. Bad values are marked next to the field before anything is saved.
- **EMERGENCY STOP** — blocks all automation immediately and quits the app.

### Keyboard shortcuts

| Keys | Action |
|---|---|
| **Ctrl + 1 / 2 / 3 / 4** | Dashboard / Conversation / Vision & Tracking / Settings |
| **Ctrl + Enter** | Send the typed message |
| **Alt + M** | Start or stop microphone recording |
| **Ctrl + S** | Save settings |
| **Ctrl + Shift + J** | Emergency stop and quit |
| **F1** | Show the shortcut list |
| **Esc** | Deny a confirmation dialog or close the shortcut list |

## Commands

### Informational

| Say or type | Result |
|---|---|
| `what time is it` | current local time |
| `system status`, `check CPU`, `my RAM usage` | CPU/RAM/disk/network snapshot |
| anything else | answered by local Ollama `llama3.2:latest` |

### Applications and web

| Say or type | Result |
|---|---|
| `open firefox`, `launch terminal`, `start VS Code` | launch a known app (aliases live in Settings/config) |
| `open project NAME` | open a folder configured in `automation.project_paths` |
| `search the web for QUERY`, `google QUERY` | open a web search in the default browser |

### Memory

| Say or type | Result |
|---|---|
| `remember that KEY is VALUE` | store a local fact; secrets are refused |
| `recall KEY`, `what did I tell you about KEY` | recall a fact |
| `what do you remember`, `list my memories` | list facts |
| `forget KEY` | forget matching facts |
| `clear all my memories` | clear memory after confirmation |

### Vision and desktop input

| Say or type | Result |
|---|---|
| `take a screenshot` | capture through the GNOME portal (one-time consent) |
| `describe my screen`, `what's on my screen` | screenshot + local OCR (if installed) + local AI description |
| `enable head tracking`, `turn on gaze control` | start cursor control (needs portal consent) |
| `disable head tracking`, `stop eye tracking` | stop cursor control |
| `move the mouse to X, Y`, `click`, `right click`, `press CTRL+L` | medium-risk input actions; confirmation prompt |

### Control and safety

| Say or type | Result |
|---|---|
| `stop talking`, `be quiet` | stop speech immediately |
| `go to sleep` | pause command handling |
| `wake up`, `Jarvis, wake up` | resume |
| `quit`, `shut down`, `exit` | stop the terminal chat / assistant |

## How the microphone works

Everything is local:

1. The mic is streamed at 16 kHz mono while Wednesday is on.
2. A small ONNX model watches for "Jarvis" in a background thread.
3. On detection, Wednesday says "Yes?" and records up to 12 seconds.
4. `faster-whisper tiny.en` transcribes it on CPU.
5. Local Ollama decides the response or action, and Piper speaks the reply.

Typing in Conversation uses the same AI but skips wake word and STT, so it is much faster. If voice feels laggy, keep commands short or type them.

Settings worth knowing: wake threshold (default `0.5`), microphone device, STT model, TTS voice/speed/volume. Raise the threshold if the wake word fires during normal speech; lower it if you have to shout.

## Gaze / head calibration

1. Open **Vision & Tracking**, click **Camera ON**, and make sure your face is visible.
2. Choose **gaze** or **head** mode. Portal consent is needed for cursor control.
3. Click **Start calibration**. A circle appears on the preview and the status shows which of the 9 targets to look at. Click **Capture point** for each one.
4. The progress bar fills as points are captured. If no face is detected, the status says so and the point is not recorded. **Cancel** stops the attempt and keeps the previous fit.
5. When the last point is captured the fit is saved locally and shows as **Calibrated**.
6. Set dwell time (default 900 ms); the cursor rests on a target to click. Leave blink click off unless you have verified it.

A normal webcam is not an eye tracker. Expect large-target selection, not pixel-perfect pointing.

## Safety model

- Low-risk actions run directly: time, status, memory, app launch, web search, screenshots.
- Medium-risk actions (mouse clicks, key presses, window close) ask for confirmation when `require_confirmation` is on.
- High-risk actions (file deletion, shell commands, installs, system settings, messages, purchases) are blocked by policy.
- The model must emit `ACTION: <whitelisted_tool> <json>`; anything else is treated as ordinary text.
- Cloud AI is off by default; no microphone, camera or screen data is uploaded.
- Every tool execution is appended to `logs/actions.jsonl`.

Manual stops: GUI **EMERGENCY STOP** (or **Ctrl + Shift + J**), `./scripts/off.sh`, `systemctl --user stop jarvis.service`, or closing the window.
