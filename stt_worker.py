import json
import queue
import threading

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
        self._stop_evt.set()
        try:
            if self._stream is not None:
                self._stream.close()
        except Exception:
            pass

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.on_status(f"Audio status: {status}")
        # indata is a bytes-like object in RawInputStream when dtype=int16
        self._audio_q.put(bytes(indata))

    def _run(self, model_path: str, device_index: int, sample_rate: int):
        try:
            self.on_status("Loading model...")
            model = Model(model_path)

            rec = KaldiRecognizer(model, sample_rate)
            rec.SetWords(True)

            self.on_status("Opening microphone...")
            self._stream = sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=8000,
                device=device_index,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            )

            with self._stream:
                self.on_status("Listening...")
                prev_partial = ""

                while not self._stop_evt.is_set():
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
                        self.on_partial("")  # clear partial after a finalized chunk
                    else:
                        partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                        if partial != prev_partial:
                            self.on_partial(partial)
                            prev_partial = partial

            self.on_status("Stopped.")
        except Exception as e:
            self.on_status("Error.")
            self.on_final(f"[ERROR] {e}")
        finally:
            self._stream = None