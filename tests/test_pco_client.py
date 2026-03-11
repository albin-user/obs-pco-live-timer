"""Tests for PCOClient API interactions.

All tests mock requests.get to avoid real API calls.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
import requests

from src.pco_client import PCOClient, _MAX_RETRIES


# ── Helpers ──────────────────────────────────────────────────────────


def _make_client():
    return PCOClient("test_app_id", "test_secret")


def _mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status.side_effect = (
        None if status_code < 400
        else requests.exceptions.HTTPError(response=resp)
    )
    return resp


# ── Constructor ──────────────────────────────────────────────────────


class TestConstructor:

    def test_stores_credentials(self):
        client = PCOClient("myapp", "mysecret")
        assert client.app_id == "myapp"
        assert client.secret == "mysecret"

    def test_base_url(self):
        client = _make_client()
        assert "planningcenteronline.com" in client.base_url


# ── _get() basics ────────────────────────────────────────────────────


class TestGet:

    @patch("src.pco_client.requests.get")
    def test_successful_get(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": [{"id": "1"}]})
        client = _make_client()
        result = client._get("/test")
        assert result == {"data": [{"id": "1"}]}

    @patch("src.pco_client.requests.get")
    def test_passes_auth(self, mock_get):
        mock_get.return_value = _mock_response(200, {})
        client = _make_client()
        client._get("/test")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] is not None

    @patch("src.pco_client.requests.get")
    def test_passes_params(self, mock_get):
        mock_get.return_value = _mock_response(200, {})
        client = _make_client()
        client._get("/test", params={"per_page": 3})
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"] == {"per_page": 3}


# ── _get() error handling ────────────────────────────────────────────


class TestGetErrors:

    @patch("src.pco_client.requests.get")
    def test_http_401_raises(self, mock_get):
        mock_get.return_value = _mock_response(401, {})
        client = _make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client._get("/test")

    @patch("src.pco_client.requests.get")
    def test_http_403_raises(self, mock_get):
        mock_get.return_value = _mock_response(403, {})
        client = _make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client._get("/test")

    @patch("src.pco_client.requests.get")
    def test_http_404_raises(self, mock_get):
        mock_get.return_value = _mock_response(404, {})
        client = _make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client._get("/test")

    @patch("src.pco_client.requests.get")
    def test_json_decode_error(self, mock_get):
        resp = _mock_response(200)
        resp.json.side_effect = ValueError("No JSON")
        mock_get.return_value = resp
        client = _make_client()
        with pytest.raises(ValueError, match="Invalid JSON"):
            client._get("/test")


# ── _get() retry / backoff ───────────────────────────────────────────


class TestRetry:

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_429_retries_then_succeeds(self, mock_get, mock_sleep):
        """429 triggers retry; second attempt succeeds."""
        rate_resp = _mock_response(429, headers={"Retry-After": "1"})
        ok_resp = _mock_response(200, {"data": []})
        mock_get.side_effect = [rate_resp, ok_resp]

        client = _make_client()
        result = client._get("/test")
        assert result == {"data": []}
        assert mock_get.call_count == 2

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_500_retries(self, mock_get, mock_sleep):
        """5xx triggers retry."""
        err_resp = _mock_response(500)
        ok_resp = _mock_response(200, {"data": []})
        mock_get.side_effect = [err_resp, ok_resp]

        client = _make_client()
        result = client._get("/test")
        assert mock_get.call_count == 2

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_connection_error_retries(self, mock_get, mock_sleep):
        """ConnectionError triggers retry."""
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            _mock_response(200, {"data": []}),
        ]
        client = _make_client()
        result = client._get("/test")
        assert result == {"data": []}

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_timeout_retries(self, mock_get, mock_sleep):
        """Timeout triggers retry."""
        mock_get.side_effect = [
            requests.exceptions.Timeout("timed out"),
            _mock_response(200, {"ok": True}),
        ]
        client = _make_client()
        result = client._get("/test")
        assert result == {"ok": True}

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_max_retries_exceeded_raises(self, mock_get, mock_sleep):
        """After _MAX_RETRIES connection errors, raises the last exception."""
        mock_get.side_effect = requests.exceptions.ConnectionError("down")
        client = _make_client()
        with pytest.raises(requests.exceptions.ConnectionError):
            client._get("/test")
        assert mock_get.call_count == _MAX_RETRIES


# ── get_service_types() ──────────────────────────────────────────────


class TestGetServiceTypes:

    @patch("src.pco_client.requests.get")
    def test_parses_service_types(self, mock_get):
        mock_get.return_value = _mock_response(200, {
            "data": [
                {"id": "1", "attributes": {"name": "Sunday"}},
                {"id": "2", "attributes": {"name": "Wednesday"}},
            ]
        })
        client = _make_client()
        result = client.get_service_types()
        assert len(result) == 2
        assert result[0] == {"id": "1", "name": "Sunday"}

    @patch("src.pco_client.requests.get")
    def test_empty_data(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        result = client.get_service_types()
        assert result == []

    @patch("src.pco_client.requests.get")
    def test_missing_data_key(self, mock_get):
        mock_get.return_value = _mock_response(200, {})
        client = _make_client()
        result = client.get_service_types()
        assert result == []


# ── get_folder_service_types() ───────────────────────────────────────


class TestGetFolderServiceTypes:

    @patch("src.pco_client.requests.get")
    def test_parses_folder_types(self, mock_get):
        mock_get.return_value = _mock_response(200, {
            "data": [
                {"id": "10", "attributes": {"name": "Worship"}},
                {"id": "20", "attributes": {"name": "Events"}},
            ]
        })
        client = _make_client()
        result = client.get_folder_service_types("folder123")
        assert len(result) == 2
        assert result[1] == {"id": "20", "name": "Events"}

    @patch("src.pco_client.requests.get")
    def test_empty_folder(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        result = client.get_folder_service_types("folder123")
        assert result == []


# ── get_item_notes() ─────────────────────────────────────────────────


class TestGetItemNotes:

    @patch("src.pco_client.requests.get")
    def test_returns_notes(self, mock_get):
        mock_get.return_value = _mock_response(200, {
            "data": [
                {"attributes": {"category_name": "Video", "content": "Close-up"}},
                {"attributes": {"category_name": "Audio", "content": "Soft start"}},
            ]
        })
        client = _make_client()
        notes = client.get_item_notes("st1", "plan1", "item1")
        assert len(notes) == 2
        assert notes[0] == {"category": "Video", "content": "Close-up"}

    @patch("src.pco_client.requests.get")
    def test_no_notes(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        notes = client.get_item_notes("st1", "plan1", "item1")
        assert notes == []

    @patch("src.pco_client.requests.get")
    def test_error_returns_empty_list(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("down")
        client = _make_client()
        notes = client.get_item_notes("st1", "plan1", "item1")
        assert notes == []


# ── Pagination ───────────────────────────────────────────────────────


class TestPagination:

    @patch("src.pco_client.requests.get")
    def test_populate_items_paginates(self, mock_get):
        """_populate_items follows links.next to get all pages."""
        from src.models import Service
        page1 = _mock_response(200, {
            "data": [
                {"id": "i1", "attributes": {"title": "Song 1", "length": 300,
                                             "sequence": 1, "item_type": "song"}},
            ],
            "links": {"next": "https://api.planningcenteronline.com/services/v2/service_types/1/plans/1/items?offset=1"}
        })
        page2 = _mock_response(200, {
            "data": [
                {"id": "i2", "attributes": {"title": "Song 2", "length": 600,
                                             "sequence": 2, "item_type": "song"}},
            ],
            "links": {}
        })
        mock_get.side_effect = [page1, page2]

        client = _make_client()
        svc = Service(
            id="1", type_id="st1", series_title=None, plan_title="Test",
            dates="Feb 8", start_time=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
            items=[], total_length=900,
        )
        client._populate_items(svc)
        assert len(svc.items) == 2
        assert svc.items[0].title == "Song 1"
        assert svc.items[1].title == "Song 2"
        # Verify start_time_offset is cumulative
        assert svc.items[0].start_time_offset == 0
        assert svc.items[1].start_time_offset == 300


# ── get_next_plans_for_types() ───────────────────────────────────────


class TestGetNextPlansForTypes:

    @patch("src.pco_client.requests.get")
    def test_aggregates_multiple_types(self, mock_get):
        """get_next_plans_for_types merges plans from multiple service type IDs."""
        mock_get.return_value = _mock_response(200, {
            "data": [
                {
                    "id": "p1", "attributes": {"title": "Plan", "sort_date": "2026-02-08T10:00:00Z",
                                                "series_title": None, "dates": "Feb 8",
                                                "total_length": 3600},
                    "relationships": {"plan_times": {"data": []}},
                },
            ],
            "included": [],
        })
        client = _make_client()
        plans = client.get_next_plans_for_types(["st1", "st2"])
        # Each type returns one plan
        assert len(plans) == 2

    @patch("src.pco_client.requests.get")
    def test_empty_response(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        plans = client.get_next_plans_for_types(["st1"])
        assert len(plans) == 0

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_handles_failure_for_one_type(self, mock_get, mock_sleep):
        """If one service type fails after all retries, the other still returns plans."""
        ok_response = _mock_response(200, {
            "data": [
                {
                    "id": "p2", "attributes": {"title": "Plan B",
                                                "sort_date": "2026-02-08T10:00:00Z",
                                                "series_title": None, "dates": "Feb 8",
                                                "total_length": 3600},
                    "relationships": {"plan_times": {"data": []}},
                },
            ],
            "included": [],
        })

        # First _MAX_RETRIES calls fail (all retries for st1), then st2 succeeds
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("fail"),
            requests.exceptions.ConnectionError("fail"),
            requests.exceptions.ConnectionError("fail"),
            ok_response,
        ]

        client = _make_client()
        plans = client.get_next_plans_for_types(["st1", "st2"])
        assert len(plans) == 1
        assert plans[0].id == "p2"


# ── get_team_members() ──────────────────────────────────────────────


def _team_members_response():
    """Build a realistic team_members?include=person,team response."""
    return {
        "data": [
            {
                "id": "tm1",
                "type": "TeamMember",
                "attributes": {
                    "name": "Alice Smith",
                    "team_position_name": "Worship Leader",
                    "status": "C",
                    "photo_thumbnail": None,
                },
                "relationships": {
                    "person": {"data": {"type": "Person", "id": "p100"}},
                    "team": {"data": {"type": "Team", "id": "t1"}},
                },
            },
            {
                "id": "tm2",
                "type": "TeamMember",
                "attributes": {
                    "name": "Bob Jones",
                    "team_position_name": "Drums",
                    "status": "U",
                    "photo_thumbnail": "https://cdn.example.com/bob-attr.jpg",
                },
                "relationships": {
                    "person": {"data": {"type": "Person", "id": "p200"}},
                    "team": {"data": {"type": "Team", "id": "t1"}},
                },
            },
        ],
        "included": [
            {
                "type": "Person",
                "id": "p100",
                "attributes": {
                    "photo_thumbnail_url": "https://cdn.example.com/alice.jpg",
                },
            },
            {
                "type": "Person",
                "id": "p200",
                "attributes": {
                    "photo_thumbnail_url": "https://cdn.example.com/bob.jpg",
                },
            },
            {
                "type": "Team",
                "id": "t1",
                "attributes": {"name": "Worship Team"},
            },
        ],
        "links": {},
    }


class TestGetTeamMembers:

    @patch("src.pco_client.requests.get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = _mock_response(200, _team_members_response())
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert len(members) == 2
        alice = members[0]
        assert alice["person_id"] == "p100"
        assert alice["name"] == "Alice Smith"
        assert alice["position"] == "Worship Leader"
        assert alice["team_name"] == "Worship Team"
        assert alice["status"] == "C"

    @patch("src.pco_client.requests.get")
    def test_photo_from_included_person(self, mock_get):
        mock_get.return_value = _mock_response(200, _team_members_response())
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert members[0]["photo_url"] == "https://cdn.example.com/alice.jpg"

    @patch("src.pco_client.requests.get")
    def test_photo_fallback_to_attribute(self, mock_get):
        """When Person has no photo, falls back to team_member attribute."""
        resp = _team_members_response()
        # Remove person p200 photo
        for inc in resp["included"]:
            if inc["id"] == "p200":
                inc["attributes"]["photo_thumbnail_url"] = None
        mock_get.return_value = _mock_response(200, resp)
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        bob = members[1]
        assert bob["photo_url"] == "https://cdn.example.com/bob-attr.jpg"

    @patch("src.pco_client.requests.get")
    def test_empty_data(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": [], "included": [], "links": {}})
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert members == []

    @patch("src.pco_client.requests.get")
    def test_missing_data_key(self, mock_get):
        mock_get.return_value = _mock_response(200, {})
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert members == []

    @patch("src.pco_client.requests.get")
    def test_team_name_from_included(self, mock_get):
        mock_get.return_value = _mock_response(200, _team_members_response())
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert all(m["team_name"] == "Worship Team" for m in members)

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_error_returns_empty(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("down")
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert members == []

    @patch("src.pco_client.requests.get")
    def test_pagination(self, mock_get):
        page1 = _team_members_response()
        page1["links"]["next"] = "https://api.planningcenteronline.com/services/v2/service_types/st1/plans/plan1/team_members?offset=2"
        page2 = {
            "data": [
                {
                    "id": "tm3",
                    "type": "TeamMember",
                    "attributes": {
                        "name": "Carol Davis",
                        "team_position_name": "Keys",
                        "status": "C",
                    },
                    "relationships": {
                        "person": {"data": {"type": "Person", "id": "p300"}},
                        "team": {"data": {"type": "Team", "id": "t1"}},
                    },
                },
            ],
            "included": [
                {"type": "Person", "id": "p300", "attributes": {"photo_thumbnail_url": None}},
                {"type": "Team", "id": "t1", "attributes": {"name": "Worship Team"}},
            ],
            "links": {},
        }
        mock_get.side_effect = [
            _mock_response(200, page1),
            _mock_response(200, page2),
        ]
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert len(members) == 3
        assert members[2]["name"] == "Carol Davis"

    @patch("src.pco_client.requests.get")
    def test_filters_declined_members(self, mock_get):
        """Members with status 'D' are excluded."""
        resp = _team_members_response()
        # Add a declined member
        resp["data"].append({
            "id": "tm3",
            "type": "TeamMember",
            "attributes": {
                "name": "Declined Dan",
                "team_position_name": "Keys",
                "status": "D",
            },
            "relationships": {
                "person": {"data": {"type": "Person", "id": "p300"}},
                "team": {"data": {"type": "Team", "id": "t1"}},
            },
        })
        resp["included"].append({
            "type": "Person", "id": "p300",
            "attributes": {"photo_thumbnail_url": None},
        })
        mock_get.return_value = _mock_response(200, resp)
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert len(members) == 2
        assert all(m["status"] != "D" for m in members)

    @patch("src.pco_client.requests.get")
    def test_skips_entry_without_person_id(self, mock_get):
        resp = {
            "data": [
                {
                    "id": "tm1",
                    "attributes": {"name": "Ghost", "team_position_name": "X", "status": "C"},
                    "relationships": {"person": {"data": None}, "team": {"data": None}},
                },
            ],
            "included": [],
            "links": {},
        }
        mock_get.return_value = _mock_response(200, resp)
        client = _make_client()
        members = client.get_team_members("st1", "plan1")
        assert members == []


# ── download_photo() ────────────────────────────────────────────────


class TestDownloadPhoto:

    @patch("src.pco_client.requests.get")
    def test_successful_download(self, mock_get, tmp_path):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"\xff\xd8\xff\xe0fake-jpeg"
        mock_get.return_value = resp

        client = _make_client()
        path = str(tmp_path / "photo.jpg")
        result = client.download_photo("https://example.com/photo.jpg", path)
        assert result is True
        assert os.path.exists(path)

    @patch("src.pco_client.requests.get")
    def test_non_200_returns_false(self, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        mock_get.return_value = resp

        client = _make_client()
        result = client.download_photo("https://example.com/nope.jpg", "/tmp/nope.jpg")
        assert result is False

    @patch("src.pco_client.requests.get")
    def test_exception_returns_false(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")
        client = _make_client()
        result = client.download_photo("https://example.com/photo.jpg", "/tmp/photo.jpg")
        assert result is False


# ── test_connection() ──────────────────────────────────────────────


class TestTestConnection:

    @patch("src.pco_client.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = _mock_response(200, {
            "data": [
                {"id": "1", "attributes": {"name": "Sunday"}},
                {"id": "2", "attributes": {"name": "Wednesday"}},
            ]
        })
        client = _make_client()
        ok, msg = client.test_connection()
        assert ok is True
        assert "2 service types" in msg

    @patch("src.pco_client._time.sleep")
    @patch("src.pco_client.requests.get")
    def test_failure(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        client = _make_client()
        ok, msg = client.test_connection()
        assert ok is False
        assert "refused" in msg


# ── get_folders() ──────────────────────────────────────────────────


class TestGetFolders:

    @patch("src.pco_client.requests.get")
    def test_parses_folders(self, mock_get):
        mock_get.return_value = _mock_response(200, {
            "data": [
                {"id": "f1", "attributes": {"name": "Weekend Services"}},
                {"id": "f2", "attributes": {"name": "Midweek"}},
            ]
        })
        client = _make_client()
        folders = client.get_folders()
        assert len(folders) == 2
        assert folders[0] == {"id": "f1", "name": "Weekend Services"}

    @patch("src.pco_client.requests.get")
    def test_empty(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        assert client.get_folders() == []


# ── get_team_positions_for_types() ─────────────────────────────────


class TestGetTeamPositionsForTypes:

    @patch("src.pco_client.requests.get")
    def test_collects_unique_positions(self, mock_get):
        # First call: get_upcoming_services for st1
        plans_resp = _mock_response(200, {
            "data": [
                {
                    "id": "p1",
                    "attributes": {"title": "Plan", "sort_date": "2026-02-08T10:00:00Z",
                                    "series_title": None, "dates": "Feb 8",
                                    "total_length": 3600},
                    "relationships": {"plan_times": {"data": []}},
                },
            ],
            "included": [],
        })
        # Second call: get_team_members for p1
        team_resp = _mock_response(200, {
            "data": [
                {
                    "id": "tm1", "type": "TeamMember",
                    "attributes": {"name": "Alice", "team_position_name": "Vocalist",
                                    "status": "C"},
                    "relationships": {
                        "person": {"data": {"type": "Person", "id": "p1"}},
                        "team": {"data": {"type": "Team", "id": "t1"}},
                    },
                },
                {
                    "id": "tm2", "type": "TeamMember",
                    "attributes": {"name": "Bob", "team_position_name": "Drums",
                                    "status": "C"},
                    "relationships": {
                        "person": {"data": {"type": "Person", "id": "p2"}},
                        "team": {"data": {"type": "Team", "id": "t1"}},
                    },
                },
            ],
            "included": [
                {"type": "Person", "id": "p1", "attributes": {"photo_thumbnail_url": None}},
                {"type": "Person", "id": "p2", "attributes": {"photo_thumbnail_url": None}},
                {"type": "Team", "id": "t1", "attributes": {"name": "Worship"}},
            ],
            "links": {},
        })
        mock_get.side_effect = [plans_resp, team_resp]

        client = _make_client()
        positions = client.get_team_positions_for_types(["st1"])
        assert positions == ["Drums", "Vocalist"]  # sorted

    @patch("src.pco_client.requests.get")
    def test_no_plans_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(200, {"data": []})
        client = _make_client()
        positions = client.get_team_positions_for_types(["st1"])
        assert positions == []
