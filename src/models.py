from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

@dataclass
class Item:
    id: str
    title: str
    length: int  # in seconds
    sequence: Optional[int] = 0
    type: str = "item"  # item, header, song
    
    # Timing info
    start_time_offset: int = 0  # seconds from service start
    
    # Live status
    is_live: bool = False
    
    # Optional metadata
    description: Optional[str] = None
    key_name: Optional[str] = None
    notes: Dict[str, str] = field(default_factory=dict) # Category -> Content

@dataclass
class Service:
    id: str
    type_id: str
    series_title: Optional[str]
    plan_title: Optional[str]
    dates: str

    # Timing
    start_time: datetime  # Absolute start time (UTC or localized)
    items: List[Item] = field(default_factory=list)

    # Total length from PCO API (seconds, "during" items only)
    total_length: int = 0

    # Service type metadata
    service_type_name: Optional[str] = None

    # Live data (from /live endpoint)
    live_item_id: Optional[str] = None
    live_start_at: Optional[datetime] = None

@dataclass
class TimerResult:
    # Required Fields
    current_item: Optional[Item]
    live_countdown: float  # seconds remaining (negative means overrun)
    service_end_time: datetime  # Original scheduled end
    projected_end_time: datetime  # Adjusted for current cumulative overrun
    service_end_countdown: float  # seconds remaining to projected end
    overrun_minutes: float  # how many minutes behind schedule we are
    is_live: bool
    is_finished: bool
    
    # Progress Trackers
    plan_index: int = 0
    plan_total: int = 0
    
    # Optional/Default Fields
    next_item: Optional[Item] = None
    message: Optional[str] = None
