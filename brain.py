import datetime
import random
import re

from llm import LLMBrain


def get_rule_response(text):
    """Built-in keyword replies, used when the local LLM isn't available."""
    t = text.lower()

    if re.search(r"\b(hello|hi|hey)\b", t):
        return random.choice(["Hello there!", "Hey! How can I help?", "Hi!"])

    if re.search(r"\btime\b", t):
        return f"The time is {datetime.datetime.now().strftime('%I:%M %p')}."

    if re.search(r"\b(date|today)\b", t):
        return f"Today is {datetime.datetime.now().strftime('%A, %B %d')}."

    if "how are you" in t:
        return random.choice(["Doing great!", "All good, thanks!", "Ready to help!"])

    if "joke" in t:
        return random.choice([
            "Why do programmers prefer dark mode? Light attracts bugs!",
            "Why did the computer go to the doctor? It had a virus!",
        ])

    if re.search(r"\b(bye|goodbye|stop)\b", t):
        return "Goodbye! Double-click me to close."

    if "thank" in t:
        return random.choice(["You're welcome!", "Happy to help!", "Anytime!"])

    return f"I heard: {text}. I'm still learning!"


class Brain:
    """Answers voice commands with the local LLM, or the built-in replies as a fallback."""

    def __init__(self, get_vision_state=None):
        self.llm = LLMBrain(get_vision_state)
        self.llm.start()

    def respond(self, text, on_sentence):
        """Call on_sentence(str) for each part of the reply as it becomes ready."""
        if re.search(r"\b(bye|goodbye|stop)\b", text.lower()):
            on_sentence(get_rule_response(text))
            return
        if self.llm.ask(text, on_sentence) is None:
            on_sentence(get_rule_response(text))
