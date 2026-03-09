# Troubleshooting Guide

## Common Issues and Solutions

### 1. Current Live Item Not Showing

**Symptom**: Timer shows "WAITING FOR LIVE START" even though producer clicked Next.

**Root Causes**:

#### A. Live Data Checked After Scheduled Time
```python
# BAD: Checks scheduled time first
if service.start_time < now:
    use_scheduled_time()  # This runs even during rehearsal!
if service.live_item_id:
    use_live_data()       # Never reached!
```

**Solution**: Check live data FIRST
```python
# GOOD: Check live data first
if service.live_item_id:
    use_live_data()       # Runs during rehearsal
if service.start_time < now:
    use_scheduled_time()  # Fallback
```

**Location**: [timing_core.py:52-127](src/timing_core.py#L52-L127)

#### B. Silent Exception Handling
```python
# BAD: Hides all errors
try:
    live_data = client.get_live_status(...)
except:
    pass  # Error lost!
```

**Solution**: Log exceptions
```python
# GOOD: Shows what went wrong
try:
    live_data = client.get_live_status(...)
except Exception as e:
    print(f"Failed to get live status: {e}")
```

**Location**: [manager.py:120-123](src/manager.py#L120-L123)

### 2. Missing Items (Pagination Issue)

**Symptom**: Only showing 25 items when service has 32.

**Root Cause**: PCO API paginates results (default 25 per page).

**Diagnosis**:
```python
# Check if you're handling pagination
data = self._get(endpoint)
items = data['data']  # Only first 25!
# Missing: Check for data['links']['next']
```

**Solution**: Implement pagination loop
```python
endpoint = f"/service_types/{type_id}/plans/{plan_id}/items"

while endpoint:
    data = self._get(endpoint)
    items.extend(data['data'])

    next_link = data.get('links', {}).get('next')
    if next_link:
        endpoint = next_link.replace(self.base_url, '')
    else:
        endpoint = None  # All pages fetched
```

**Location**: [pco_client.py:124-162](src/pco_client.py#L124-L162)

### 3. Wrong Service Selected

**Symptom**: Shows future service instead of currently running service.

**Root Cause**: Using simple distance instead of smart distance.

**Bad Implementation**:
```python
# Always uses start time
def simple_distance(plan):
    return abs((plan.start_time - now).total_seconds())

# At 11:30:
# Service A (started 10:00): distance = 1.5h
# Service B (starts 12:30): distance = 1.0h
# Selects B ← WRONG!
```

**Solution**: Use contextual distance
```python
def smart_distance(plan):
    if plan.start_time < now:
        # Running: use END time
        end_time = plan.start_time + timedelta(seconds=plan.total_length)
        return abs((end_time - now).total_seconds())
    else:
        # Future: use START time
        return abs((plan.start_time - now).total_seconds())

# At 11:30:
# Service A: distance to 12:00 end = 0.5h ✓ SELECTED
# Service B: distance to 12:30 start = 1.0h
```

**Location**: [manager.py:131-141](src/manager.py#L131-L141)

### 4. Unicode/Encoding Errors

**Symptom**:
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'
```

**Root Cause**: Windows console doesn't support Unicode characters.

**Characters That Fail**:
- ✓ (checkmark)
- ✗ (cross)
- • (bullet)
- → (arrow)
- 📋 (clipboard)

**Solution**: Use ASCII equivalents
```python
# BAD
print("✓ Success")

# GOOD
print("[OK] Success")
```

**Quick Fix**:
```python
# Set UTF-8 encoding for Python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

### 5. Rate Limit Errors

**Symptom**:
```
HTTPError: 429 Too Many Requests
```

**Root Cause**: Exceeding PCO API limits (100 requests per 20 seconds).

**Check Current Usage**:
```python
response = requests.get(url, auth=(app_id, secret))
print(response.headers.get('X-PCO-API-Request-Rate-Count'))
print(response.headers.get('X-PCO-API-Request-Rate-Limit'))
```

**Solutions**:

1. The state machine already minimizes calls (1 `/live` call per cycle in TRACKING state). If still hitting limits, increase the tracking interval:
```python
# In manager.py _get_dynamic_interval()
if self._state == "tracking":
    return 5  # Was 3
```

2. Reduce service type count:
```python
# Monitor fewer services
TARGET_IDS = ["393738"]  # Just one instead of 4
```

3. Add exponential backoff:
```python
if response.status_code == 429:
    retry_after = int(response.headers.get('Retry-After', 5))
    time.sleep(retry_after)
```

### 6. Frozen/Choppy Countdown

**Symptom**: Timer freezes or updates slowly.

**Root Cause**: Network calls blocking UI thread.

**Bad Architecture**:
```python
def update_timer(self):
    # This blocks for 200-500ms!
    result = self.manager.sync()  # Network call
    self.update_display(result)
    self.root.after(100, self.update_timer)
```

**Solution**: Use background thread
```python
# UI thread (fast)
def update_timer(self):
    result = self.manager.tick()  # Local cache read
    self.update_display(result)
    self.root.after(100, self.update_timer)

# Background thread (slow)
def _background_sync_loop(self):
    while not stopped:
        self._perform_sync(now)  # Network calls
        time.sleep(interval)
```

### 7. Song Block Not Showing

**Symptom**: Only current song shows, not the full block.

**Diagnosis**:
```python
# Check if current item is a song
if item.type != 'song':
    # Won't detect block for non-songs

# Check if there are consecutive songs
if all songs have length > 0:
    # Block detection expects some with 0 length
```

**Solution**: Verify song block exists
```python
block = get_song_block_for_item(service, current_item)
if len(block) > 1:
    display_song_block(block)
else:
    display_single_item(current_item)
```

**Common Patterns**:
```
Block (time-holder pattern — at most 1 song has length > 0):
- Song A (0m)
- Song B (0m)
- Song C (18m) ← Block detected, Song C holds total time

NOT a block (individually timed — 2+ songs have length > 0):
- Song A (5m)
- Song B (6m)
- Song C (7m) ← Each song timed separately, not a grouped set

Non-block (non-song breaks continuity):
- Song A (5m)
- Prayer (2m)  ← Non-song breaks block
- Song B (4m)  ← Separate item
```

### 8. Credentials Not Loading

**Symptom**:
```
Error: Credentials not found.
```

**Check**:
1. File exists:
```bash
ls config.toml
```

2. Format correct (TOML):
```toml
[pco]
app_id = "your_app_id"
secret = "your_secret"
folder_id = "your_folder_id"
```

3. File in correct location:
```
obs-pco-live-timer/
  config.toml  <- Here
  src/
  tests/
```

4. Use `config.example.toml` as a template:
```bash
cp config.example.toml config.toml
```

### 9. Authentication Errors

**Symptom**:
```
HTTPError: 401 Unauthorized
```

**Solutions**:

1. Verify credentials:
   - Go to https://api.planningcenteronline.com/oauth/applications
   - Regenerate token if needed

2. Check authorization header:
```python
import base64
auth_string = f"{app_id}:{secret}"
encoded = base64.b64encode(auth_string.encode()).decode()
print(f"Authorization: Basic {encoded}")
```

3. Test with curl:
```bash
curl -u "app_id:secret" https://api.planningcenteronline.com/services/v2/service_types
```

### 10. Time Calculations Wrong

**Symptom**: Countdown doesn't match expected time.

**Common Issues**:

1. **Timezone problems**:
```python
# BAD: No timezone
now = datetime.now()  # Naive datetime

# GOOD: Use UTC
now = datetime.now(timezone.utc)
```

2. **Cumulative overrun not tracked**:
```python
# BAD: Only current item
countdown = item.length - elapsed

# GOOD: Account for previous overruns
cumulative_overrun = sum_previous_overruns()
countdown = item.length - elapsed + cumulative_overrun
```

3. **Start time offset not calculated**:
```python
# BAD: All items start at service start
time_into_service = elapsed

# GOOD: Each item has offset
item.start_time_offset = sum(prev.length for prev in previous_items)
time_into_item = elapsed - item.start_time_offset
```

### 11. OBS WebSocket Not Connecting

**Symptom**:
```
[OBS WebSocket] Connection failed, retrying in 5s...
```

**Root Causes and Solutions**:

1. **OBS not running**: Start OBS Studio first
2. **WebSocket not enabled**: In OBS, go to **Tools > WebSocket Server Settings** and check **Enable WebSocket server**
3. **Wrong port**: Verify the port in OBS matches `config.toml` (default: `4455`)
4. **Password mismatch**: If OBS has a WebSocket password set, add it to `config.toml`
5. **obs.enabled = false**: Check `config.toml` has `enabled = true` under `[obs]`

**Verification**:
```bash
# Test WebSocket connectivity
python -c "import obsws_python as obs; ws = obs.ReqClient(host='localhost', port=4455); print('Connected!')"
```

### 12. OBS Text Source Not Updating

**Symptom**: Some or all text sources stay blank or stale.

**Root Causes**:

1. **Source name mismatch**: Names must match exactly (case-sensitive):
   - Correct: `PCO Countdown`
   - Wrong: `pco countdown`, `PCO_Countdown`, `PCO countdown`

2. **Wrong source type**: Must be **Text (FreeType2)** on macOS/Linux or **Text (GDI+)** on Windows. Other text sources may not support the `text` property via WebSocket.

3. **Source in different scene**: The source must exist in the currently active scene (or be in a scene that's visible).

**Diagnosis**:
```python
# Enable debug logging to see which sources are being skipped
import logging
logging.basicConfig(level=logging.INFO)
# You'll see messages like: "Source 'PCO Countdown' not found in OBS, skipping"
```

### 13. OBS Countdown Colors Not Changing

**Symptom**: Timer text updates but stays white/default color.

**Root Cause**: The OBS text source may not support the `color1`/`color2` properties, or the source may have custom CSS overriding colors.

**Solutions**:
1. Ensure you're using **Text (FreeType2)** (macOS/Linux) or **Text (GDI+)** (Windows)
2. In the text source properties, set the color to white — the app will override it via WebSocket
3. Check that `color1` and `color2` are the correct property names for your OBS version

## Debugging Techniques

### 1. Enable Detailed Logging

```python
# At top of manager.py
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# In sync loop
logger.debug(f"Found {len(candidates)} candidates")
logger.debug(f"Selected: {best_plan.plan_title if best_plan else 'None'}")
```

### 2. Print API Responses

```python
# In pco_client.py
def _get(self, endpoint):
    response = self.session.get(url)
    data = response.json()

    # Temporary debug
    import json
    print(json.dumps(data, indent=2))

    return data
```

### 3. Test Components Individually

```python
# Test timing without network
from src.timing_core import calculate_timers
from src.models import Service, Item

service = create_test_service()
result = calculate_timers(service, now)
print(result)
```

### 4. Mock API Responses

```python
# For testing without hitting API
class MockPCOClient:
    def get_next_plans_for_types(self, type_ids):
        return [create_mock_service()]

    def get_live_status(self, type_id, plan_id):
        return {'data': {...}}
```

### 5. Monitor Network Traffic

```python
# Log all requests
import requests
import logging

logging.basicConfig()
logging.getLogger('urllib3').setLevel(logging.DEBUG)
```

## Getting Help

1. **Check API Status**: https://status.planningcenteronline.com/
2. **API Docs**: https://developer.planning.center/docs/#/apps/services
3. **Community**: https://pco.church/
4. **GitHub Issues**: File bugs with minimal reproduction

## Error Message Reference

| Error | Meaning | Solution |
|-------|---------|----------|
| 401 Unauthorized | Bad credentials | Check App ID and Secret |
| 403 Forbidden | Missing scopes | Add 'services' scope |
| 404 Not Found | Invalid ID | Verify service type/plan ID |
| 429 Too Many Requests | Rate limited | Increase poll interval |
| 500 Internal Server | PCO issue | Check status page, retry |
| TypeError: NoneType | Missing data | Add None checks |
| KeyError | Missing key | Use .get() instead of [] |
| UnicodeEncodeError | Console encoding | Use ASCII or set UTF-8 |
| OBS Connection failed | OBS not running / WebSocket off | Start OBS, enable WebSocket |
| Source not found (600) | OBS text source name mismatch | Create source with exact name |
| ConnectionRefusedError | OBS WebSocket port wrong | Check port in config.toml |
