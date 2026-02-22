import json
import queue
import threading
import time

import sounddevice as sd
from vosk import Model, KaldiRecognizer


class VoskSTTWorker:
    """
    Offline speech-to-text worker using Vosk + sounddevice.

    Runs recognition in a background thread and reports results via callbacks:
      - on_status(str)
      - on_partial(str)
      - on_final(str)

    Notes:
    - UI frameworks (Tkinter) should NOT be updated from this worker thread.
      Use a queue in the UI layer.
    """

    def __init__(self, on_partial, on_final, on_status):
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_status = on_status

        self._stop_evt = threading.Event()
        self._thread = None
        self._audio_q = queue.Queue()
        self._stream = None

        self._model = None
        self._model_path = None
        self._sample_rate = None

        self._pause_evt = threading.Event()

    def preload_model(self, model_path: str):
        try:
            if self._model is not None and self._model_path == model_path:
                self.on_status("Model already loaded.")
                return

            self.on_status("Loading model...")
            self._model = Model(model_path)
            self._model_path = model_path
            self.on_status("Model loaded.")
        except Exception as e:
            self.on_status(f"Model preload failed: {e}")
            self._model = None
            self._model_path = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, model_path: str, device_index: int, sample_rate: int):
        if self.is_running():
            return

        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(model_path, device_index, sample_rate),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """
        Signals the worker loop to stop and closes the audio stream to help unblock reads.
        Safe to call multiple times.
        """
        self.on_status("Stopping...")
        self._stop_evt.set()
        try:
            if self._stream is not None:
                self._stream.close()
        except Exception:
            pass
        self.on_status("Stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.on_status(f"Audio status: {status}")
        # indata is a bytes-like object in RawInputStream when dtype=int16
        self._audio_q.put(bytes(indata))

    def _run(self, model_path: str, device_index: int, sample_rate: int):
        rec = None

        try:
            # Ensure model is loaded (preload step)
            if self._model is None or self._model_path != model_path:
                self.preload_model(model_path)

            if self._model is None:
                raise RuntimeError("Model failed to load (model is None).")

            model = self._model

            # Outer loop: re-open the stream on resume, exit on stop
            prev_partial = ""
            while not self._stop_evt.is_set():

                # If paused, wait here until resumed or stopped
                if self._pause_evt.is_set():
                    self.on_status("Paused.")
                    time.sleep(0.1)
                    continue

                rec = KaldiRecognizer(model, sample_rate)
                rec.SetWords(True)

                # Clear any stale audio before opening the mic
                self._clear_audio_queue()
                prev_partial = ""
                self.on_partial("")

                self.on_status("Opening microphone...")
                try:
                    self._stream = sd.RawInputStream(
                        samplerate=sample_rate,
                        blocksize=8000,
                        device=device_index,
                        dtype="int16",
                        channels=1,
                        callback=self._audio_callback,
                    )
                except Exception as e:
                    # If the stream can't open, wait a bit and retry unless stopped.
                    self.on_status(f"Failed to open microphone: {e}")
                    time.sleep(0.5)
                    continue

                # Inner loop: run while stream is open and not paused/stopped
                try:
                    with self._stream:
                        self.on_status("Listening...")
                        while not self._stop_evt.is_set() and not self._pause_evt.is_set():
                            try:
                                data = self._audio_q.get(timeout=0.1)
                            except queue.Empty:
                                continue

                            if rec.AcceptWaveform(data):
                                result = json.loads(rec.Result())
                                text = (result.get("text") or "").strip()
                                if text:
                                    self.on_final(text)
                                prev_partial = ""
                                self.on_partial("")
                            else:
                                partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                                if partial != prev_partial:
                                    self.on_partial(partial)
                                    prev_partial = partial
                finally:
                    self._stream = None

            self.on_status("Stopped.")
        except Exception as e:
            self.on_status("Error.")
            self.on_final(f"[ERROR] {e}")
        finally:
            self._stream = None

    def pause(self):
        self._pause_evt.set()
        self._clear_audio_queue()
        try:
            if self._stream is not None:
                self._stream.close()
        except Exception:
            pass
        self.on_status("Pausing...")

    def resume(self):
        self._pause_evt.clear()
        self.on_status("Resuming...")

    def _clear_audio_queue(self):
        try:
            while True:
                self._audio_q.get_nowait()
        except queue.Empty:
            pass