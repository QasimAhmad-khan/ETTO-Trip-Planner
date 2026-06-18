"""
Hours of Service (HOS) Simulation Engine
Pure, deterministic Python module. No Django imports.
"""
from dataclasses import dataclass
from typing import List, Optional

# Constants (with CFR citations)
MAX_DRIVE_PER_SHIFT   = 11.0   # hrs driving        § 395.3(a)(3)
MAX_DUTY_WINDOW       = 14.0   # hrs window          § 395.3(a)(2)
DRIVE_BEFORE_BREAK    = 8.0    # cumulative drive hrs before 30-min break § 395.3(a)(3)(ii)
BREAK_DURATION        = 0.5    # 30 minutes          § 395.3(a)(3)(ii)
DAILY_OFF_RESET       = 10.0   # consecutive off-duty hrs to reset shift  § 395.3(a)
CYCLE_LIMIT           = 70.0   # on-duty hrs / 8 days § 395.3(b)
CYCLE_WINDOW_DAYS     = 8
RESTART_DURATION      = 34.0   # consecutive off-duty hrs to reset cycle  § 395.3(c)
FUEL_INTERVAL_MI      = 1000.0 # fuel at least this often
FUEL_DURATION         = 0.5    # on-duty not driving
PICKUP_DURATION       = 1.0    # on-duty not driving
DROPOFF_DURATION      = 1.0    # on-duty not driving
AVG_SPEED_MPH         = 55.0   # fallback speed

@dataclass
class UnitOfWork:
    type: str  # 'DRIVE', 'ON', 'PC', 'YM'
    duration_hours: float
    distance_mi: float = 0.0
    label: str = ""

@dataclass
class StatusSegment:
    status: str  # 'OFF', 'SB', 'D', 'ON'
    duration_hours: float
    label: str = ""
    # In a full implementation we'd track start_min and end_min or timestamps,
    # but the engine just outputs ordered segments. log_builder.py assigns absolute times.

def decompose_into_units(legs) -> List[UnitOfWork]:
    """
    Takes route legs and inserts fuel stops.
    `legs` format: [{'from': ..., 'to': ..., 'distance_mi': ..., 'drive_hours': ...}, ...]
    """
    units = []
    # This will be implemented in connection with routing
    pass

