"""Client for a local LLM served by Ollama (https://ollama.com).

The LLM is optional: if Ollama isn't running, the model isn't pulled, or a
request fails, `available` is False and callers use the built-in replies.
"""
import collections
import datetime
import json
import re
import threading
import time

import requests

from config import (
    LLM_ENABLED, LLM_URL, LLM_MODEL, LLM_TIMEOUT, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    LLM_KEEP_ALIVE, LLM_HISTORY_TURNS, LLM_RETRY_INTERVAL, LLM_SYSTEM_PROMPT,
    VISION_CONTEXT_MAX_AGE,
)

CONNECT_TIMEOUT = 2.0      # Ollama is local, so a slow connect means it isn't there

VISION_DESCRIPTIONS = {
    "Sleeping": "the student appears to be sleeping or resting their head",
    "Mobile":   "the student appears to be using their mobile phone",
    "Reading":  "the student appears to be reading or studying",
}

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_UNSPEAKABLE = re.compile(r"[*#`_~>|\[\]]|[\U0001F000-\U0001FAFF☀-➿️]")


def clean_for_speech(text):
    return re.sub(r"\s+", " ", _UNSPEAKABLE.sub("", text)).strip()


class LLMBrain:
    def __init__(self, get_vision_state=None):
        self.get_vision_state = get_vision_state
        self.available = False
        self._reported = None
        self._history =collections.deque(maxlen=LLM_HISTORY_TURNS * 2)
        self._lock = threading.Lock()
        self._checking = False

    # ---------- availability ----------
    def start(self):
        """Check / load the model in the background; never blocks the caller."""
        if LLM_ENABLED:
            self._check_in_background(delay=0)

    def _check_in_background(self, delay):
        with self._lock:
            if self._checking:
                return
            self._checking = True

        def run():
            try:
                time.sleep(delay)
                while not self._warm_up():
                    time.sleep(LLM_RETRY_INTERVAL)
            finally:
                with self._lock:
                    self._checking = False

        threading.Thread(target=run, daemon=True, name="LLM-check").start()

    def _warm_up(self):
        """Return True once the model answers; prints why not otherwise."""
        try:
            tags = requests.get(f"{LLM_URL}/api/tags", timeout=CONNECT_TIMEOUT).json()
            names = {m.get("name") for m in tags.get("models", [])}
            if LLM_MODEL not in names and f"{LLM_MODEL}:latest" not in names:
                self._mark_unavailable(f"model not pulled - run: ollama pull {LLM_MODEL}")
                return False
            r = requests.post(f"{LLM_URL}/api/chat", json={
                "model": LLM_MODEL, "stream": False, "think": False,
                "keep_alive": LLM_KEEP_ALIVE,
                "messages": [{"role": "user", "content": "Say OK."}],
                "options": {"num_predict": 1},
            }, timeout=(CONNECT_TIMEOUT, 120))      # first load can take a while
            r.raise_for_status()
        except requests.ConnectionError:
            self._mark_unavailable("Ollama is not running")
            return False
        except Exception as e:
            self._mark_unavailable(_short_error(e))
            return False
        self.available = True
        self._reported = None
        print(f"[LLM] ready: {LLM_MODEL}")
        return True

    def _mark_unavailable(self, reason):
        if self.available or reason != self._reported:     # don't repeat every retry
            print(f"[LLM] not available ({reason}) - using built-in replies")
            self._reported = reason
        self.available = False

    # ---------- asking ----------
    def ask(self, text, on_sentence):
        """
        Stream a reply, calling on_sentence(str) for each complete sentence.
        Returns the full reply, or None if the LLM failed (caller falls back).
        """
        if not self.available:
            return None

        messages = [{"role": "system", "content": self._system_prompt()}]
        messages += list(self._history)
        # Camera info goes with the current question (small models weigh it more
        # there); history keeps only the plain question
        messages.append({"role": "user", "content": self._camera_note() + text})

        reply, buffer, spoke = [], "", False
        try:
            with requests.post(f"{LLM_URL}/api/chat", json={
                "model": LLM_MODEL, "messages": messages, "stream": True, "think": False,
                "keep_alive": LLM_KEEP_ALIVE,
                "options": {"num_predict": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE},
            }, stream=True, timeout=(CONNECT_TIMEOUT, LLM_TIMEOUT)) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise RuntimeError(chunk["error"])
                    buffer += chunk.get("message", {}).get("content", "")
                    *done, buffer = _SENTENCE_END.split(buffer)
                    for sentence in done:
                        spoke |= self._emit(sentence, reply, on_sentence)
                    if chunk.get("done"):
                        break
            spoke |= self._emit(buffer, reply, on_sentence)
        except Exception as e:
            self._mark_unavailable(_short_error(e))
            self._check_in_background(delay=LLM_RETRY_INTERVAL)
            # Half an answer was already spoken: don't add a canned one on top
            return " ".join(reply) if spoke else None

        if not spoke:
            return None
        full = " ".join(reply)
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": full})
        return full

    @staticmethod
    def _emit(sentence, reply, on_sentence):
        sentence = clean_for_speech(sentence)
        if not sentence:
            return False
        reply.append(sentence)
        on_sentence(sentence)
        return True

    def _system_prompt(self):
        now = datetime.datetime.now()
        return (f"{LLM_SYSTEM_PROMPT} "
                f"Current date and time: {now.strftime('%A, %d %B %Y, %I:%M %p')}. "
                f"A note in square brackets before the student's words tells you what "
                f"the webcam sees right now; use it when relevant.")

    def _camera_note(self):
        if not self.get_vision_state:
            return ""
        state, age = self.get_vision_state()
        if state in VISION_DESCRIPTIONS and age <= VISION_CONTEXT_MAX_AGE:
            return f"[Webcam right now: {VISION_DESCRIPTIONS[state]}.] "
        return ""


def _short_error(e):
    msg = str(e)
    if "memory" in msg.lower():
        return "not enough memory to run the model"
    if isinstance(e, requests.ConnectionError):     # includes "connect timed out"
        return "Ollama is not running"
    if isinstance(e, requests.Timeout):
        return "timed out"
    return msg[:120]
