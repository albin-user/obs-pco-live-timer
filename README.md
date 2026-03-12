# OBS PCO Live Timer

A real-time production timer system for Planning Center Online (PCO) designed for OBS Studio. Pushes countdown timers, service info, and schedule status directly to OBS text sources via WebSocket.

## Features

- **OBS WebSocket text sources** - Push timer data to individual, independently positionable OBS text sources
- **PCO Live integration** - Syncs with producer's "Next" clicks in real-time
- **Multi-service auto-selection** - Monitors multiple service types and auto-selects the active one
- **Service progress tracking** - Shows current item, next item, and service end projections
- **Overrun/ahead tracking** - Know exactly how far behind or ahead of schedule you are
- **Dynamic colors** - Countdown turns red on overtime; service end turns red when behind

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PCO API       │<────│  Python Backend  │────>│  OBS Studio     │
│   (services)    │     │  (PlanManager)   │     │  (WebSocket)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**How it works:**
- Python backend uses IDLE/SCANNING/TRACKING state machine for efficient PCO API polling
- OBS WebSocket pusher sends formatted values to named OBS text sources every 1000ms
- Each text source is independently positionable in OBS — no Browser Source needed

## Quick Start

### 1. Install Dependencies

```bash
# System GTK3 bindings (Xubuntu 24.04)
sudo apt install python3-gi gir1.2-appindicator3-0.1 gir1.2-gtk-3.0

cd obs-pco-live-timer
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `--system-site-packages` flag gives the venv access to the GTK3/AppIndicator3 system bindings installed via apt.

### 2. Run

```bash
.venv/bin/python gui.py
```

A system tray icon appears and the Settings window opens automatically on first run. Enter your PCO credentials, select a folder, configure OBS WebSocket settings, and click Save. The engine starts immediately.

**Get your credentials:** https://api.planningcenteronline.com/oauth/applications

**Get folder IDs:** https://api.planningcenteronline.com/services/v2/folders

### 3. Set Up OBS

1. Open OBS Studio (version 28+)
2. Go to **Tools > WebSocket Server Settings** and enable WebSocket server (port 4455)
3. For each value you want to display, click **+** under Sources and add a **Text (FreeType2)** source named **exactly** as listed below:
   - `PCO Countdown` — countdown timer (green/red)
   - `PCO Current Title` — current item title
   - `PCO Current Description` — current item notes/description
   - `PCO Next Title` — next item title
   - `PCO Next Length` — next item length
   - `PCO Service Type` — service type name (uppercase)
   - `PCO Service Date` — formatted service date and time
   - `PCO Plan Title` — plan/series title
   - `PCO Progress` — e.g. "4 of 12"
   - `PCO Service End` — schedule status (red when behind)
   - `PCO Item Length` — current item's total length
4. Position and resize each source wherever you want in your scene
5. Run `python gui.py` — sources update automatically

You don't need all 11 sources — only create the ones you want. Missing sources are silently skipped.

## Configuration

All configuration is managed through the GUI Settings window (right-click the tray icon > Show > Settings tab). Settings are saved to `config.toml` automatically — no manual editing needed.

## OBS WebSocket Text Sources — Complete Reference

When using OBS WebSocket mode, the app pushes data to **11 named text sources**. Create these as **Text (FreeType2)** on Linux/macOS. Names are **case-sensitive and must match exactly**.

You only need to create the sources you want — the app silently skips any that don't exist.

| # | OBS Source Name (exact) | Data Source (PCO API field) | Example Output | Dynamic Color? |
|---|---|---|---|---|
| 1 | `PCO Countdown` | Current item remaining time | `05:42` or `-01:30` | Green (>=0) / Red (overtime) |
| 2 | `PCO Current Title` | Current item title | `Worship Set` | No (white) |
| 3 | `PCO Current Description` | Item notes, key, description | `Key: G`<br>`BPM: 72` | No (white) |
| 4 | `PCO Item Length` | Current item's scheduled length | `05:00` | No (white) |
| 5 | `PCO Next Title` | Next item title | `Message` | No (white) |
| 6 | `PCO Next Length` | Next item's scheduled length | `(35:00)` | No (white) |
| 7 | `PCO Service Type` | Service type name (uppercased) | `SUNDAY MORNING` | No (white) |
| 8 | `PCO Service Date` | Service date + start time | `Feb 9, 2025 · 9:00 AM` | No (white) |
| 9 | `PCO Plan Title` | Plan title or series title | `"Week 3: Hope"` | No (white) |
| 10 | `PCO Progress` | Item position in plan | `4 of 12` | No (white) |
| 11 | `PCO Service End` | Schedule status + projected end | `Ends 2m behind at 11:47 AM` | Red (behind) / White (ahead or on time) |

### Recommended Minimum Set

If you don't need all 11, start with these 4:

| Source Name | Why |
|---|---|
| `PCO Countdown` | The main timer — most important |
| `PCO Current Title` | What's happening right now |
| `PCO Next Title` | What's coming up next |
| `PCO Service End` | Are we running on time? |

### Font Recommendation

For `PCO Countdown`, use a **monospace font** (SF Mono, Menlo, JetBrains Mono) at large size (72-120pt). This prevents the text from "jumping" as digit widths change.

## Multi-Service Auto-Selection

The system monitors multiple service types and automatically selects the active one.

### How It Works

1. **Configure a folder ID** in config.toml — service types are discovered automatically
2. **System uses a three-state machine** (IDLE → SCANNING → TRACKING) for efficient polling
3. **When TRACKING:** Polls only the tracked plan (1 API call per 2-3s cycle)
4. **Election priority:**
   - **Priority 1**: Plan with the most recent `live_start_at` (handles abandoned sessions)
   - **Priority 2**: Closest to start/end time (smart distance, `filter=future` candidates)

### Scenarios

| Scenario | What Happens |
|----------|--------------|
| Normal Sunday (one service) | Locks to service when producer starts |
| Special event (different type) | Detects live activity, switches automatically |
| Overlapping services | Picks the one being actively controlled |
| Nothing live | Falls back to closest scheduled start |
| Service ends | Unlocks, scans for next service |

## Project Structure

```
obs-pco-live-timer/
├── gui.py                  # Entry point (system tray app)
├── config.toml             # Configuration (auto-managed by GUI)
├── config.example.toml     # Configuration template
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── TROUBLESHOOTING.md      # Detailed debugging guide
├── LINUX_SETUP.md          # Production Linux deployment (Xubuntu + NUC)
├── src/
│   ├── __init__.py
│   ├── formatting.py       # build_timer_response() + format helpers
│   ├── obs_websocket.py    # OBS WebSocket text source pusher
│   ├── manager.py          # Multi-service election & background sync
│   ├── pco_client.py       # PCO API client (with retry/backoff)
│   ├── timing_core.py      # Countdown calculations
│   ├── models.py           # Data models (Service, Item, TimerResult)
│   ├── song_blocks.py      # Song block detection
│   └── gui/
│       ├── __init__.py
│       ├── tray_app.py     # AppIndicator3 tray icon + engine lifecycle
│       ├── main_window.py  # GTK3 settings/status window
│       ├── config_io.py    # Config load/save/validate
│       └── icons.py        # Tray icon + placeholder PNG generation
└── tests/
    ├── test_manager.py             # PlanManager state machine tests
    ├── test_timing_core.py         # Timer calculation tests
    ├── test_pco_client.py          # API client tests
    ├── test_formatting.py          # Formatting/response tests
    ├── test_obs_websocket.py       # OBS pusher tests
    ├── test_song_blocks.py         # Song block detection tests
    ├── test_smart_distance.py      # Smart distance tests
    └── test_smart_distance_transition.py  # Transition timing tests
