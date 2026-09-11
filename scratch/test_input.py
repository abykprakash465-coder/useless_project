import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor

def tick():
    buttons = QApplication.mouseButtons()
    mods = QApplication.keyboardModifiers()
    print(f"Mouse: {buttons}, Mods: {mods}, Pos: {QCursor.pos()}")

app = QApplication(sys.argv)
timer = QTimer()
timer.timeout.connect(tick)
timer.start(500)
app.exec()
