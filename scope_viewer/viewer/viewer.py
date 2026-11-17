"""
viewer.py — scope_viewer
─────────────────────────
Entry point for the Arduino UNO R4 Serial Oscilloscope Viewer.

Usage:
    python viewer.py

Requirements:
    pip install -r requirements.txt
"""

from oscilloscope_ui import OscilloscopeApp


def main() -> None:
    app = OscilloscopeApp()
    app.run()


if __name__ == "__main__":
    main()
