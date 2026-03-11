"""
TOML configuration read/write for the GUI settings panel.
Pure functions — no GTK dependency, fully unit-testable.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "pco": {
        "app_id": "",
        "secret": "",
        "folder_id": "",
    },
    "obs": {
        "enabled": True,
        "host": "localhost",
        "port": 4455,
        "password": "",
        "update_interval_ms": 1000,
    },
    "team": {
        "enabled": True,
        "photo_cache_dir": "",
        "placeholder_photo": "",
        "slots": [],
    },
}


def load_config(path: str) -> Dict[str, Any]:
    """Load config from a TOML file. Returns defaults for missing keys."""
    import copy
    config = copy.deepcopy(_DEFAULT_CONFIG)

    p = Path(path)
    if not p.exists():
        return config

    try:
        import tomli
        with open(p, "rb") as f:
            toml_data = tomli.load(f)
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
        return config

    # Merge loaded values over defaults
    for section in ("pco", "obs", "team"):
        if section in toml_data:
            for key, value in toml_data[section].items():
                if key in config[section]:
                    config[section][key] = value

    return config


def save_config(path: str, config: Dict[str, Any]) -> None:
    """Write config dict to a TOML file with comments matching config.example.toml style."""
    lines = [
        "[pco]",
        f'app_id = "{config["pco"]["app_id"]}"',
        f'secret = "{config["pco"]["secret"]}"',
        "",
        "# Folder ID \u2014 service types are discovered automatically at startup",
        "# Get folder IDs from: https://api.planningcenteronline.com/services/v2/folders",
        f'folder_id = "{config["pco"]["folder_id"]}"',
        "",
        "[obs]",
        f'enabled = {_toml_bool(config["obs"]["enabled"])}',
        f'host = "{config["obs"]["host"]}"',
        f'port = {config["obs"]["port"]}',
        f'password = "{config["obs"]["password"]}"'
        '            # Leave empty if no password set in OBS',
        f'update_interval_ms = {config["obs"]["update_interval_ms"]}'
        " # How often to push updates (milliseconds)",
        "",
        "[team]",
        f'enabled = {_toml_bool(config["team"]["enabled"])}',
        f'photo_cache_dir = "{config["team"]["photo_cache_dir"]}"'
        "           # Default: ~/.cache/obs-pco-live-timer/photos/",
        f'placeholder_photo = "{config["team"]["placeholder_photo"]}"'
        "         # Custom placeholder avatar (auto-generated if empty)",
        _format_slots(config["team"]["slots"]),
    ]

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Return a list of error strings. Empty list means valid."""
    errors = []

    pco = config.get("pco", {})
    app_id = pco.get("app_id", "")
    secret = pco.get("secret", "")
    folder_id = pco.get("folder_id", "")

    if not isinstance(app_id, str) or not app_id.strip():
        errors.append("Missing or empty PCO app_id")
    if not isinstance(secret, str) or not secret.strip():
        errors.append("Missing or empty PCO secret")
    if not isinstance(folder_id, str) or not folder_id.strip():
        errors.append("Missing or empty PCO folder_id")

    obs = config.get("obs", {})
    obs_port = obs.get("port", 4455)
    if not isinstance(obs_port, int) or obs_port < 1 or obs_port > 65535:
        errors.append(f"Invalid OBS port: {obs_port} (must be 1-65535)")

    return errors


def _toml_bool(value: Any) -> str:
    return "true" if value else "false"


def _format_slots(slots: List[str]) -> str:
    if not slots:
        return "slots = []"
    items = ",\n".join(f'    "{s}"' for s in slots)
    return f"slots = [\n{items},\n]"
