import logging
import time as _time
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from typing import Optional, Dict, Any, List
from .models import Service, Item
import dateutil.parser

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2
_BACKOFF_MAX = 30

class PCOClient:
    def __init__(self, app_id: str, secret: str):
        self.app_id = app_id
        self.secret = secret
        self.base_url = "https://api.planningcenteronline.com/services/v2"
        self.auth = HTTPBasicAuth(app_id, secret)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = requests.get(url, auth=self.auth, params=params, timeout=10)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = int(response.headers.get("Retry-After", 0))
                    wait = max(retry_after, min(_BACKOFF_BASE ** attempt * 2, _BACKOFF_MAX))
                    logger.warning("HTTP %d from %s, retrying in %ds", response.status_code, endpoint, wait)
                    _time.sleep(wait)
                    continue
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as e:
                    raise ValueError(f"Invalid JSON from {endpoint}: {e}") from e
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
                wait = min(_BACKOFF_BASE ** attempt * 2, _BACKOFF_MAX)
                logger.warning("Connection error on %s (attempt %d/%d): %s", endpoint, attempt + 1, _MAX_RETRIES, e)
                if attempt < _MAX_RETRIES - 1:
                    _time.sleep(wait)
        if last_exc:
            raise last_exc
        response.raise_for_status()
        return response.json()

    def get_service_types(self) -> List[Dict[str, str]]:
        """
        Fetches all service types available in the organization.
        Returns a list of dicts with 'id' and 'name'.
        """
        data = self._get("/service_types")
        service_types = []
        for item in data.get('data', []):
            item_id = item.get('id')
            name = item.get('attributes', {}).get('name')
            if not item_id or not name:
                logger.warning("Skipping malformed service type item: %s", item)
                continue
            service_types.append({'id': item_id, 'name': name})
        return service_types

    def get_folder_service_types(self, folder_id: str) -> List[Dict[str, str]]:
        """
        Fetches service types belonging to a specific folder.
        Returns a list of dicts with 'id' and 'name'.
        """
        data = self._get(f"/folders/{folder_id}/service_types")
        results = []
        for item in data.get('data', []):
            item_id = item.get('id')
            name = item.get('attributes', {}).get('name')
            if not item_id or not name:
                logger.warning("Skipping malformed folder service type item: %s", item)
                continue
            results.append({'id': item_id, 'name': name})
        return results

    def get_live_status(self, service_type_id: str, plan_id: str) -> Dict[str, Any]:
        """
        Fetches the live status of a plan.
        """
        endpoint = f"/service_types/{service_type_id}/plans/{plan_id}/live"
        params = {'include': 'current_item_time,next_item_time,items'}
        return self._get(endpoint, params=params)

    def get_team_members(self, service_type_id: str, plan_id: str) -> List[Dict[str, Any]]:
        """
        Fetches team members for a plan with included person and team data.
        Returns a list of dicts: {person_id, name, position, team_name, photo_url, status}.
        """
        try:
            endpoint = f"/service_types/{service_type_id}/plans/{plan_id}/team_members"
            params = {"include": "person,team", "per_page": 100}

            all_data = []
            all_included = []

            while endpoint:
                raw = self._get(endpoint, params=params)
                params = None  # only on first request
                all_data.extend(raw.get("data", []))
                all_included.extend(raw.get("included", []))

                next_link = raw.get("links", {}).get("next")
                if next_link:
                    if next_link.startswith(self.base_url):
                        endpoint = next_link[len(self.base_url):]
                    else:
                        endpoint = None
                else:
                    endpoint = None

            # Index included records by (type, id)
            included_by = {}
            for inc in all_included:
                key = (inc.get("type"), inc.get("id"))
                if key[0] and key[1]:
                    included_by[key] = inc

            members = []
            for entry in all_data:
                attrs = entry.get("attributes", {})
                rels = entry.get("relationships", {})

                person_rel = rels.get("person", {}).get("data", {})
                person_id = person_rel.get("id") if isinstance(person_rel, dict) else None
                if not person_id:
                    continue

                name = attrs.get("name", "")
                position = attrs.get("team_position_name", "")
                status = attrs.get("status", "U")

                if status == "D":
                    continue

                # Photo: try included Person first, then team_member attribute
                photo_url = None
                person_inc = included_by.get(("Person", person_id))
                if person_inc:
                    photo_url = person_inc.get("attributes", {}).get("photo_thumbnail_url")
                if not photo_url:
                    photo_url = attrs.get("photo_thumbnail")

                # Team name from included Team
                team_name = ""
                team_rel = rels.get("team", {}).get("data", {})
                team_id = team_rel.get("id") if isinstance(team_rel, dict) else None
                if team_id:
                    team_inc = included_by.get(("Team", team_id))
                    if team_inc:
                        team_name = team_inc.get("attributes", {}).get("name", "")

                members.append({
                    "person_id": person_id,
                    "name": name,
                    "position": position,
                    "team_name": team_name,
                    "photo_url": photo_url,
                    "status": status,
                })

            return members
        except Exception as e:
            logger.warning("Failed to fetch team members for plan %s: %s", plan_id, e)
            return []

    def download_photo(self, url: str, save_path: str) -> bool:
        """Download a photo from a URL to a local path. Returns True on success."""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return True
            logger.warning("Photo download returned status %d for %s", response.status_code, url)
            return False
        except Exception as e:
            logger.warning("Failed to download photo from %s: %s", url, e)
            return False

    def get_item_notes(self, service_type_id: str, plan_id: str, item_id: str) -> List[Dict[str, str]]:
        """
        Fetches production notes for a specific item.
        Returns a list of {category: name, content: text}
        """
        endpoint = f"/service_types/{service_type_id}/plans/{plan_id}/items/{item_id}/item_notes"
        try:
            data = self._get(endpoint)
            notes = []
            for note in data.get('data', []):
                attrs = note.get('attributes', {})
                category = attrs.get('category_name')
                content = attrs.get('content')
                if not category:
                    continue
                notes.append({'category': category, 'content': content or ''})
            return notes
        except Exception as e:
            logger.warning("Failed to fetch notes for item %s: %s", item_id, e)
            return []

    def get_next_plans_for_types(self, service_type_ids: List[str]) -> List[Service]:
        """
        Fetches upcoming plans for a list of service type IDs.
        Returns up to 5 plans per service type.
        """
        plans = []
        for st_id in service_type_ids:
            try:
                plans.extend(self.get_upcoming_services(st_id))
            except Exception as e:
                logger.warning("Failed to fetch plans for service type %s: %s", st_id, e)
        return plans

    def test_connection(self) -> tuple:
        """Test PCO credentials by fetching service types.
        Returns (True, "Connected! Found N service types") or (False, "error message").
        """
        try:
            types = self.get_service_types()
            return (True, f"Connected! Found {len(types)} service types")
        except Exception as e:
            return (False, str(e))

    def get_folders(self) -> List[Dict[str, str]]:
        """Fetch all folders. Returns [{id, name}, ...]."""
        data = self._get("/folders")
        folders = []
        for item in data.get('data', []):
            item_id = item.get('id')
            name = item.get('attributes', {}).get('name')
            if not item_id or not name:
                continue
            folders.append({'id': item_id, 'name': name})
        return folders

    def get_team_positions_for_types(self, service_type_ids: List[str]) -> List[str]:
        """Scan recent plans for unique team position names.
        Returns a sorted deduplicated list of position strings.
        """
        positions = set()
        for st_id in service_type_ids:
            try:
                plans = self.get_upcoming_services(st_id)
                if plans:
                    members = self.get_team_members(st_id, plans[0].id)
                    for m in members:
                        pos = m.get("position", "")
                        if pos:
                            positions.add(pos)
            except Exception as e:
                logger.warning("Failed to scan positions for type %s: %s", st_id, e)
        return sorted(positions)

    def get_upcoming_services(self, service_type_id: str) -> List[Service]:
        """
        Fetches up to 3 upcoming plans for a service type (lightweight).

        Uses filter=future which includes:
        - Plans scheduled in the future
        - Plans currently Live (in progress)

        Returns lightweight Service objects WITHOUT items populated.
        Call populate_plan_details() separately for the plan you need items for.

        PlanTimes are matched to each plan via the plan's
        relationships.plan_times.data array.
        """
        params = {
            'filter': 'future',
            'order': 'sort_date',
            'per_page': 3,
            'include': 'plan_times'
        }
        data = self._get(f"/service_types/{service_type_id}/plans", params=params)

        if not data.get('data'):
            return []

        # Index included PlanTimes by ID for fast lookup
        included_by_id = {}
        for inc in data.get('included', []):
            if inc.get('type') == 'PlanTime':
                inc_id = inc.get('id')
                if inc_id:
                    included_by_id[inc_id] = inc

        services = []
        for plan_data in data['data']:
            plan_id = plan_data.get('id')
            attrs = plan_data.get('attributes', {})
            if not plan_id:
                logger.warning("Skipping plan with missing id")
                continue

            # Match PlanTime to THIS plan via relationships
            start_time = None
            plan_time_ids = [
                ref.get('id') for ref in
                plan_data.get('relationships', {}).get('plan_times', {}).get('data', [])
                if ref.get('id')
            ]
            for pt_id in plan_time_ids:
                pt = included_by_id.get(pt_id)
                if pt and pt.get('attributes', {}).get('time_type') == 'service':
                    starts_at = pt.get('attributes', {}).get('starts_at')
                    if starts_at:
                        try:
                            start_time = dateutil.parser.isoparse(starts_at)
                        except (ValueError, TypeError):
                            logger.warning("Invalid starts_at date for plan %s: %s", plan_id, starts_at)
                            continue
                        break

            # Fallback to sort_date if no PlanTime found
            if start_time is None:
                sort_date = attrs.get('sort_date')
                if not sort_date:
                    continue
                try:
                    start_time = dateutil.parser.isoparse(sort_date)
                except (ValueError, TypeError):
                    logger.warning("Invalid sort_date for plan %s: %s", plan_id, sort_date)
                    continue

            service = Service(
                id=plan_id,
                type_id=service_type_id,
                series_title=attrs.get('series_title'),
                plan_title=attrs.get('title'),
                dates=attrs.get('dates'),
                start_time=start_time,
                total_length=attrs.get('total_length') or 0
            )

            services.append(service)

        return services

    def populate_plan_details(self, service: Service):
        """
        Fetches items for a single plan. Call only for the plan you intend to display.
        Skips if items are already populated.
        """
        if service.items:
            return
        self._populate_items(service)

    def _populate_items(self, service: Service):
        """
        Fetches items for the service and populates the items list.
        Handles pagination to ensure all items are retrieved.
        """
        endpoint = f"/service_types/{service.type_id}/plans/{service.id}/items"
        first_request = True
        current_offset = 0

        # Handle pagination - keep fetching until no more pages
        while endpoint:
            data = self._get(endpoint, params={'per_page': 100} if first_request else None)
            first_request = False

            for item_data in data.get('data', []):
                item_id = item_data.get('id')
                attrs = item_data.get('attributes', {})
                if not item_id:
                    logger.warning("Skipping item with missing id: %s", item_data)
                    continue
                item_type = attrs.get('item_type', 'item')
                length = attrs.get('length') or 0

                item = Item(
                    id=item_id,
                    title=attrs.get('title') or "Untitled",
                    length=length,
                    sequence=attrs.get('sequence'),
                    type=item_type,
                    start_time_offset=current_offset,
                    description=attrs.get('description'),
                    key_name=attrs.get('key_name')
                )

                service.items.append(item)
                current_offset += length

            # Check for next page
            next_link = data.get('links', {}).get('next')
            if next_link:
                # Extract path relative to base_url
                if next_link.startswith(self.base_url):
                    endpoint = next_link[len(self.base_url):]
                else:
                    logger.warning("Unexpected pagination URL format: %s", next_link)
                    endpoint = None
            else:
                endpoint = None
