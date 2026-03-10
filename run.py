#!/usr/bin/env python3
"""
PCO Live Timer - Entry Point

Starts the PCO Live Timer and pushes data to OBS via WebSocket.
Configure credentials in config.toml (see config.example.toml).
"""
import logging
import os
import signal
import sys
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)


def load_config():
    """
    Load configuration from config.toml or environment variables.
    """
    config_path = Path(__file__).parent / "config.toml"

    config = {
        "pco": {
            "app_id": None,
            "secret": None,
            "folder_id": None
        },
        "obs": {
            "enabled": False,
            "host": "localhost",
            "port": 4455,
            "password": "",
            "update_interval_ms": 1000
        }
    }

    # Try config.toml first
    if config_path.exists():
        try:
            import tomli
            with open(config_path, "rb") as f:
                toml_config = tomli.load(f)

            # PCO settings
            pco = toml_config.get("pco", {})
            config["pco"]["app_id"] = pco.get("app_id")
            config["pco"]["secret"] = pco.get("secret")
            config["pco"]["folder_id"] = pco.get("folder_id")

            # OBS WebSocket settings
            obs = toml_config.get("obs", {})
            config["obs"]["enabled"] = obs.get("enabled", False)
            config["obs"]["host"] = obs.get("host", "localhost")
            config["obs"]["port"] = obs.get("port", 4455)
            config["obs"]["password"] = obs.get("password", "")
            config["obs"]["update_interval_ms"] = obs.get("update_interval_ms", 1000)

            # Team settings
            team = toml_config.get("team", {})
            config["team"] = {
                "enabled": team.get("enabled", True),
                "photo_cache_dir": team.get("photo_cache_dir", ""),
                "placeholder_photo": team.get("placeholder_photo", ""),
                "slots": team.get("slots", []),
            }

            logger.info("Loaded config from %s", config_path)
            return config
        except ImportError:
            logger.warning("tomli not installed, trying environment variables")
        except Exception as e:
            logger.error("Error loading config.toml: %s", e)

    # Try environment variables
    import os
    config["pco"]["app_id"] = os.environ.get("PCO_APP_ID")
    config["pco"]["secret"] = os.environ.get("PCO_SECRET")
    config["pco"]["folder_id"] = os.environ.get("PCO_FOLDER_ID")

    if config["pco"]["app_id"]:
        logger.info("Loaded config from environment variables")

    return config


def validate_config(config):
    """Validate configuration and print warnings."""
    errors = []

    app_id = config["pco"]["app_id"]
    secret = config["pco"]["secret"]
    folder_id = config["pco"]["folder_id"]

    if not isinstance(app_id, str) or not app_id.strip():
        errors.append("Missing or empty PCO app_id")
    if not isinstance(secret, str) or not secret.strip():
        errors.append("Missing or empty PCO secret")
    if not isinstance(folder_id, str) or not folder_id.strip():
        errors.append("Missing or empty PCO folder_id")

    obs_port = config["obs"].get("port", 4455)
    if not isinstance(obs_port, int) or obs_port < 1 or obs_port > 65535:
        errors.append(f"Invalid OBS port: {obs_port} (must be 1-65535)")

    if errors:
        logger.error("Configuration errors:")
        for err in errors:
            logger.error("  - %s", err)
        logger.error("Please update config.toml (see config.example.toml)")
        return False

    return True


def _generate_placeholder_png(path: str):
    """Generate a 128x128 dark gray (#2d2d2d) PNG using only stdlib."""
    import struct
    import zlib

    width, height = 128, 128
    r, g, b = 0x2D, 0x2D, 0x2D

    # Build raw image data: each row has a filter byte (0) + RGB pixels
    raw_row = b"\x00" + bytes([r, g, b]) * width
    raw_data = raw_row * height

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat_data = zlib.compress(raw_data)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr_data))
        f.write(_chunk(b"IDAT", idat_data))
        f.write(_chunk(b"IEND", b""))

    logger.info("Generated placeholder avatar: %s", path)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("=" * 50)
    logger.info("  PCO Live Timer for OBS")
    logger.info("=" * 50)

    # Load configuration
    config = load_config()

    if not validate_config(config):
        sys.exit(1)

    # Import after config loaded to catch import errors early
    from src.pco_client import PCOClient
    from src.manager import PlanManager

    folder_id = config["pco"]["folder_id"]

    # Create PCO client
    client = PCOClient(
        app_id=config["pco"]["app_id"],
        secret=config["pco"]["secret"],
    )

    # Discover service types from folder
    logger.info("Discovering service types from folder %s...", folder_id)
    try:
        service_types = client.get_folder_service_types(folder_id)
    except Exception as e:
        logger.error("Failed to fetch service types from folder %s: %s", folder_id, e)
        sys.exit(1)

    if not service_types:
        logger.error("No service types found in folder %s", folder_id)
        sys.exit(1)

    service_type_ids = [st['id'] for st in service_types]
    logger.info("Found %d service types:", len(service_types))
    for st in service_types:
        logger.info("  - %s (ID: %s)", st['name'], st['id'])

    # Team config
    team_config = config.get("team", {})
    team_cache_dir = team_config.get("photo_cache_dir", "") or os.path.join(
        os.path.expanduser("~"), ".cache", "obs-pco-live-timer", "photos"
    )

    # Resolve placeholder photo path
    placeholder_photo_path = team_config.get("placeholder_photo", "")
    if not placeholder_photo_path and team_config.get("enabled", True):
        os.makedirs(team_cache_dir, exist_ok=True)
        placeholder_photo_path = os.path.join(team_cache_dir, "placeholder_avatar.png")
        if not os.path.exists(placeholder_photo_path):
            _generate_placeholder_png(placeholder_photo_path)

    # Create plan manager (starts background sync)
    manager = PlanManager(
        client=client,
        target_service_type_ids=service_type_ids,
        start_thread=True,
        team_enabled=team_config.get("enabled", True),
        team_cache_dir=team_cache_dir,
        team_slots=team_config.get("slots", []),
        team_placeholder_photo=placeholder_photo_path,
    )

    # Start OBS WebSocket pusher if enabled
    obs_pusher = None
    obs_config = config["obs"]
    if obs_config["enabled"]:
        from src.obs_websocket import OBSTextPusher
        obs_pusher = OBSTextPusher(
            manager=manager,
            host=obs_config["host"],
            port=obs_config["port"],
            password=obs_config["password"],
            update_interval_ms=obs_config["update_interval_ms"],
        )
        obs_pusher.start()

    logger.info("=" * 50)
    logger.info("  PCO Live Timer running")
    logger.info("=" * 50)
    if obs_pusher:
        logger.info("OBS WebSocket: pushing to %s:%s every %dms",
                     obs_config['host'], obs_config['port'], obs_config['update_interval_ms'])
    else:
        logger.info("OBS WebSocket: disabled (set obs.enabled = true in config.toml)")
    if team_config.get("enabled", True):
        logger.info("Team members: enabled (photos: %s)", team_cache_dir)
    logger.info("Press Ctrl+C to stop")

    # Shutdown handler for SIGTERM (systemd) and KeyboardInterrupt (Ctrl+C)
    stop_event = threading.Event()

    def _shutdown(signum=None, frame=None):
        logger.info("Shutting down...")
        if obs_pusher:
            obs_pusher.stop()
        manager.stop()
        logger.info("Shutdown complete")
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
