import sys
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt

app = QApplication(sys.argv)
w = QWidget()
w.setAttribute(Qt.WA_TranslucentBackground, True)
# Try without ToolTip
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.BypassWindowManagerHint | Qt.WindowDoesNotAcceptFocus)
w.show()
sys.exit(0)
