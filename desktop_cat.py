from __future__ import annotations

import argparse
import math
import random
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QThread, QTimer, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


class Mood(Enum):
    SLEEPY = "passive / sleepy"  # 😴
    SPICY = "spicy / aggressive"
    DROWSY = "drowsy / napping"  # 😴


class Animation(Enum):
    WALK = "walk"
    JUMP = "jump"
    SIT = "sit"
    STRETCH = "stretch"
    NAP = "nap"  # 😴


@dataclass
class FrameSet:
    frames: list[QPixmap]

    def frame(self, index: int) -> QPixmap:
        return self.frames[index % len(self.frames)]


@dataclass
class DesktopItem:
    name: str
    icon_rect: QRect
    cat_pos: QPoint
    atime: float
    platform: QRect


@dataclass
class Treat:
    x: float
    y: float
    vy: float = 0.0


@dataclass
class Heart:
    x: float
    y: float
    life: float = 1.5


@dataclass
class SpeechBubble:
    text: str = ""
    life: float = 0.0


def fallback_frame(scale: float = 4.0, sleeping: bool = False) -> QPixmap:
    width, height = (26, 16) if sleeping else (20, 22)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    colors = {"#": "#2c211e", "b": "#b87955", "s": "#815039", "c": "#f0d8b7"}
    rows = (
        [
            "..........................",
            ".......##....##...........",
            ".....##bb####bb##.........",
            "...##bbbbbbbbbbbb##.......",
            "..#bbbbssbbbbbbssbbb#.....",
            ".#bbbbbbbbbbbbbbbbbbbb#...",
            "#bbbbbbbbbbbbbbbbbbbbbb#..",
            "#bbbbbccccccccccccbbbbbb#.",
            ".#bbbbbbbbbbbbbbbbbbbb#...",
            "..##bbbbbbbbbbbbbbbb##....",
            "....##s##########s##......",
            "..........................",
            "..........................",
            "..........................",
            "..........................",
            "..........................",
        ]  # 😴
        if sleeping
        else [
            "......##....##......",
            ".....#bb#..#bb#.....",
            "....#bbbb##bbbb#....",
            "....#bbbbbbbbbb#....",
            "...#bb#bbbbbb#bb#...",
            "...#bbbbbbbbbbbb#...",
            "...#bbccccccbb#....",
            "....#bccccccb#.....",
            ".....#bbbbbb#......",
            "..###bbbbbb###.....",
            ".#bbbbbbbbbbbb#.....",
            "#bbbbssbbbbssbbb#...",
            "#bbbbbbbbbbbbbbb#...",
            ".#bbbbbbbbbbbbbb#...",
            "..#bbbbbbbbbbbbb#...",
            "...#bbbbbbbbbb#....",
            "....##......##.....",
            "....................",
            "....................",
            "....................",
            "....................",
            "....................",
        ]
    )
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char in colors:
                image.setPixelColor(x, y, QColor(colors[char]))
    return QPixmap.fromImage(image).scaled(
        int(image.width() * scale),
        int(image.height() * scale),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


def load_frames(
    path: str | None,
    frame_width: int,
    frame_height: int,
    columns: int,
    rows: int,
    scale: float,
) -> dict[Animation, FrameSet]:
    if not path or not Path(path).is_file():
        return {
            animation: FrameSet([fallback_frame(scale, animation is Animation.NAP)])
            for animation in Animation
        }
    sheet = QPixmap(path)
    if sheet.isNull():
        raise ValueError(f"Could not load sprite sheet: {path}")
    sets = {}
    for row, animation in enumerate(Animation):
        frames = []
        for column in range(columns):
            rect = QRect(
                column * frame_width,
                row * frame_height,
                frame_width,
                frame_height,
            )
            if (
                rect.right() <= sheet.width() - 1
                and rect.bottom() <= sheet.height() - 1
            ):
                frames.append(
                    sheet.copy(rect).scaled(
                        int(frame_width * scale),
                        int(frame_height * scale),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )
                )
        if frames:
            if len(frames) > 2:
                frames.extend(frames[1:-1][::-1])
            sets[animation] = FrameSet(frames)
    if len(sets) != len(Animation):
        raise ValueError("Sprite sheet needs five rows: walk, jump, sit, stretch, nap")
    return sets


DEFAULT_SPRITE_SHEET = (
    Path(__file__).resolve().parent / "assets" / "tabby_cat_spritesheet.png"
)


class DesktopScanner(QThread):
    items_scanned = Signal(list)

    def __init__(self, cat_width: int, cat_height: int, parent: QObject | None = None):
        super().__init__(parent)
        self.cat_width = cat_width
        self.cat_height = cat_height
        self._has_gio = shutil.which("gio") is not None

    def run(self) -> None:
        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            self.items_scanned.emit([])
            return

        try:
            item_paths = sorted(
                [p for p in desktop.iterdir() if not p.name.startswith(".")],
                key=lambda p: p.name.lower(),
            )
        except OSError:
            self.items_scanned.emit([])
            return

        metadata_map = {}
        if self._has_gio and item_paths:
            try:
                args = ["gio", "info", "-a", "metadata::*"] + [str(p) for p in item_paths]
                res = subprocess.run(args, capture_output=True, text=True, timeout=5.0)
                current_path = None
                for line in res.stdout.splitlines():
                    if line.startswith("local path: "):
                        current_path = line[12:].strip()
                    elif "icon-position:" in line and current_path:
                        pos = line.rsplit(":", 1)[-1].strip()
                        metadata_map[Path(current_path).name] = pos
            except (subprocess.SubprocessError, OSError):
                pass

        items: list[DesktopItem] = []
        for i, path in enumerate(item_paths):
            if self.isInterruptionRequested():
                return

            pos = metadata_map.get(path.name)

            if pos:
                try:
                    x, y = (int(v) for v in pos.split(","))
                except ValueError:
                    x, y = 200 + (i % 6) * 160, 100 + (i // 6) * 120
            else:
                x, y = 200 + (i % 6) * 160, 100 + (i // 6) * 120

            cat_x = x - (self.cat_width - 120) // 2
            cat_y = max(0, y - 45)
            icon_rect = QRect(x, y, 120, 106)
            platform_rect = QRect(x - 10, y + 80, 140, 20)

            try:
                atime = path.stat().st_atime
            except OSError:
                atime = time.time()

            items.append(
                DesktopItem(
                    name=path.name,
                    icon_rect=icon_rect,
                    cat_pos=QPoint(cat_x, cat_y),
                    atime=atime,
                    platform=platform_rect,
                )
            )

        self.items_scanned.emit(items)


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

        self.mood = Mood.SLEEPY  # 😴
        self.auto_mood = True
        self.animation = Animation.SIT
        self.animation_time = 0.0

        self.stretch_timer = 0.0
        self.eating_pause_timer = 0.0
        self.pet_pause_timer = 0.0
        self.rest_nap_timer = 0.0  # 💤
        self.jump_cooldown = 0.0
        self.time_alive = 0.0
        self.rescan_timer = 0.0
        self.telemetry_tick = 0.0

        self.manual_platforms = self.parse_platforms(platform_args)
        self.platforms: list[QRect] = list(self.manual_platforms)
        self.items: list[DesktopItem] = []

        self.behavior_state = "WANDER"
        self.behavior_timer = 0.0
        self.target_item: DesktopItem | None = None
        self.target_x = 200.0

        screen = QApplication.primaryScreen().geometry()
        self.pos_x = 200.0
        self.pos_y = float(screen.height() - self.CAT_HEIGHT)
        self.vx, self.vy = self.WALK_SPEED, 0.0
        self.facing = 1
        self.last_tick = time.monotonic()

        self.laser_active = False
        self.laser_pos = QPoint()
        self.treats: list[Treat] = []
        self.last_shift_ctrl = False

        self.petting_score = 0.0
        self.last_mouse_pos = self.mapFromGlobal(QCursor.pos())
        self.hearts: list[Heart] = []
        self.speech = SpeechBubble()

        self.click_through = True
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.last_interacted_item: DesktopItem | None = None
        self.item_cooldown = 0.0
        self.item_cooldowns: dict[str, float] = {}
        self.last_interacted_x: float | None = None
        self.tower_cooldown = 0.0
        self.consecutive_tower_hops = 0
        self.rest_seek_timer = 0.0
        self._did_pounce = False

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(screen)
        self.show()

        self.scanner = DesktopScanner(self.CAT_WIDTH, self.CAT_HEIGHT, self)
        self.scanner.items_scanned.connect(self.on_desktop_items_scanned)
        self.scanner.start()

        self.setup_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        tray_pixmap = self.frames[Animation.SIT].frame(0)
        self.tray = QSystemTrayIcon(QIcon(tray_pixmap), self)
        self.tray.setToolTip("Desktop Cat 🐈")

        self.tray_menu = QMenu(self)

        title_action = self.tray_menu.addAction("🐾 Desktop Cat")
        title_action.setEnabled(False)
        self.tray_menu.addSeparator()

        mood_menu = self.tray_menu.addMenu("Mood Engine")
        self.mood_action_group = QActionGroup(self)

        auto_action = QAction("Auto (Battery / AC)", self, checkable=True)
        auto_action.setChecked(self.auto_mood)
        auto_action.triggered.connect(lambda: self.set_mood_mode("AUTO"))
        self.mood_action_group.addAction(auto_action)
        mood_menu.addAction(auto_action)
        mood_menu.addSeparator()

        self.mood_actions: dict[Mood, QAction] = {}
        for m in Mood:
            act = QAction(f"{m.name.title()} ({m.value})", self, checkable=True)
            act.setChecked(not self.auto_mood and self.mood is m)
            act.triggered.connect(lambda checked=False, target_mood=m: self.set_manual_mood(target_mood))
            self.mood_action_group.addAction(act)
            mood_menu.addAction(act)
            self.mood_actions[m] = act

        self.tray_menu.addSeparator()
        feed_action = self.tray_menu.addAction("🐟 Feed Treat")
        feed_action.triggered.connect(self.spawn_treat_at_center)

        pet_action = self.tray_menu.addAction("💖 Pet Cat (Purr)")
        pet_action.triggered.connect(self.pet_cat)

        laser_action = self.tray_menu.addAction("🔴 Toggle Laser Pointer")
        laser_action.triggered.connect(self.toggle_laser)

        self.tray_menu.addSeparator()
        clickthrough_action = QAction("🖱️ Click-Through Mode", self, checkable=True)
        clickthrough_action.setChecked(self.click_through)
        clickthrough_action.triggered.connect(self.toggle_click_through)
        self.tray_menu.addAction(clickthrough_action)

        rescan_action = self.tray_menu.addAction("🔍 Rescan Desktop Items")
        rescan_action.triggered.connect(self.trigger_desktop_scan)

        reset_action = self.tray_menu.addAction("🎯 Reset Position to Center")
        reset_action.triggered.connect(self.reset_position)

        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("❌ Quit (Esc)")
        quit_action.triggered.connect(self.close)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

    def pet_cat(self) -> None:
        self.hearts.append(
            Heart(
                x=self.pos_x + self.CAT_WIDTH / 2 + random.randint(-20, 20),
                y=self.pos_y + 20,
                life=1.5,
            )
        )
        self.say("Purrrrr~ ♥", 2.0)
        self.animation = Animation.NAP  # 😴
        self.pet_pause_timer = 2.0
        self.vx = 0.0

    def toggle_laser(self) -> None:
        self.laser_active = not self.laser_active
        if self.laser_active:
            max_x = float(self.width() - self.CAT_WIDTH)
            target_x = self.pos_x + (150 if self.facing >= 0 else -100)
            target_x = max(20.0, min(target_x, max_x - 20.0))
            self.laser_pos = QPoint(int(target_x), int(self.pos_y + self.CAT_HEIGHT / 2))
            self.say("Ooh, red dot! 🔴", 1.5)
        else:
            self.say("Where did it go? 🐾", 1.5)

    def toggle_click_through(self, enabled: bool) -> None:
        self.click_through = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        self.show()
        if enabled:
            self.say("Click-through: ON", 1.8)
        else:
            self.say("Interactive mode: ON", 1.8)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        if hasattr(self, "scanner") and self.scanner.isRunning():
            self.scanner.requestInterruption()
            self.scanner.quit()
            self.scanner.wait(800)
        if hasattr(self, "tray") and self.tray is not None:
            self.tray.hide()
        event.accept()

    def set_mood_mode(self, mode: str) -> None:
        if mode == "AUTO":
            self.auto_mood = True
            self.say("Auto mood: ON", 2.0)
            self.check_power_telemetry()

    def set_manual_mood(self, mood: Mood) -> None:
        self.auto_mood = False
        self.set_mood(mood)
        self.say(f"Mood: {mood.name.title()}!", 2.0)

    def spawn_treat_at_center(self) -> None:
        max_x = float(self.width() - self.CAT_WIDTH)
        spawn_x = max(20.0, min(self.pos_x + self.CAT_WIDTH / 2, max_x - 20.0))
        self.treats.append(Treat(x=spawn_x, y=20.0, vy=0.0))
        self.say("Snack! 🐟", 2.0)

    def trigger_desktop_scan(self) -> None:
        if not self.scanner.isRunning():
            self.scanner.start()

    def pick_wander_target(self) -> float:
        max_x = float(self.width() - self.CAT_WIDTH)

        if self.pos_x > max_x * 0.70:
            return random.uniform(150.0, max_x * 0.50)
        elif self.pos_x < max_x * 0.30:
            return random.uniform(max_x * 0.50, max_x - 150.0)

        if self.items and random.random() < 0.45:
            available = [
                it for it in self.items
                if self.item_cooldowns.get(it.name, 0) <= 0
                and (self.tower_cooldown <= 0 or abs(it.cat_pos.x() - (self.last_interacted_x or -999)) > 50)
            ]
            if available:
                chosen = random.choice(available)
                tgt = float(chosen.cat_pos.x())
                return max(50.0, min(tgt, max_x - 50.0))

        tgt = self.pos_x + random.uniform(-450.0, 450.0)
        tgt = max(60.0, min(tgt, max_x - 60.0))
        if abs(tgt - self.pos_x) < 50:
            tgt += 150 if self.pos_x < max_x / 2 else -150
        return max(60.0, min(tgt, max_x - 60.0))

    def reset_position(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        self.pos_x = (screen.width() - self.CAT_WIDTH) / 2.0
        self.pos_y = float(screen.height() - self.CAT_HEIGHT)
        self.vx = 0.0
        self.vy = 0.0
        self.behavior_state = "WANDER"
        self.target_x = self.pick_wander_target()
        self.behavior_timer = 2.0
        self.animation = Animation.SIT
        self.say("Meow! I'm back!", 2.0)

    def on_desktop_items_scanned(self, items: list[DesktopItem]) -> None:
        self.items = items
        floor = float(self.height() - self.CAT_HEIGHT)
        item_platforms = [it.platform for it in items if it.platform.top() < floor - 30]
        self.platforms = list(self.manual_platforms) + item_platforms

    def say(self, text: str, life: float = 3.0) -> None:
        self.speech = SpeechBubble(text=text, life=life)

    @staticmethod
    def format_item_name(name: str) -> str:
        base = Path(name).stem if "." in name else name
        clean = base.replace("_", " ")
        if len(clean) > 20:
            short = clean[:18].rsplit(" ", 1)[0]
            return (short or clean[:17]) + "..."
        return clean

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

    @staticmethod
    def system_power() -> tuple[int | None, bool]:
        root = Path("/sys/class/power_supply")
        if not root.is_dir():
            return None, True

        battery = next(iter(root.glob("BAT*/capacity")), None)
        percentage: int | None = None

        if battery:
            try:
                percentage = int(battery.read_text().strip())
            except (OSError, ValueError):
                percentage = None

        plugged = False
        for online_path in root.glob("*/online"):
            try:
                if online_path.read_text().strip() == "1":
                    plugged = True
                    break
            except OSError:
                continue

        if battery is None and not plugged:
            plugged = True

        return percentage, plugged

    def check_power_telemetry(self) -> None:
        if not self.auto_mood:
            return
        percentage, plugged = self.system_power()
        if plugged:
            self.set_mood(Mood.DROWSY)  # 😴
        elif percentage is not None and percentage < 30:
            self.set_mood(Mood.SLEEPY)  # 😴
            if random.random() < 0.3 and self.speech.life <= 0:
                self.say("Need charger... 🪫", 2.5)
        else:
            self.set_mood(Mood.SPICY)

    def get_mood_speed_mult(self) -> float:
        if self.mood is Mood.SPICY:
            return 1.45
        elif self.mood is Mood.SLEEPY:
            return 0.65
        return 0.85

    def get_mood_jump_velocity(self) -> float:
        if self.mood is Mood.SPICY:
            return -750.0
        elif self.mood is Mood.SLEEPY:
            return -560.0
        return -660.0

    def update_state(self, dt: float) -> None:
        self.time_alive += dt
        self.telemetry_tick += dt
        self.rescan_timer += dt
        if self.item_cooldown > 0:
            self.item_cooldown = max(0.0, self.item_cooldown - dt)
        if self.tower_cooldown > 0:
            self.tower_cooldown = max(0.0, self.tower_cooldown - dt)

        for name in list(self.item_cooldowns):
            self.item_cooldowns[name] -= dt
            if self.item_cooldowns[name] <= 0:
                del self.item_cooldowns[name]

        for heart in list(self.hearts):
            heart.life -= dt
            heart.y -= 30.0 * dt
            if heart.life <= 0:
                self.hearts.remove(heart)

        if self.speech.life > 0:
            self.speech.life -= dt

        floor = float(self.height() - 20)
        for treat in self.treats:
            prev_treat_y = treat.y
            treat.vy += self.GRAVITY * dt
            treat.y += treat.vy * dt
            if treat.y >= floor:
                treat.y = floor
                treat.vy = 0.0
            elif treat.vy > 0:
                for plat in self.platforms:
                    if plat.left() <= treat.x <= plat.right():
                        if prev_treat_y <= plat.top() + 4 and treat.y >= plat.top() - 4:
                            treat.y = float(plat.top() - 2)
                            treat.vy = 0.0
                            break

        if self.rescan_timer > 30.0:
            self.rescan_timer = 0.0
            if not self.scanner.isRunning():
                self.scanner.start()

        if self.telemetry_tick >= 5.0:
            self.telemetry_tick = 0.0
            self.check_power_telemetry()

    def advance_physics(self, dt: float) -> None:
        floor = float(self.height() - self.CAT_HEIGHT)
        max_x = float(self.width() - self.CAT_WIDTH)
        self.jump_cooldown = max(0.0, self.jump_cooldown - dt)

        mods = QApplication.keyboardModifiers()
        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        cursor = self.mapFromGlobal(QCursor.pos())

        if has_ctrl and has_shift:
            if not self.last_shift_ctrl:
                self.last_shift_ctrl = True
                snack_x = max(20.0, min(float(cursor.x()), max_x + self.CAT_WIDTH - 20.0))
                self.treats.append(Treat(x=snack_x, y=float(cursor.y()), vy=0.0))
                self.say("Snack! 🐟", 2.0)
        else:
            self.last_shift_ctrl = False

        if has_ctrl and not has_shift:
            self.laser_active = True
            clamped_x = max(20, min(cursor.x(), int(self.width() - 20)))
            clamped_y = max(20, min(cursor.y(), int(self.height() - 20)))
            self.laser_pos = QPoint(clamped_x, clamped_y)
        else:
            self.laser_active = False

        cat_rect = QRect(int(self.pos_x), int(self.pos_y), self.CAT_WIDTH, self.CAT_HEIGHT)
        if cat_rect.contains(cursor):
            mouse_speed = abs(cursor.x() - self.last_mouse_pos.x()) + abs(cursor.y() - self.last_mouse_pos.y())
            if mouse_speed > 8:
                self.petting_score += mouse_speed * dt
            if self.petting_score > 25:
                self.petting_score = 0.0
                self.hearts.append(
                    Heart(
                        x=self.pos_x + self.CAT_WIDTH / 2 + random.randint(-20, 20),
                        y=self.pos_y + 20,
                        life=1.5,
                    )
                )
                if random.random() < 0.4 and self.speech.life <= 0:
                    self.say("Purrrrr~ ♥", 2.0)
                self.animation = Animation.NAP  # 😴
                self.pet_pause_timer = 2.0
                self.vx = 0.0
        else:
            self.petting_score = max(0.0, self.petting_score - dt * 40.0)

        self.last_mouse_pos = cursor

        if self.eating_pause_timer > 0:
            self.eating_pause_timer -= dt
            self.animation = Animation.NAP  # 😴
            self.vx = 0.0
            self.apply_gravity(dt, floor)
            return

        if self.pet_pause_timer > 0:
            self.pet_pause_timer -= dt
            self.animation = Animation.NAP  # 😴
            self.vx = 0.0
            self.apply_gravity(dt, floor)
            return

        if self.stretch_timer > 0:
            self.stretch_timer -= dt
            self.animation = Animation.STRETCH
            self.vx = 0.0
            self.apply_gravity(dt, floor)
            return

        cat_center_x = self.pos_x + self.CAT_WIDTH / 2
        cat_center_y = self.pos_y + self.CAT_HEIGHT / 2
        dx_cursor = cursor.x() - cat_center_x
        dy_cursor = cursor.y() - cat_center_y
        dist_to_cursor = math.hypot(dx_cursor, dy_cursor)

        mood_speed = self.get_mood_speed_mult()

        if self.laser_active:
            dx = self.laser_pos.x() - cat_center_x
            dy = self.laser_pos.y() - cat_center_y
            self.move_towards(dx, dy, dt, speed_mult=mood_speed * 2.0, interact_dist=20)

        elif self.treats:
            closest = min(
                self.treats,
                key=lambda t: (t.x - cat_center_x) ** 2 + (t.y - cat_center_y) ** 2,
            )
            dx = closest.x - cat_center_x
            cat_bottom_y = self.pos_y + self.CAT_HEIGHT
            dy = closest.y - (cat_bottom_y - 20)

            if abs(dx) < 45 and abs(dy) < 45:
                self.treats.remove(closest)
                self.hearts.append(
                    Heart(x=self.pos_x + self.CAT_WIDTH / 2, y=self.pos_y + 20, life=1.5)
                )
                self.animation = Animation.NAP  # 😴
                self.eating_pause_timer = 1.5
                self.say("Nom nom! 🐟", 1.8)
                self.vx = 0.0
            else:
                self.move_towards(dx, closest.y - cat_center_y, dt, speed_mult=mood_speed * 1.6, interact_dist=25)

        elif dist_to_cursor < 150.0 and not cat_rect.contains(cursor):
            self.facing = 1 if dx_cursor >= 0 else -1
            if self.mood is Mood.SPICY:
                self.move_towards(dx_cursor, dy_cursor, dt, speed_mult=1.5, interact_dist=35)
                if dy_cursor < -40 and self.vy == 0 and self.jump_cooldown <= 0:
                    self.vy = self.get_mood_jump_velocity()
                    self.animation = Animation.JUMP
                    self.jump_cooldown = 0.8
                    if random.random() < 0.2 and self.speech.life <= 0:
                        self.say("Pounce! 🐾", 1.5)
            elif self.mood is Mood.SLEEPY:  # 😴
                self.vx = 0.0
                self.animation = Animation.SIT
            else:  # 😴
                self.vx = 0.0
                self.animation = Animation.SIT
                if random.random() < 0.05 and self.speech.life <= 0:
                    self.say("Watching you... 👀", 1.5)

        else:
            self.behavior_timer -= dt

            candidates = [
                it for it in self.items
                if self.item_cooldowns.get(it.name, 0) <= 0
                and (self.tower_cooldown <= 0 or abs(it.cat_pos.x() - (self.last_interacted_x or -999)) > 80)
            ]
            unused_item = min(candidates, key=lambda i: i.atime) if candidates else None

            if self.time_alive > 60.0 and unused_item:  # 💤
                self.rest_seek_timer += dt
                if self.rest_seek_timer > 20.0:
                    self.time_alive = 0.0
                    self.rest_seek_timer = 0.0
                    if unused_item:
                        self.item_cooldowns[unused_item.name] = 30.0
                    self.behavior_state = "WANDER"
                    self.target_x = self.pick_wander_target()
                    self.behavior_timer = 4.0
                else:
                    dx = unused_item.cat_pos.x() - self.pos_x
                    dy = unused_item.cat_pos.y() - self.pos_y

                    if abs(dy) < 60 and abs(dx) < 25:
                        self.vx = 0.0
                        self.animation = Animation.NAP  # 😴 💤
                        if self.rest_nap_timer <= 0:
                            self.rest_nap_timer = 12.0
                            self.say(f"Napping on {self.format_item_name(unused_item.name)}... 💤", 3.0)
                        else:
                            self.rest_nap_timer -= dt
                            if self.rest_nap_timer <= 0:
                                self.time_alive = 0.0
                                self.rest_seek_timer = 0.0
                                self.stretch_timer = 1.5
                                self.animation = Animation.STRETCH
                                if unused_item:
                                    self.item_cooldowns[unused_item.name] = 30.0
                                    self.last_interacted_item = unused_item
                                    self.last_interacted_x = float(unused_item.cat_pos.x())
                                self.behavior_state = "WANDER"
                                self.target_x = self.pick_wander_target()
                                self.behavior_timer = 3.0
                    else:
                        height_diff = max(0.0, self.pos_y - unused_item.cat_pos.y())
                        launch_dist = min(130.0, max(75.0, height_diff * 0.35)) if height_diff > 45 else 20.0
                        if abs(dx) > launch_dist and self.vy == 0:
                            self.move_x(dx, dt, speed_mult=mood_speed * 1.1)
                        else:
                            if self.vy == 0 and self.jump_cooldown <= 0:
                                required_vy = -math.sqrt(
                                    2 * self.GRAVITY * max(10, height_diff + 25)
                                )
                                self.vy = max(-1600.0, required_vy)
                                self.animation = Animation.JUMP
                                self.jump_cooldown = 1.0

                                time_to_apex = abs(self.vy) / self.GRAVITY
                                flight_time = time_to_apex * 1.3
                                jump_vx = dx / max(0.2, flight_time)
                                max_jump_speed = self.WALK_SPEED * mood_speed * 1.8
                                self.vx = max(-max_jump_speed, min(max_jump_speed, jump_vx))
                                self.facing = 1 if self.vx >= 0 else -1

            else:
                if self.behavior_state == "WANDER":
                    if self.behavior_timer <= 0:
                        self.target_x = self.pick_wander_target()
                        wander_time = (
                            random.uniform(2.5, 5.0)
                            if self.mood is Mood.SPICY
                            else random.uniform(4.0, 8.0)
                        )
                        self.behavior_timer = wander_time
                        self.animation = Animation.WALK

                    dx = self.target_x - self.pos_x
                    if abs(dx) > 10:
                        self.move_x(dx, dt, speed_mult=mood_speed)
                    else:
                        self.vx = 0.0
                        self.animation = Animation.SIT

                    if self.vy == 0:
                        for item in self.items:
                            if self.item_cooldowns.get(item.name, 0) > 0:
                                continue
                            if self.tower_cooldown > 0 and self.last_interacted_x is not None:
                                if abs(item.cat_pos.x() - self.last_interacted_x) < 50:
                                    continue
                            if self.pos_x >= max_x - 20 and self.facing < 0 and item.cat_pos.x() > max_x - 40:
                                continue

                            dx_item = item.cat_pos.x() - self.pos_x
                            height_diff = self.pos_y - item.cat_pos.y()
                            is_floor_item = (item.platform.top() >= floor - 30) or (abs(height_diff) < 50)
                            is_elevated_item = (not is_floor_item) and (50 <= height_diff <= 380)

                            detect_dist = 160.0 if is_floor_item else 170.0
                            if abs(dx_item) < detect_dist:
                                if is_elevated_item and item.cat_pos.x() > max_x - 30 and self.pos_x >= item.cat_pos.x():
                                    continue

                                if is_floor_item or is_elevated_item:
                                    interact_chance = 1.0 if abs(dx) <= 25 else 0.80
                                    if random.random() < interact_chance:
                                        self.behavior_state = "INTERACT_ITEM"
                                        self.target_item = item
                                        self.behavior_timer = random.uniform(3.5, 6.5)
                                        self._did_pounce = False
                                        display_name = self.format_item_name(item.name)
                                        if is_floor_item:
                                            self.say(
                                                random.choice([
                                                    f"Pouncing {display_name}! 🐾",
                                                    f"Inspecting {display_name} 📂",
                                                    f"Sniffing {display_name}... 👃",
                                                ]),
                                                2.2,
                                            )
                                        else:
                                            self.say(
                                                random.choice([
                                                    f"Pouncing to {display_name}! 🐾",
                                                    f"Leaping to {display_name}! 🏔️",
                                                ]),
                                                2.0,
                                            )
                                        break

                elif self.behavior_state == "INTERACT_ITEM":
                    if self.target_item:
                        dx = self.target_item.cat_pos.x() - self.pos_x
                        dy = self.target_item.cat_pos.y() - self.pos_y
                        height_diff = self.pos_y - self.target_item.cat_pos.y()
                        is_floor_item = (self.target_item.platform.top() >= floor - 30) or (abs(height_diff) < 50)

                        if is_floor_item:
                            if abs(dx) > 15:
                                self.move_x(dx, dt, speed_mult=mood_speed)
                            else:
                                self.vx = 0.0
                                self.facing = 1 if dx >= 0 else -1
                                self.animation = (
                                    Animation.SIT
                                    if self.behavior_timer > 1.8
                                    else Animation.STRETCH
                                )
                        else:
                            if abs(dy) < 60 and self.vy == 0:
                                self.vx = 0.0
                                self.animation = (
                                    Animation.SIT
                                    if self.behavior_timer > 2.0
                                    else Animation.STRETCH
                                )
                            else:
                                launch_dist = min(130.0, max(75.0, height_diff * 0.35))
                                if abs(dx) > launch_dist and self.vy == 0:
                                    self.move_x(dx, dt, speed_mult=mood_speed)
                                else:
                                    if self.vy == 0 and self.jump_cooldown <= 0:
                                        required_vy = -math.sqrt(
                                            2 * self.GRAVITY * max(10, height_diff + 25)
                                        )
                                        self.vy = max(-1100.0, required_vy)
                                        self.animation = Animation.JUMP
                                        self.jump_cooldown = 0.9

                                        time_to_apex = abs(self.vy) / self.GRAVITY
                                        flight_time = time_to_apex * 1.3
                                        jump_vx = dx / max(0.2, flight_time)
                                        max_jump_speed = self.WALK_SPEED * mood_speed * 1.8
                                        self.vx = max(-max_jump_speed, min(max_jump_speed, jump_vx))
                                        self.facing = 1 if self.vx >= 0 else -1

                    if self.behavior_timer <= 0:
                        if self.target_item:
                            self.item_cooldowns[self.target_item.name] = 20.0
                            self.last_interacted_item = self.target_item
                            self.last_interacted_x = float(self.target_item.cat_pos.x())
                            self.consecutive_tower_hops += 1
                            if self.consecutive_tower_hops >= 3 or self.target_item.cat_pos.x() > max_x - 30:
                                self.tower_cooldown = 15.0
                                self.consecutive_tower_hops = 0
                        self.behavior_state = "WANDER"
                        self.target_x = self.pick_wander_target()
                        self.behavior_timer = random.uniform(2.5, 5.0)

        self.apply_gravity(dt, floor)

    def move_towards(
        self,
        dx: float,
        dy: float,
        dt: float,
        speed_mult: float,
        interact_dist: float,
    ) -> None:
        max_x = float(self.width() - self.CAT_WIDTH)
        if (self.pos_x <= 0.0 and dx < 0.0) or (self.pos_x >= max_x and dx > 0.0):
            dx = 0.0

        speed = self.WALK_SPEED * speed_mult
        if abs(dx) > interact_dist:
            self.vx = max(-speed, min(speed, dx * 2.5))
            self.facing = 1 if self.vx >= 0 else -1
        else:
            self.vx = 0.0

        if dy < -45 and self.vy >= 0 and self.jump_cooldown <= 0:
            self.vy = self.get_mood_jump_velocity()
            self.animation = Animation.JUMP
            self.jump_cooldown = 0.8
        elif self.vy == 0:
            self.animation = Animation.WALK if abs(self.vx) > 5 else Animation.SIT

    def move_x(self, dx: float, dt: float, speed_mult: float) -> None:
        max_x = float(self.width() - self.CAT_WIDTH)
        if (self.pos_x <= 0.0 and dx < 0.0) or (self.pos_x >= max_x and dx > 0.0):
            dx = 0.0

        speed = self.WALK_SPEED * speed_mult
        self.vx = max(-speed, min(speed, dx * 2.5))
        self.facing = 1 if self.vx >= 0 else -1
        if self.vy == 0:
            self.animation = Animation.WALK if abs(self.vx) > 5 else Animation.SIT

    def apply_gravity(self, dt: float, floor: float) -> None:
        prev_feet = self.pos_y + self.CAT_HEIGHT
        self.vy += self.GRAVITY * dt
        self.pos_x += self.vx * dt
        self.pos_y += self.vy * dt

        if self.pos_y >= floor:
            self.pos_y, self.vy = floor, 0.0
        elif self.pos_y <= 0.0:
            self.pos_y = 0.0
            self.vy = max(0.0, self.vy)

        max_x = float(self.width() - self.CAT_WIDTH)
        if self.pos_x <= 0.0:
            self.pos_x = 0.0
            self.vx = max(0.0, self.vx)
            if self.vx == 0.0:
                self.vx = self.WALK_SPEED
            self.facing = 1
            if self.behavior_state == "WANDER":
                self.target_x = self.pick_wander_target()
                self.behavior_timer = random.uniform(3.0, 6.0)
        elif self.pos_x >= max_x:
            self.pos_x = max_x
            self.vx = -self.WALK_SPEED
            self.facing = -1
            self.tower_cooldown = 15.0
            self.last_interacted_x = max_x
            self.behavior_state = "WANDER"
            self.target_x = self.pick_wander_target()
            self.behavior_timer = random.uniform(3.0, 6.0)

        curr_feet = self.pos_y + self.CAT_HEIGHT
        if self.vy > 0.0:
            for platform in self.platforms:
                cat_mid_x = self.pos_x + self.CAT_WIDTH / 2
                on_platform_x = (platform.left() - 20) <= cat_mid_x <= (platform.right() + 20)
                if on_platform_x and (prev_feet <= platform.top() + 6) and (curr_feet >= platform.top() - 6):
                    self.pos_y = float(platform.top() - self.CAT_HEIGHT)
                    self.vy = 0.0
                    break

        if self.vy > 60.0 and self.animation not in (Animation.NAP, Animation.SIT, Animation.STRETCH):
            self.animation = Animation.JUMP

        self.pos_x = max(0.0, min(self.pos_x, max_x))
        self.pos_y = max(0.0, min(self.pos_y, floor))

    def tick(self) -> None:
        now = time.monotonic()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now

        self.update_state(dt)
        self.advance_physics(dt)

        anim_speed = (
            2.0
            if self.animation in (Animation.NAP, Animation.SIT, Animation.STRETCH)
            else (10.0 if self.mood is Mood.SPICY else 8.0)
        )
        self.animation_time += dt * anim_speed
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.eraseRect(self.rect())
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        painter.setBrush(QColor("#b87955"))
        painter.setPen(Qt.PenStyle.NoPen)
        for treat in self.treats:
            painter.drawEllipse(QPoint(int(treat.x), int(treat.y)), 6, 4)

        if self.laser_active:
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.laser_pos, 4, 4)
            painter.setBrush(QColor(255, 0, 0, 50))
            painter.drawEllipse(self.laser_pos, 8, 8)

        if self.animation is Animation.JUMP:
            frame_idx = 0 if self.vy <= 0 else 2
            pixmap = self.frames[Animation.JUMP].frame(frame_idx)
        else:
            pixmap = self.frames[self.animation].frame(int(self.animation_time))

        if self.facing < 0:
            pixmap = pixmap.transformed(QTransform().scale(-1, 1))

        painter.drawPixmap(QPoint(int(self.pos_x), int(self.pos_y)), pixmap)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QColor(255, 50, 50))
        font = painter.font()
        font.setPointSize(14)
        painter.setFont(font)
        for heart in self.hearts:
            painter.setOpacity(max(0.0, min(1.0, heart.life)))
            painter.drawText(int(heart.x), int(heart.y), "♥")

        painter.setOpacity(1.0)

        if self.speech.life > 0 and self.speech.text:
            text = self.speech.text
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()

            bx = int(self.pos_x + self.CAT_WIDTH / 2 - tw / 2)
            by = int(self.pos_y - 15 - th)

            bx = max(10, min(bx, self.width() - tw - 25))
            by = max(10, min(by, self.height() - th - 20))

            painter.setBrush(QColor(255, 255, 255, 230))
            painter.setPen(QColor(0, 0, 0, 160))
            painter.drawRoundedRect(bx - 10, by - 5, tw + 20, th + 10, 6, 6)

            painter.setPen(QColor(0, 0, 0))
            painter.drawText(bx, by + th - 3, text)

        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mouseMoveEvent(self, event) -> None:
        if not self.click_through:
            cursor = event.position().toPoint()
            cat_rect = QRect(int(self.pos_x), int(self.pos_y), self.CAT_WIDTH, self.CAT_HEIGHT)
            if cat_rect.contains(cursor):
                self.petting_score += 10.0
                if self.petting_score > 30.0:
                    self.petting_score = 0.0
                    self.pet_cat()
            if self.is_dragging:
                max_x = float(self.width() - self.CAT_WIDTH)
                floor = float(self.height() - self.CAT_HEIGHT)
                self.pos_x = max(0.0, min(float(cursor.x() - self.drag_offset.x()), max_x))
                self.pos_y = max(0.0, min(float(cursor.y() - self.drag_offset.y()), floor))
                self.vx, self.vy = 0.0, 0.0
                self.update()

    def mousePressEvent(self, event) -> None:
        if not self.click_through and event.button() == Qt.MouseButton.LeftButton:
            cursor = event.position().toPoint()
            cat_rect = QRect(int(self.pos_x), int(self.pos_y), self.CAT_WIDTH, self.CAT_HEIGHT)
            if cat_rect.contains(cursor):
                self.is_dragging = True
                self.drag_offset = QPoint(int(cursor.x() - self.pos_x), int(cursor.y() - self.pos_y))
                self.animation = Animation.JUMP

    def mouseReleaseEvent(self, event) -> None:
        if self.is_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False


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
        frames = load_frames(
            args.sprite_sheet,
            args.frame_width,
            args.frame_height,
            args.columns,
            args.rows,
            args.scale,
        )
        cat = DesktopCat(frames, args.platform)
    except ValueError as error:
        print(f"desktop_cat: {error}", file=sys.stderr)
        return 2
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())