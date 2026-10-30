"""Microphone + speech-recognition test (no avatar, no LLM).

Run:  python mic_test.py            - uses MIC_DEVICE from config.py
      python mic_test.py Realtek    - try a specific mic (part of its name, or its number)

Shows a live volume bar and what Vosk hears. Say "david" and check it's recognised.
Press Ctrl+C to stop (in PyCharm: the red Stop button).
"""
import json
import queue
import sys

import numpy as np
import sounddevice as sd
import vosk

from config import SAMPLERATE, BLOCKSIZE, VOSK_MODEL_PATH, WAKE_WORD
from voice import resolve_mic, mic_name, find_wake_word

print("Microphones:")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0 and d["hostapi"] == 0:
        print(f"  {i}: {d['name']}")

setting = None
if len(sys.argv) > 1:
    setting = int(sys.argv[1]) if sys.argv[1].isdigit() else sys.argv[1]
    device = resolve_mic(setting)
else:
    device = resolve_mic()
print(f"\nListening on: {mic_name(device)}")

print("Loading speech model (10-20 s)…")
vosk.SetLogLevel(-1)
rec = vosk.KaldiRecognizer(vosk.Model(VOSK_MODEL_PATH), SAMPLERATE)
print(f"Ready. Speak now - try '{WAKE_WORD}' and then a question.\n")

q = queue.Queue()
with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=BLOCKSIZE // 2, device=device,
                       dtype="int16", channels=1,
                       callback=lambda data, *_: q.put(bytes(data))):
    try:
        while True:
            data = q.get()
            peak = int(np.abs(np.frombuffer(data, dtype=np.int16)).max())
            bar = "#" * min(40, peak // 400)
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
                if text:
                    wake = "   <-- WAKE WORD" if find_wake_word(text) is not None else ""
                    print(f"\r{' ' * 60}\rHeard: {text}{wake}")
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "")
                print(f"\rlevel {peak:5d} {bar:<40} {partial[-30:]:<30}", end="", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")
