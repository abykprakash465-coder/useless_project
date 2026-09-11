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

# Create real desktop items reflecting user's desktop stack at x=1789
items = [
    DesktopItem("abywebbuild", QRect(1789, 965, 120, 106), QPoint(1789, 920), 10.0, QRect(1779, 1045, 140, 20)),
    DesktopItem("file1", QRect(1789, 850, 120, 106), QPoint(1789, 805), 20.0, QRect(1779, 930, 140, 20)),
    DesktopItem("file2", QRect(1789, 730, 120, 106), QPoint(1789, 685), 30.0, QRect(1779, 810, 140, 20)),
    DesktopItem("file3", QRect(1789, 610, 120, 106), QPoint(1789, 565), 40.0, QRect(1779, 690, 140, 20)),
]
cat.items = items

# Place cat right at the stuck position: x=1805, y=965, facing right, vx=0
max_x = float(cat.width() - cat.CAT_WIDTH)
cat.pos_x = max_x
cat.pos_y = floor
cat.vx = 0.0
cat.vy = 0.0
cat.facing = 1
cat.behavior_state = "WANDER"
cat.behavior_timer = 0.0

dt = 0.016
sim_time = 60.0 # 60 seconds
positions_x = []
times = int(sim_time / dt)

for i in range(times):
    cat.update_state(dt)
    cat.advance_physics(dt)
    positions_x.append(cat.pos_x)

min_x = min(positions_x)
max_x_observed = max(positions_x)
avg_x = sum(positions_x) / len(positions_x)
time_spent_at_wall = sum(1 for x in positions_x if x >= max_x - 5) * dt

print(f"Simulation 60s completed:")
print(f"  Start X: {max_x}")
print(f"  Min X reached: {min_x:.1f} (Interior traversal: {max_x - min_x:.1f}px)")
print(f"  Max X reached: {max_x_observed:.1f}")
print(f"  Average X: {avg_x:.1f}")
print(f"  Time spent within 5px of right edge: {time_spent_at_wall:.2f}s out of {sim_time}s")

# Assert that cat escaped and explored the left/middle screen
assert min_x < 1200.0, f"Cat failed to escape right side! Min X was {min_x}"
assert time_spent_at_wall < 10.0, f"Cat stayed too long at the wall: {time_spent_at_wall}s"
print("SUCCESS: Cat freely escaped the right edge and explored the desktop!")
