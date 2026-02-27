import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import json

from config import ConfigReader
from stt_worker import VoskSTTWorker
from audio_devices import (
    list_input_devices,
    get_default_input_device_index,
    safe_sample_rate_for_device,
)
from rules_engine import load_rules_json, RuleEngine
from rules_editor import RulesEditor


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Offline Live Speech-to-Text (Vosk)")
        self.geometry("900x600")

        # Thread-safe queue to receive updates from worker
        self._ui_q = queue.Queue()

        self.worker = VoskSTTWorker(
            on_partial=lambda txt: self._ui_q.put(("partial", txt)),
            on_final=lambda txt: self._ui_q.put(("final", txt)),
            on_status=lambda txt: self._ui_q.put(("status", txt)),
        )

        # Build UI
        self._input_devices = []
        self._build_ui()

        # Load Configuration
        self._cfg = ConfigReader()
        self.model_var.set(self._cfg.get_value("model_path") or "")
        self.sr_var.set(str(self._cfg.get_value("sample_rate") or 16000))

        # Load rules
        self.rules_path = "rules.json"
        self._rules_cache = []  # list[dict]
        self._load_rules()

        # Load audio devices
        self._refresh_devices()

        # Start thread work queue
        self._poll_ui_queue()

        # Bind close to on close function
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)
        row = 0

        # Model path
        ttk.Label(top, text="Model folder:").grid(row=row, column=0, sticky="w")
        self.model_var = tk.StringVar(value="")
        self.model_entry = ttk.Entry(top, textvariable=self.model_var, width=60)
        self.model_entry.grid(row=row, column=1, sticky="we", padx=5)

        ttk.Button(top, text="Browse…", command=self._browse_model).grid(row=row, column=2, padx=5)
        row += 1

        # Device
        ttk.Label(top, text="Input device:").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(top, textvariable=self.device_var, state="readonly", width=60)
        self.device_combo.grid(row=row, column=1, sticky="we", padx=5, pady=(8, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_changed)
        ttk.Button(top, text="Refresh devices", command=self._refresh_devices).grid(row=row, column=2, padx=5, pady=(8, 0))
        row += 1

        # Sample rate
        ttk.Label(top, text="Sample rate:").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self.sr_var = tk.StringVar(value="16000")
        self.sr_entry = ttk.Entry(top, textvariable=self.sr_var, width=10)
        self.sr_entry.bind("<FocusOut>", self._on_sample_rate_changed)
        self.sr_entry.bind("<Return>", self._on_sample_rate_changed)
        self.sr_entry.grid(row=row, column=1, sticky="w", padx=5, pady=(8, 0))
        row += 1

        # Button Controls
        btns = ttk.Frame(top)
        btns.grid(row=row, column=0, columnspan=4, sticky="w", pady=(12, 0))

        self.preload_btn = ttk.Button(btns, text="Preload", command=self._preload_model)
        self.preload_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.start_btn = ttk.Button(btns, text="Start", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.pause_btn = ttk.Button(btns, text="Pause", command=self._pause, state="disabled")
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.resume_btn = ttk.Button(btns, text="Resume", command=self._resume, state="disabled")
        self.resume_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.clear_btn = ttk.Button(btns, text="Clear", command=self._clear)
        self.clear_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.save_btn = ttk.Button(btns, text="Save transcript", command=self._save)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.rules_btn = ttk.Button(btns, text="Edit Rules", command=self._open_rules_editor)
        self.rules_btn.pack(side=tk.LEFT, padx=(0, 8))

        top.columnconfigure(1, weight=1)

        # Status
        self.status_var = tk.StringVar(value="Idle.")
        self.status_var2 = tk.StringVar(value="-")
        self.status_var3 = tk.StringVar(value="-")

        self.status_lbl1 = ttk.Label(self, textvariable=self.status_var, padding=(10, 0))
        self.status_lbl1.pack(side=tk.TOP, anchor="w")

        self.status_lbl2 = ttk.Label(self, textvariable=self.status_var2, padding=(10, 0))
        self.status_lbl2.pack(side=tk.TOP, anchor="w")

        self.status_lbl3 = ttk.Label(self, textvariable=self.status_var3, padding=(10, 0))
        self.status_lbl3.pack(side=tk.TOP, anchor="w")
        self.status_lbl3.configure(foreground="#888888")

        # Partial line
        partial_frame = ttk.Frame(self, padding=(10, 5))
        partial_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(partial_frame, text="Live:").pack(side=tk.LEFT)
        self.partial_var = tk.StringVar(value="")
        ttk.Label(partial_frame, textvariable=self.partial_var).pack(side=tk.LEFT, padx=(6, 0))

        # Transcript + scrollbar
        mid = ttk.Frame(self, padding=10)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.text = tk.Text(mid, wrap="word", state="disabled")
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(mid, command=self.text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.configure(yscrollcommand=scroll.set)

    def _browse_model(self):
        path = filedialog.askdirectory(title="Select Vosk model folder")
        if path:
            self.model_var.set(path)
            self._cfg.update_value("model_path", path)

    def _preload_model(self):
        model_path = self.model_var.get().strip()
        if not model_path:
            messagebox.showerror("Missing model", "Please select the Vosk model folder.")
            return

        # Disable button to prevent double-click preload
        self.preload_btn.configure(state="disabled")
        self.status_var.set("Preloading...")

        def _task():
            try:
                # Send status updates back through the same UI queue
                self._ui_q.put(("status", "Loading model..."))
                self.worker.preload_model(model_path)
                self._ui_q.put(("status", "Model loaded."))
            except Exception as e:
                self._ui_q.put(("status", f"Preload error: {e}"))
            finally:
                # Re-enable button from UI thread (via queue)
                self._ui_q.put(("ui", ("preload_btn", "normal")))

        threading.Thread(target=_task, daemon=True).start()

    def _refresh_devices(self):
        self._input_devices = list_input_devices()
        display = [f"{d['index']}: {d['name']}" for d in self._input_devices]

        if not display:
            self.device_combo["values"] = []
            self.device_var.set("")
            self.status_var.set("No input devices found.")
            return

        self.device_combo["values"] = display

        # 1) Try to use saved device index from config
        saved_idx = self._cfg.get_value("sound_device_index")
        chosen_idx = None

        if saved_idx not in (None, ""):
            try:
                saved_idx = int(saved_idx)
                for j, d in enumerate(self._input_devices):
                    if d["index"] == saved_idx:
                        chosen_idx = j
                        break
            except Exception:
                chosen_idx = None

        # 2) Fall back to system default input device
        if chosen_idx is None:
            default_in = get_default_input_device_index()
            chosen_idx = 0
            if default_in is not None:
                for j, d in enumerate(self._input_devices):
                    if d["index"] == default_in:
                        chosen_idx = j
                        break

        self.device_combo.current(chosen_idx)

        # Apply sample rate:
        # - If config has a non-zero sample_rate, keep it
        # - Otherwise auto-pick based on the device
        saved_sr = self._cfg.get_value("sample_rate") or 0
        try:
            saved_sr = int(saved_sr)
        except Exception:
            saved_sr = 0

        if saved_sr > 0:
            self.sr_var.set(str(saved_sr))
        else:
            self._update_sample_rate()

        self.status_var.set("Devices loaded.")

    def _selected_device_index(self):
        val = self.device_var.get().strip()
        if not val:
            return None
        try:
            return int(val.split(":")[0].strip())
        except Exception:
            return None
        
    def _on_device_changed(self, event=None):
        idx = self._selected_device_index()
        if idx is None:
            return

        # Save device configuration
        self._cfg.update_value("sound_device_index", str(idx))
        self._update_sample_rate()
        try:
            sr = int(self.sr_var.get().strip())
            self._cfg.update_value("sample_rate", sr)
        except Exception:
            pass

    def _on_sample_rate_changed(self, event=None):
        try:
            sr = int(self.sr_var.get().strip())
            if sr <= 0:
                raise ValueError
            self._cfg.update_value("sample_rate", sr)
        except Exception:
            messagebox.showerror("Invalid sample rate", "Sample rate must be a positive integer (e.g., 16000, 44100, 48000).")
            # Revert to something safe
            self.sr_var.set(str(self._cfg.get_value("sample_rate") or 16000))

    def _update_sample_rate(self):
        idx = self._selected_device_index()
        if idx is None:
            return
        sr = safe_sample_rate_for_device(idx, preferred=16000)
        self.sr_var.set(str(sr))

    def _start(self):
        model_path = self.model_var.get().strip()
        if not model_path:
            messagebox.showerror("Missing model", "Please select the Vosk model folder.")
            return

        device_idx = self._selected_device_index()
        if device_idx is None:
            messagebox.showerror("Missing device", "Please select a microphone input device.")
            return

        try:
            sample_rate = int(self.sr_var.get().strip())
            if sample_rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid sample rate", "Sample rate must be a positive integer (e.g., 16000).")
            return

        self.status_var.set("Starting...")
        self.worker.start(model_path=model_path, device_index=device_idx, sample_rate=sample_rate)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal")
        self.resume_btn.configure(state="disabled")

    def _stop(self):
        self.worker.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="disabled")

    def _pause(self):
        self.worker.pause()
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="normal")

    def _resume(self):
        self.worker.resume()
        self.pause_btn.configure(state="normal")
        self.resume_btn.configure(state="disabled")

    def _clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")
        self.partial_var.set("")

    def _save(self):
        path = filedialog.asksaveasfilename(
            title="Save transcript",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return
        content = self.text.get("1.0", tk.END).rstrip() + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.status_var.set(f"Saved: {path}")

    def _poll_ui_queue(self):
        try:
            while True:
                msg_type, payload = self._ui_q.get_nowait()
                if msg_type == "status":
                    self._push_status(payload)
                elif msg_type == "partial":
                    self.partial_var.set(payload)
                elif msg_type == "final":
                    self._append_transcript(payload)
                    self._process_rules(payload)
                elif msg_type == "ui":
                    widget_name, state = payload
                    if widget_name == "preload_btn":
                        self.preload_btn.configure(state=state)
        except queue.Empty:
            pass

        # Ensure buttons return to normal if worker exits unexpectedly
        if not self.worker.is_running():
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

        self.after(50, self._poll_ui_queue)

    def _append_transcript(self, line: str):
        self.text.configure(state="normal")
        self.text.insert(tk.END, line + "\n")
        self.text.see(tk.END)
        self.text.configure(state="disabled")

    def _push_status(self, text: str):
        if text == self.status_var.get():
            return
        self.status_var3.set(self.status_var2.get())
        self.status_var2.set(self.status_var.get())
        self.status_var.set(text)

    def _process_rules(self, text: str):
        def dispatch(action: str, param: str | None):
            if action == "status" and param:
                self._push_status(param)
            elif action == "pause":
                self._pause()
            elif action == "resume":
                self._resume()
            elif action == "stop":
                self._stop()
            elif action == "log" and param:
                self._append_transcript(f"[RULE] {param}")
            else:
                self._append_transcript(f"[RULE] Unknown action={action} param={param}")

        self.rules_engine.process(text, dispatch)

    def _load_rules(self):
        if not os.path.exists(self.rules_path):
            self._rules_cache = []
            return
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._rules_cache = data if isinstance(data, list) else []
        except Exception:
            self._rules_cache = []

    def _open_rules_editor(self):
        def on_saved(new_rules):
            # Called after editor saves to disk
            self._rules_cache = new_rules

        RulesEditor(self, self.rules_path, on_save_callback=on_saved)

    def _process_rules(self, text: str):
        t_lower = text.lower()

        for rule in self._rules_cache:
            if not rule.get("enabled", True):
                continue

            mt = (rule.get("match_type") or "contains").lower()
            pat = rule.get("pattern") or ""

            matched = False
            if mt == "contains":
                matched = pat.lower() in t_lower
            elif mt == "regex":
                import re
                matched = re.search(pat, text, flags=re.IGNORECASE) is not None

            if not matched:
                continue

            for a in rule.get("actions", []) or []:
                action = (a.get("action") or "").lower()
                param = a.get("param")

                if action == "status" and param:
                    self._push_status(str(param))
                elif action == "pause":
                    self._pause()
                elif action == "resume":
                    self._resume()
                elif action == "stop":
                    self._stop()
                elif action == "log" and param:
                    self._append_transcript(f"[RULE] {param}")

    def _on_close(self):
        try:
            self.worker.stop()
        except Exception:
            pass

        try:
            self._cfg.update_value("model_path", self.model_var.get().strip())
            self._cfg.update_value("sound_device_index", str(self._selected_device_index() or ""))
            self._cfg.update_value("sample_rate", int(self.sr_var.get().strip() or "16000"))
        except Exception:
            pass

        self.after(100, self.destroy)


if __name__ == "__main__":
    App().mainloop()