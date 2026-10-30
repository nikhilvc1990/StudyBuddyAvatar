import json
import os
import queue
import threading
import time

import sounddevice as sd
import vosk

from config import SAMPLERATE, BLOCKSIZE, WAKE_WORD, LISTEN_TIMEOUT, VOSK_MODEL_PATH

audio_queue = queue.Queue()


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

    def run(self):
        if not os.path.exists(VOSK_MODEL_PATH):
            self.bridge.set_message.emit("ERROR: audio_model missing!")
            print(f"[Voice] Vosk model not found: {VOSK_MODEL_PATH}")
            return

        print("[Voice] Loading Vosk model…")
        model = vosk.Model(VOSK_MODEL_PATH)
        rec = vosk.KaldiRecognizer(model, SAMPLERATE)
        print("[Voice] Model loaded.")
        self._reset_to_idle()

        with sd.RawInputStream(
            samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
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

                if not rec.AcceptWaveform(data):
                    continue

                text = json.loads(rec.Result()).get("text", "").strip()
                if not text:
                    continue
                print(f"Heard: {text}")
                if self.busy.is_set():
                    continue    # still answering the previous question

                if not self.listening:
                    # Phase 1: wake word
                    if WAKE_WORD in text.lower():
                        print(">>> Wake word detected!")
                        self.bridge.set_state.emit("listening")
                        self.tts.mark_voice_interaction()
                        self.tts.speak("Yes? I'm listening.", state_after="listening")
                        self.listening = True
                        self._listen_since = time.time()
                else:
                    # Phase 2: command - answered on its own thread so the mic
                    # keeps being read while the LLM thinks
                    print(">>> Processing command…")
                    self.bridge.set_state.emit("thinking")
                    self.bridge.set_message.emit("Thinking…")
                    self.listening = False
                    self._listen_since = 0.0
                    self.busy.set()
                    threading.Thread(target=self._answer, args=(text,),
                                     daemon=True, name="Answer").start()

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