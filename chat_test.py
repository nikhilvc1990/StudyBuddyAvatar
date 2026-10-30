"""Type questions to StudyBuddy's brain - tests the LLM without the mic or avatar.

Run:  python chat_test.py           - text only
      python chat_test.py --speak   - also read the answers aloud

Answers marked [LLM] come from Ollama; [built-in] means the fallback replies were used.
Type 'phone' / 'sleeping' / 'reading' to pretend the camera sees that. Empty line quits.
"""
import sys
import time

from brain import Brain

camera = {"state": None}
brain = Brain(get_vision_state=lambda: (camera["state"], 0.0))

tts = None
if "--speak" in sys.argv:
    import pyttsx3
    tts = pyttsx3.init()

print("Checking the local LLM...", end="", flush=True)
for _ in range(60):                     # first load of the model can take a while
    if brain.llm.available or brain.llm._reported:
        break
    time.sleep(1)
print("\nAsk something (Enter on an empty line to quit).\n")

CAMERA_WORDS = {"phone": "Mobile", "sleeping": "Sleeping", "reading": "Reading"}

while True:
    try:
        text = input("You: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        break
    if text in CAMERA_WORDS:
        camera["state"] = CAMERA_WORDS[text]
        print(f"   (camera now sees: {camera['state']})\n")
        continue

    source = "LLM" if brain.llm.available else "built-in"
    start = time.time()
    sentences = []

    def on_sentence(s):
        sentences.append(s)
        print(f"   [{time.time() - start:4.1f}s] {s}")

    brain.respond(text, on_sentence)
    if source == "LLM" and not brain.llm.available:
        source = "built-in"             # the LLM failed during this answer
    print(f"Buddy [{source}]\n")
    if tts:
        tts.say(" ".join(sentences))
        tts.runAndWait()
