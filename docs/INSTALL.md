# Installation

Wednesday runs out of a virtual environment inside the project folder. It does not install system packages and does not need sudo. The notes below are written for Ubuntu 24.04 with GNOME on Wayland, which is what I developed against; other Linux desktops with freedesktop portals should work too.

## Prerequisites

- Python 3.10 or newer with `venv` and `pip` (3.12 was used here)
- [Ollama](https://ollama.com) running locally, with `llama3.2:latest` pulled:

  ```bash
  ollama pull llama3.2:latest
  ```

- A microphone, and a webcam if you want the Vision panel
- `curl` for downloading models
- GNOME/Freedesktop portals for screenshots and desktop input. These are present in a normal GNOME session; other desktops may need `xdg-desktop-portal` installed.

## Install

From the repo root:

```bash
./scripts/install.sh
```

The script:

1. creates or refreshes `.venv`,
2. installs `requirements.txt`,
3. checks that Ollama answers,
4. checks for model files and reports any that are missing,
5. installs `~/.local/share/applications/Wednesday.desktop`,
6. writes a health report to `logs/doctor.json`.

Then download the models described in [MODELS.md](MODELS.md). This is a separate step on purpose: the source repo stays small and no third-party weights are redistributed here.

## Optional offline OCR

Screen text extraction is an optional extra. Screenshots and AI screen descriptions work without it; only reading text out of a captured image needs OCR.

```bash
.venv/bin/python -m pip install -r requirements-optional.txt
```

The optional file pins `numpy==1.26.4` and `opencv-python==4.10.0.84` so RapidOCR and MediaPipe can coexist. It is not part of the core install because it pulls in extra wheels.

## Desktop launcher and background service

After `install.sh`, search for **Wednesday** in the Activities overview. Or start it from a terminal:

```bash
./scripts/on.sh       # GUI in the background
./scripts/off.sh      # stop GUI + service
./scripts/toggle.sh   # flip between them
```

Headless wake-word mode needs no GUI:

```bash
./scripts/launch.sh voice
```

A user-level systemd unit can be installed with:

```bash
./scripts/install-service.sh            # install only (default)
./scripts/install-service.sh --enable   # also start at login
./scripts/install-service.sh --start    # also start now
```

It installs `~/.config/systemd/user/jarvis.service` (the old service name). Autostart is off by default; the unit is installed but not enabled unless you ask for it. Useful commands:

```bash
systemctl --user start|stop|restart|status jarvis.service
journalctl --user -u jarvis.service -f
systemctl --user disable jarvis.service
```

## Verify

```bash
./scripts/launch.sh doctor
./scripts/launch.sh test
```

`doctor` prints Ollama state, audio devices, cameras, model presence and memory counts as JSON. See [TESTING.md](TESTING.md) for the live hardware tests.

## Update and uninstall

Re-run `scripts/install.sh` to refresh dependencies and the launcher. Git pulls update the source; they do not touch your models, config or memory.

Run `scripts/uninstall.sh` to remove the Wednesday launcher, its config `~/.config/Jarvis` and its data directory `~/.local/share/Jarvis`. It asks for `--yes` before deleting anything and deliberately leaves the source folder alone, so a cloned repo is never wiped. Ollama and system packages are never touched.
