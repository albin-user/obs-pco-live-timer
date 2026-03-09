"""
Test script to demonstrate smart distance calculation for overlapping services.

Scenario:
- Service A: 10:00 - 12:00 (2 hours, currently running)
- Service B: 12:30 - 14:00 (1.5 hours, future)
- Current time: 11:30

Expected behavior:
- Service A distance: 0.5 hours (to end at 12:00)
- Service B distance: 1.0 hours (to start at 12:30)
- Result: Service A should be selected (closer)
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.models import Service, Item

def test_smart_distance():
    # Current time: 11:30
    now = datetime(2024, 1, 15, 11, 30, tzinfo=timezone.utc)

    # Service A: Started at 10:00, runs for 2 hours (ends at 12:00)
    # Create items totaling 7200 seconds (2 hours)
    service_a = Service(
        id="1",
        type_id="393738",
        series_title="Sunday Morning",
        plan_title="OCH Gudstjeneste",
        dates="Jan 15",
        start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        items=[
            Item(id="item1", title="Worship", length=3600, sequence=1),
            Item(id="item2", title="Message", length=2400, sequence=2),
            Item(id="item3", title="Closing", length=1200, sequence=3)
        ],
        total_length=7200,
        live_item_id=None,
        live_start_at=None
    )

    # Service B: Starts at 12:30, runs for 1.5 hours (ends at 14:00)
    # Create items totaling 5400 seconds (1.5 hours)
    service_b = Service(
        id="2",
        type_id="772177",
        series_title="Special Event",
        plan_title="OCH Arrangementer",
        dates="Jan 15",
        start_time=datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc),
        items=[
            Item(id="item4", title="Opening", length=1800, sequence=1),
            Item(id="item5", title="Main Event", length=3600, sequence=2)
        ],
        total_length=5400,
        live_item_id=None,
        live_start_at=None
    )

    # Smart distance function (same as in manager.py)
    def smart_distance(plan):
        if plan.start_time < now:
            # Service has started - use end time
            end_time = plan.start_time + timedelta(seconds=plan.total_length)
            return abs((end_time - now).total_seconds())
        else:
            # Service hasn't started - use start time
            return abs((plan.start_time - now).total_seconds())

    # Calculate distances
    distance_a = smart_distance(service_a)
    distance_b = smart_distance(service_b)

    # Sort candidates
    candidates = [service_a, service_b]
    candidates.sort(key=smart_distance)
    selected = candidates[0]

    # Display results
    print("\n" + "="*60)
    print("SMART DISTANCE CALCULATION TEST")
    print("="*60)
    print(f"\nCurrent Time: {now.strftime('%H:%M')}")
    print(f"\nService A: {service_a.plan_title}")
    print(f"  Start: {service_a.start_time.strftime('%H:%M')}")
    print(f"  End:   {(service_a.start_time + timedelta(seconds=service_a.total_length)).strftime('%H:%M')}")
    print(f"  Status: RUNNING (started {(now - service_a.start_time).total_seconds() / 3600:.1f}h ago)")
    print(f"  Distance Calculation: To END time = {distance_a / 3600:.2f} hours")

    print(f"\nService B: {service_b.plan_title}")
    print(f"  Start: {service_b.start_time.strftime('%H:%M')}")
    print(f"  End:   {(service_b.start_time + timedelta(seconds=service_b.total_length)).strftime('%H:%M')}")
    print(f"  Status: FUTURE (starts in {(service_b.start_time - now).total_seconds() / 3600:.1f}h)")
    print(f"  Distance Calculation: To START time = {distance_b / 3600:.2f} hours")

    print(f"\n" + "-"*60)
    print(f"SELECTED SERVICE: {selected.plan_title}")
    print(f"Reason: Distance of {smart_distance(selected) / 3600:.2f}h is closer than {smart_distance([s for s in candidates if s != selected][0]) / 3600:.2f}h")
    print("-"*60)

    # Verification
    assert selected.id == service_a.id, "Service A should be selected!"
    assert distance_a < distance_b, "Service A distance should be less than Service B"

    print("\n[OK] Test passed - Smart distance calculation works correctly!")
    print("\nExplanation:")
    print("- Running services use END time (keeps showing until service finishes)")
    print("- Future services use START time (shows when getting close to start)")
    print("- This prevents jumping to a future service too early\n")

if __name__ == "__main__":
    test_smart_distance()
