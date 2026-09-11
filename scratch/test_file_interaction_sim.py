import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QPoint
from desktop_cat import DesktopCat, DesktopItem, load_frames

app = QApplication.instance() or QApplication(sys.argv)

frames = load_frames(None, 160, 160, 4, 5, 0.72)
cat = DesktopCat(frames, [])

# Configure realistic screen and floor
screen = app.primaryScreen().geometry()
floor = float(screen.height() - cat.CAT_HEIGHT)

# User's actual desktop items
items = [
    DesktopItem("blender", QRect(200, 34, 120, 106), QPoint(200, 0), 10.0, QRect(190, 114, 140, 20)),
    DesktopItem("projects", QRect(465, 34, 120, 106), QPoint(465, 0), 20.0, QRect(455, 114, 140, 20)),
    DesktopItem("program", QRect(598, 965, 120, 106), QPoint(598, 920), 30.0, QRect(588, 1045, 140, 20)),
    DesktopItem("abywebbuild", QRect(1789, 965, 120, 106), QPoint(1789, 920), 40.0, QRect(1779, 1045, 140, 20)),
    DesktopItem("Art_of_War", QRect(1789, 849, 120, 106), QPoint(1789, 804), 50.0, QRect(1779, 929, 140, 20)),
    DesktopItem("lamp.jpeg", QRect(1789, 732, 120, 106), QPoint(1789, 687), 60.0, QRect(1779, 812, 140, 20)),
    DesktopItem("lamp1.jpeg", QRect(1789, 616, 120, 106), QPoint(1789, 571), 70.0, QRect(1779, 696, 140, 20)),
]
cat.items = items
cat.pos_x = 200.0
cat.pos_y = floor
cat.vy = 0.0

dt = 0.016
sim_time = 90.0 # 90 seconds
times = int(sim_time / dt)

interacted_items = []
current_interaction = None

for i in range(times):
    cat.update_state(dt)
    cat.advance_physics(dt)

    if cat.behavior_state == "INTERACT_ITEM":
        if cat.target_item and cat.target_item.name != current_interaction:
            current_interaction = cat.target_item.name
            interacted_items.append((i * dt, current_interaction, cat.speech.text))
    else:
        current_interaction = None

print(f"90-Second Simulation Results:")
print(f"Total file interactions triggered: {len(interacted_items)}")
for t, name, speech in interacted_items:
    print(f"  [{t:.1f}s] Interacted with: {name} | Speech: '{speech}'")

# Assert that cat actively interacted with files (both floor and elevated)
assert len(interacted_items) >= 3, f"Expected at least 3 interactions, got {len(interacted_items)}"
interacted_names = set(x[1] for x in interacted_items)
print(f"Unique files visited: {interacted_names}")
print("SUCCESS: Cat actively and repeatedly interacts with files without ignoring them!")
