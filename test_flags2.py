import sys
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt
import time

app = QApplication(sys.argv)
w = QWidget()
w.setAttribute(Qt.WA_TranslucentBackground, True)
w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
w.show()
time.sleep(1)
sys.exit(0)
