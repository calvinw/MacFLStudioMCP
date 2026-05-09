"""Always-on-top button for triggering the piano-roll bridge hotkey."""

from __future__ import annotations

import sys
import time

from .keystroke import send_hotkey_mac, send_hotkey_windows


def _focus_piano_roll() -> None:
    """Ask the FL bridge to bring the piano roll window to the front."""
    try:
        from .bridge_client import get_client
        get_client().call("ui.showWindow", name="piano_roll", focus=True)
        time.sleep(0.15)  # let FL finish raising the window
    except Exception:
        pass  # bridge offline — keystroke will still go to whatever is focused


def _send_hotkey() -> bool:
    _focus_piano_roll()
    if sys.platform == "darwin":
        return send_hotkey_mac()
    if sys.platform == "win32":
        return send_hotkey_windows()
    return False


def main() -> None:
    try:
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtGui import QColor, QFont, QPalette
        from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
    except ImportError as exc:
        raise SystemExit("PyQt5 is required. Install with: .venv/bin/pip install '.[mac]'") from exc

    class HotkeyWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("ComposeWithLLM Trigger")
            self.resize(300, 180)
            self.setMinimumSize(260, 150)
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")

            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(24, 22, 24, 22)
            layout.setSpacing(14)

            title = QLabel("Piano Roll Script Trigger")
            title.setFont(QFont("Helvetica Neue", 16, QFont.Bold))
            title.setStyleSheet("color: #ffcc00; padding: 4px;")
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)

            self.status = QLabel("Ready to trigger ComposeWithLLM")
            self.status.setFont(QFont("Helvetica Neue", 11))
            self.status.setStyleSheet("color: #00ff88; padding: 8px;")
            self.status.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.status)

            button = QPushButton("Trigger Cmd+Opt+Y")
            button.setMinimumHeight(58)
            button.setFont(QFont("Helvetica Neue", 18, QFont.Bold))
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: #4a6a9a;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 14px;
                }
                QPushButton:hover { background-color: #5a7aaa; }
                QPushButton:pressed { background-color: #3a5a8a; }
            """)
            button.clicked.connect(self.trigger)
            layout.addWidget(button)

        def trigger(self) -> None:
            ok = _send_hotkey()
            if ok:
                self.status.setText("ComposeWithLLM triggered")
                self.status.setStyleSheet("color: #00ff88; padding: 8px;")
            else:
                self.status.setText("Trigger failed")
                self.status.setStyleSheet("color: #ff4444; padding: 8px;")
            QTimer.singleShot(1400, lambda: self.status.setText("Ready to trigger ComposeWithLLM"))

    app = QApplication(sys.argv)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, Qt.white)
    app.setPalette(palette)

    window = HotkeyWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
