"""Tests for song_blocks.py (get_song_block_for_item, format_song_block_for_display, get_all_song_blocks)."""

from src.models import Service, Item
from src.song_blocks import get_song_block_for_item, format_song_block_for_display, get_all_song_blocks
from datetime import datetime, timezone


# ── Helpers ──────────────────────────────────────────────────────────


def _make_service(items):
    return Service(
        id="100", type_id="st1", series_title="Series",
        plan_title="Sunday", dates="Feb 8",
        start_time=datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc),
        items=items, total_length=3600,
    )


def _song(id, title, length=0, description=None):
    return Item(id=id, title=title, length=length, sequence=0, type="song",
                description=description)


def _item(id, title, length=300):
    return Item(id=id, title=title, length=length, sequence=0, type="item")


def _header(id, title):
    return Item(id=id, title=title, length=0, sequence=0, type="header")


# ── get_song_block_for_item() ────────────────────────────────────────


class TestGetSongBlock:

    def test_single_song_returns_itself(self):
        """A single song not adjacent to other songs returns just itself."""
        items = [_item("i1", "Prayer", 120), _song("s1", "Solo Song", 300), _item("i2", "Sermon", 1800)]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[1])
        assert len(block) == 1
        assert block[0].id == "s1"

    def test_block_of_three_songs(self):
        """Three consecutive songs form a block."""
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 0),
            _song("s3", "Song C", 1080),
        ]
        svc = _make_service(items)
        # Query from last song
        block = get_song_block_for_item(svc, items[2])
        assert len(block) == 3
        assert [s.id for s in block] == ["s1", "s2", "s3"]

    def test_block_from_first_song(self):
        """Querying from the first song of a block returns the whole block."""
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 0),
            _song("s3", "Song C", 1080),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[0])
        assert len(block) == 3

    def test_block_from_middle_song(self):
        """Querying from the middle song returns the whole block."""
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 0),
            _song("s3", "Song C", 1080),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[1])
        assert len(block) == 3

    def test_songs_separated_by_non_song(self):
        """Songs separated by a non-song item form separate blocks."""
        items = [
            _song("s1", "Song A", 300),
            _item("p1", "Prayer", 120),
            _song("s2", "Song B", 400),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[0])
        assert len(block) == 1
        assert block[0].id == "s1"

        block2 = get_song_block_for_item(svc, items[2])
        assert len(block2) == 1
        assert block2[0].id == "s2"

    def test_non_song_item_returns_itself(self):
        """A non-song item returns just itself."""
        items = [_item("i1", "Sermon", 1800)]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[0])
        assert len(block) == 1
        assert block[0].id == "i1"

    def test_none_service(self):
        block = get_song_block_for_item(None, _song("s1", "Song"))
        assert block == []

    def test_none_item(self):
        svc = _make_service([_song("s1", "Song")])
        block = get_song_block_for_item(svc, None)
        assert block == []

    def test_individual_timed_songs_not_a_block(self):
        """3 songs each with length > 0 are not a block (individually scheduled)."""
        items = [
            _song("s1", "Song A", 300),
            _song("s2", "Song B", 300),
            _song("s3", "Song C", 300),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[1])
        assert len(block) == 1
        assert block[0].id == "s2"

    def test_item_not_in_service(self):
        """Item not found in service returns just itself."""
        svc = _make_service([_song("s1", "Song A")])
        orphan = _song("s99", "Orphan")
        block = get_song_block_for_item(svc, orphan)
        assert len(block) == 1
        assert block[0].id == "s99"

    def test_song_at_start_of_service(self):
        """Song at the very start of a service with a block."""
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 600),
            _item("i1", "Sermon", 1800),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[0])
        assert len(block) == 2
        assert [s.id for s in block] == ["s1", "s2"]

    def test_song_at_end_of_service(self):
        """Song at the very end of a service with a block."""
        items = [
            _item("i1", "Sermon", 1800),
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 600),
        ]
        svc = _make_service(items)
        block = get_song_block_for_item(svc, items[2])
        assert len(block) == 2
        assert [s.id for s in block] == ["s1", "s2"]


# ── format_song_block_for_display() ──────────────────────────────────


class TestFormatSongBlock:

    def test_single_song_returns_empty(self):
        """Single songs don't format as blocks."""
        items = [_item("i1", "Prayer"), _song("s1", "Solo", 300), _item("i2", "Sermon")]
        svc = _make_service(items)
        result = format_song_block_for_display(svc, items[1])
        assert result == ""

    def test_block_formatting(self):
        items = [
            _song("s1", "Song A", 0, description="Lead: John"),
            _song("s2", "Song B", 0, description="Lead: Sarah"),
            _song("s3", "Song C", 1080, description="Lead: David"),
        ]
        svc = _make_service(items)
        result = format_song_block_for_display(svc, items[2])
        assert "Song Block (3 songs):" in result
        assert "Song A" in result
        assert "Song B" in result
        assert "Song C" in result
        assert "CURRENT" in result
        assert "Lead: John" in result
        assert "Lead: David" in result

    def test_no_descriptions(self):
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 1080),
        ]
        svc = _make_service(items)
        result = format_song_block_for_display(svc, items[1], include_descriptions=False)
        assert "Song Block" in result
        assert "->" not in result

    def test_time_shown_for_nonzero_length(self):
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 1080),
        ]
        svc = _make_service(items)
        result = format_song_block_for_display(svc, items[1])
        assert "(18m)" in result
        # Song A has 0 length, no time shown
        assert "(0m)" not in result


# ── get_all_song_blocks() ────────────────────────────────────────────


class TestGetAllSongBlocks:

    def test_no_songs(self):
        items = [_item("i1", "Sermon", 1800)]
        svc = _make_service(items)
        assert get_all_song_blocks(svc) == []

    def test_single_song_not_a_block(self):
        """A lone song is not a block (needs 2+)."""
        items = [_song("s1", "Solo", 300)]
        svc = _make_service(items)
        assert get_all_song_blocks(svc) == []

    def test_two_consecutive_songs(self):
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 600),
        ]
        svc = _make_service(items)
        blocks = get_all_song_blocks(svc)
        assert len(blocks) == 1
        assert len(blocks[0]) == 2

    def test_multiple_blocks(self):
        items = [
            _song("s1", "Song A", 0),
            _song("s2", "Song B", 600),
            _item("i1", "Prayer", 120),
            _song("s3", "Song C", 0),
            _song("s4", "Song D", 0),
            _song("s5", "Song E", 900),
        ]
        svc = _make_service(items)
        blocks = get_all_song_blocks(svc)
        assert len(blocks) == 2
        assert len(blocks[0]) == 2
        assert len(blocks[1]) == 3

    def test_empty_service(self):
        svc = _make_service([])
        assert get_all_song_blocks(svc) == []

    def test_get_all_song_blocks_skips_individually_timed(self):
        """Groups where 2+ songs have length > 0 are excluded."""
        items = [
            _song("s1", "Song A", 300),
            _song("s2", "Song B", 300),
            _song("s3", "Song C", 300),
            _item("i1", "Prayer", 120),
            _song("s4", "Song D", 0),
            _song("s5", "Song E", 900),
        ]
        svc = _make_service(items)
        blocks = get_all_song_blocks(svc)
        # First group (3 individually timed songs) excluded, second group kept
        assert len(blocks) == 1
        assert [s.id for s in blocks[0]] == ["s4", "s5"]

    def test_none_service(self):
        assert get_all_song_blocks(None) == []
