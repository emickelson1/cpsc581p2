"""Expert / helper side: transcribe the microphone and send the text to the novice's Blender.

Usage:  python expert_start.py [--host IP] [--port N] [--model DIR]
Sends one JSON object per line: {"kind": "partial" | "final", "text": "..."}
"""
import argparse
import json
import queue
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = SCRIPTS_DIR.parent / "model"

sys.path.insert(0, str(SCRIPTS_DIR))
import connection_client as cc


def parse_args():
    p = argparse.ArgumentParser(description="Send live voice transcription to the novice's Blender.")
    p.add_argument("--host", default=cc.HOST, help="IP of the machine running Blender (default: %(default)s)")
    p.add_argument("--port", type=int, default=cc.PORT, help="default: %(default)s")
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Vosk model folder (default: %(default)s)")
    return p.parse_args()


def forward_events(transcriber):
    """Print every pending transcription event, and send it if connected (otherwise it is dropped as stale)."""
    while True:
        try:
            kind, text = transcriber.events.get_nowait()
        except queue.Empty:
            return
        print(f"[{kind}] {text}")
        if cc.client_execution_state == 1:
            line = json.dumps({"kind": kind, "text": text}) + "\n"
            cc.client_send_message(line.encode("utf-8"))


def main():
    args = parse_args()
    if not args.model.is_dir():
        sys.exit(f"Model folder not found: {args.model}\nPass --model, or put it at {DEFAULT_MODEL}")
    from transcription import Transcriber   # imported late so --help works without vosk installed

    cc.HOST, cc.PORT = args.host, args.port
    print(f"Loading model from {args.model} ...")
    transcriber = Transcriber(args.model)
    transcriber.start()
    print(f"Listening to the microphone. Connecting to {cc.HOST}:{cc.PORT} (Ctrl+C to quit)")

    was_connected = False
    try:
        while True:
            delay = cc.client_execution_loop()
            state = cc.client_execution_state
            if state not in (0, 1):
                print("Connection failed with an unexpected error; exiting.")
                break
            connected = state == 1
            if connected != was_connected:
                print("-- connected to Blender --" if connected else "-- disconnected, retrying --")
                was_connected = connected
            forward_events(transcriber)
            time.sleep(min(delay, 0.05) if connected else delay)
    except KeyboardInterrupt:
        pass
    finally:
        transcriber.stop()
        cc.client_close()


if __name__ == "__main__":
    main()
