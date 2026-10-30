import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from milestones import decide_notifications, label, progress_ratio  # noqa: E402

STEP = 1_000_000
DISCORD_APPROACH = 50_000


def decide(entry, views):
    return decide_notifications(entry, views, STEP, DISCORD_APPROACH)


class DecideNotificationsTest(unittest.TestCase):
    def test_new_video_is_baselined_without_notification(self):
        d = decide(None, 2_300_000)
        self.assertTrue(d.is_new)
        self.assertFalse(d.reached)
        self.assertFalse(d.approach_notify)
        self.assertEqual(d.current_milestone, 2)

    def test_new_video_near_first_milestone_gets_approach(self):
        d = decide(None, 960_000)
        self.assertFalse(d.reached)
        self.assertTrue(d.approach_notify)
        self.assertEqual(d.next_milestone, 1)
        self.assertEqual(label(d.next_milestone, STEP), "100万")

    def test_approach_within_threshold(self):
        d = decide({"last_milestone": 2, "approach_notified_for": None}, 2_960_000)
        self.assertTrue(d.approach_notify)
        self.assertEqual(d.next_milestone, 3)
        self.assertEqual(d.remaining, 40_000)

    def test_approach_not_repeated(self):
        d = decide({"last_milestone": 2, "approach_notified_for": 3}, 2_980_000)
        self.assertFalse(d.reached)
        self.assertFalse(d.approach_notify)

    def test_reach_single_milestone(self):
        d = decide({"last_milestone": 2, "approach_notified_for": 3}, 3_000_000)
        self.assertTrue(d.reached)
        self.assertEqual(d.reached_from, 2)
        self.assertEqual(d.current_milestone, 3)
        self.assertFalse(d.skipped_multiple)
        # 次の節目(400万)まで100万あるので事前通知はしない
        self.assertFalse(d.approach_notify)

    def test_reach_multiple_milestones_at_once(self):
        d = decide({"last_milestone": 2, "approach_notified_for": None}, 4_100_000)
        self.assertTrue(d.reached)
        self.assertTrue(d.skipped_multiple)
        self.assertEqual(d.current_milestone, 4)

    def test_decrease_is_ignored(self):
        d = decide({"last_milestone": 3, "approach_notified_for": None}, 2_999_000)
        self.assertFalse(d.reached)
        self.assertFalse(d.approach_notify)
        self.assertEqual(d.current_milestone, 3)

    def test_reach_and_new_next_within_threshold_sends_both(self):
        d = decide({"last_milestone": 2, "approach_notified_for": 3}, 3_960_000)
        self.assertTrue(d.reached)
        self.assertTrue(d.approach_notify)
        self.assertEqual(d.next_milestone, 4)

    def test_exact_threshold_boundary(self):
        d = decide({"last_milestone": 2, "approach_notified_for": None}, 2_950_000)
        self.assertTrue(d.approach_notify)
        d = decide({"last_milestone": 2, "approach_notified_for": None}, 2_949_999)
        self.assertFalse(d.approach_notify)


class LabelTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(label(1, STEP), "100万")
        self.assertEqual(label(10, STEP), "1000万")


class ProgressTest(unittest.TestCase):
    def test_progress_is_clamped(self):
        self.assertAlmostEqual(progress_ratio(2_500_000, 2, STEP), 0.5)
        # 減少時(views < current*step)でも負にならない
        self.assertEqual(progress_ratio(2_999_000, 3, STEP), 0.0)


if __name__ == "__main__":
    unittest.main()
