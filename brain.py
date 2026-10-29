import datetime
import random
import re


def get_voice_response(text):
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