"""A transparent, animated desktop companion for Linux."""

from __future__ import annotations

import argparse
import math
import random
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget


class Mood(Enum):
    SLEEPY = "passive / sleepy"
    SPICY = "spicy / aggressive"
    DROWSY = "drowsy / napping"


class Animation(Enum):
    WALK = "walk"
    JUMP = "jump"
    SIT = "sit"
    STRETCH = "stretch"
    NAP = "nap"


@dataclass
class FrameSet:
    frames: list[QPixmap]

    def frame(self, index: int) -> QPixmap:
        return self.frames[index % len(self.frames)]


def fallback_frame(scale: float = 4.0, sleeping: bool = False) -> QPixmap:
    """Create a crisp pixel cat when no sprite sheet is supplied."""
    width, height = (26, 16) if sleeping else (20, 22)
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    colors = {"#": "#2c211e", "b": "#b87955", "s": "#815039", "c": "#f0d8b7"}
    rows = ([
        "..........................", ".......##....##...........",
        ".....##bb####bb##.........", "...##bbbbbbbbbbbb##.......",
        "..#bbbbssbbbbbbssbbb#.....", ".#bbbbbbbbbbbbbbbbbbbb#...",
        "#bbbbbbbbbbbbbbbbbbbbbb#..", "#bbbbbccccccccccccbbbbbb#.",
        ".#bbbbbbbbbbbbbbbbbbbb#...", "..##bbbbbbbbbbbbbbbb##....",
        "....##s##########s##......", "..........................",
        "..........................", "..........................", "..........................", "..........................",
    ] if sleeping else [
        "......##....##......", ".....#bb#..#bb#.....", "....#bbbb##bbbb#....",
        "....#bbbbbbbbbb#....", "...#bb#bbbbbb#bb#...", "...#bbbbbbbbbbbb#...",
        "...#bbccccccbb#....", "....#bccccccb#.....", ".....#bbbbbb#......",
        "..###bbbbbb###.....", ".#bbbbbbbbbbbb#.....", "#bbbbssbbbbssbbb#...",
        "#bbbbbbbbbbbbbbb#...", ".#bbbbbbbbbbbbbb#...", "..#bbbbbbbbbbbbb#...",
        "...#bbbbbbbbbb#....", "....##......##.....", "....................", "....................",
        "....................", "....................", "....................",
    ])
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char in colors:
                image.setPixelColor(x, y, QColor(colors[char]))
    return QPixmap.fromImage(image).scaled(int(image.width() * scale), int(image.height() * scale),
                                           Qt.IgnoreAspectRatio, Qt.FastTransformation)


def load_frames(path: str | None, frame_width: int, frame_height: int,
                columns: int, rows: int, scale: float) -> dict[Animation, FrameSet]:
    if not path:
        return {animation: FrameSet([fallback_frame(scale, animation is Animation.NAP)])
                for animation in Animation}
    sheet = QPixmap(path)
    if sheet.isNull():
        raise ValueError(f"Could not load sprite sheet: {path}")
    sets = {}
    for row, animation in enumerate(Animation):
        frames = []
        for column in range(columns):
            rect = QRect(column * frame_width, row * frame_height, frame_width, frame_height)
            if rect.right() <= sheet.width() - 1 and rect.bottom() <= sheet.height() - 1:
                frames.append(sheet.copy(rect).scaled(int(frame_width * scale), int(frame_height * scale),
                                                      Qt.IgnoreAspectRatio, Qt.FastTransformation))
        if frames:
            sets[animation] = FrameSet(frames)
    if len(sets) != len(Animation):
        raise ValueError("Sprite sheet needs five rows: walk, jump, sit, stretch, nap")
    return sets


DEFAULT_SPRITE_SHEET = Path(__file__).resolve().parent / "assets" / "tabby_cat_spritesheet.png"


