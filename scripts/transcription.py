import json
import queue
import threading

import sounddevice as sd
from vosk import KaldiRecognizer, Model

SAMPLERATE = 16000
BLOCKSIZE = 4000


class Transcriber:
    def __init__(self, model_path):
        """Load the Vosk model found at model_path."""
        self.model = Model(str(model_path))
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        """Start microphone capture and transcription in a background thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background thread and release the microphone."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        """Read audio blocks and push ('partial' | 'final', text) onto self.events."""
        recognizer = KaldiRecognizer(self.model, SAMPLERATE)
        audio = queue.Queue()
        last_partial = ""

        def on_audio(indata, frames, time, status):
            """Queue each raw audio block from the sounddevice stream."""
            audio.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=SAMPLERATE,
            blocksize=BLOCKSIZE,
            dtype="int16",
            channels=1,
            callback=on_audio,
        ):
            while not self._stop.is_set():
                try:
                    pcm = audio.get(timeout=0.2)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(pcm):
                    text = json.loads(recognizer.Result())["text"]
                    last_partial = ""
                    if text:
                        self.events.put(("final", text))
                else:
                    text = json.loads(recognizer.PartialResult())["partial"]
                    if text and text != last_partial:
                        last_partial = text
                        self.events.put(("partial", text))
