# Desktop Cat

A local Linux desktop companion built with Python, PySide6, and QPainter. It runs a fully transparent, animated pixel tabby cat sprite that patrols real desktop folders, lands on icons, stretches, naps, and interacts with cursor movements.

*Built for the Useless Projects Hackathon.*

---

## Quick Start

```bash
cd /home/aby/interactive
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python desktop_cat.py
```

### Controls & System Tray

- **System Tray Icon (🐾)**: Look for the cat icon in your system tray to access:
  - **Mood Override**: Switch between Auto (Battery / AC), Spicy, Sleepy, and Drowsy.
  - **Feed Treat**: Drops a fish treat for the cat.
  - **Rescan Desktop Items**: Refreshes desktop icons without restarting.
  - **Reset Position**: Teleports the cat back to the screen center.
  - **Quit**: Cleanly exits the application.
- **Interactive Hotkeys**:
  - `Ctrl` (Hold): Activates the **laser pointer** (cat chases the red laser dot).
  - `Ctrl + Shift`: Drops a **fish snack 🐟** where your mouse is pointing.
  - **Mouse Petting**: Move your mouse cursor rapidly back and forth across the cat to pet it (emits hearts and purrs ♥).
- **Terminal Exit**: You can also run `./lov` from the terminal to stop the cat anytime.

---

## Features

- **Desktop Folder Patrol**: Automatically discovers real items in `~/Desktop` in the background (using GNOME `gio` metadata) and leaps between icons and platforms without UI freezes.
- **Oldest File Resting**: After 60 seconds of patrol, seeks out the least recently accessed desktop file to rest and take a cozy nap.
- **Cursor Proximity Interaction (150px)**:
  - **Spicy Mood**: Actively stalks and pounces towards the cursor when within 150px!
  - **Sleepy / Drowsy Mood**: Stops and curiously watches your cursor movements.
- **Power & Mood System**:
  - **Unplugged (< 30% battery)**: *Passive / Sleepy* — moves slowly (0.65x speed), takes frequent long naps, gentle hops, and asks for a charger.
  - **Unplugged (≥ 30% battery)**: *Spicy / Aggressive* — runs with the zoomies (1.45x speed), high leaps, aggressive cursor pouncing.
  - **AC Connected / Desktop PC**: *Cozy / Drowsy* — relaxed strolls, stretches, and napping on desktop files.
  - *Override anytime via the System Tray menu!*
- **100% Transparent & Click-Through**: Runs as a frameless, transparent overlay with complete click-through support so your workflow is never interrupted.

---

## Custom Sprite Sheets & CLI Options

The application automatically loads the built-in tabby cat character sprite sheet from `assets/tabby_cat_spritesheet.png` (160x160 frames, 4 columns, 5 rows).

Custom sprite sheets and manual platforms can be supplied via CLI flags:

```bash
python desktop_cat.py --sprite-sheet /path/to/custom_sheet.png \
  --frame-width 160 --frame-height 160 --columns 4 --rows 5 --scale 0.72
```

Jumpable custom platform rectangles (x, y, width, height) can also be supplied:

```bash
python desktop_cat.py --platform 400,620,320,40 --platform 900,420,240,24
```

---

## Desktop Compositor Notes

Qt requests transparent, frameless, topmost, and click-through behavior. On X11, window managers generally honor all hints. On Wayland, compositors intentionally restrict arbitrary global stacking and global input tracking for security; running under XWayland ensures global cursor tracking and hotkey modifier polling function properly.
