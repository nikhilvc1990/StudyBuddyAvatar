import sys

from PyQt6.QtWidgets import QApplication

from avatar import AssistantWindow
from bridge import Bridge
from config import VISION_MESSAGES, ALERT_STATES
from detection import VisionThread
from tts import TTSEngine
from voice import VoiceThread


def main():
    app = QApplication(sys.argv)
    bridge = Bridge()
    window = AssistantWindow(bridge)     # keep a reference so it isn't garbage collected
    tts = TTSEngine(bridge)

    def handle_alert(state, conf):
        """Called by the vision thread. Return False if the alert was suppressed."""
        msg = VISION_MESSAGES.get(state)
        if not msg:
            return True
        print(f"[Main] Alert: {state} ({conf:.0%})")
        during = "alert" if state in ALERT_STATES else "talking"
        return tts.speak_vision(msg, state_during=during, state_after="idle")

    vision = VisionThread(on_alert=handle_alert)
    voice = VoiceThread(bridge, tts)

    vision.start()
    voice.start()

    app.aboutToQuit.connect(vision.stop)
    app.aboutToQuit.connect(voice.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()