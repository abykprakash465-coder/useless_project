# Desktop Cat

A local Linux desktop companion built with Python, PySide6, and QPainter. It
runs a fully transparent, animated pixel tabby cat sprite that patrols real
desktop folders, lands on icons, stretches, naps, and interacts with cursor
movements.

## Run

```bash
cd /home/aby/interactive
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python desktop_cat.py
```

Press `Esc` to quit.

### Features
- **Desktop Folder Patrol**: Automatically detects real folders in `~/Desktop` and paths to each one, leaping between platforms and icons.
- **Folder Interactions**: On arriving at a folder, the cat sits on or beside it, stretches, takes a nap (or playful hops), and moves on to the next folder.
- **Cursor Proximity Interaction**: Senses when your mouse cursor comes near (within 150px) to watch, playfully bat, or pounce.
- **100% Transparent & Click-Through**: Transparent overlay with complete click-through support so you can work and click desktop icons uninterrupted.
- **Power & Mood System**:
  - Unplugged and below 30%: passive/sleepy
  - Unplugged at 30% or above: spicy/aggressive pouncing
  - AC connected: cozy/drowsy napping patrol

## Sprite sheet

The application automatically loads the built-in tabby cat character sprite
sheet from `assets/tabby_cat_spritesheet.png` (160x160 frames, 4 columns, 5 rows).
Custom sprite sheets can also be supplied via CLI flags:

```bash
python desktop_cat.py --sprite-sheet /path/to/custom_sheet.png \
  --frame-width 160 --frame-height 160 --columns 4 --rows 5 --scale 1
```

Jumpable rectangles can be supplied when their coordinates are known:

```bash
python desktop_cat.py --platform 400,620,320,40 --platform 900,420,240,24
```

## Desktop compositor notes

Qt can request transparent, frameless, topmost, and click-through behavior.
On X11, window managers generally honor the above hint. Wayland intentionally
restricts arbitrary global stacking and desktop-layer placement, so GNOME may
ignore the request to sit behind application windows; this is a compositor
policy limitation, not a Python rendering limitation. The app still switches
its topmost hint and remains click-through except while the spicy cat is under
the cursor.