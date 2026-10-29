import queue
import threading
import time

import pyttsx3

try:
    import pythoncom    # Windows only: SAPI5 needs COM initialised on the TTS thread
except ImportError:
    pythoncom = None

from config import WAKE_WORD, TTS_TIMEOUT, TTS_RATE, VOICE_SUPPRESS_WINDOW


class TTSEngine:
    PRIO_VOICE = 0     # replies to the user
    PRIO_VISION = 1    # vision alerts

    def __init__(self, bridge):
        self.bridge = bridge
        self.is_speaking = threading.Event()

        self._queue = queue.PriorityQueue()
        self._counter = 0
        self._counter_lock = threading.Lock()

        self.last_voice_spoke_at = 0.0
        self._voice_lock = threading.Lock()

        threading.Thread(target=self._worker, daemon=True, name="TTS").start()

    # ---------- public API ----------
    def mark_voice_interaction(self):
        """Stamp 'now' as voice activity, so vision alerts are muted."""
        with self._voice_lock:
            self.last_voice_spoke_at = time.time()

    def speak(self, text, state_after="idle"):
        """Voice-priority speech (wake-word reply, command answers)."""
        self._enqueue(text, "talking", state_after, self.PRIO_VOICE)

    def speak_vision(self, text, state_during="talking", state_after="idle"):
        """
        Vision alert. Returns True if accepted, False if suppressed
        (TTS busy or a voice chat happened recently).
        """
        with self._voice_lock:
            voice_recent = (time.time() - self.last_voice_spoke_at) < VOICE_SUPPRESS_WINDOW
        if self.is_speaking.is_set() or voice_recent:
            return False
        self._enqueue(text, state_during, state_after, self.PRIO_VISION)
        return True

    # ---------- internals ----------
    def _enqueue(self, text, state_during, state_after, priority):
        text = text.strip()
        if not text:
            return
        with self._counter_lock:
            self._counter += 1
            count = self._counter
        self._queue.put((priority, count, text, state_during, state_after,
                         priority == self.PRIO_VOICE))
        print(f"[TTS] Enqueued: {text[:50]}")

    def _fresh_engine(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", TTS_RATE)
        return engine

    def _speak_one(self, text, state_during, state_after, is_voice):
        display = text[:80] + ("…" if len(text) > 80 else "")
        self.bridge.set_message.emit(display)
        self.bridge.set_state.emit(state_during)

        done = threading.Event()
        engine = self._fresh_engine()
        engine.connect("finished-utterance", lambda name, completed: done.set())
        engine.say(text)
        engine.runAndWait()

        if not done.wait(timeout=TTS_TIMEOUT):
            print("[TTS] WARNING: utterance timed out.")
        try:
            engine.stop()
        except Exception:
            pass

        if is_voice:
            # Voice window starts when speech ENDS
            self.mark_voice_interaction()
            # Restore the prompt after 2.5 s (QTimer doesn't work from this
            # thread, so use threading.Timer; the signal is thread-safe)
            threading.Timer(
                2.5,
                lambda: self.bridge.set_message.emit(f"Say '{WAKE_WORD}' to wake me…")
            ).start()

        self.bridge.set_state.emit(state_after)

    def _worker(self):
        if pythoncom is not None:
            pythoncom.CoInitialize()
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            _, _, text, state_during, state_after, is_voice = item
            print(f"  Buddy [{'voice' if is_voice else 'vision'}]: {text}")
            self.is_speaking.set()
            try:
                self._speak_one(text, state_during, state_after, is_voice)
            except Exception as e:
                print(f"[TTS] Engine error: {e}")
                self.bridge.set_state.emit(state_after)
            finally:
                self.is_speaking.clear()
                self._queue.task_done()