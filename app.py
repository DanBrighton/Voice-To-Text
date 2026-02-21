import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config import ConfigReader
from stt_worker import VoskSTTWorker
from audio_devices import (
    list_input_devices,
    get_default_input_device_index,
    safe_sample_rate_for_device,
)


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

        self._input_devices = []
        self._build_ui()

        self._cfg = ConfigReader()
        self.model_var.set(self._cfg.get_value("model_path") or "")
        self.sr_var.set(str(self._cfg.get_value("sample_rate") or 16000))

        self._refresh_devices()
        self._poll_ui_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        # Model path
        ttk.Label(top, text="Model folder:").grid(row=0, column=0, sticky="w")
        self.model_var = tk.StringVar(value="")
        self.model_entry = ttk.Entry(top, textvariable=self.model_var, width=60)
        self.model_entry.grid(row=0, column=1, sticky="we", padx=5)

        ttk.Button(top, text="Browse…", command=self._browse_model).grid(row=0, column=2, padx=5)
        ttk.Button(top, text="Refresh devices", command=self._refresh_devices).grid(row=0, column=3, padx=5)

        # Device
        ttk.Label(top, text="Input device:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(top, textvariable=self.device_var, state="readonly", width=60)
        self.device_combo.grid(row=1, column=1, sticky="we", padx=5, pady=(8, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_changed)

        # Sample rate
        ttk.Label(top, text="Sample rate:").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.sr_var = tk.StringVar(value="16000")
        self.sr_entry = ttk.Entry(top, textvariable=self.sr_var, width=10)
        self.sr_entry.bind("<FocusOut>", self._on_sample_rate_changed)
        self.sr_entry.bind("<Return>", self._on_sample_rate_changed)
        self.sr_entry.grid(row=1, column=3, sticky="w", padx=5, pady=(8, 0))

        # Start/Stop
        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=4, sticky="w", pady=(12, 0))

        self.start_btn = ttk.Button(btns, text="Start", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side=tk.LEFT)

        top.columnconfigure(1, weight=1)

        # Status
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0)).pack(side=tk.TOP, anchor="w")

        # Partial line
        partial_frame = ttk.Frame(self, padding=(10, 5))
        partial_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(partial_frame, text="Live:").pack(side=tk.LEFT)
        self.partial_var = tk.StringVar(value="")
        ttk.Label(partial_frame, textvariable=self.partial_var).pack(side=tk.LEFT, padx=(6, 0))

        # Transcript + scrollbar
        mid = ttk.Frame(self, padding=10)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.text = tk.Text(mid, wrap="word")
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(mid, command=self.text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.configure(yscrollcommand=scroll.set)

        # Bottom buttons
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(bottom, text="Clear", command=self._clear).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Save transcript…", command=self._save).pack(side=tk.LEFT, padx=(8, 0))

    def _browse_model(self):
        path = filedialog.askdirectory(title="Select Vosk model folder")
        if path:
            self.model_var.set(path)
            self._cfg.update_value("model_path", path)

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

        # Save device index
        self._cfg.update_value("sound_device_index", str(idx))

        # Optionally auto-update sample rate when device changes.
        # If you want to preserve a manually-set sample rate, remove this call.
        self._update_sample_rate()

        # If you DO auto-update, save it too:
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

        self.worker.start(model_path=model_path, device_index=device_idx, sample_rate=sample_rate)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("Starting...")

    def _stop(self):
        self.worker.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _clear(self):
        self.text.delete("1.0", tk.END)
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
                    self.status_var.set(payload)
                elif msg_type == "partial":
                    self.partial_var.set(payload)
                elif msg_type == "final":
                    self.text.insert(tk.END, payload + "\n")
                    self.text.see(tk.END)
        except queue.Empty:
            pass

        # Ensure buttons return to normal if worker exits unexpectedly
        if not self.worker.is_running():
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

        self.after(50, self._poll_ui_queue)

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