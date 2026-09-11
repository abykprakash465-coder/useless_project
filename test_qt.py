import sys
from PySide6.QtCore import Qt

print("ControlModifier:", hasattr(Qt.KeyboardModifier, "ControlModifier"))
print("ShiftModifier:", hasattr(Qt.KeyboardModifier, "ShiftModifier"))
print("NoPen:", hasattr(Qt.PenStyle, "NoPen"))
print("Key_Escape:", hasattr(Qt.Key, "Key_Escape"))
print("LeftButton:", hasattr(Qt.MouseButton, "LeftButton"))
print("WA_TranslucentBackground:", hasattr(Qt.WidgetAttribute, "WA_TranslucentBackground"))
print("WA_TransparentForMouseEvents:", hasattr(Qt.WidgetAttribute, "WA_TransparentForMouseEvents"))