class DesktopCat(QWidget):
    GRAVITY = 1500.0
    WALK_SPEED = 120.0
    CAT_WIDTH = 160
    CAT_HEIGHT = 160

    def __init__(self, frames: dict[Animation, FrameSet], platform_args: list[str]):
        super().__init__()
        self.frames = frames
        sample = frames[Animation.WALK].frame(0)
        self.CAT_WIDTH = sample.width()
        self.CAT_HEIGHT = sample.height()
        self.mood = Mood.SLEEPY
        self.animation = Animation.SIT
        self.animation_time = 0.0
        self.stretch_timer = 0.0
        self.manual_platforms = self.parse_platforms(platform_args)
        self.platforms: list[QRect] = list(self.manual_platforms)

        # Item interaction state
        self.items = self.discover_desktop_items()
        self.behavior_state = "WANDER"
        self.behavior_timer = 0.0
        self.target_item = None
        self.target_x = 200.0
        self.time_alive = 0.0
        self.rescan_timer = 0.0

        # Start position (will fall to floor)
        screen = QApplication.primaryScreen().geometry()
        self.x = 200.0
        self.y = float(screen.height() - self.CAT_HEIGHT)

        self.vx, self.vy = self.WALK_SPEED, 0.0
        self.facing = 1
        self.last_tick = time.monotonic()
        self.telemetry_tick = 0.0
        self.jump_cooldown = 0.0

        # Interactive state
        self.laser_active = False
        self.laser_pos = QPoint()
        self.treats = []
        self.last_shift_ctrl = False
        
        self.petting_score = 0.0
        self.last_mouse_pos = QCursor.pos()
        self.hearts = []
        
        self.speech = {"text": "", "life": 0.0}

        # Set up a fully transparent, frameless, topmost, click-through overlay
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(screen)
        self.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def say(self, text: str, life: float = 3.0) -> None:
        self.speech = {"text": text, "life": life}

    def discover_desktop_items(self) -> list[dict]:
        """Scan ~/Desktop for files and directories and extract their real screen positions."""
        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            return []

        items = []
        item_paths = sorted(list(desktop.iterdir()), key=lambda p: p.name.lower())
        item_platforms = []

        for i, path in enumerate(item_paths):
            res = subprocess.run(["gio", "info", "-a", "metadata::*", str(path)], capture_output=True, text=True)
            pos = None
            for line in res.stdout.splitlines():
                if "icon-position:" in line:
                    pos = line.rsplit(":", 1)[-1].strip()
            if pos:
                try:
                    x, y = (int(v) for v in pos.split(","))
                except ValueError:
                    x, y = 200 + i * 160, 50
            else:
                x, y = 200 + i * 160, 50

            cat_x = x - (self.CAT_WIDTH - 120) // 2
            cat_y = max(0, y - 45)
            icon_rect = QRect(x, y, 120, 106)
            platform_rect = QRect(x - 10, y + 80, 140, 20)
            item_platforms.append(platform_rect)

            try:
                atime = path.stat().st_atime
            except OSError:
                atime = time.time()

            items.append({
                "name": path.name,
                "icon_rect": icon_rect,
                "cat_pos": QPoint(cat_x, cat_y),
                "atime": atime,
                "platform": platform_rect
            })

        self.platforms = list(self.manual_platforms) + item_platforms
        return items

    @staticmethod
    def parse_platforms(values: list[str]) -> list[QRect]:
        platforms = []
        for value in values:
            try:
                x, y, width, height = (int(part) for part in value.split(","))
                platforms.append(QRect(x, y, width, height))
            except ValueError as error:
                raise ValueError(f"Platform must be x,y,width,height: {value}") from error
        return platforms

    def set_mood(self, mood: Mood) -> None:
        if mood is self.mood:
            return
        old_mood = self.mood
        self.mood = mood
        if old_mood is Mood.DROWSY and mood is not Mood.DROWSY:
            self.stretch_timer = 1.5
            self.animation = Animation.STRETCH
            self.vx = 0.0

    def system_power(self) -> tuple[int | None, bool]:
        root = Path("/sys/class/power_supply")
        battery = next(iter(root.glob("BAT*/capacity")), None)
        ac = next(iter(root.glob("AC*/online")), None)
        try:
            percentage = int(battery.read_text().strip()) if battery else None
        except (OSError, ValueError):
            percentage = None
        try:
            plugged = bool(int(ac.read_text().strip())) if ac else False
        except (OSError, ValueError):
            plugged = False
        return percentage, plugged

    def update_state(self, dt: float) -> None:
        self.telemetry_tick += dt
        self.rescan_timer += dt
        self.time_alive += dt

        # Particles & Effects logic
        for heart in list(self.hearts):
            heart["life"] -= dt
            heart["y"] -= 30 * dt
            if heart["life"] <= 0:
                self.hearts.remove(heart)
                
        if self.speech["life"] > 0:
            self.speech["life"] -= dt

        # Treat gravity logic
        floor = float(self.height() - 20)
        for treat in self.treats:
            treat["vy"] += self.GRAVITY * dt
            treat["y"] += treat["vy"] * dt
            if treat["y"] >= floor:
                treat["y"] = floor
                treat["vy"] = 0.0

        if self.rescan_timer > 15.0:
            self.rescan_timer = 0.0
            self.items = self.discover_desktop_items()

        if self.telemetry_tick < 5.0:
            return
        self.telemetry_tick = 0.0
        percentage, plugged = self.system_power()
        if plugged:
            self.set_mood(Mood.DROWSY)
        elif percentage is not None and percentage < 30:
            self.set_mood(Mood.SLEEPY)
            if random.random() < 0.3:
                self.say("Need charger... 🪫")
        else:
            self.set_mood(Mood.SPICY)

    def advance_physics(self, dt: float) -> None:
        floor = float(self.height() - self.CAT_HEIGHT)
        self.jump_cooldown = max(0.0, self.jump_cooldown - dt)

        # Process inputs
        mods = QApplication.keyboardModifiers()
        has_ctrl = bool(mods & Qt.ControlModifier)
        has_shift = bool(mods & Qt.ShiftModifier)
        
        cursor = QCursor.pos()
        
        # Treat Spawning (Ctrl + Shift click emulation via just holding them)
        if has_ctrl and has_shift:
            if not self.last_shift_ctrl:
                self.last_shift_ctrl = True
                self.treats.append({"x": float(cursor.x()), "y": float(cursor.y()), "vy": 0.0})
                self.say("Snack! 🐟")
        else:
            self.last_shift_ctrl = False

        # Laser Pointer logic (Ctrl only)
        if has_ctrl and not has_shift:
            self.laser_active = True
            self.laser_pos = cursor
        else:
            self.laser_active = False

        # Petting Logic
        cat_rect = QRect(int(self.x), int(self.y), self.CAT_WIDTH, self.CAT_HEIGHT)
        if cat_rect.contains(cursor):
            mouse_speed = abs(cursor.x() - self.last_mouse_pos.x()) + abs(cursor.y() - self.last_mouse_pos.y())
            if mouse_speed > 10:
                self.petting_score += mouse_speed * dt
            if self.petting_score > 30:
                self.petting_score = 0
                self.hearts.append({"x": self.x + self.CAT_WIDTH/2 + random.randint(-20, 20),
                                    "y": self.y + 20, "life": 1.5})
                if random.random() < 0.3 and self.speech["life"] <= 0:
                    self.say("Purrrrr~ ♥", 2.0)
                self.animation = Animation.NAP
                self.vx = 0.0
                self.folder_state = "APPROACH" # Reset folder interaction
        else:
            self.petting_score = max(0.0, self.petting_score - dt * 50)
            
        self.last_mouse_pos = cursor

        if self.stretch_timer > 0:
            self.stretch_timer -= dt
            self.animation = Animation.STRETCH
            self.vx = 0.0
            self.apply_gravity(dt, floor)
            return

        cat_center_x = self.x + self.CAT_WIDTH / 2
        cat_center_y = self.y + self.CAT_HEIGHT / 2
        
        # Behavior Priorities: Laser > Treats > Folder Patrol
        if self.laser_active:
            dx = self.laser_pos.x() - cat_center_x
            dy = self.laser_pos.y() - cat_center_y
            self.move_towards(dx, dy, dt, speed_mult=2.0, interact_dist=20)
            
        elif self.treats:
            # Find closest treat
            closest = min(self.treats, key=lambda t: (t["x"] - cat_center_x)**2 + (t["y"] - cat_center_y)**2)
            dx = closest["x"] - cat_center_x
            dy = closest["y"] - cat_center_y
            
            if abs(dx) < 30 and abs(dy) < 50:
                self.treats.remove(closest)
                self.hearts.append({"x": self.x + self.CAT_WIDTH/2, "y": self.y + 20, "life": 1.5})
                self.animation = Animation.NAP # Eating animation
                self.stretch_timer = 1.0 # Pause to eat
            else:
                self.move_towards(dx, dy, dt, speed_mult=1.5, interact_dist=30)
                
        else:
            # Autonomous patrol and interaction
            self.behavior_timer -= dt
            
            # Find the most unused item (oldest atime)
            unused_item = min(self.items, key=lambda i: i["atime"]) if self.items else None

            # After 60 seconds, seek out the unused file to rest
            if self.time_alive > 60.0 and unused_item:
                dx = unused_item["cat_pos"].x() - self.x
                dy = unused_item["cat_pos"].y() - self.y
                
                if abs(dy) < 60 and abs(dx) < 25:
                    self.vx = 0.0
                    self.animation = Animation.NAP
                else:
                    if abs(dx) > 20:
                        self.move_x(dx, dt, speed_mult=1.2)
                    else:
                        self.vx = 0.0
                        if self.vy == 0 and self.jump_cooldown <= 0:
                            height_diff = max(0.0, self.y - unused_item["cat_pos"].y())
                            required_vy = -math.sqrt(2 * self.GRAVITY * max(10, height_diff + 20))
                            self.vy = max(-1500.0, required_vy)
                            self.animation = Animation.JUMP
                            self.jump_cooldown = 1.0
            else:
                if self.behavior_state == "WANDER":
                    if self.behavior_timer <= 0:
                        self.target_x = self.x + random.uniform(-300, 300)
                        self.target_x = max(0, min(self.target_x, self.width() - self.CAT_WIDTH))
                        self.behavior_timer = random.uniform(3.0, 8.0)
                        self.animation = Animation.WALK
                    
                    dx = self.target_x - self.x
                    if abs(dx) > 10:
                        self.move_x(dx, dt, speed_mult=0.8)
                        
                        # Stop if we walk past an item we can jump on
                        if self.vy == 0:
                            for item in self.items:
                                if abs(self.x - item["cat_pos"].x()) < 30:
                                    height_diff = self.y - item["cat_pos"].y()
                                    if 40 < height_diff < 250:
                                        self.behavior_state = "INTERACT_ITEM"
                                        self.target_item = item
                                        self.behavior_timer = random.uniform(5.0, 10.0)
                                        self.vx = 0.0
                                        break
                    else:
                        self.vx = 0.0
                        self.animation = Animation.SIT
                        
                elif self.behavior_state == "INTERACT_ITEM":
                    if self.target_item:
                        dx = self.target_item["cat_pos"].x() - self.x
                        dy = self.target_item["cat_pos"].y() - self.y
                        
                        if abs(dy) < 60:
                            self.vx = 0.0
                            self.animation = Animation.SIT if self.behavior_timer > 2.0 else Animation.STRETCH
                        else:
                            if abs(dx) > 10:
                                self.move_x(dx, dt, speed_mult=1.0)
                            else:
                                self.vx = 0.0
                                if self.vy == 0 and self.jump_cooldown <= 0:
                                    height_diff = max(0.0, self.y - self.target_item["cat_pos"].y())
                                    required_vy = -math.sqrt(2 * self.GRAVITY * max(10, height_diff + 20))
                                    self.vy = max(-1500.0, required_vy)
                                    self.animation = Animation.JUMP
                                    self.jump_cooldown = 1.0
                    
                    if self.behavior_timer <= 0:
                        self.behavior_state = "WANDER"
                        self.behavior_timer = 0.0

        self.apply_gravity(dt, floor)

    def move_towards(self, dx: float, dy: float, dt: float, speed_mult: float, interact_dist: float) -> None:
        speed = self.WALK_SPEED * speed_mult
        
        if abs(dx) > interact_dist:
            self.vx = max(-speed, min(speed, dx * 2.5))
            self.facing = 1 if self.vx >= 0 else -1
        else:
            self.vx = 0.0
            
        if dy < -45 and self.vy >= 0 and self.jump_cooldown <= 0:
            self.vy = -680.0
            self.animation = Animation.JUMP
            self.jump_cooldown = 0.8
        elif self.vy == 0:
            self.animation = Animation.WALK if abs(self.vx) > 5 else Animation.SIT

    def move_x(self, dx: float, dt: float, speed_mult: float) -> None:
        speed = self.WALK_SPEED * speed_mult
        self.vx = max(-speed, min(speed, dx * 2.5))
        self.facing = 1 if self.vx >= 0 else -1
        if self.vy == 0:
            self.animation = Animation.WALK if abs(self.vx) > 5 else Animation.SIT

    def apply_gravity(self, dt: float, floor: float) -> None:
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.y >= floor:
            self.y, self.vy = floor, 0.0
        elif self.y <= 0:
            self.y = 0.0
            self.vy = max(0.0, self.vy)

        # Fix screen bounds
        if self.x <= 0:
            self.x = 0.0
            self.vx *= -1
            self.facing = 1 if self.vx >= 0 else -1
        elif self.x >= self.width() - self.CAT_WIDTH:
            self.x = float(self.width() - self.CAT_WIDTH)
            self.vx *= -1
            self.facing = 1 if self.vx >= 0 else -1

        feet = self.y + self.CAT_HEIGHT
        if self.vy > 0:
            for platform in self.platforms:
                on_platform_x = platform.left() - self.CAT_WIDTH / 2 < self.x < platform.right() - self.CAT_WIDTH / 2
                if on_platform_x and abs(feet - platform.top()) < 30:
                    self.y = float(platform.top() - self.CAT_HEIGHT)
                    self.vy = 0.0
                    break

    def tick(self) -> None:
        now = time.monotonic()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now
        self.update_state(dt)
        self.advance_physics(dt)

        anim_speed = 2.0 if self.animation in (Animation.NAP, Animation.SIT, Animation.STRETCH) else 8.0
        self.animation_time += dt * anim_speed
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.eraseRect(self.rect())
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        # Draw treats
        painter.setBrush(QColor("#b87955")) # Brown fish/treat
        painter.setPen(Qt.NoPen)
        for treat in self.treats:
            painter.drawEllipse(QPoint(int(treat["x"]), int(treat["y"])), 5, 3)

        # Draw Laser
        if self.laser_active:
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(self.laser_pos, 4, 4)
            # glow
            painter.setBrush(QColor(255, 0, 0, 50))
            painter.drawEllipse(self.laser_pos, 8, 8)

        # Draw Cat
        if self.animation is Animation.JUMP:
            frame_idx = 0 if self.vy <= 0 else 2
            pixmap = self.frames[Animation.JUMP].frame(frame_idx)
        else:
            pixmap = self.frames[self.animation].frame(int(self.animation_time))

        if self.facing < 0:
            pixmap = pixmap.transformed(QTransform().scale(-1, 1))

        painter.drawPixmap(QPoint(int(self.x), int(self.y)), pixmap)
        
        # Draw Hearts
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor(255, 50, 50))
        font = painter.font()
        font.setPointSize(14)
        painter.setFont(font)
        for heart in self.hearts:
            painter.setOpacity(max(0.0, min(1.0, heart["life"])))
            painter.drawText(int(heart["x"]), int(heart["y"]), "♥")
            
        painter.setOpacity(1.0)

        # Draw Speech Bubble
        if self.speech["life"] > 0 and self.speech["text"]:
            text = self.speech["text"]
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            
            bx = int(self.x + self.CAT_WIDTH/2 - tw/2)
            by = int(self.y - 15 - th)
            
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.setPen(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(bx - 10, by - 5, tw + 20, th + 10, 5, 5)
            
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(bx, by + th - 3, text)

        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transparent pixel tabby desktop companion")
    default_sheet = str(DEFAULT_SPRITE_SHEET) if DEFAULT_SPRITE_SHEET.is_file() else None
    parser.add_argument("--sprite-sheet", default=default_sheet, help="Path to sprite sheet PNG")
    parser.add_argument("--frame-width", type=int, default=160, help="Frame width in pixels")
    parser.add_argument("--frame-height", type=int, default=160, help="Frame height in pixels")
    parser.add_argument("--columns", type=int, default=4, help="Number of sprite columns")
    parser.add_argument("--rows", type=int, default=5, help="Number of sprite rows")
    parser.add_argument("--scale", type=float, default=0.72, help="Scale multiplier (default: 0.72)")
    parser.add_argument("--platform", action="append", default=[], help="x,y,width,height")
    return parser.parse_args()


def main() -> int:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    args = parse_args()
    application = QApplication(sys.argv)
    try:
        frames = load_frames(args.sprite_sheet, args.frame_width, args.frame_height,
                             args.columns, args.rows, args.scale)
        cat = DesktopCat(frames, args.platform)
    except ValueError as error:
        print(f"desktop_cat: {error}", file=sys.stderr)
        return 2
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())