from datetime import datetime, timedelta
import math
from typing import List, Dict, Any
from .hos_engine import StatusSegment

def snap_to_15_min(dt: datetime) -> datetime:
    minute = dt.minute
    # round to nearest 15
    rounded_minute = round(minute / 15) * 15
    if rounded_minute == 60:
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return dt.replace(minute=rounded_minute, second=0, microsecond=0)

def build_logs(segments: List[StatusSegment], start_time: datetime, total_distance: float) -> List[Dict[str, Any]]:
    current_time = start_time
    
    # We will build an exact timeline of events, then split by midnight
    # For simplicity, we assign absolute start and end times to each segment
    
    timeline = []
    for seg in segments:
        duration_td = timedelta(hours=seg.duration_hours)
        end_time = current_time + duration_td
        
        # Split by midnight if necessary
        # We check if current_time and end_time are on different calendar days
        # Since a segment could span multiple days (e.g. 34 hr restart), we loop
        
        temp_start = current_time
        while temp_start.date() < end_time.date():
            # Find next midnight
            next_midnight = datetime(temp_start.year, temp_start.month, temp_start.day, tzinfo=temp_start.tzinfo) + timedelta(days=1)
            # Emit segment from temp_start to next_midnight
            if next_midnight > temp_start:
                timeline.append({
                    "status": seg.status,
                    "start": temp_start,
                    "end": next_midnight,
                    "remark": seg.label
                })
            temp_start = next_midnight
            
        if temp_start < end_time:
            timeline.append({
                "status": seg.status,
                "start": temp_start,
                "end": end_time,
                "remark": seg.label
            })
            
        current_time = end_time

    # Now group by calendar day
    days = {}
    for entry in timeline:
        date_str = entry["start"].strftime("%Y-%m-%d")
        if date_str not in days:
            days[date_str] = []
        days[date_str].append(entry)
        
    logs = []
    for date_str, entries in days.items():
        day_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=start_time.tzinfo)
        midnight = day_date
        next_midnight = midnight + timedelta(days=1)
        
        # Calculate exactly 24 hours of duration by status, snapping transitions
        # We need to map exact timestamps to 15-min grid.
        # But wait, to ensure sum is exactly 24, we map the snapped start and end minutes
        # and calculate duration as end_min - start_min in the snapped space!
        
        segments_for_day = []
        totals = {"OFF": 0.0, "SB": 0.0, "D": 0.0, "ON": 0.0}
        unsnapped_drive_hours = 0.0  # Track precise driving hours for mile proportioning
        
        # Pad the beginning of the day with OFF if the first segment starts after midnight
        if entries:
            first_snap = snap_to_15_min(entries[0]["start"])
            if first_snap < midnight:
                first_snap = midnight
            first_min = int((first_snap - midnight).total_seconds() / 60)
            if first_min > 0:
                segments_for_day.append({
                    "status": "OFF",
                    "start_min": 0,
                    "end_min": first_min,
                    "remark": "Off Duty"
                })
                totals["OFF"] += first_min / 60.0

        for i, entry in enumerate(entries):
            # snap start
            snapped_start = snap_to_15_min(entry["start"])
            if snapped_start < midnight:
                snapped_start = midnight
                
            # snap end
            if i == len(entries) - 1 and entry["end"] < next_midnight:
                snapped_end = snap_to_15_min(entry["end"])
            else:
                snapped_end = snap_to_15_min(entry["end"])
                
            if snapped_end > next_midnight:
                snapped_end = next_midnight
                
            # minutes from midnight
            start_min = int((snapped_start - midnight).total_seconds() / 60)
            end_min = int((snapped_end - midnight).total_seconds() / 60)
            
            if end_min < start_min:
                end_min = start_min # Should not happen unless rounding inversion
                
            if start_min == end_min and i > 0 and i < len(entries) - 1:
                # If a segment is squashed to 0 length by snapping, skip it unless it's critical
                continue
                
            dur_hours = (end_min - start_min) / 60.0
            
            # If there's a gap between previous segment's end and this start due to snapping,
            # we should patch it. But it's easier to just force continuity:
            if segments_for_day:
                # patch gap
                gap_start = segments_for_day[-1]["end_min"]
                if gap_start < start_min:
                    segments_for_day[-1]["end_min"] = start_min
                    totals[segments_for_day[-1]["status"]] += (start_min - gap_start) / 60.0
                elif gap_start > start_min:
                    start_min = gap_start # push this one forward
                    
            dur_hours = (end_min - start_min) / 60.0
            
            if dur_hours > 0:
                segments_for_day.append({
                    "status": entry["status"],
                    "start_min": start_min,
                    "end_min": end_min,
                    "remark": entry["remark"]
                })
                totals[entry["status"]] += dur_hours
                # Track unsnapped driving hours for accurate mile proportioning
                if entry["status"] == "D":
                    raw_dur = (entry["end"] - entry["start"]).total_seconds() / 3600.0
                    unsnapped_drive_hours += raw_dur
                
        # Fill any remaining time up to 24 hours with OFF if the trip ended early on this day
        if segments_for_day:
            last_end = segments_for_day[-1]["end_min"]
            if last_end < 1440: # 24 * 60
                segments_for_day.append({
                    "status": "OFF",
                    "start_min": last_end,
                    "end_min": 1440,
                    "remark": ""
                })
                totals["OFF"] += (1440 - last_end) / 60.0
        else:
            # Full day OFF
            segments_for_day.append({
                "status": "OFF",
                "start_min": 0,
                "end_min": 1440,
                "remark": ""
            })
            totals["OFF"] = 24.0

        # Calculate miles for the day (rough estimation based on driving proportion or total)
        # If there's driving, let's just assign total distance to the first day or distribute.
        # For simplicity, assign total distance if it's the last day, or divide by days?
        # Actually, we can sum the exact driving chunks, but total_miles is a daily field.
        # We can approximate: if D > 0, miles = total_distance * (totals["D"] / total_trip_drive_time)
        # To avoid passing total_trip_drive_time, let's just do totals["D"] * 55 unless we have exact.
        total_trip_drive_time = sum(s.duration_hours for s in segments if s.status == "D")
        if total_trip_drive_time > 0 and unsnapped_drive_hours > 0:
            miles_today = int(total_distance * (unsnapped_drive_hours / total_trip_drive_time))
        else:
            miles_today = 0
        
        # fix float precision issues
        for k in totals:
            totals[k] = round(totals[k], 2)
            
        # Ensure exact 24
        total_sum = sum(totals.values())
        if total_sum != 24.0:
            diff = 24.0 - total_sum
            totals["OFF"] = round(totals["OFF"] + diff, 2)
        
        # Clamp OFF to non-negative (Bug 11 fix)
        if totals["OFF"] < 0:
            totals["OFF"] = 0.0

        logs.append({
            "date": date_str,
            "total_miles": miles_today,
            "totals": totals,
            "segments": segments_for_day
        })
        
    return logs
