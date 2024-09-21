# Voice To Text

VoiceToText is a Proof-of-concept Python class that uses the Vosk library to continuously transcribe spoken language into text from an audio input. 
Note that it still uses Print statements for testing. If you are using this for your own project, update it to utilise whatever logging system you have implemented.

This is designed to run of the Vosk models by Alphacephei
Website: https://alphacephei.com/vosk/

A list of their Models exist here: https://alphacephei.com/vosk/models

## Features
* Continuous audio transcription: Transcribe spoken language into text in real-time.
* Energy threshold detection: The class only processes audio when it detects sound, which is determined by an energy threshold.
* Multithreading: The transcription process is multithreaded for better performance.
* Interruption support: The transcription process can be interrupted and resumed.
* Transcription retrieval and reset: Transcriptions can be retrieved and reset for a new transcription session.

## Installation

To use this class, you need to have Python installed along with the vosk, pyaudio, and numpy libraries. You can install these with pip:

```bash
pip install vosk pyaudio numpy
```

You will also need a trained model from Vosk. You can downloaded it from their models website (see introduction).
Once downloaded, set the _model_path_ variable to the path of the downloaded model (folder)

## Usage

First, import the class:
```python
from voice_to_text import VoiceToText
```

Next, initialize an instance of the class:
```python
vtt = VoiceToText(model_path="path_to_your_model")
```

Start transcribing audio:
```python
vtt.continuously_transcribe_audio()
```

Stop the transcription process:
```python
vtt.stop_recording()
```

Retrieve the transcriptions:
```python
transcriptions = vtt.get_transcript()
```

And reset the transcriptions:
```python
vtt.new_transcript()
```

Please refer to the class and method docstrings in voice_to_text.py for detailed information about the class and its methods.