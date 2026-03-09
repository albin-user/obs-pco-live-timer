"""
Formatting utilities for PCO Live Timer.
Provides build_timer_response() and helper formatters used by the OBS WebSocket pusher.
"""
import time
from datetime import datetime, timezone
from typing import Dict, Any

from .manager import PlanManager
from .song_blocks import get_song_block_for_item


def format_seconds(seconds: float) -> str:
    """Format seconds as MM:SS or -MM:SS for negative values."""
    is_negative = seconds < 0
    total = abs(int(seconds))
    mins = total // 60
    secs = total % 60
    formatted = f"{mins:02d}:{secs:02d}"
    return f"-{formatted}" if is_negative else formatted


def format_end_time(dt: datetime) -> str:
    """Format datetime as HH:MM AM/PM."""
    return dt.strftime("%-I:%M %p") if dt else ""


def build_timer_response(manager: PlanManager) -> Dict[str, Any]:
    """Build the JSON response from current timer state."""
    with manager._lock:
        result = manager.tick()
        plan = manager.current_plan

    # Base response for no data
    if not result or not plan:
        return {
            "service_type_name": None,
            "service_date": None,
            "plan_title": None,
            "is_live": False,
            "is_finished": False,
            "current_item": None,
            "next_item": None,
            "service_end": None,
            "progress": None,
            "message": result.message if result else "Waiting for service data...",
            "timestamp": int(time.time())
        }

    # Build current item info
    current_item_data = None
    if result.current_item:
        item = result.current_item
        song_block = get_song_block_for_item(plan, item)

        if len(song_block) > 1:
            # Song block — override title and build block description
            title = "Worship Set"
            description_parts = []
            for song in song_block:
                description_parts.append(song.title)
                if song.key_name:
                    description_parts.append(f"  Key: {song.key_name}")
                if song.description:
                    description_parts.append(f"  {song.description}")
                # Notes only fetched for the live item
                if song.id == item.id:
                    for category, content in item.notes.items():
                        if content:
                            description_parts.append(f"  {category}: {content}")
        else:
            # Single item — existing behavior
            title = item.title
            description_parts = []
            if item.key_name:
                description_parts.append(f"Key: {item.key_name}")
            if item.description:
                description_parts.append(item.description)
            # Add notes
            for category, content in item.notes.items():
                if content:
                    description_parts.append(f"{category}: {content}")

        current_item_data = {
            "title": title,
            "description": "\n".join(description_parts) if description_parts else None,
            "countdown_seconds": result.live_countdown,
            "countdown_formatted": format_seconds(result.live_countdown),
            "is_overtime": result.live_countdown < 0,
            "length_formatted": format_seconds(item.length)
        }

    # Build next item info
    next_item_data = None
    if result.next_item:
        item = result.next_item
        description_parts = []
        if item.description:
            description_parts.append(item.description)

        next_item_data = {
            "title": item.title,
            "description": "\n".join(description_parts) if description_parts else None,
            "length_formatted": format_seconds(item.length)
        }

    # Build service end info
    overrun_mins = round(result.overrun_minutes)
    if overrun_mins > 0:
        status_text = f"Ends {overrun_mins}m behind at {format_end_time(result.projected_end_time)}"
    elif overrun_mins < 0:
        status_text = f"Ends {abs(overrun_mins)}m ahead at {format_end_time(result.projected_end_time)}"
    else:
        status_text = f"On time - ends at {format_end_time(result.projected_end_time)}"

    service_end_data = {
        "countdown_seconds": result.service_end_countdown,
        "countdown_formatted": format_seconds(result.service_end_countdown),
        "overrun_minutes": overrun_mins,
        "end_time_formatted": format_end_time(result.projected_end_time),
        "scheduled_end_formatted": format_end_time(result.service_end_time),
        "status_text": status_text
    }

    # Build progress info
    progress_data = None
    if result.plan_total > 0:
        progress_data = {
            "current": result.plan_index,
            "total": result.plan_total,
            "text": f"{result.plan_index} of {result.plan_total}"
        }

    # Format service date
    service_date = plan.dates
    if plan.start_time:
        # Format as "Feb 9, 2025 · 9:00 AM"
        local_time = plan.start_time.astimezone()
        service_date = local_time.strftime("%b %-d, %Y · %-I:%M %p")

    return {
        "service_type_name": plan.service_type_name,
        "service_date": service_date,
        "plan_title": plan.plan_title or plan.series_title,
        "series_title": plan.series_title,
        "is_live": result.is_live,
        "is_finished": result.is_finished,
        "current_item": current_item_data,
        "next_item": next_item_data,
        "service_end": service_end_data,
        "progress": progress_data,
        "message": result.message,
        "timestamp": int(time.time())
    }
