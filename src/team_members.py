"""
Team member fetching, photo caching, and OBS source mapping.
"""
import logging
import os
from typing import List, Dict, Any

from .models import TeamMember
from .pco_client import PCOClient

logger = logging.getLogger(__name__)


def fetch_and_cache_team(
    client: PCOClient,
    service_type_id: str,
    plan_id: str,
    cache_dir: str,
) -> List[TeamMember]:
    """Fetch team members for a plan and download photos to cache_dir."""
    raw = client.get_team_members(service_type_id, plan_id)
    members = []
    for m in raw:
        photo_path = None
        photo_url = m.get("photo_url")
        if photo_url and cache_dir:
            photo_path = os.path.join(cache_dir, f"{m['person_id']}.jpg")
            if not os.path.exists(photo_path):
                if not client.download_photo(photo_url, photo_path):
                    photo_path = None
        members.append(TeamMember(
            person_id=m["person_id"],
            name=m["name"],
            position=m["position"],
            team_name=m["team_name"],
            photo_url=photo_url,
            photo_path=photo_path,
            status=m.get("status", "U"),
        ))
    return members


def build_team_response(
    members: List[TeamMember],
    slots: List[str],
    placeholder_photo: str = "",
) -> List[Dict[str, Any]]:
    """Build team slot data from config-driven position list.

    Args:
        members: TeamMember objects fetched from PCO.
        slots: Ordered list of position names from config (e.g. ["Vocalist", "Vocalist", "Drums"]).
        placeholder_photo: Path to placeholder avatar for empty/photo-less slots.
    """
    # Build a pool: {position_name: [member, member, ...]}
    pool: Dict[str, List[TeamMember]] = {}
    for m in members:
        pool.setdefault(m.position, []).append(m)

    # Track how many of each position we've consumed
    position_used: Dict[str, int] = {}
    result = []

    for pos in slots:
        idx = position_used.get(pos, 0)
        position_used[pos] = idx + 1
        num = idx + 1  # 1-based index for OBS source name

        name_src = f"PCO Position {pos} {num} Name"
        pos_src = f"PCO Position {pos} {num} Position"
        photo_src = f"PCO Position {pos} {num} Photo"

        available = pool.get(pos, [])
        if idx < len(available):
            member = available[idx]
            first_name = member.name.split()[0] if member.name else ""
            result.append({
                "name": first_name,
                "position": member.position,
                "team": member.team_name,
                "status": member.status,
                "name_source": name_src,
                "position_source": pos_src,
                "photo_source": photo_src,
                "photo_path": member.photo_path or placeholder_photo,
            })
        else:
            result.append({
                "name": "",
                "position": "Empty",
                "team": "",
                "status": "",
                "name_source": name_src,
                "position_source": pos_src,
                "photo_source": photo_src,
                "photo_path": placeholder_photo,
            })

    return result
