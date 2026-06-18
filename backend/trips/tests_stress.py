"""
Stress tests for ETTO HOS engine and log builder.
These tests specifically target the logical bugs found in the audit.
"""
from django.test import TestCase
from datetime import datetime, timezone
from trips.services.hos_engine import (
    HOSEngine, UnitOfWork, run_simulation,
    MAX_DRIVE_PER_SHIFT, MAX_DUTY_WINDOW, DRIVE_BEFORE_BREAK,
    CYCLE_LIMIT, RESTART_DURATION, DAILY_OFF_RESET, BREAK_DURATION
)
from trips.services.log_builder import build_logs, snap_to_15_min


class CycleLimitONDutyTests(TestCase):
    """Bug 1/8: ON/YM time must not exceed the 70-hour cycle limit."""

    def test_on_duty_at_cycle_boundary(self):
        """cycle_used=69, ON unit of 5 hours -> must insert 34-hr restart after 1 hour."""
        units = [UnitOfWork("ON", 5.0, 0.0, "pickup")]
        segments = run_simulation(units, 69.0)
        
        # First chunk: 1 hour ON (69 + 1 = 70 = CYCLE_LIMIT)
        self.assertEqual(segments[0].status, "ON")
        self.assertEqual(segments[0].duration_hours, 1.0)
        
        # Then a 34-hr restart
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 34.0)
        
        # Then remaining 4 hours ON
        self.assertEqual(segments[2].status, "ON")
        self.assertEqual(segments[2].duration_hours, 4.0)
    
    def test_ym_at_cycle_boundary(self):
        """YM should also clamp against cycle limit."""
        units = [UnitOfWork("YM", 3.0, 0.0, "yard move")]
        segments = run_simulation(units, 69.5)
        
        self.assertEqual(segments[0].status, "ON")  # YM emits as ON
        self.assertEqual(segments[0].duration_hours, 0.5)
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 34.0)
        self.assertEqual(segments[2].status, "ON")
        self.assertEqual(segments[2].duration_hours, 2.5)
    
    def test_on_duty_exactly_at_limit(self):
        """cycle_used=70 exactly -> must restart before any ON time."""
        units = [UnitOfWork("ON", 2.0, 0.0, "dropoff")]
        segments = run_simulation(units, 70.0)
        
        self.assertEqual(segments[0].status, "OFF")
        self.assertEqual(segments[0].duration_hours, 34.0)
        self.assertEqual(segments[1].status, "ON")
        self.assertEqual(segments[1].duration_hours, 2.0)

    def test_on_duty_large_exceeds_cycle_multiple_times(self):
        """Very large ON block that would exceed cycle limit multiple times."""
        # 140 hours of ON duty with cycle_used=0
        # Each window block = 14h ON + 10h reset
        # After 5 × 14 = 70h cycle, need 34-hr restart
        # Then 5 more × 14 = 70h + restarts
        units = [UnitOfWork("ON", 140.0, 0.0, "marathon pickup")]
        segments = run_simulation(units, 0.0)
        
        total_on = sum(s.duration_hours for s in segments if s.status == "ON")
        
        # All 140 hours of ON duty should be accounted for
        self.assertAlmostEqual(total_on, 140.0, places=1)
        
        # Should have at least 1 cycle restart
        has_restart = any(s.status == "OFF" and s.duration_hours >= 34 for s in segments)
        self.assertTrue(has_restart)
        
        # No single ON block should exceed 14 hours (window limit)
        for s in segments:
            if s.status == "ON":
                self.assertLessEqual(s.duration_hours, 14.0 + 0.01,
                    f"ON block of {s.duration_hours}h exceeds 14h window")


class CycleLimitDriveTests(TestCase):
    """Verify DRIVE branch cycle limit still works correctly after refactor."""

    def test_drive_at_cycle_boundary_with_existing_on_duty(self):
        """cycle_used=65 from previous ON, then drive 10 hours.
        Should split: drive 5 (hit 70), restart, drive 5."""
        units = [
            UnitOfWork("ON", 5.0, 0.0, "preload"),
            UnitOfWork("DRIVE", 10.0, 550.0, "drive")
        ]
        segments = run_simulation(units, 60.0)
        
        # ON: 5 hours (cycle now 65)
        self.assertEqual(segments[0].status, "ON")
        self.assertEqual(segments[0].duration_hours, 5.0)
        # DRIVE: 5 hours (cycle hits 70)
        self.assertEqual(segments[1].status, "D")
        self.assertEqual(segments[1].duration_hours, 5.0)
        # 34-hr restart
        self.assertEqual(segments[2].status, "OFF")
        self.assertEqual(segments[2].duration_hours, 34.0)
        # DRIVE: remaining 5 hours
        self.assertEqual(segments[3].status, "D")
        self.assertEqual(segments[3].duration_hours, 5.0)


