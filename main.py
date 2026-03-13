import os
import re
import time
import shutil
import pygame
import pyperclip
import logging
import hashlib
import tempfile
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, Listbox, Scrollbar
import threading
import json
import sys
import atexit

# Setup logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-7s | %(threadName)-10s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ── Runtime paths ─────────────────────────────────────────────────────────────
# All data lives next to this script by default.
# Override by setting the VN_TTS_BASE environment variable.
BASE_DIR = os.environ.get("VN_TTS_BASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
PIPER_EXE  = os.path.join(BASE_DIR, "piper", "piper.exe")
VOICES_DIR = os.path.join(BASE_DIR, "voices")
CACHE_DIR  = os.path.join(BASE_DIR, "cache")
TEMP_DIR   = os.path.join(BASE_DIR, "temp")
EMOTION_SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emotion_sounds")
OUTPUT_WAV = os.path.join(BASE_DIR, "vn_tts_out.wav")

for _d in (BASE_DIR, os.path.join(BASE_DIR, "piper"), VOICES_DIR, CACHE_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)
# ──────────────────────────────────────────────────────────────────────────────


class VNReader:
    def __init__(self):
        self.config_file = "vntts_config.json"
        self.voice_model_path = os.path.join(
            VOICES_DIR, "en_US-libritts_r-medium", "en_US-libritts_r-medium.onnx"
        )
        self.default_voice_model_path = os.path.join(
            VOICES_DIR, "en_US-libritts_r-medium", "en_US-libritts_r-medium.onnx"
        )
        self.male_voice_model_path = os.path.join(
            VOICES_DIR, "en_US-hfc_male-medium", "en_US-hfc_male-medium.onnx"
        )
        self.max_speakers = 10
        self.libritts_synthesis_params = {
            "length_scale": 1.0,
            "noise_scale": 0.333,
            "noise_w": 0.333,
        }
        self.cori_high_params = {
            "length_scale": 1.0,
            "noise_scale": 0.333,
            "noise_w": 0.333,
        }
        self.male_synthesis_params = {
            "length_scale": 0.8,
            "noise_scale": 0.333,
            "noise_w": 0.8,
        }

        self.approved_speakers = self.load_approved_speakers()
        self.speaker_configs = {}
        self.name_to_speaker = {}
        self.pending_names = set()  # Names seen but not yet assigned a speaker
        self.override_speaker = None
        self.last_text = ""
        self.output_file = OUTPUT_WAV
        self.is_processing = False
        self.current_emotions = []
        self.cache_dir = CACHE_DIR

        self.emotion_sounds_dir = EMOTION_SOUNDS_DIR
        os.makedirs(self.emotion_sounds_dir, exist_ok=True)

        # Keys match the emotion_tag strings used in emotion_patterns exactly
        self.emotion_sound_map = {
            "moan": "soft_moan.wav",
            "moans": "soft_moan.wav",
            "laugh": "laughs.wav",
            "laughs": "laughs.wav",
            "chuckles": "chuckles.wav",
            "chuckle": "chuckles.wav",
            "giggle": "giggles.wav",
            "giggles": "giggles.wav",
            "sigh": "sigh.wav",
            "sighs": "sigh.wav",
            "groan": "groan.wav",
            "groans": "groan.wav",
            "gasp": "gasp.wav",
            "gasps": "gasp.wav",
            "yawn": "yawn.wav",
            "yawns": "yawn.wav",
            "cough": "coughs.wav",
            "coughs": "coughs.wav",
            "hmm": "hmm.wav",
            "mmmm": "mmmm.wav",
            "yell": "yell.wav",
            "slurp": "slurp.wav",
            "slurps": "slurp.wav",
            "mhmm": "mhmm.wav",
            "ah": "ah.wav",
            "pants": "pants.wav",
            "panting": "pants.wav",
            "sniffle": "sniffle.wav",
            "sniffles": "sniffle.wav",
        }

        self.short_whitelist = [
            "I",
            "I'm",
            "Yes",
            "No",
            "What?",
            "Huh?",
            "Okay.",
            "Sure.",
            "Why?",
            "How?",
            "Thanks.",
            "Sorry.",
            "Hey!",
            "Wait!",
            "Stop!",
            "Go.",
            "Run!",
            "Help!",
        ]

        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=256)
        except Exception as e:
            logger.error(f"Failed to initialize pygame mixer: {e}")

        self.rebuild_speaker_configs()
        self.load_config()

        self.enable_gui = True

        atexit.register(self.cleanup_files)

    def cleanup_files(self):
        try:
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
                logger.info(f"Cleaned up output file: {self.output_file}")
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")

    def load_approved_speakers(self):
        try:
            with open("approved_speakers.txt", "r", encoding="utf-8") as f:
                content = f.read().strip()
            raw_ids = re.split(r"[;\s,]+", content)
            speaker_ids = [int(raw.strip()) for raw in raw_ids if raw.strip().isdigit()]
            logger.info(f"Loaded {len(speaker_ids)} approved speakers")
            return speaker_ids
        except Exception as e:
            logger.error(f"Failed to load approved speakers: {e}")
            return []

    def rebuild_speaker_configs(self):
        num_available = len(self.approved_speakers)
        for i in range(1, self.max_speakers + 1):
            speaker = f"Speaker{i}"
            if speaker not in self.speaker_configs:
                self.speaker_configs[speaker] = {"id": 0}

            idx = i - 1
            default_id = (
                self.approved_speakers[idx] if idx < num_available else 198 + idx * 10
            )

            current_id = self.speaker_configs[speaker].get("id", 0)
            if not (1 <= current_id <= 902):
                self.speaker_configs[speaker]["id"] = default_id
            else:
                self.speaker_configs[speaker]["id"] = current_id

        logger.info(f"Rebuilt {len(self.speaker_configs)} speaker configs")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                loaded_speakers = config.get("speaker_configs", {})
                for speaker, data in loaded_speakers.items():
                    if speaker in self.speaker_configs:
                        self.speaker_configs[speaker]["id"] = data.get(
                            "id", self.speaker_configs[speaker]["id"]
                        )
                self.name_to_speaker = config.get(
                    "name_to_speaker", self.name_to_speaker
                )
                logger.info(f"Loaded {len(self.name_to_speaker)} name mappings")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

    def save_config(self):
        config = {
            "speaker_configs": self.speaker_configs,
            "name_to_speaker": self.name_to_speaker,
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
            logger.info("Saved config to JSON")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def launch_gui(self):
        self.rebuild_speaker_configs()
        self.gui_root = tk.Tk()
        self.gui_root.title("VisualNovelTTS - Character Name Manager")
        self.gui_root.geometry("860x640")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#f9f9f9", foreground="black")
        style.configure("TButton", padding=5)
        style.configure("TLabelframe", background="#e0e8ff", foreground="navy")
        style.configure("Pending.TLabelframe", background="#fff4e0", foreground="#7a4500")
        style.map("Pending.TLabelframe", background=[("", "#fff4e0")])
        self.gui_root.configure(bg="#E8F0FF")

        # Root grid: two columns — left (main controls) and right (unassigned names)
        self.gui_root.columnconfigure(0, weight=3)
        self.gui_root.columnconfigure(1, weight=1, minsize=190)
        self.gui_root.rowconfigure(0, weight=1)

        # ── LEFT COLUMN ──────────────────────────────────────────────────────
        left_frame = ttk.Frame(self.gui_root, padding="10")
        left_frame.grid(row=0, column=0, sticky="nsew")
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        left_frame.rowconfigure(2, weight=1)

        # Override speaker
        override_frame = ttk.LabelFrame(
            left_frame, text="Override Speaker (for testing)", padding="10"
        )
        override_frame.grid(row=0, column=0, sticky="ew", pady=(10, 5))
        ttk.Label(override_frame, text="Force all dialogue to use:").grid(
            row=0, column=0, padx=5
        )
        self.speaker_var = tk.StringVar(value="None")
        ttk.Combobox(
            override_frame,
            textvariable=self.speaker_var,
            values=("None",) + tuple(sorted(self.speaker_configs.keys())),
            state="readonly",
            width=15,
        ).grid(row=0, column=1, padx=5)

        # Speaker Voice IDs
        speaker_frame = ttk.LabelFrame(
            left_frame, text="Speaker Voice IDs (1-902)", padding="10"
        )
        speaker_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 5))
        speaker_frame.columnconfigure(0, weight=1)
        speaker_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(speaker_frame, bg="#e0e8ff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            speaker_frame, orient="vertical", command=canvas.yview
        )
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.speaker_id_entries = {}
        speakers_sorted = sorted(self.speaker_configs.keys())
        cols_per_row = 2  # pairs of (label + entry) side by side
        for i, speaker in enumerate(speakers_sorted):
            row, col = i // cols_per_row, (i % cols_per_row) * 2
            ttk.Label(scrollable_frame, text=f"{speaker}:").grid(
                row=row, column=col, padx=(10, 2), pady=2, sticky=tk.E
            )
            entry = ttk.Entry(scrollable_frame, width=8)
            entry.insert(0, str(self.speaker_configs[speaker]["id"]))
            entry.grid(row=row, column=col + 1, padx=(2, 12), pady=2, sticky=tk.W)
            self.speaker_id_entries[speaker] = entry

        # Character Name → Speaker Assignments
        names_frame = ttk.LabelFrame(
            left_frame, text="Character Name → Speaker Assignments", padding="10"
        )
        names_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 5))
        names_frame.columnconfigure(0, weight=1)
        names_frame.columnconfigure(1, weight=1)
        names_frame.columnconfigure(2, weight=1)
        names_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(names_frame)
        list_frame.grid(row=0, column=0, columnspan=3, sticky="nsew")
        names_frame.rowconfigure(0, weight=1)

        names_scrollbar = Scrollbar(list_frame)
        names_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.names_listbox = Listbox(
            list_frame, height=7, yscrollcommand=names_scrollbar.set
        )
        self.names_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        names_scrollbar.config(command=self.names_listbox.yview)
        self.update_names_listbox()

        ttk.Label(names_frame, text="Character Name:").grid(
            row=1, column=0, padx=5, pady=5, sticky=tk.E
        )
        self.name_entry = ttk.Entry(names_frame, width=18)
        self.name_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(names_frame, text="Speaker:").grid(
            row=2, column=0, padx=5, pady=5, sticky=tk.E
        )
        self.assign_var = tk.StringVar(value="Speaker1")
        self.assign_dropdown = ttk.Combobox(
            names_frame,
            textvariable=self.assign_var,
            values=tuple(sorted(self.speaker_configs.keys())),
            state="readonly",
            width=15,
        )
        self.assign_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)

        button_frame = ttk.Frame(names_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=5)
        ttk.Button(
            button_frame, text="Add/Update", command=self.add_update_name, width=13
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            button_frame, text="Delete Selected", command=self.delete_name, width=13
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            button_frame, text="Clear Selection", command=self.clear_selection, width=13
        ).pack(side=tk.LEFT, padx=4)

        self.names_listbox.bind("<<ListboxSelect>>", self.on_name_select)

        # Bottom action buttons
        bottom_frame = ttk.Frame(left_frame)
        bottom_frame.grid(row=3, column=0, pady=10)
        ttk.Button(
            bottom_frame, text="Apply & Save", command=self.apply_configuration, width=18,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            bottom_frame, text="Apply & Restart", command=self.apply_and_restart, width=18,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            bottom_frame, text="Reload Config", command=self.reload_config, width=18,
        ).pack(side=tk.LEFT, padx=5)

        # ── RIGHT COLUMN — Unassigned Names ──────────────────────────────────
        right_frame = ttk.LabelFrame(
            self.gui_root,
            text="⚠ Unassigned Names",
            padding="10",
            style="Pending.TLabelframe",
        )
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        ttk.Label(
            right_frame,
            text="Names without a speaker\nClick to prefill the form →",
            background="#fff4e0",
            foreground="#7a4500",
            font=("TkDefaultFont", 8),
            justify="center",
        ).grid(row=0, column=0, pady=(0, 5))

        pending_list_frame = ttk.Frame(right_frame)
        pending_list_frame.grid(row=1, column=0, sticky="nsew")
        pending_list_frame.columnconfigure(0, weight=1)
        pending_list_frame.rowconfigure(0, weight=1)

        pending_scrollbar = Scrollbar(pending_list_frame)
        pending_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pending_listbox = Listbox(
            pending_list_frame,
            height=20,
            yscrollcommand=pending_scrollbar.set,
            bg="#fff8ee",
            fg="#7a4500",
            selectbackground="#f5c97a",
            selectforeground="#3a2000",
            relief="flat",
            borderwidth=1,
        )
        self.pending_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pending_scrollbar.config(command=self.pending_listbox.yview)
        self.pending_listbox.bind("<<ListboxSelect>>", self.on_pending_select)

        pending_btn_frame = ttk.Frame(right_frame)
        pending_btn_frame.grid(row=2, column=0, pady=(6, 0))
        ttk.Button(
            pending_btn_frame,
            text="Clear All",
            command=self.clear_all_pending,
            width=14,
        ).pack()

        self.update_pending_listbox()

        self.gui_root.protocol("WM_DELETE_WINDOW", self.on_gui_close)

    def update_names_listbox(self):
        self.names_listbox.delete(0, tk.END)
        for name, speaker in sorted(self.name_to_speaker.items()):
            self.names_listbox.insert(tk.END, f"{name} → {speaker}")

    def on_name_select(self, event):
        selection = self.names_listbox.curselection()
        if selection:
            selected = self.names_listbox.get(selection[0])
            name = selected.split(" → ")[0]
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, name)
            self.assign_var.set(self.name_to_speaker[name])

    def add_update_name(self):
        name = self.name_entry.get().strip()
        speaker = self.assign_var.get()
        if name and speaker in self.speaker_configs:
            self.name_to_speaker[name] = speaker
            self.pending_names.discard(name)  # Remove from unassigned if present
            self.update_names_listbox()
            self.update_pending_listbox()
            messagebox.showinfo("Success", f"Assigned: {name} → {speaker}")
            self.clear_selection()
        else:
            messagebox.showerror("Error", "Invalid name or speaker")

    def delete_name(self):
        selection = self.names_listbox.curselection()
        if selection:
            selected = self.names_listbox.get(selection[0])
            name = selected.split(" → ")[0]
            if messagebox.askyesno("Confirm Delete", f"Delete mapping for '{name}'?"):
                del self.name_to_speaker[name]
                self.update_names_listbox()
                self.clear_selection()
                messagebox.showinfo("Deleted", f"Removed mapping for '{name}'")
        else:
            messagebox.showwarning("No Selection", "Please select a name to delete")

    def clear_selection(self):
        self.names_listbox.selection_clear(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.assign_var.set("Speaker1")

    def update_pending_listbox(self):
        """Refresh the unassigned-names listbox on the right panel."""
        if not hasattr(self, "pending_listbox"):
            return
        self.pending_listbox.delete(0, tk.END)
        for name in sorted(self.pending_names):
            self.pending_listbox.insert(tk.END, name)

    def on_pending_select(self, event):
        """Clicking an unassigned name prefills the assignment form on the left."""
        selection = self.pending_listbox.curselection()
        if selection:
            name = self.pending_listbox.get(selection[0])
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, name)
            self.assign_var.set(self.name_to_speaker.get(name, "Speaker1"))

    def dismiss_pending_name(self):
        """Remove a single name from the pending list without assigning a speaker."""
        selection = self.pending_listbox.curselection()
        if selection:
            name = self.pending_listbox.get(selection[0])
            self.pending_names.discard(name)
            self.update_pending_listbox()

    def clear_all_pending(self):
        """Clear all unassigned names from the pending list."""
        self.pending_names.clear()
        self.update_pending_listbox()

    def apply_configuration(self):
        try:
            self.override_speaker = (
                self.speaker_var.get() if self.speaker_var.get() != "None" else None
            )
            for speaker, entry in self.speaker_id_entries.items():
                sid = int(entry.get().strip())
                if not (1 <= sid <= 902):
                    raise ValueError(f"Speaker ID for {speaker} must be 1–902")
                self.speaker_configs[speaker]["id"] = sid
            self.save_config()
            messagebox.showinfo("Success", "Configuration applied and saved!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def apply_and_restart(self):
        self.apply_configuration()
        logger.info("Restarting script...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def reload_config(self):
        self.load_config()
        self.rebuild_speaker_configs()
        self.update_names_listbox()
        for speaker, entry in self.speaker_id_entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(self.speaker_configs[speaker]["id"]))
        messagebox.showinfo("Reloaded", "Config reloaded from file!")

    def on_gui_close(self):
        self.cleanup_files()
        self.gui_root.destroy()
        os._exit(0)

    def extract_emotions_from_text(self, text: str):
        """
        Extract emotion tags from `text`.
        Returns the cleaned text (tags removed) and a list of tuples
        `(position_in_cleaned_text, emotion_tag)`.
        """
        # Patterns mapping to tags. None means "verwijderen maar geen emotietag".
        emotion_patterns = [
            (re.compile(r"\*Soft\s+Moan\*", re.I), "soft_moan"),
            (re.compile(r"\*(?:haha|ha+aha)?(?:ha|haha)+(?:\s+(?:ha|haha))*\*", re.I), "laugh"),
            (re.compile(r"\*(?:e+he)?he+ehe(?:\s+he+)*\*", re.I), "laugh"),
            (re.compile(r"\*chuckle+s?\*", re.I), "chuckles"),
            (re.compile(r"\*laugh+s?\*", re.I), "laugh"),
            (re.compile(r"\*giggle+s?\*", re.I), "giggle"),
            (re.compile(r"\*sigh+s?\*", re.I), "sigh"),
            (re.compile(r"\*groan+s?\*", re.I), "groan"),
            (re.compile(r"\*gasp+s?\*", re.I), "gasp"),
            (re.compile(r"\*yawn+s?\*", re.I), "yawn"),
            (re.compile(r"\*moan+s?\*", re.I), "moan"),
            (re.compile(r"\*cough+s?\*", re.I), "coughs"),
            (re.compile(r"\*sniffle+s?\*", re.I), "sniffle"),
            (re.compile(r"\*aA{2,}h+H\*", re.I), "mmmm"),
            (re.compile(r"\*pant+s?\*", re.I), "pants"),
            (re.compile(r"\*(?:m+)?moan+s+ing?\*", re.I), "moan"),
            (re.compile(r"\*slurp+s?\*", re.I), "slurp"),
            (re.compile(r"\*ah+H\*", re.I), "ah"),
            # generieke *...* die niet in bovenstaande vallen → altijd weghalen
            (re.compile(r"\*[^*]+\*", re.I), None),
            # text only ("bareword" -- not asterisk)
            (re.compile(r"\b(?:e+he)?he+ehe(?:\s+he+)*\b", re.I), "laugh"),
            (re.compile(r"\bchuckle+s?\b", re.I), "chuckles"),
            (re.compile(r"\blaugh+s?\b", re.I), "laugh"),
            (re.compile(r"\bgiggle+s?\b", re.I), "giggle"),
            (re.compile(r"\bsigh+s?\b", re.I), "sigh"),
            (re.compile(r"\bgroan+s?\b", re.I), "groan"),
            (re.compile(r"\bgasp+s?\b", re.I), "gasp"),
            (re.compile(r"\byawn+s?\b", re.I), "yawn"),
            (re.compile(r"\bmoan+s?\b", re.I), "moan"),
            (re.compile(r"\bcough+s?\b", re.I), "coughs"),
            (re.compile(r"\bsniffle+s?\b", re.I), "sniffle"),
            (re.compile(r"\baA{2,}h+H\b", re.I), "mmmm"),
            #(re.compile(r"\bpant+s?\b", re.I), "pants"),
            (re.compile(r"\b(?:m+)?moan+s+ing?\b", re.I), "moan"),
            (re.compile(r"\bslurp+s?\b", re.I), "slurp"),
            (re.compile(r"\bah+H\b", re.I), "ah"),
            (re.compile(r"\ba+ha+(?:\s+ha+)*\b", re.I), "laugh"),
            (re.compile(r"\b(Haha|haha)\b", re.I), "chuckles"),
            (re.compile(r"\b(e+)?hh+(?:\s+eh+)*\b", re.I), "chuckle"),
            (re.compile(r"\b(h+)?hmpf+(?:\s+hmpfh+)*\b", re.I), "groan"),
            (re.compile(r"\b[aA]{2,}h+\b", re.I), "yell"),
            (re.compile(r"\b(h+)?hm{2,}(?:\s+hmz+)*\b", re.I), "hmm"),
            (re.compile(r"\b(p+)?pant+s+ing?\b", re.I), "pants"),
            (re.compile(r"\b(m+)?moan+s+ing?\b", re.I), "moan"),
            (re.compile(r"\b([a-zA-Z])\1{3,}\b", re.I), None),  # remove only
            (re.compile(r"\bm{3,}\b", re.I), "mmmm"),
        ]

        raw_matches: list[tuple[int, int, str | None]] = []
        for pattern, tag in emotion_patterns:
            for m in pattern.finditer(text):
                start, end = m.span()
                raw_matches.append((start, end, tag))

        # sort by original position
        raw_matches.sort(key=lambda t: t[0])

        cleaned_parts: list[str] = []
        positions: list[tuple[int, str]] = []
        removed = 0
        last_idx = 0
        for start, end, tag in raw_matches:
            # Skip overlapping matches (bijv. "*pant*" en bare "pant" daarbinnen).
            # We houden alleen de eerste (meestal specifieke) match.
            if start < last_idx:
                continue
            cleaned_parts.append(text[last_idx:start])
            pos_in_cleaned = start - removed
            if tag is not None:
                positions.append((pos_in_cleaned, tag))
            last_idx = end
            removed += end - start

        cleaned_parts.append(text[last_idx:])
        cleaned_text = "".join(cleaned_parts)
        # Veiligheidsnet: haal eventueel overgebleven losse '*' weg
        cleaned_text = cleaned_text.replace("*", "")
        return cleaned_text, positions

    def clean_dialog_text(self, raw_text: str) -> str:
        if not raw_text or not raw_text.strip():
            return ""
        text = raw_text.strip()
        text = re.sub(r"\{[^}]+\}", "", text)
        text = re.sub(r"\[[^]]*\](?!:)", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        # Removed stripping of asterisks to preserve emotion-only content; emotions are
        # extracted later in `process_text` after the speaker has been resolved.

        speaker_match = re.match(
            r"^\[(Speaker\d+|default)\]:\s*(.*)$", text, re.IGNORECASE
        )
        if speaker_match:
            speaker, content = speaker_match.groups()
            return f"[{speaker}]: {content.strip()}" if content.strip() else ""

        for name, speaker in self.name_to_speaker.items():
            if text.lower().startswith(f"{name.lower()}:"):
                content = text[len(name) + 1 :].strip()
                return f"[{speaker}]: {content}" if content else ""

        # Detect "Name: dialogue" patterns where the name has no speaker assigned yet
        name_tag_match = re.match(r"^([A-Za-z][A-Za-z0-9 '_\-]{0,29}):\s+\S", text)
        if name_tag_match:
            detected_name = name_tag_match.group(1).strip()
            known_names_lower = {n.lower() for n in self.name_to_speaker}
            if (
                detected_name.lower() not in known_names_lower
                and detected_name.lower() not in ("default", "narrator")
            ):
                # Auto-assign to the next available speaker slot (up to max_speakers)
                used_speakers = set(self.name_to_speaker.values())
                next_speaker = None
                for i in range(1, self.max_speakers + 1):
                    candidate = f"Speaker{i}"
                    if candidate not in used_speakers:
                        next_speaker = candidate
                        break

                if next_speaker:
                    self.name_to_speaker[detected_name] = next_speaker
                    self.save_config()
                    logger.info(f"Auto-mapped '{detected_name}' \u2192 {next_speaker}")
                    content = text[len(detected_name) + 1:].strip()
                    if hasattr(self, "gui_root"):
                        self.gui_root.after(0, self.update_names_listbox)
                    return f"[{next_speaker}]: {content}" if content else ""
                else:
                    # All speaker slots taken — add to pending for manual assignment
                    if detected_name not in self.pending_names:
                        self.pending_names.add(detected_name)
                        if hasattr(self, "gui_root"):
                            self.gui_root.after(0, self.update_pending_listbox)

        return text

    def get_voice_model(self, text):
        if self.override_speaker and text.startswith(f"[{self.override_speaker}]:"):
            clean_text = text.replace(f"[{self.override_speaker}]:", "").strip()
            return self.voice_model_path, clean_text, self.override_speaker

        for speaker in self.speaker_configs:
            if text.startswith(f"[{speaker}]:"):
                clean_text = text.replace(f"[{speaker}]:", "").strip()
                return self.voice_model_path, clean_text, speaker

        for name, speaker in self.name_to_speaker.items():
            if text.lower().startswith(f"{name.lower()}:"):
                content = text[len(name) + 1 :].strip()
                if name.lower() == "narrator":
                    return self.male_voice_model_path, content, "narrator"
                else:
                    return self.voice_model_path, content, speaker

        if text.lower().startswith("narrator:"):
            content = text[len("Narrator:"):].strip()
            return self.male_voice_model_path, content, "narrator"

        return self.default_voice_model_path, text, "default"

    def play_emotion_sound(self, emotion_tag: str):
        sound_file = self.emotion_sound_map.get(emotion_tag)
        if not sound_file:
            logger.warning(f"No sound file mapped for emotion: {emotion_tag}")
            return False

        base_name = os.path.splitext(sound_file)[0]
        sound_path = None
        for ext in [".wav", ".mp3"]:
            potential_path = os.path.join(self.emotion_sounds_dir, base_name + ext)
            if os.path.exists(potential_path):
                sound_path = potential_path
                break

        if not sound_path:
            logger.warning(
                f"Emotion sound file not found: {base_name}.wav or {base_name}.mp3 in {self.emotion_sounds_dir}"
            )
            return False
        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            return True
        except Exception as e:
            logger.error(f"Error playing emotion sound {sound_path}: {e}")
            try:
                subprocess.run(
                    ["start", "/min", sound_path], shell=True, check=False, timeout=2
                )
                time.sleep(0.5)
                return True
            except Exception:
                return False

    def process_text(self, text):
        if self.is_processing or not text.strip():
            return
        self.is_processing = True
        #logger.debug(f"Processing: {text[:50]}...")

        try:
            model_path, base_text, speaker = self.get_voice_model(text)
            clean_text, emotions = self.extract_emotions_from_text(base_text)
            self.current_emotions = emotions
            speaker_id = (
                self.speaker_configs.get(speaker, {"id": 0})["id"]
                if speaker != "default"
                else 0
            )
            #logger.debug(f"Speaker: {speaker}, Speaker ID: {speaker_id}")
            # If there are no words and only emotions, play them sequentially
            if not clean_text.strip() and emotions:
                for _, tag in sorted(emotions):
                    self.play_emotion_sound(tag)
                return
            #logger.debug(f"Emotions: {emotions}")
            def _synthesize_and_play(segment: str):
                if not segment.strip():
                    return
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".txt",
                    delete=False,
                    dir=r"C:\\Piper\\temp",
                ) as f_seg:
                    f_seg.write(segment)
                    seg_path = f_seg.name
                seg_hash = hashlib.md5((segment + speaker).encode()).hexdigest()
                seg_wav = os.path.join(self.cache_dir, f"{seg_hash}.wav")
                if os.path.exists(seg_wav):
                    shutil.copyfile(seg_wav, self.output_file)
                else:
                    params = (
                        self.libritts_synthesis_params
                        if model_path == self.voice_model_path
                        else (
                            self.male_synthesis_params
                            if model_path == self.male_voice_model_path
                            else self.cori_high_params
                        )
                    )
                    #logger.debug(f"Command: {cmd}")
                    cmd = (
                        f'type "{seg_path}" | PIPER_EXE '
                        f'-m "{model_path}" -f "{self.output_file}" --speaker {speaker_id} '
                        f"--length_scale {params['length_scale']} "
                        f"--noise_scale {params['noise_scale']} "
                        f"--noise_w {params['noise_w']}"
                    )
                    subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        cwd=os.path.dirname(PIPER_EXE),
                        timeout=30,
                    )
                    os.unlink(seg_path)
                    if os.path.exists(self.output_file):
                        shutil.copyfile(self.output_file, seg_wav)
                sound = pygame.mixer.Sound(self.output_file)
                sound.play()
                time.sleep(sound.get_length() + 0.1)
                if os.path.exists(self.output_file):
                    os.remove(self.output_file)

            last_pos = 0
            for pos, tag in sorted(emotions):
                _synthesize_and_play(clean_text[last_pos:pos])
                self.play_emotion_sound(tag)
                last_pos = pos
            _synthesize_and_play(clean_text[last_pos:])

        except Exception as e:
            #logger.debug(f"Exception: {e}")
            logger.error(f"Playback error: {e}")
        finally:
            self.is_processing = False
            self.current_emotions = []

    def check_clipboard(self):
        try:
            text = pyperclip.paste().strip()
            if not text or text == self.last_text:
                return

            is_short = any(
                text.lower().startswith(s.lower()) for s in self.short_whitelist
            ) or re.match(r"^[A-Za-z]{1,2}[.!?]?$", text)
            has_vn_pattern = any(
                re.search(p, text)
                for p in [r"\[.*?\]", r"\{.*?\}", r".*?:", r"「.*?」"]
            )

            if is_short or has_vn_pattern or len(text) >= 2:
                cleaned = self.clean_dialog_text(text)
                if cleaned and cleaned != self.last_text:
                    self.process_text(cleaned)
                    self.last_text = cleaned
        except Exception as e:
            logger.error(f"Clipboard error: {e}")
            #logger.debug(f"Exception: {e}")
    def polling_loop(self):
        logger.info("Polling loop GESTART - zou nu moeten blijven draaien")
        last_check = time.time()

        while True:
            if time.time() - last_check >= 0.1:
                self.check_clipboard()
                last_check = time.time()
            time.sleep(0.01)

    def run(self):
        logger.info("run() aangeroepen")
        if self.enable_gui:
            logger.warning("GUI-modus actief - Tkinter wordt gestart")
            try:
                self.launch_gui()
            except Exception as e:
                logger.error(f"GUI launch failed: {e}", exc_info=True)
                raise
            threading.Thread(target=self.polling_loop, daemon=True).start()
            self.gui_root.mainloop()
        else:
            logger.info("Geen GUI → start polling loop direct")
            self.polling_loop()


if __name__ == "__main__":
    tts = VNReader()
    tts.run()
