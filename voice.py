import json
import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd
import vosk

from config import (
    SAMPLERATE, BLOCKSIZE, WAKE_WORD, WAKE_WORD_ALIASES, LISTEN_TIMEOUT,
    VOSK_MODEL_PATH, MIC_DEVICE,
)

audio_queue = queue.Queue()

SILENT_PEAK = 300           # int16 peak below this for the first seconds = mic is dead
SILENCE_CHECK_SECONDS = 5
ECHO_TAIL = 0.4             # seconds of audio ignored after the avatar stops speaking


def resolve_mic(setting=MIC_DEVICE):
    """Turn MIC_DEVICE (None, index or part of a name) into a sounddevice index."""
    if setting is None or isinstance(setting, int):
        return setting
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and setting.lower() in d["name"].lower():
            return i
    print(f"[Voice] No microphone matching '{setting}' - using the Windows default.")
    return None


def mic_name(device):
    return sd.query_devices(device if device is not None else sd.default.device[0])["name"]


def find_wake_word(text):
    """Return the words after the wake word, or None if it wasn't said."""
    words = text.lower().split()
    for i, w in enumerate(words):
        if w in WAKE_WORD_ALIASES:
            return " ".join(words[i + 1:])
    return None


class VoiceThread(threading.Thread):
    def __init__(self, bridge, tts, brain):
        super().__init__(daemon=True, name="Voice")
        self.bridge = bridge
        self.tts = tts
        self.brain = brain
        self.busy = threading.Event()       # set while a reply is being generated
        self.listening = False
        self._listen_since = 0.0
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def _callback(self, indata, frames, t, status):
        if status:
            print("Mic:", status)
        audio_queue.put(bytes(indata))

    def _reset_to_idle(self):
        self.listening = False
        self._listen_since = 0.0
        self.bridge.set_state.emit("idle")
        self.bridge.set_message.emit(f"Say '{WAKE_WORD}' to wake me…")

    def _wake(self):
        print(">>> Wake word detected!")
        self.bridge.set_state.emit("listening")
        self.tts.mark_voice_interaction()
        self.tts.speak("Yes? I'm listening.", state_after="listening")
        self.listening = True
        self._listen_since = time.time()

    def _command(self, text):
        # Answered on its own thread so the mic keeps being read while the LLM thinks
        print(f">>> Processing command: {text}")
        self.bridge.set_state.emit("thinking")
        self.bridge.set_message.emit("Thinking…")
        self.listening = False
        self._listen_since = 0.0
        self.busy.set()
        threading.Thread(target=self._answer, args=(text,),
                         daemon=True, name="Answer").start()

    def run(self):
        if not os.path.exists(VOSK_MODEL_PATH):
            self.bridge.set_message.emit("ERROR: audio_model missing!")
            print(f"[Voice] Vosk model not found: {VOSK_MODEL_PATH}")
            return

        print("[Voice] Loading Vosk model…")
        vosk.SetLogLevel(-1)
        model = vosk.Model(VOSK_MODEL_PATH)
        rec = vosk.KaldiRecognizer(model, SAMPLERATE)
        print("[Voice] Model loaded.")

        device = resolve_mic()
        print(f"[Voice] Microphone: {mic_name(device)}")
        self._reset_to_idle()

        started = time.time()
        peak = 0
        silence_checked = False
        quiet_until = 0.0
        heard_name = False          # partial result already contained the wake word

        with sd.RawInputStream(
            samplerate=SAMPLERATE, blocksize=BLOCKSIZE, device=device,
            dtype="int16", channels=1, callback=self._callback,
        ):
            while not self._stop_flag.is_set():
                # Command-mode timeout
                if self.listening and (time.time() - self._listen_since) > LISTEN_TIMEOUT:
                    print("[Voice] Listen timeout.")
                    self._reset_to_idle()
                    self.tts.speak("I didn't catch that. Say my name when you need me.")

                try:
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if not silence_checked:
                    peak = max(peak, int(np.abs(np.frombuffer(data, dtype=np.int16)).max()))
                    if time.time() - started > SILENCE_CHECK_SECONDS:
                        silence_checked = True
                        if peak < SILENT_PEAK:
                            print(f"[Voice] WARNING: '{mic_name(device)}' seems silent "
                                  f"(peak {peak}). Check the mic or set MIC_DEVICE in config.py "
                                  f"(run mic_test.py to find the right one).")

                # Don't listen to the avatar's own voice coming out of the speakers
                if self.tts.is_speaking.is_set():
                    quiet_until = time.time() + ECHO_TAIL
                if time.time() < quiet_until:
                    rec.Reset()
                    continue

                if not rec.AcceptWaveform(data):
                    # Show straight away that the name was heard; the full sentence
                    # (after a short pause) decides what to do, so a command said
                    # in the same breath isn't lost
                    if not self.listening and not self.busy.is_set() and not heard_name:
                        partial = json.loads(rec.PartialResult()).get("partial", "")
                        if find_wake_word(partial) is not None:
                            heard_name = True
                            self.bridge.set_state.emit("listening")
                            self.bridge.set_message.emit("Listening…")
                    continue

                text = json.loads(rec.Result()).get("text", "").strip()
                was_heard, heard_name = heard_name, False
                if not text:
                    if was_heard and not self.listening:
                        self._reset_to_idle()
                    continue
                print(f"Heard: {text}")
                if self.busy.is_set():
                    continue    # still answering the previous question

                if not self.listening:
                    # Phase 1: wake word ("david" alone, or "david what is gravity")
                    rest = find_wake_word(text)
                    if rest is None:
                        if was_heard:
                            self._reset_to_idle()   # partial match was a false alarm
                        continue
                    if len(rest.split()) >= 2:
                        self.tts.mark_voice_interaction()
                        self._command(rest)
                    else:
                        self._wake()
                else:
                    # Phase 2: command (a repeated "david ..." is stripped off)
                    rest = find_wake_word(text)
                    if rest == "":
                        self._wake()        # just the name again: keep listening
                    else:
                        self._command(rest if rest is not None else text)

    def _answer(self, text):
        try:
            # Each sentence is spoken as soon as it's ready
            self.brain.respond(text, lambda s: self.tts.speak(s, state_after="talking"))
        except Exception as e:
            print(f"[Voice] Answer error: {e}")
        finally:
            self.tts.set_state_when_done("idle")
            self.busy.clear()
            print(f"Listening for wake word: '{WAKE_WORD}'")