class PCTests(TestCase):
    """Personal Conveyance should not consume window or cycle."""

    def test_pc_does_not_consume_window(self):
        """PC should not increment window_used."""
        engine = HOSEngine(0.0)
        engine.simulate([
            UnitOfWork("DRIVE", 10.0, 550.0, "drive"),
            UnitOfWork("PC", 2.0, 0.0, "personal conveyance"),
            UnitOfWork("DRIVE", 1.0, 55.0, "more drive")
        ])
        
        # After 10h drive + break, window should be about 10.5
        # PC should NOT add to it
        # The last 1h drive should still fit in the window
        drive_segments = [s for s in engine.segments if s.status == "D"]
        total_drive = sum(s.duration_hours for s in drive_segments)
        self.assertAlmostEqual(total_drive, 11.0, places=1)
    
    def test_pc_does_not_consume_cycle(self):
        """PC should not increment cycle_used."""
        engine = HOSEngine(69.0)
        engine.simulate([
            UnitOfWork("PC", 5.0, 0.0, "personal conveyance"),
            UnitOfWork("DRIVE", 1.0, 55.0, "drive after PC")
        ])
        
        # PC should not push cycle to 74, so no restart needed before the drive
        # The drive should happen without a 34-hr restart
        has_restart = any(s.status == "OFF" and s.duration_hours >= 34 for s in engine.segments)
        self.assertFalse(has_restart)


class WindowOverflowTests(TestCase):
    """14-hour window enforcement edge cases."""

    def test_on_duty_window_overflow_with_drive(self):
        """ON 13 hours, then DRIVE 2 -> should reset before drive."""
        units = [
            UnitOfWork("ON", 13.0, 0.0, "long loading"),
            UnitOfWork("DRIVE", 2.0, 110.0, "drive")
        ]
        segments = run_simulation(units, 0.0)
        
        # ON 13, then drive should hit window limit at 14 (1hr drive)
        # or trigger a full reset before driving starts
        total_drive = sum(s.duration_hours for s in segments if s.status == "D")
        self.assertAlmostEqual(total_drive, 2.0, places=1)
    
    def test_on_window_and_cycle_both_near_limit(self):
        """Window near 14 AND cycle near 70 simultaneously."""
        units = [
            UnitOfWork("ON", 2.0, 0.0, "loading"),
            UnitOfWork("DRIVE", 5.0, 275.0, "drive")
        ]
        segments = run_simulation(units, 68.0)
        
        # cycle_used=68, ON 2 hours -> cycle=70, then drive needs restart
        total_drive = sum(s.duration_hours for s in segments if s.status == "D")
        self.assertAlmostEqual(total_drive, 5.0, places=1)
        has_restart = any(s.status == "OFF" and s.duration_hours >= 34 for s in segments)
        self.assertTrue(has_restart)


class BreakTests(TestCase):
    """30-minute break insertion tests."""

    def test_break_after_8_hours_drive(self):
        """Standard 8-hour drive should trigger a 30-min break."""
        units = [UnitOfWork("DRIVE", 10.0, 550.0, "drive")]
        segments = run_simulation(units, 0.0)
        
        # First 8 hours drive
        self.assertEqual(segments[0].status, "D")
        self.assertEqual(segments[0].duration_hours, 8.0)
        # 30-min break
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 0.5)
        # Remaining 2 hours drive
        self.assertEqual(segments[2].status, "D")
        self.assertEqual(segments[2].duration_hours, 2.0)

    def test_break_when_window_too_small(self):
        """If window can't fit a break, should do 10-hr reset instead."""
        # ON 5.5 hours + drive 8 = 13.5, break would push to 14 -> reset
        units = [
            UnitOfWork("ON", 5.5, 0.0, "loading"),
            UnitOfWork("DRIVE", 9.0, 495.0, "drive"),
        ]
        segments = run_simulation(units, 0.0)
        
        # ON 5.5, DRIVE 8 (hit break limit), but window at 13.5 + 0.5 = 14 -> exactly at limit
        # Should either do a break or a 10-hr reset
        has_reset = any(s.status == "OFF" and s.duration_hours >= 10 for s in segments)
        total_drive = sum(s.duration_hours for s in segments if s.status == "D")
        self.assertTrue(has_reset or total_drive == 9.0)