class HOSEngine:
    def __init__(self, current_cycle_used: float):
        self.cycle_used = current_cycle_used
        self.drive_in_shift = 0.0
        self.window_used = 0.0
        self.drive_since_break = 0.0
        self.segments: List[StatusSegment] = []
        
    def emit(self, status: str, duration: float, label: str = ""):
        if duration <= 0:
            return
        if self.segments and self.segments[-1].status == status and self.segments[-1].label == label:
            self.segments[-1].duration_hours += duration
        else:
            self.segments.append(StatusSegment(status, duration, label))

    def reset_shift_clocks(self):
        self.drive_in_shift = 0.0
        self.window_used = 0.0
        self.drive_since_break = 0.0

    def simulate(self, units: List[UnitOfWork]) -> List[StatusSegment]:
        # Pre-trip: if no cycle room at all, restart first
        if self.cycle_used >= CYCLE_LIMIT:
            self.emit("OFF", RESTART_DURATION, "34-hr Restart")
            self.cycle_used = 0.0

        for unit in units:
            remaining_duration = unit.duration_hours
            
            while remaining_duration > 0:
                # Cycle check
                if self.cycle_used >= CYCLE_LIMIT:
                    self.emit("OFF", RESTART_DURATION, "34-hr Restart")
                    self.cycle_used = 0.0
                    self.reset_shift_clocks()
                
                if unit.type == "DRIVE":
                    # 30-min break check
                    if self.drive_since_break >= DRIVE_BEFORE_BREAK:
                        # If break pushes window over 14, we must 10-hr reset instead
                        if self.window_used + BREAK_DURATION > MAX_DUTY_WINDOW:
                            self.emit("OFF", DAILY_OFF_RESET, "10-hr Off Duty")
                            self.reset_shift_clocks()
                        else:
                            self.emit("OFF", BREAK_DURATION, "30-min Break")
                            self.window_used += BREAK_DURATION
                            self.drive_since_break = 0.0
                    
                    # Shift limits
                    if self.drive_in_shift >= MAX_DRIVE_PER_SHIFT or self.window_used >= MAX_DUTY_WINDOW:
                        self.emit("OFF", DAILY_OFF_RESET, "10-hr Off Duty")
                        self.reset_shift_clocks()
                    
                    # Drive chunk
                    chunk = min(
                        remaining_duration,
                        MAX_DRIVE_PER_SHIFT - self.drive_in_shift,
                        MAX_DUTY_WINDOW - self.window_used,
                        DRIVE_BEFORE_BREAK - self.drive_since_break,
                        CYCLE_LIMIT - self.cycle_used
                    )
                    
                    # Precision edge case: if chunk is extremely small due to floats
                    if chunk < 1e-5:
                        if CYCLE_LIMIT - self.cycle_used < 1e-5:
                            self.emit("OFF", RESTART_DURATION, "34-hr Restart")
                            self.cycle_used = 0.0
                            self.reset_shift_clocks()
                        elif MAX_DRIVE_PER_SHIFT - self.drive_in_shift < 1e-5 or MAX_DUTY_WINDOW - self.window_used < 1e-5:
                            self.emit("OFF", DAILY_OFF_RESET, "10-hr Off Duty")
                            self.reset_shift_clocks()
                        elif DRIVE_BEFORE_BREAK - self.drive_since_break < 1e-5:
                            self.emit("OFF", BREAK_DURATION, "30-min Break")
                            self.window_used += BREAK_DURATION
                            self.drive_since_break = 0.0
                        else:
                            chunk = remaining_duration
                        if chunk < 1e-5:
                            continue
                        
                    self.emit("D", chunk, unit.label)
                    self.drive_in_shift += chunk
                    self.window_used += chunk
                    self.drive_since_break += chunk
                    self.cycle_used += chunk
                    remaining_duration -= chunk

                elif unit.type == "ON" or unit.type == "YM":
                    # Clamp against both window and cycle limit
                    chunk = min(
                        remaining_duration,
                        MAX_DUTY_WINDOW - self.window_used,
                        CYCLE_LIMIT - self.cycle_used
                    )
                    
                    if chunk < 1e-5:
                        # Determine which limit was hit
                        if CYCLE_LIMIT - self.cycle_used < 1e-5:
                            self.emit("OFF", RESTART_DURATION, "34-hr Restart")
                            self.cycle_used = 0.0
                            self.reset_shift_clocks()
                        elif MAX_DUTY_WINDOW - self.window_used < 1e-5:
                            self.emit("OFF", DAILY_OFF_RESET, "10-hr Off Duty")
                            self.reset_shift_clocks()
                        else:
                            chunk = remaining_duration  # force progress
                        if chunk < 1e-5:
                            continue
                    
                    self.emit("ON", chunk, unit.label)
                    self.window_used += chunk
                    self.cycle_used += chunk
                    remaining_duration -= chunk

                elif unit.type == "PC":
                    self.emit("OFF", remaining_duration, unit.label)
                    # PC is off-duty, does not consume 70-hr cycle and does not increment window!
                    remaining_duration = 0

        # Emit final OFF (end of duty)
        self.emit("OFF", 0.0, "End of Duty") # A zero duration just for tracking, or standard OFF?
        # Actually, let log builder handle end of duty, or we just emit the segments we have.
        
        return self.segments

def run_simulation(units: List[UnitOfWork], current_cycle_used: float) -> List[StatusSegment]:
    engine = HOSEngine(current_cycle_used)
    return engine.simulate(units)
