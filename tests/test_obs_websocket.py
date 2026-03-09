"""Tests for OBSTextPusher (obs_websocket.py).

All tests mock obsws_python to avoid requiring a running OBS instance.
"""

from unittest.mock import MagicMock, patch

from src.obs_websocket import OBSTextPusher, COLOR_GREEN, COLOR_RED, COLOR_WHITE


# ── Helpers ──────────────────────────────────────────────────────────


def _make_pusher(manager=None):
    if manager is None:
        manager = MagicMock()
    return OBSTextPusher(
        manager=manager,
        host="localhost",
        port=4455,
        password="",
        update_interval_ms=1000,
    )


# ── Color logic ──────────────────────────────────────────────────────


class TestCountdownColor:

    def test_positive_seconds_green(self):
        assert OBSTextPusher._countdown_color(300) == COLOR_GREEN

    def test_zero_seconds_green(self):
        assert OBSTextPusher._countdown_color(0) == COLOR_GREEN

    def test_negative_seconds_red(self):
        assert OBSTextPusher._countdown_color(-1) == COLOR_RED

    def test_large_negative_red(self):
        assert OBSTextPusher._countdown_color(-600) == COLOR_RED


class TestServiceEndColor:

    def test_behind_schedule_red(self):
        assert OBSTextPusher._service_end_color(5.0) == COLOR_RED

    def test_ahead_of_schedule_white(self):
        assert OBSTextPusher._service_end_color(-3.0) == COLOR_WHITE

    def test_on_time_white(self):
        assert OBSTextPusher._service_end_color(0.0) == COLOR_WHITE

    def test_small_behind_rounds_to_zero_white(self):
        # 0.4 rounds to 0
        assert OBSTextPusher._service_end_color(0.4) == COLOR_WHITE

    def test_rounds_up_to_one_red(self):
        # 0.6 rounds to 1
        assert OBSTextPusher._service_end_color(0.6) == COLOR_RED


# ── _set_text() ──────────────────────────────────────────────────────


class TestSetText:

    def test_pushes_text_to_obs(self):
        pusher = _make_pusher()
        pusher._ws = MagicMock()
        pusher._set_text("PCO Countdown", "05:00")
        pusher._ws.set_input_settings.assert_called_once_with(
            "PCO Countdown", {"text": "05:00"}, overlay=True
        )

    def test_pushes_text_with_color(self):
        pusher = _make_pusher()
        pusher._ws = MagicMock()
        pusher._set_text("PCO Countdown", "05:00", color=COLOR_GREEN)
        call_args = pusher._ws.set_input_settings.call_args
        settings = call_args[0][1]
        assert settings["text"] == "05:00"
        assert settings["color1"] == COLOR_GREEN
        assert settings["color2"] == COLOR_GREEN

    def test_skips_when_no_connection(self):
        pusher = _make_pusher()
        pusher._ws = None
        # Should not raise
        pusher._set_text("PCO Countdown", "05:00")

    def test_skips_missing_source(self):
        pusher = _make_pusher()
        pusher._ws = MagicMock()
        pusher._missing_sources.add("PCO Countdown")
        pusher._set_text("PCO Countdown", "05:00")
        pusher._ws.set_input_settings.assert_not_called()

    def test_source_not_found_adds_to_missing(self):
        pusher = _make_pusher()
        pusher._ws = MagicMock()
        pusher._ws.set_input_settings.side_effect = Exception("Error code 600: Source not found")
        pusher._set_text("PCO Missing", "text")
        assert "PCO Missing" in pusher._missing_sources

    def test_other_error_reraises(self):
        pusher = _make_pusher()
        pusher._ws = MagicMock()
        pusher._ws.set_input_settings.side_effect = Exception("Network timeout")
        import pytest
        with pytest.raises(Exception, match="Network timeout"):
            pusher._set_text("PCO Countdown", "text")


# ── _push_all_values() ──────────────────────────────────────────────


class TestPushAllValues:

    def test_pushes_all_sources_with_data(self):
        """Verify all 11 OBS sources get pushed when data is available."""
        pusher = _make_pusher()
        pusher._ws = MagicMock()

        # Mock build_timer_response to return full data
        full_data = {
            "service_type_name": "Sunday Morning",
            "service_date": "Feb 8, 2026",
            "plan_title": "Week 3",
            "is_live": True,
            "current_item": {
                "title": "Worship",
                "description": "Acoustic set",
                "countdown_seconds": 300.0,
                "countdown_formatted": "05:00",
                "is_overtime": False,
                "length_formatted": "30:00",
            },
            "next_item": {
                "title": "Sermon",
                "description": None,
                "length_formatted": "35:00",
            },
            "service_end": {
                "status_text": "On time - ends at 11:00 AM",
                "overrun_minutes": 0,
            },
            "progress": {"text": "1 of 2"},
        }

        with patch("src.obs_websocket.build_timer_response", return_value=full_data):
            pusher._push_all_values()

        # Check that set_input_settings was called for multiple sources
        call_names = [
            call[0][0] for call in pusher._ws.set_input_settings.call_args_list
        ]
        assert "PCO Countdown" in call_names
        assert "PCO Current Title" in call_names
        assert "PCO Next Title" in call_names
        assert "PCO Service End" in call_names
        assert "PCO Progress" in call_names
        assert "PCO Service Type" in call_names
        assert "PCO Service Date" in call_names
        assert "PCO Plan Title" in call_names
        assert "PCO Item Length" in call_names
        assert "PCO Current Description" in call_names
        assert "PCO Next Length" in call_names

    def test_clears_sources_when_no_current_item(self):
        """When no current item, countdown and title sources get empty strings."""
        pusher = _make_pusher()
        pusher._ws = MagicMock()

        data = {
            "service_type_name": None,
            "service_date": None,
            "plan_title": None,
            "is_live": False,
            "current_item": None,
            "next_item": None,
            "service_end": None,
            "progress": None,
        }

        with patch("src.obs_websocket.build_timer_response", return_value=data):
            pusher._push_all_values()

        # Find the PCO Current Title call
        calls = {
            call[0][0]: call[0][1]
            for call in pusher._ws.set_input_settings.call_args_list
        }
        assert calls["PCO Current Title"] == {"text": ""}
        assert calls["PCO Next Title"] == {"text": ""}


# ── Connection handling ──────────────────────────────────────────────


class TestConnection:

    @patch("src.obs_websocket.build_timer_response")
    def test_connect_success(self, mock_btr):
        pusher = _make_pusher()
        mock_obs = MagicMock()

        with patch.dict("sys.modules", {"obsws_python": mock_obs}):
            mock_obs.ReqClient.return_value = MagicMock()
            result = pusher._connect()

        assert result is True
        assert pusher._ws is not None
        assert len(pusher._missing_sources) == 0

    def test_connect_failure(self):
        pusher = _make_pusher()

        with patch.dict("sys.modules", {"obsws_python": MagicMock()}) as modules:
            import sys
            sys.modules["obsws_python"].ReqClient.side_effect = ConnectionRefusedError("refused")
            result = pusher._connect()

        assert result is False
        assert pusher._ws is None

    def test_disconnect_cleans_up(self):
        pusher = _make_pusher()
        mock_ws = MagicMock()
        pusher._ws = mock_ws
        pusher._disconnect()
        assert pusher._ws is None

    def test_stop_sets_event(self):
        pusher = _make_pusher()
        pusher.stop()
        assert pusher._stop_event.is_set()