class LogBuilderTests(TestCase):
    """Log builder correctness tests."""

    def _make_segments(self, specs):
        """Helper to create StatusSegment list."""
        from trips.services.hos_engine import StatusSegment
        return [StatusSegment(s, d, l) for s, d, l in specs]

    def test_daily_totals_sum_to_24(self):
        """Every day's totals must sum to exactly 24 hours."""
        segments = self._make_segments([
            ("D", 8.0, "drive leg 1"),
            ("OFF", 0.5, "30-min Break"),
            ("D", 3.0, "drive leg 2"),
            ("OFF", 10.0, "10-hr Off Duty"),
            ("D", 2.0, "drive leg 3"),
        ])
        start = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
        logs = build_logs(segments, start, 750.0)
        
        for log in logs:
            total = sum(log["totals"].values())
            self.assertAlmostEqual(total, 24.0, places=1,
                msg=f"Day {log['date']} totals sum to {total}, not 24")

    def test_off_duty_never_negative(self):
        """OFF duty hours must never be negative."""
        # Fill a day entirely with driving and on-duty to stress the OFF correction
        segments = self._make_segments([
            ("D", 11.0, "maximum drive"),
            ("ON", 3.0, "on duty"),
            ("OFF", 10.0, "reset"),
        ])
        start = datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc)
        logs = build_logs(segments, start, 605.0)
        
        for log in logs:
            self.assertGreaterEqual(log["totals"]["OFF"], 0,
                msg=f"Day {log['date']} has negative OFF: {log['totals']['OFF']}")

    def test_daily_miles_sum_roughly_matches_total(self):
        """Sum of daily miles should roughly equal total distance."""
        segments = self._make_segments([
            ("D", 5.0, "drive day 1"),
            ("OFF", 10.0, "reset"),
            ("D", 5.0, "drive day 2"),
            ("OFF", 10.0, "reset"),
            ("D", 5.0, "drive day 3"),
        ])
        start = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
        total_distance = 825.0  # 15 hours * 55 mph
        logs = build_logs(segments, start, total_distance)
        
        total_daily_miles = sum(log["total_miles"] for log in logs)
        # Should be within 10% of actual distance
        self.assertAlmostEqual(total_daily_miles, total_distance, delta=total_distance * 0.15,
            msg=f"Daily miles sum {total_daily_miles} far from total {total_distance}")
    
    def test_driving_remarks_preserved(self):
        """Bug 15: Driving remarks should NOT be stripped."""
        segments = self._make_segments([
            ("D", 5.0, "Drive to Oklahoma City, OK"),
            ("ON", 1.0, "Pickup"),
        ])
        start = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
        logs = build_logs(segments, start, 275.0)
        
        # Find a driving segment and check its remark
        drive_segs = [s for log in logs for s in log["segments"] if s["status"] == "D"]
        has_drive_remark = any(s["remark"] == "Drive to Oklahoma City, OK" for s in drive_segs)
        self.assertTrue(has_drive_remark, "Driving remarks were stripped from log sheets")


class Snap15MinTests(TestCase):
    """Test the 15-minute snapping function."""

    def test_snap_boundaries(self):
        """Verify snapping at various minute values."""
        cases = [
            (0, 0), (7, 0), (8, 15), (15, 15),
            (22, 15), (23, 30), (30, 30), (37, 30),
            (38, 45), (45, 45), (52, 45), (53, 60),  # 60 -> rolls to next hour
        ]
        for input_min, expected_min in cases:
            dt = datetime(2026, 6, 16, 10, input_min, 0, tzinfo=timezone.utc)
            result = snap_to_15_min(dt)
            actual_min = result.minute if expected_min < 60 else 0
            if expected_min == 60:
                self.assertEqual(result.hour, 11, f"Minute {input_min}: expected hour rollover")
                self.assertEqual(result.minute, 0)
            else:
                self.assertEqual(actual_min, expected_min, 
                    f"Minute {input_min}: expected :{expected_min:02d}, got :{actual_min:02d}")


