"""
Helper functions for handling song blocks in PCO plans.

In typical worship services, multiple songs are grouped into blocks where:
- First songs have 0 length
- Last song has the total time for the entire block
- Video directors need to see ALL songs in the block, not just the current one
"""

from typing import List, Optional
from .models import Item, Service

def get_song_block_for_item(service: Service, current_item: Item) -> List[Item]:
    """
    Gets all songs in the block containing the current item.

    A song block is defined as consecutive songs where some may have 0 length.
    Example:
        Song A (0m) ← part of block
        Song B (0m) ← part of block
        Song C (18m) ← current item, has all the time

    Returns all 3 songs if current_item is Song C.
    """
    if not service or not current_item:
        return []

    if current_item.type != 'song':
        return [current_item]  # Not a song, return just this item

    # Find the current item's position
    try:
        current_idx = next(i for i, item in enumerate(service.items) if item.id == current_item.id)
    except StopIteration:
        return [current_item]

    # Look backwards to find the start of the song block
    block_start = current_idx
    while block_start > 0:
        prev_item = service.items[block_start - 1]
        # Include previous item if it's a song (regardless of length)
        if prev_item.type == 'song':
            block_start -= 1
        else:
            break  # Hit a non-song, stop looking backwards

    # Look forwards to find the end of the song block
    block_end = current_idx
    while block_end < len(service.items) - 1:
        next_item = service.items[block_end + 1]
        # Include next item if it's a song
        if next_item.type == 'song':
            block_end += 1
        else:
            break  # Hit a non-song, stop looking forwards

    # Extract the block
    song_block = service.items[block_start:block_end + 1]

    # Only treat as a block if it's the PCO "time holder" pattern:
    # at most 1 song has length > 0. If multiple songs have their own
    # times, they're individually scheduled — not a grouped worship set.
    songs_with_time = sum(1 for s in song_block if s.length > 0)
    if songs_with_time > 1:
        return [current_item]

    return song_block


def format_song_block_for_display(service: Service, current_item: Item, include_descriptions: bool = True) -> str:
    """
    Formats a song block for display to video directors.

    Shows all songs in the block with:
    - Titles
    - Descriptions (who's leading, transitions, etc.)
    - Current item highlighted

    Example output:
        Song Block (3 songs):
        • Løfte vore hænder
          → Lead: John
        • What A Beautiful Name
          → Lead: Sarah
        • Agnus dei / King of kings ← CURRENT (18m)
          → Lead: David
    """
    block = get_song_block_for_item(service, current_item)

    if len(block) <= 1:
        return ""  # Not a block, just a single song

    lines = []
    lines.append(f"Song Block ({len(block)} songs):")

    for song in block:
        # Mark current song
        marker = " <- CURRENT" if song.id == current_item.id else ""
        if song.length > 0:
            mins, secs = divmod(song.length, 60)
            time_info = f" ({mins}:{secs:02d})" if secs else f" ({mins}m)"
        else:
            time_info = ""

        lines.append(f"  * {song.title}{time_info}{marker}")

        # Add description if available
        if include_descriptions and song.description:
            # Take first line of description (usually has leader info)
            first_line = song.description.split('\n')[0].strip()
            if first_line:
                lines.append(f"    -> {first_line}")

    return '\n'.join(lines)


def get_all_song_blocks(service: Service) -> List[List[Item]]:
    """
    Gets all song blocks in the service.

    Returns a list of lists, where each inner list is a consecutive group of songs.
    """
    if not service or not service.items:
        return []

    blocks = []
    current_block = []

    for item in service.items:
        if item.type == 'song':
            current_block.append(item)
        else:
            # Non-song item - save current block if it exists
            if len(current_block) >= 2 and sum(1 for s in current_block if s.length > 0) <= 1:
                blocks.append(current_block)
            current_block = []

    # Don't forget the last block
    if len(current_block) >= 2 and sum(1 for s in current_block if s.length > 0) <= 1:
        blocks.append(current_block)

    return blocks
