import sounddevice as sd


def list_input_devices():
    """
    Returns a list of dicts for input-capable devices:
      [
        {
          "index": int,
          "name": str,
          "max_input_channels": int,
          "default_samplerate": float,
        },
        ...
      ]
    """
    devices = sd.query_devices()
    out = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            out.append(
                {
                    "index": i,
                    "name": d.get("name", f"Device {i}"),
                    "max_input_channels": int(d.get("max_input_channels", 0)),
                    "default_samplerate": float(d.get("default_samplerate", 0.0)),
                }
            )
    return out


def get_default_input_device_index():
    """
    Returns the default input device index if available, else None.
    """
    try:
        # sd.default.device => (input_device, output_device)
        default_in = sd.default.device[0]
        if default_in is None:
            return None
        return int(default_in)
    except Exception:
        return None


def safe_sample_rate_for_device(device_index: int, preferred: int = 16000) -> int:
    """
    Picks a sensible sample rate for a given device.

    Why:
    - Vosk models often use 16000 Hz comfortably.
    - Some devices behave better at their default samplerate (often 44100/48000).

    Strategy:
    - If device default is >= preferred, return preferred (16000).
    - Otherwise return the device default rounded to int.
    - Final fallback is preferred.
    """
    try:
        d = sd.query_devices(device_index)
        default_sr = int(d.get("default_samplerate", preferred))
        return default_sr if default_sr > 0 else preferred
    except Exception:
        return preferred