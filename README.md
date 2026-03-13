# VN-TTS-Reader

**Clipboard-driven Text-to-Speech for Visual Novels**  
Automatically voices dialogue as you read — with per-character voices, emotion sounds, and zero configuration required to get started.

---

## What it does

VN-TTS-Reader sits in the background while you play a Visual Novel. Every time a line of dialogue is copied to your clipboard (most VNs support this natively via a "Copy to Clipboard" or `Shift+C` option), it:

1. **Detects the character name** and assigns a unique voice automatically
2. **Strips emotion tags** like `*laughs*`, `*sighs*`, `*gasps*` and plays matching sound files instead
3. **Speaks the dialogue** using [Piper TTS](https://github.com/rhasspy/piper) — fully offline, no API key needed
4. **Remembers all assignments** between sessions via a local JSON config

The first 10 characters you encounter are automatically mapped to Speaker1–Speaker10, so immersion is never broken. You can reassign voices at any time through the GUI.

---

## Requirements

- Windows 10 / 11 (64-bit)
- Python 3.10 or newer
- A Visual Novel with "copy text to clipboard" support (most modern VNs have this)
- Your own emotion sound `.wav` files (see [`emotion_sounds/README.md`](emotion_sounds/README.md))

---

## Installation

### Option A — uv (recommended, fastest)

```bash
# Install uv if you don't have it
pip install uv

# Clone and install
git clone https://github.com/NeverToOldToLearn/Visual-Novel-Text-To-Speech.git
cd vn-tts-reader
uv venv
uv pip install .

# Download Piper and the voice model
uv run install.py
```

### Option B — plain pip

```bash
git clone https://github.com/NeverToOldToLearn/Visual-Novel-Text-To-Speech.git
cd vn-tts-reader
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Download Piper and the voice model
python install.py
```

The installer will:
- Download **Piper TTS** from the official GitHub releases
- Download the **en_US-libritts_r-medium** voice model from Hugging Face
- Create the `data/` directory structure next to the script

---

## Running

```bash
# With uv
uv run main.py

# Or with your venv active
python main.py
```

Then in your Visual Novel, enable **"Copy text to clipboard"** (usually `Shift+C` or in the game settings). That's it — voices will play automatically as you advance through dialogue.

---

## Emotion Sounds

The reader detects emotion tags in dialogue and plays a matching sound file instead of having TTS speak them. Add your own `.wav` or `.mp3` files to the `emotion_sounds/` folder.

See [`emotion_sounds/README.md`](emotion_sounds/README.md) for the full list of expected filenames.

> The `emotion_sounds/` folder is **not included** in the repo (sounds are personal/licensed). Freesound.org is a good free source.

---

## GUI Overview

| Panel | Description |
|---|---|
| **Override Speaker** | Force all lines to one voice — useful for auditioning speaker IDs |
| **Speaker Voice IDs** | Assign a numeric voice ID (1–902) to each of the 10 speaker slots |
| **Character Name → Speaker** | View and edit automatic name mappings |
| **⚠ Unassigned Names** | Names detected but not yet auto-mapped (when all 10 slots are full). Click a name to prefill the form. |

### Buttons
- **Apply & Save** — saves current config without restarting
- **Apply & Restart** — saves and hot-reloads the script
- **Reload Config** — reads config from disk (useful if you edited `vntts_config.json` manually)

---

## Voice Customization

Speaker IDs correspond to voices in the `en_US-libritts_r-medium` model (range: 1–902).  
To audition a voice before assigning it:

1. Set **Override Speaker** to any slot
2. Enter an ID in that slot's field
3. Click **Apply & Save**
4. Advance a line of dialogue in your VN

The `approved_speakers.txt` file contains the default IDs loaded on first run. Edit it to change the defaults for new sessions.

### Adding a second voice model

The `Narrator` speaker slot uses a separate model path (`en_US-hfc_male-medium` by default).  
To change it, edit `VOICES_DIR` and `male_voice_model_path` in `main.py`, or download an additional model to `data/voices/`.

---

## Configuration file

`vntts_config.json` is auto-generated next to `main.py` and stores:
- Speaker ID assignments per slot
- Character name → speaker mappings

It is excluded from `.gitignore` so your settings stay local.

---

## Project structure

```
vn-tts-reader/
├── main.py                  # Main application
├── install.py               # One-time setup script
├── approved_speakers.txt    # Default speaker IDs
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── emotion_sounds/
│   └── README.md            # Expected sound filenames
└── data/                    # Created by install.py (gitignored)
    ├── piper/
    │   └── piper.exe
    ├── voices/
    │   └── en_US-libritts_r-medium/
    ├── cache/
    └── temp/
```

---

## License

MIT — do whatever you want with it.

---

## Credits

- [Piper TTS](https://github.com/rhasspy/piper) by Rhasspy / Michael Hansen
- [en_US-libritts_r-medium](https://huggingface.co/rhasspy/piper-voices) voice model via Hugging Face