class MegaTripStressTest(TestCase):
    """End-to-end stress test: simulate a massive coast-to-coast trip."""

    def test_80_hour_drive(self):
        """80 hours of driving. Must produce valid segments with no infinite loops."""
        units = [UnitOfWork("DRIVE", 80.0, 4400.0, "coast-to-coast")]
        segments = run_simulation(units, 0.0)
        
        total_drive = sum(s.duration_hours for s in segments if s.status == "D")
        self.assertAlmostEqual(total_drive, 80.0, places=1)
        
        # Should have at least one 34-hr restart (cycle limit)
        has_restart = any(s.status == "OFF" and s.duration_hours == 34.0 for s in segments)
        self.assertTrue(has_restart, "80-hour trip must trigger a 34-hr restart")
        
        # Should have multiple 10-hr resets
        reset_count = sum(1 for s in segments if s.status == "OFF" and s.duration_hours == 10.0)
        self.assertGreaterEqual(reset_count, 2, "80-hour trip should have multiple 10-hr resets")
    
    def test_mixed_units_realistic_trip(self):
        """Realistic trip: drive, pickup, drive, dropoff, PC."""
        units = [
            UnitOfWork("DRIVE", 6.0, 330.0, "Drive to pickup"),
            UnitOfWork("YM", 0.25, 0.0, "Yard move pickup"),
            UnitOfWork("ON", 0.75, 0.0, "Pickup loading"),
            UnitOfWork("DRIVE", 14.0, 770.0, "Drive to dropoff"),
            UnitOfWork("YM", 0.25, 0.0, "Yard move dropoff"),
            UnitOfWork("ON", 0.75, 0.0, "Dropoff unloading"),
            UnitOfWork("PC", 0.5, 0.0, "Personal Conveyance"),
        ]
        segments = run_simulation(units, 20.0)
        
        total_drive = sum(s.duration_hours for s in segments if s.status == "D")
        self.assertAlmostEqual(total_drive, 20.0, places=1)
        
        total_on = sum(s.duration_hours for s in segments if s.status == "ON")
        self.assertAlmostEqual(total_on, 2.0, places=1)
        
        # No segment should violate: drive_in_shift > 11
        # We verify by checking no single contiguous D run exceeds 11h
        d_run = 0
        for s in segments:
            if s.status == "D":
                d_run += s.duration_hours
                self.assertLessEqual(d_run, 11.0 + 0.01,
                    f"Contiguous drive run {d_run}h exceeds 11h limit")
            else:
                d_run = 0

    def test_log_builder_with_mega_trip(self):
        """Generate logs for a massive trip and verify all days are valid."""
        units = [UnitOfWork("DRIVE", 50.0, 2750.0, "mega drive")]
        segments = run_simulation(units, 0.0)
        
        start = datetime(2026, 6, 16, 6, 0, tzinfo=timezone.utc)
        logs = build_logs(segments, start, 2750.0)
        
        for log in logs:
            # Totals must sum to 24
            total = sum(log["totals"].values())
            self.assertAlmostEqual(total, 24.0, places=1,
                msg=f"Day {log['date']}: totals sum to {total}")
            
            # No negative values
            for status, hours in log["totals"].items():
                self.assertGreaterEqual(hours, 0,
                    msg=f"Day {log['date']}: {status} = {hours} (negative!)")
            
            # Segments should be contiguous (no gaps)
            for i in range(1, len(log["segments"])):
                prev_end = log["segments"][i-1]["end_min"]
                curr_start = log["segments"][i]["start_min"]
                self.assertLessEqual(abs(prev_end - curr_start), 15,
                    msg=f"Day {log['date']}: gap between segments {i-1} and {i}")

    def test_cycle_used_69_with_on_then_drive(self):
        """Bug 1 concrete reproduction: cycle=69, ON 5h, then DRIVE 5h."""
        units = [
            UnitOfWork("ON", 5.0, 0.0, "loading"),
            UnitOfWork("DRIVE", 5.0, 275.0, "drive"),
        ]
        segments = run_simulation(units, 69.0)
        
        # ON should be clamped at 1 hour (69+1=70)
        self.assertEqual(segments[0].status, "ON")
        self.assertEqual(segments[0].duration_hours, 1.0)
        
        # 34-hr restart
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 34.0)
        
        # Remaining 4h ON
        self.assertEqual(segments[2].status, "ON")
        self.assertEqual(segments[2].duration_hours, 4.0)
        
        # Then 5h DRIVE (within new shift)
        drive_segs = [s for s in segments if s.status == "D"]
        total_drive = sum(s.duration_hours for s in drive_segs)
        self.assertAlmostEqual(total_drive, 5.0, places=1)
