"""
Generate colored circle PNG icons for tray states.
Reuses the stdlib-only PNG generation pattern from run.py.
"""
import os
import struct
import zlib
import logging

logger = logging.getLogger(__name__)

# Tray icon states → RGB colors
ICON_COLORS = {
    "gray": (0x80, 0x80, 0x80),
    "yellow": (0xFA, 0xCC, 0x15),
    "green": (0x4A, 0xDE, 0x80),
    "red": (0xEF, 0x44, 0x44),
}


def generate_circle_png(path: str, rgb: tuple, size: int = 22) -> str:
    """Generate a size x size PNG with a filled circle. Returns the path."""
    cx = cy = size / 2.0
    radius = size / 2.0 - 1  # 1px inset for anti-alias room
    r, g, b = rgb

    rows = []
    for y in range(size):
        row = bytearray()
        row.append(0)  # PNG filter byte
        for x in range(size):
            dx = x + 0.5 - cx
            dy = y + 0.5 - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius - 0.5:
                # Fully inside
                row.extend([r, g, b, 0xFF])
            elif dist <= radius + 0.5:
                # Edge — anti-alias
                alpha = int(max(0, min(1, radius + 0.5 - dist)) * 255)
                row.extend([r, g, b, alpha])
            else:
                row.extend([0, 0, 0, 0])
        rows.append(bytes(row))

    raw_data = b"".join(rows)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    # IHDR: width, height, bit_depth=8, color_type=6 (RGBA)
    ihdr_data = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat_data = zlib.compress(raw_data)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr_data))
        f.write(_chunk(b"IDAT", idat_data))
        f.write(_chunk(b"IEND", b""))

    return path


def generate_all_icons(cache_dir: str) -> dict:
    """Generate all tray state icons. Returns {state_name: path}."""
    os.makedirs(cache_dir, exist_ok=True)
    icons = {}
    for name, rgb in ICON_COLORS.items():
        path = os.path.join(cache_dir, f"tray_{name}.png")
        generate_circle_png(path, rgb)
        icons[name] = path
    logger.info("Generated tray icons in %s", cache_dir)
    return icons
