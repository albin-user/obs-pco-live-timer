from datetime import datetime, timedelta, timezone
from typing import Optional
from .models import Service, TimerResult, Item

def calculate_timers(service: Optional[Service], current_time: datetime) -> TimerResult:
    """
    Calculates the current live status and countdowns based on the service data and current time.
    """
    # Ensure current_time is timezone-aware (UTC if not specified)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
        
    if not service:
        return TimerResult(
            current_item=None,
            live_countdown=0,
            service_end_time=current_time,
            projected_end_time=current_time,
            service_end_countdown=0,
            overrun_minutes=0,
            is_live=False,
            is_finished=False,
            message="No Service Data"
        )

    # Ensure service start time is comparable
    service_start = service.start_time
    if service_start.tzinfo is None:
        service_start = service_start.replace(tzinfo=timezone.utc)
        
    # Calculate scheduled end time
    scheduled_end_time = service_start + timedelta(seconds=service.total_length)

    # Calculate elapsed time from scheduled start
    elapsed = (current_time - service_start).total_seconds()

    # Variables to hold results
    current_item: Optional[Item] = None
    next_item: Optional[Item] = None
    live_countdown = 0.0
    projected_end_time = scheduled_end_time
    overrun_seconds = 0.0

    # helper to find next item
    def find_next(current_id):
        for i, item in enumerate(service.items):
            if item.id == current_id:
                if i + 1 < len(service.items):
                    return service.items[i+1]
        return None

    # PRIORITY 1: Use PCO Live data if available (check this FIRST, even before scheduled start!)
    if service.live_item_id:
        current_item = next((item for item in service.items if item.id == service.live_item_id), None)
        if current_item and service.live_start_at:
            live_start = service.live_start_at
            if live_start.tzinfo is None:
                live_start = live_start.replace(tzinfo=timezone.utc)
                
            next_item = find_next(current_item.id)

            # CALCULATE OVERRUN
            # Calculate projected end based on time remaining from current position

            # Time already elapsed in current item
            time_elapsed_in_current_item = (current_time - live_start).total_seconds()

            # Time remaining in current item
            time_remaining_in_current_item = max(0, current_item.length - time_elapsed_in_current_item)

            # Sum all items that come after current item
            remaining_items = [item for item in service.items
                             if item.start_time_offset > current_item.start_time_offset]
            remaining_time_after_current = sum(item.length for item in remaining_items)

            # Total time remaining in service
            total_time_remaining = time_remaining_in_current_item + remaining_time_after_current

            # Projected end time
            projected_end_time = current_time + timedelta(seconds=total_time_remaining)

            # Overrun = difference between projected end and scheduled end
            overrun_seconds = (projected_end_time - scheduled_end_time).total_seconds()
            
            # Item countdown
            expected_item_end = live_start + timedelta(seconds=current_item.length)
            live_countdown = (expected_item_end - current_time).total_seconds()
            
            # Service end countdown
            service_end_countdown = (projected_end_time - current_time).total_seconds()
            
            # CALCULATE PROGRESS (Item X of Y)
            non_headers = [i for i in service.items if i.type != 'header']
            plan_total = len(non_headers)
            try:
                plan_index = next(idx for idx, i in enumerate(non_headers, 1) if i.id == current_item.id)
            except StopIteration:
                plan_index = 0

            return TimerResult(
                current_item=current_item,
                next_item=next_item,
                live_countdown=live_countdown,
                service_end_time=scheduled_end_time,
                projected_end_time=projected_end_time,
                service_end_countdown=service_end_countdown,
                overrun_minutes=overrun_seconds / 60.0,
                is_live=True,
                is_finished=False,
                plan_index=plan_index,
                plan_total=plan_total
            )

    # Check if service hasn't started (and no live data available)
    if elapsed < 0:
        return TimerResult(
            current_item=None,
            next_item=service.items[0] if service.items else None,
            live_countdown=abs(elapsed),
            service_end_time=scheduled_end_time,
            projected_end_time=scheduled_end_time,
            service_end_countdown=abs(elapsed) + service.total_length,
            overrun_minutes=0,
            is_live=False,
            is_finished=False,
            message=f"Starts in {int(abs(elapsed)//60)}m"
        )

    # PRIORITY 2: Fallback to wall-clock calculation
    for i, item in enumerate(service.items):
        item_start = item.start_time_offset
        item_end = item_start + item.length
        
        if elapsed >= item_start and elapsed < item_end:
            current_item = item
            if i + 1 < len(service.items):
                next_item = service.items[i+1]
            break
            
    service_end_countdown = (scheduled_end_time - current_time).total_seconds()
    
    if elapsed >= service.total_length:
        return TimerResult(
            current_item=None,
            live_countdown=0,
            service_end_time=scheduled_end_time,
            projected_end_time=scheduled_end_time,
            service_end_countdown=service_end_countdown,
            overrun_minutes=0,
            is_live=False,
            is_finished=True,
            message="Service Finished"
        )

    if current_item:
        item_end_absolute = service_start + timedelta(seconds=current_item.start_time_offset + current_item.length)
        live_countdown = (item_end_absolute - current_time).total_seconds()
    
    return TimerResult(
        current_item=current_item,
        next_item=next_item,
        live_countdown=live_countdown,
        service_end_time=scheduled_end_time,
        projected_end_time=scheduled_end_time,
        service_end_countdown=service_end_countdown,
        overrun_minutes=0,
        is_live=True,
        is_finished=False
    )
