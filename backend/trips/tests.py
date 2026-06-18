from django.test import TestCase
from trips.services.hos_engine import HOSEngine, UnitOfWork, run_simulation
from trips.serializers import TripPlanSerializer

class SerializerTests(TestCase):
    def test_valid_payload(self):
        data = {
            "current_location": "Dallas, TX",
            "pickup_location": "OKC, OK",
            "dropoff_location": "Denver, CO",
            "current_cycle_used": 12.5
        }
        s = TripPlanSerializer(data=data)
        self.assertTrue(s.is_valid())

    def test_invalid_cycle(self):
        data = {
            "current_location": "Dallas, TX",
            "pickup_location": "OKC, OK",
            "dropoff_location": "Denver, CO",
            "current_cycle_used": 75.0
        }
        s = TripPlanSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("current_cycle_used", s.errors)

class HOSEngineTests(TestCase):
    def test_edge_case_1_pre_trip_restart(self):
        # cycle already at 70 -> pre-trip restart inserted at start
        units = [UnitOfWork("DRIVE", 5.0, 275.0, "current->pickup")]
        segments = run_simulation(units, 70.0)
        self.assertEqual(segments[0].status, "OFF")
        self.assertEqual(segments[0].duration_hours, 34.0)
        self.assertEqual(segments[1].status, "D")
        self.assertEqual(segments[1].duration_hours, 5.0)

    def test_edge_case_2_cycle_near_70(self):
        # cycle near 70 -> drive remaining hours, then restart
        units = [UnitOfWork("DRIVE", 5.0, 275.0, "current->pickup")]
        segments = run_simulation(units, 68.0)
        self.assertEqual(segments[0].status, "D")
        self.assertEqual(segments[0].duration_hours, 2.0)
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 34.0)
        self.assertEqual(segments[2].status, "D")
        self.assertEqual(segments[2].duration_hours, 3.0)

    def test_edge_case_3_trip_gt_11_drive_hours(self):
        # trip needs > 11 drive hrs -> 10-hr reset inserted
        units = [UnitOfWork("DRIVE", 12.0, 660.0, "current->pickup")]
        segments = run_simulation(units, 0.0)
        # 8 hours drive, 30 min break, 3 hours drive, 10 hr reset, 1 hour drive
        self.assertEqual(segments[0].status, "D")
        self.assertEqual(segments[0].duration_hours, 8.0)
        self.assertEqual(segments[1].status, "OFF")
        self.assertEqual(segments[1].duration_hours, 0.5)
        self.assertEqual(segments[2].status, "D")
        self.assertEqual(segments[2].duration_hours, 3.0)
        self.assertEqual(segments[3].status, "OFF")
        self.assertEqual(segments[3].duration_hours, 10.0)
        self.assertEqual(segments[4].status, "D")
        self.assertEqual(segments[4].duration_hours, 1.0)

    def test_edge_case_4_on_duty_overflows_window(self):
        # on-duty overflows 14-hr window before driving is exhausted
        # e.g., drive 10 hours, then ON for 5 hours.
        units = [
            UnitOfWork("DRIVE", 10.0, 550.0, "current->pickup"),
            UnitOfWork("ON", 5.0, 0.0, "pickup")
        ]
        segments = run_simulation(units, 0.0)
        # Drive 8, break 0.5, Drive 2 (Total window = 10.5)
        # ON 5 -> wait, at ON 3.5, window hits 14.
        # So chunking ON isn't explicitly requested for ON units in pseudocode, 
        # wait! PRD says: "If next unit is ON... if window_used + duration > 14: emit 10-hr reset."
        # The pseudocode forces a 10-hr reset BEFORE the ON block if the whole block doesn't fit!
        # "if window_used + duration > MAX_DUTY_WINDOW: emit RESET (OFF, 10 hr); reset shift clocks"
        self.assertEqual(segments[0].status, "D")
        self.assertEqual(segments[0].duration_hours, 8.0)
        self.assertEqual(segments[1].status, "OFF") # break
        self.assertEqual(segments[1].duration_hours, 0.5)
        self.assertEqual(segments[2].status, "D")
        self.assertEqual(segments[2].duration_hours, 2.0)
        # ON is now properly chunked at window boundary (14 - 10.5 = 3.5)
        self.assertEqual(segments[3].status, "ON")
        self.assertEqual(segments[3].duration_hours, 3.5)
        self.assertEqual(segments[4].status, "OFF") # reset forced when window hits 14
        self.assertEqual(segments[4].duration_hours, 10.0)
        self.assertEqual(segments[5].status, "ON")
        self.assertEqual(segments[5].duration_hours, 1.5)

    def test_edge_case_10_break_vs_window_conflict(self):
        # break would push window over 14 hr -> take 10-hr reset instead
        # e.g. window is at 13.6, drive_since_break is 8.
        # But wait, how to get window to 13.6 without driving 8? 
        # By doing ON duty first.
        # ON duty for 6 hours. Then DRIVE for 8 hours.
        # Window is at 14. drive_since_break is 8.
        # Next drive needs a break, but window + break (0.5) > 14.
        units = [
            UnitOfWork("ON", 6.0, 0.0, "pickup"),
            UnitOfWork("DRIVE", 8.0, 440.0, "current->pickup"),
            UnitOfWork("DRIVE", 1.0, 55.0, "pickup->dropoff")
        ]
        segments = run_simulation(units, 0.0)
        self.assertEqual(segments[0].status, "ON")
        self.assertEqual(segments[0].duration_hours, 6.0)
        self.assertEqual(segments[1].status, "D")
        self.assertEqual(segments[1].duration_hours, 8.0) # total window 14
        self.assertEqual(segments[2].status, "OFF")
        self.assertEqual(segments[2].duration_hours, 10.0) # 10-hr reset, not 30-min break
        self.assertEqual(segments[3].status, "D")
        self.assertEqual(segments[3].duration_hours, 1.0)

    def test_edge_case_11_long_trip_both_resets(self):
        # Very long trip forcing a 34-hr restart and 10-hr resets
        # 70 hours limit. Drive 11, OFF 10, repeatedly.
        # 11 * 6 = 66 hrs drive + cycle used 0.
        units = [UnitOfWork("DRIVE", 80.0, 4400.0, "coast->coast")]
        segments = run_simulation(units, 0.0)
        # We just check that a 34 hr restart exists in the segments
        has_restart = any(s.status == "OFF" and s.duration_hours == 34.0 for s in segments)
        has_reset = any(s.status == "OFF" and s.duration_hours == 10.0 for s in segments)
        self.assertTrue(has_restart)
        self.assertTrue(has_reset)
