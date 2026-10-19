import sys
from pathlib import Path

from transcription import Transcriber

default_model = Path(__file__).resolve().parent.parent / "model"

transcriber = Transcriber(sys.argv[1] if len(sys.argv) > 1 else default_model)
transcriber.start()
try:
    while True:
        kind, text = transcriber.events.get()
        print(f"[{kind}] {text}")
except KeyboardInterrupt:
    transcriber.stop()