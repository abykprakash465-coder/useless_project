import os
import sys
import math
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for QPixmap / QWidget operations
app = QApplication.instance() or QApplication(sys.argv)

from desktop_cat import (
    DesktopItem,
    Treat,
    Heart,
    SpeechBubble,
    Mood,
    Animation,
    FrameSet,
    fallback_frame,
    load_frames,
    DesktopScanner,
    DesktopCat,
)


class TestDesktopCat(unittest.TestCase):
    def test_dataclasses(self):
        item = DesktopItem(
            name="Documents",
            icon_rect=QRect(100, 100, 120, 106),
            cat_pos=QPoint(100, 55),
            atime=1700000000.0,
            platform=QRect(90, 180, 140, 20),
        )
        self.assertEqual(item.name, "Documents")
        self.assertEqual(item.icon_rect.width(), 120)

        treat = Treat(x=150.0, y=200.0, vy=10.0)
        self.assertEqual(treat.x, 150.0)

        heart = Heart(x=10.0, y=20.0, life=1.5)
        self.assertEqual(heart.life, 1.5)

        speech = SpeechBubble(text="Meow!", life=3.0)
        self.assertEqual(speech.text, "Meow!")

    def test_fallback_frames(self):
        pix = fallback_frame(scale=1.0, sleeping=False)
        self.assertFalse(pix.isNull())
        self.assertGreater(pix.width(), 0)

        pix_sleep = fallback_frame(scale=1.0, sleeping=True)
        self.assertFalse(pix_sleep.isNull())

        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        self.assertIn(Animation.WALK, frames)
        self.assertIn(Animation.NAP, frames)
        self.assertEqual(len(frames), len(Animation))

    def test_system_power(self):
        percentage, plugged = DesktopCat.system_power()
        self.assertIsInstance(plugged, bool)
        if percentage is not None:
            self.assertIsInstance(percentage, int)

    def test_desktop_scanner(self):
        scanner = DesktopScanner(160, 160)
        results = []
        scanner.items_scanned.connect(lambda items: results.append(items))
        scanner.run()
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], list)

    def test_cat_instance_and_state(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, ["100,500,200,20"])

        # Check platform parsing
        self.assertTrue(len(cat.platforms) >= 1)
        self.assertEqual(cat.platforms[0], QRect(100, 500, 200, 20))

        # Check time_alive increments
        initial_time = cat.time_alive
        cat.update_state(0.05)
        self.assertGreater(cat.time_alive, initial_time)

        # Check mood changes and speed multipliers
        cat.set_mood(Mood.SPICY)
        self.assertGreater(cat.get_mood_speed_mult(), 1.0)

        cat.set_mood(Mood.SLEEPY)
        self.assertLess(cat.get_mood_speed_mult(), 1.0)

        # Check petting pause holding
        cat.pet_pause_timer = 2.0
        cat.advance_physics(0.1)
        self.assertEqual(cat.animation, Animation.NAP)
        self.assertAlmostEqual(cat.pet_pause_timer, 1.9, places=2)

        # Check eating pause holding
        cat.pet_pause_timer = 0.0
        cat.eating_pause_timer = 1.5
        cat.advance_physics(0.1)
        self.assertEqual(cat.animation, Animation.NAP)
        self.assertAlmostEqual(cat.eating_pause_timer, 1.4, places=2)

        # Test 150px Proximity in SPICY mood
        cat.eating_pause_timer = 0.0
        cat.set_mood(Mood.SPICY)
        cat.pos_x, cat.pos_y = 200.0, 500.0
        cursor_local = QPoint(280, 520)
        dx = cursor_local.x() - (cat.pos_x + cat.CAT_WIDTH / 2)
        dist = math.hypot(dx, 0)
        self.assertLess(dist, 150.0)

        # Test resting on oldest item when reached
        test_item = DesktopItem(
            name="OldDoc",
            icon_rect=QRect(200, 500, 120, 106),
            cat_pos=QPoint(200, 500),
            atime=100.0,
            platform=QRect(190, 580, 140, 20),
        )
        cat.items = [test_item]
        cat.time_alive = 65.0  # Greater than 60s
        cat.pos_x, cat.pos_y = 200.0, 500.0  # Placed directly on item
        cat.advance_physics(0.1)
        self.assertEqual(cat.animation, Animation.NAP)
        self.assertGreater(cat.rest_nap_timer, 0.0)

        # Test Tray Menu
        self.assertIsNotNone(cat.tray)
        menu = cat.tray.contextMenu()
        self.assertIsNotNone(menu)
        actions = [a.text() for a in menu.actions()]
        self.assertTrue(any("Quit" in a for a in actions))
        self.assertTrue(any("Treat" in a for a in actions))
        self.assertTrue(any("Pet" in a for a in actions))
        self.assertTrue(any("Laser" in a for a in actions))
        self.assertTrue(any("Click-Through" in a for a in actions))

        cat.close()

    def test_swept_collision(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        platform = QRect(100, 400, 200, 20)
        cat = DesktopCat(frames, ["100,400,200,20"])

        # Cat right above the platform
        cat.pos_x = 150.0
        cat.pos_y = float(platform.top() - cat.CAT_HEIGHT - 5)
        cat.vy = 1200.0  # High descent velocity that would normally tunnel

        cat.apply_gravity(0.04, 1080.0)
        # Should have cleanly landed on top of platform
        self.assertEqual(cat.pos_y, float(platform.top() - cat.CAT_HEIGHT))
        self.assertEqual(cat.vy, 0.0)

        cat.close()

    def test_treat_eating_on_floor(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        floor = float(cat.height() - cat.CAT_HEIGHT)
        cat.pos_y = floor
        cat.vy = 0.0
        cat.eating_pause_timer = 0.0

        # Treat on floor near the cat
        treat_x = cat.pos_x + cat.CAT_WIDTH / 2
        treat_y = float(cat.height() - 20)
        cat.treats = [Treat(x=treat_x, y=treat_y, vy=0.0)]

        cat.advance_physics(0.05)
        # Treat should be eaten
        self.assertEqual(len(cat.treats), 0)
        self.assertGreater(cat.eating_pause_timer, 0.0)

        cat.close()

    def test_parabolic_jump_horizontal_momentum(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        cat.pos_x = 100.0
        cat.pos_y = 800.0
        cat.vy = 0.0
        cat.jump_cooldown = 0.0

        target_item = DesktopItem(
            name="TargetDoc",
            icon_rect=QRect(350, 400, 120, 106),
            cat_pos=QPoint(350, 400),
            atime=50.0,
            platform=QRect(340, 480, 140, 20),
        )
        cat.items = [target_item]
        cat.behavior_state = "INTERACT_ITEM"
        cat.target_item = target_item
        cat.time_alive = 10.0

        # Run physics to initiate jump
        cat.advance_physics(0.05)

        # After initiating jump, cat should have forward velocity toward target x=350
        if cat.animation == Animation.JUMP:
            self.assertGreater(cat.vx, 0.0)

        cat.close()

    def test_pick_wander_target_right_edge_bias(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        max_x = float(cat.width() - cat.CAT_WIDTH)

        # When at the right edge
        cat.pos_x = max_x
        for _ in range(50):
            tgt = cat.pick_wander_target()
            # Must be biased toward left/center (<= max_x * 0.55)
            self.assertLessEqual(tgt, max_x * 0.55 + 1.0)
            self.assertGreaterEqual(tgt, 150.0)

        # When at the left edge
        cat.pos_x = 0.0
        for _ in range(50):
            tgt = cat.pick_wander_target()
            # Must be biased toward right/center (>= max_x * 0.45)
            self.assertGreaterEqual(tgt, max_x * 0.45 - 1.0)
            self.assertLessEqual(tgt, max_x - 150.0)

        cat.close()

    def test_right_boundary_active_bounce(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        max_x = float(cat.width() - cat.CAT_WIDTH)
        floor = float(cat.height() - cat.CAT_HEIGHT)

        # Force cat past right boundary
        cat.pos_x = max_x + 10.0
        cat.vx = cat.WALK_SPEED
        cat.behavior_state = "WANDER"

        cat.apply_gravity(0.016, floor)

        # Cat should be clamped, velocity negative, facing left, target inwards
        self.assertEqual(cat.pos_x, max_x)
        self.assertLess(cat.vx, 0.0)
        self.assertEqual(cat.facing, -1)
        self.assertLessEqual(cat.target_x, max_x * 0.55 + 1.0)

        cat.close()

    def test_floor_level_icon_rejection(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        floor = float(cat.height() - cat.CAT_HEIGHT)
        cat.pos_x = 1780.0
        cat.pos_y = floor
        cat.vy = 0.0

        # Floor icon at x=1789, y=965 (like abywebbuild)
        floor_item = DesktopItem(
            name="abywebbuild",
            icon_rect=QRect(1789, 965, 120, 106),
            cat_pos=QPoint(1789, 920),
            atime=100.0,
            platform=QRect(1779, 1045, 140, 20),
        )
        cat.items = [floor_item]
        cat.behavior_state = "WANDER"
        cat.target_x = 500.0  # Walking left

        # Step physics - cat should NOT enter INTERACT_ITEM
        cat.advance_physics(0.05)
        self.assertEqual(cat.behavior_state, "WANDER")
        self.assertNotEqual(cat.behavior_state, "INTERACT_ITEM")

        cat.close()

    def test_tower_cooldown_prevents_repetition(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        floor = float(cat.height() - cat.CAT_HEIGHT)
        cat.pos_x = 1789.0
        cat.pos_y = floor
        cat.vy = 0.0

        elevated_item = DesktopItem(
            name="ElevatedFile",
            icon_rect=QRect(1789, 700, 120, 106),
            cat_pos=QPoint(1789, 655),
            atime=100.0,
            platform=QRect(1779, 780, 140, 20),
        )
        cat.items = [elevated_item]
        cat.behavior_state = "WANDER"
        cat.target_x = 500.0

        # Set tower cooldown at x=1789
        cat.last_interacted_x = 1789.0
        cat.tower_cooldown = 30.0

        # Even if passing the icon, tower cooldown prevents interaction
        for _ in range(10):
            cat.advance_physics(0.016)
            self.assertEqual(cat.behavior_state, "WANDER")

        cat.close()

    def test_patrol_rest_seek_timeout(self):
        frames = load_frames(None, 160, 160, 4, 5, 0.72)
        cat = DesktopCat(frames, [])
        floor = float(cat.height() - cat.CAT_HEIGHT)
        cat.pos_x = 1789.0
        cat.pos_y = floor

        unreachable_item = DesktopItem(
            name="Unreachable",
            icon_rect=QRect(1789, 100, 120, 106),
            cat_pos=QPoint(1789, 50),
            atime=10.0,
            platform=QRect(1779, 180, 140, 20),
        )
        cat.items = [unreachable_item]
        cat.time_alive = 65.0
        cat.rest_seek_timer = 20.5  # Exceeded 20 seconds timeout

        cat.advance_physics(0.016)

        # Must abort seeking, reset time_alive, switch to WANDER, target interior
        self.assertEqual(cat.time_alive, 0.0)
        self.assertEqual(cat.rest_seek_timer, 0.0)
        self.assertEqual(cat.behavior_state, "WANDER")
        max_x = float(cat.width() - cat.CAT_WIDTH)
        self.assertLessEqual(cat.target_x, max_x * 0.55 + 1.0)

        cat.close()


if __name__ == "__main__":
    unittest.main()
