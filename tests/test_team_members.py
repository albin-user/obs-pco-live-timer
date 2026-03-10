"""Tests for src/team_members.py (slot-based source mapping, response building, fetch+cache)."""

import os
from unittest.mock import MagicMock, patch

from src.models import TeamMember
from src.team_members import build_team_response, fetch_and_cache_team


# ── Helpers ──────────────────────────────────────────────────────────


def _member(position="Vocalist", name="Alice", person_id="1", **kw):
    return TeamMember(
        person_id=person_id, name=name, position=position,
        team_name=kw.get("team_name", "Worship"), status=kw.get("status", "C"),
        photo_url=kw.get("photo_url"), photo_path=kw.get("photo_path"),
    )


# ── build_team_response() ───────────────────────────────────────────


class TestBuildTeamResponse:

    def test_filled_slot(self):
        members = [_member(position="Drums", name="Bob Jones", photo_path="/tmp/bob.jpg")]
        result = build_team_response(members, ["Drums"])
        assert len(result) == 1
        entry = result[0]
        assert entry["name"] == "Bob"
        assert entry["position"] == "Drums"
        assert entry["name_source"] == "PCO Position Drums 1 Name"
        assert entry["position_source"] == "PCO Position Drums 1 Position"
        assert entry["photo_source"] == "PCO Position Drums 1 Photo"
        assert entry["photo_path"] == "/tmp/bob.jpg"

    def test_empty_slot_placeholder(self):
        result = build_team_response([], ["Keys"], placeholder_photo="/tmp/placeholder.png")
        assert len(result) == 1
        entry = result[0]
        assert entry["name"] == ""
        assert entry["position"] == "Empty"
        assert entry["name_source"] == "PCO Position Keys 1 Name"
        assert entry["position_source"] == "PCO Position Keys 1 Position"
        assert entry["photo_source"] == "PCO Position Keys 1 Photo"
        assert entry["photo_path"] == "/tmp/placeholder.png"

    def test_duplicate_position_numbering(self):
        members = [
            _member(position="Vocalist", name="Alice Smith", person_id="1"),
            _member(position="Vocalist", name="Bob Jones", person_id="2"),
        ]
        result = build_team_response(members, ["Vocalist", "Vocalist"])
        assert result[0]["name_source"] == "PCO Position Vocalist 1 Name"
        assert result[1]["name_source"] == "PCO Position Vocalist 2 Name"
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"

    def test_first_name_only(self):
        members = [_member(name="Alice Smith")]
        result = build_team_response(members, ["Vocalist"])
        assert result[0]["name"] == "Alice"

    def test_first_name_single_name(self):
        members = [_member(name="Madonna")]
        result = build_team_response(members, ["Vocalist"])
        assert result[0]["name"] == "Madonna"

    def test_first_name_empty_name(self):
        members = [_member(name="")]
        result = build_team_response(members, ["Vocalist"])
        assert result[0]["name"] == ""

    def test_placeholder_photo_used_for_empty(self):
        result = build_team_response([], ["Drums"], placeholder_photo="/placeholder.png")
        assert result[0]["photo_path"] == "/placeholder.png"

    def test_member_with_no_photo_gets_placeholder(self):
        members = [_member(photo_path=None)]
        result = build_team_response(members, ["Vocalist"], placeholder_photo="/placeholder.png")
        assert result[0]["photo_path"] == "/placeholder.png"

    def test_empty_slots_list(self):
        members = [_member()]
        result = build_team_response(members, [])
        assert result == []

    def test_extra_members_not_in_slots_ignored(self):
        members = [
            _member(position="Drums", name="Bob", person_id="1"),
            _member(position="Keys", name="Carol", person_id="2"),
        ]
        result = build_team_response(members, ["Drums"])
        assert len(result) == 1
        assert result[0]["name"] == "Bob"

    def test_correct_keys(self):
        members = [_member(photo_path="/tmp/1.jpg")]
        result = build_team_response(members, ["Vocalist"])
        entry = result[0]
        assert "name" in entry
        assert "position" in entry
        assert "team" in entry
        assert "status" in entry
        assert "name_source" in entry
        assert "position_source" in entry
        assert "photo_source" in entry
        assert "photo_path" in entry

    def test_mixed_filled_and_empty(self):
        members = [_member(position="Worship Leader", name="Alice Smith", person_id="1")]
        slots = ["Worship Leader", "Vocalist", "Drums"]
        result = build_team_response(members, slots, placeholder_photo="/p.png")
        assert result[0]["name"] == "Alice"
        assert result[0]["position"] == "Worship Leader"
        assert result[1]["position"] == "Empty"
        assert result[1]["photo_path"] == "/p.png"
        assert result[2]["position"] == "Empty"


# ── fetch_and_cache_team() ──────────────────────────────────────────


class TestFetchAndCacheTeam:

    def test_downloads_photos(self, tmp_path):
        client = MagicMock()
        client.get_team_members.return_value = [
            {"person_id": "10", "name": "Alice", "position": "Vocals",
             "team_name": "Worship", "photo_url": "https://example.com/photo.jpg",
             "status": "C"},
        ]
        client.download_photo.return_value = True

        result = fetch_and_cache_team(client, "st1", "plan1", str(tmp_path))
        assert len(result) == 1
        assert result[0].photo_path == os.path.join(str(tmp_path), "10.jpg")
        client.download_photo.assert_called_once()

    def test_skips_existing_file(self, tmp_path):
        # Pre-create the file
        photo = tmp_path / "10.jpg"
        photo.write_bytes(b"existing")

        client = MagicMock()
        client.get_team_members.return_value = [
            {"person_id": "10", "name": "Alice", "position": "Vocals",
             "team_name": "Worship", "photo_url": "https://example.com/photo.jpg",
             "status": "C"},
        ]

        result = fetch_and_cache_team(client, "st1", "plan1", str(tmp_path))
        client.download_photo.assert_not_called()
        assert result[0].photo_path == str(photo)

    def test_missing_photo_url(self, tmp_path):
        client = MagicMock()
        client.get_team_members.return_value = [
            {"person_id": "10", "name": "Alice", "position": "Vocals",
             "team_name": "Worship", "photo_url": None, "status": "C"},
        ]

        result = fetch_and_cache_team(client, "st1", "plan1", str(tmp_path))
        assert result[0].photo_path is None
        client.download_photo.assert_not_called()

    def test_download_failure(self, tmp_path):
        client = MagicMock()
        client.get_team_members.return_value = [
            {"person_id": "10", "name": "Alice", "position": "Vocals",
             "team_name": "Worship", "photo_url": "https://example.com/photo.jpg",
             "status": "C"},
        ]
        client.download_photo.return_value = False

        result = fetch_and_cache_team(client, "st1", "plan1", str(tmp_path))
        assert result[0].photo_path is None

    def test_empty_cache_dir_skips_download(self):
        client = MagicMock()
        client.get_team_members.return_value = [
            {"person_id": "10", "name": "Alice", "position": "Vocals",
             "team_name": "Worship", "photo_url": "https://example.com/photo.jpg",
             "status": "C"},
        ]

        result = fetch_and_cache_team(client, "st1", "plan1", "")
        client.download_photo.assert_not_called()
        assert result[0].photo_path is None
