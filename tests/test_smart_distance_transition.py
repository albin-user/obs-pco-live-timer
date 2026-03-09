"""
Test to demonstrate the transition point when service selection changes.

Shows when the system switches from showing Service A (ending) to Service B (starting).
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.models import Service, Item

def test_transition_point():
    # Service A: Started at 10:00, ends at 12:00
    service_a = Service(
        id="1",
        type_id="393738",
        series_title="Sunday Morning",
        plan_title="OCH Gudstjeneste",
        dates="Jan 15",
        start_time=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        items=[Item(id="item1", title="Worship", length=7200, sequence=1)],
        total_length=7200,
        live_item_id=None,
        live_start_at=None
    )

    # Service B: Starts at 12:30, ends at 14:00
    service_b = Service(
        id="2",
        type_id="772177",
        series_title="Special Event",
        plan_title="OCH Arrangementer",
        dates="Jan 15",
        start_time=datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc),
        items=[Item(id="item4", title="Opening", length=5400, sequence=1)],
        total_length=5400,
        live_item_id=None,
        live_start_at=None
    )

    def smart_distance(plan, now):
        if plan.start_time < now:
            end_time = plan.start_time + timedelta(seconds=plan.total_length)
            return abs((end_time - now).total_seconds())
        else:
            return abs((plan.start_time - now).total_seconds())

    print("\n" + "="*70)
    print("SERVICE SELECTION TRANSITION TEST")
    print("="*70)
    print("\nService A: 10:00 - 12:00 (OCH Gudstjeneste)")
    print("Service B: 12:30 - 14:00 (OCH Arrangementer)")
    print("\n" + "-"*70)

    # Test multiple time points
    time_points = [
        datetime(2024, 1, 15, 11, 30, tzinfo=timezone.utc),  # 11:30
        datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),   # 12:00
        datetime(2024, 1, 15, 12, 10, tzinfo=timezone.utc),  # 12:10
        datetime(2024, 1, 15, 12, 15, tzinfo=timezone.utc),  # 12:15 (transition)
        datetime(2024, 1, 15, 12, 20, tzinfo=timezone.utc),  # 12:20
    ]

    for now in time_points:
        dist_a = smart_distance(service_a, now)
        dist_b = smart_distance(service_b, now)

        candidates = [service_a, service_b]
        candidates.sort(key=lambda p: smart_distance(p, now))
        selected = candidates[0]

        status_a = "ENDED" if now > service_a.start_time + timedelta(seconds=service_a.total_length) else "RUNNING"

        print(f"\nTime: {now.strftime('%H:%M')}")
        print(f"  Service A distance: {dist_a/60:.0f} min (to END at 12:00) [{status_a}]")
        print(f"  Service B distance: {dist_b/60:.0f} min (to START at 12:30) [FUTURE]")
        print(f"  >> SELECTED: {selected.plan_title}")

    print("\n" + "="*70)
    print("TRANSITION POINT: Around 12:15")
    print("Before 12:15 -> Service A (still running, closer to end)")
    print("After 12:15  -> Service B (closer to its start than A's end)")
    print("="*70 + "\n")

if __name__ == "__main__":
    test_transition_point()