```

## Dependencies

```
requests>=2.28.0          # HTTP client
python-dateutil>=2.8.2    # Date parsing
tomli>=2.0.0              # TOML config parsing
obsws-python>=1.7.0       # OBS WebSocket client
PyGObject>=3.42.0         # GTK3 bindings
```

System packages (Xubuntu 24.04):
```
python3-gi                    # PyGObject runtime
gir1.2-appindicator3-0.1     # System tray support
gir1.2-gtk-3.0               # GTK3 introspection data
```

## Development

### Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## PCO API Reference

The system uses these PCO Services API v2 endpoints (`https://api.planningcenteronline.com/services/v2`):

| Endpoint | Purpose |
|---|---|
| `GET /folders/{id}/service_types` | Discover service types in configured folder |
| `GET /service_types/{id}/plans?filter=future&per_page=3` | Get upcoming plans |
| `GET /service_types/{id}/plans/{id}/items?per_page=100` | Get plan items (paginated — follow `links.next`) |
| `GET /service_types/{id}/plans/{id}/live` | Get live status (current item + `live_start_at`) |
| `GET /service_types/{id}/plans/{id}/items/{id}/item_notes` | Get item notes for video director |

**Key behaviors:**
- `filter=future` includes plans up to 1 hour in the past
- Items endpoint paginates at 25/page by default — always follow `links.next`
- Live endpoint returns `current_item_time` relationship with `live_start_at` timestamp
- Song lengths can be 0 (first N songs in a block have 0, last holds total time)
- Rate limit: 100 requests per 20 seconds (check `X-PCO-API-Request-Rate-Count` header)

## Troubleshooting

### "Waiting for service..."

**Causes:**
- No service found via `filter=future` (no plans scheduled today or later)
- API credentials invalid
- Folder ID incorrect

**Solutions:**
1. Check `config.toml` credentials
2. Verify folder ID exists
3. Check console output for errors

### Wrong service selected

**Causes:**
- Multiple services live simultaneously
- Service type not in configured folder

**Solutions:**
1. Ensure all service types are in the configured folder
2. The service with most recent "Next" click wins

## License

MIT License

## Credits

Built using:
- Planning Center Online Services API v2
- Python 3.x
- obsws-python
