# Linux Production Setup Guide

## Hardware Target

**Beelink NUC with Intel N100** — connects via HDMI to a TV screen displaying OBS full-screen with PCO timer text sources and RTSP camera feeds. Controlled remotely via VNC.

## Recommended OS: Xubuntu 24.04 LTS

### Why Xubuntu

**x0vncserver requires X11.** Ubuntu 24.04 defaults to Wayland under GNOME, and x0vncserver mirrors the X11 display — it won't work on Wayland. Xfce (which Xubuntu ships) runs on X11 natively in 24.04, so x0vncserver works out of the box.

**Real desktop for remote control.** Since you control OBS over VNC (adjusting scenes, checking camera feeds, troubleshooting), you need panels, system tray, and a taskbar — not a bare window manager.

**Lightweight enough for the N100.** Xfce idles around ~800MB RAM vs GNOME's ~2GB. On an N100 that's also decoding multiple RTSP streams and running OBS compositing, that headroom matters.

**LTS support through April 2029.** Security updates without forced OS upgrades. Critical for a production church system that needs to "just work" every Sunday.

**Intel N100 support.** Full iGPU support via the `i915` kernel driver. Hardware-accelerated video encoding (QSV) available for OBS. The 6.8 HWE kernel has solid N100 support.

### Why Not These Alternatives

| Option | Problem |
|---|---|
| **Ubuntu Desktop (GNOME)** | Defaults to Wayland — x0vncserver won't work. Can force X11 session, but GNOME is heavy (~2GB RAM) and compositor effects waste GPU on a headless TV output |
| **Ubuntu Server + Openbox** | Too minimal for VNC control — no taskbar, no system tray, awkward to operate OBS remotely |
| **Lubuntu (LXQt)** | LXQt is moving toward Wayland; less certain X11 future. Xfce is the safer bet |
| **Ubuntu MATE** | Slightly heavier than Xfce for no real benefit here |
| **Fedora / Nobara** | 13-month lifecycle means forced upgrades ~yearly — bad for production |
| **Debian 12** | Stable but ships older packages; Python 3.11 not 3.12 |
| **Linux Mint** | Adds Cinnamon overhead; no advantage for a dedicated OBS box |

---

## Installation Steps

### Step 1: Install Xubuntu 24.04 LTS

Download from https://xubuntu.org/download/ and install with standard desktop options. Create a user (e.g., `obsuser`).

### Step 2: Install OBS Studio

```bash
sudo add-apt-repository ppa:obsproject/obs-studio
sudo apt update
sudo apt install obs-studio
```

### Step 3: Install GStreamer and the obs-gstreamer Plugin

The [obs-gstreamer plugin](https://github.com/fzwoch/obs-gstreamer) adds a dedicated GStreamer Source type to OBS with significantly lower latency than OBS's built-in Media Source for RTSP feeds (~60ms vs ~1100ms).

#### 3a. Install GStreamer runtime and dev packages

```bash
sudo apt install \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav \
  gstreamer1.0-tools \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev \
  libgstreamer-plugins-bad1.0-dev
```

`plugins-good` includes `rtspsrc` for RTSP streams. The `-dev` packages are needed to build the OBS plugin.

#### 3b. Install build tools

```bash
sudo apt install meson ninja-build git libobs-dev
```

#### 3c. Build and install the obs-gstreamer plugin

```bash
cd /tmp
git clone https://github.com/fzwoch/obs-gstreamer.git
cd obs-gstreamer
meson --buildtype=release build
ninja -C build
```

Install to the user plugin directory:

```bash
mkdir -p ~/.config/obs-studio/plugins/obs-gstreamer/bin/64bit
cp build/obs-gstreamer.so ~/.config/obs-studio/plugins/obs-gstreamer/bin/64bit/
```

#### 3d. Verify the plugin loaded

Launch OBS, then add a source — you should see **GStreamer Source** in the source type list. If it doesn't appear, check that the `.so` file is in the correct path and that GStreamer runtime packages are installed.

### Step 4: Install x0vncserver (TigerVNC)

```bash
sudo apt install tigervnc-scraping-server
```

Set a VNC password:
```bash
vncpasswd
```

### Step 5: Install Python and Project Dependencies

```bash
sudo apt install python3 python3-venv python3-pip

cd /home/obsuser/obs-pco-live-timer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Step 6: Configure the PCO Timer

Create `config.toml` with your PCO API credentials and OBS settings (see `config.example.toml`):
```toml
[pco]
app_id = "your_app_id"
secret = "your_secret"
folder_id = "your_folder_id"
```

Verify `config.toml` has OBS WebSocket enabled:
```toml
[obs]
enabled = true
host = "localhost"
port = 4455
password = ""
update_interval_ms = 1000
```

---

## Auto-Start Configuration

### Enable Auto-Login

Edit `/etc/lightdm/lightdm.conf`:
```ini
[Seat:*]
autologin-user=obsuser
autologin-user-timeout=0
```

### Auto-Start OBS

Create `/home/obsuser/.config/autostart/obs.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=OBS Studio
Exec=obs --studio-mode --startfullscreen
X-GNOME-Autostart-enabled=true
```

### Auto-Start x0vncserver

Create `/home/obsuser/.config/autostart/vnc.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=x0vncserver
Exec=x0vncserver -display :0 -PasswordFile=/home/obsuser/.vnc/passwd
X-GNOME-Autostart-enabled=true
```

### Auto-Start PCO Timer

Create `/home/obsuser/.config/autostart/pco-timer.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=PCO Timer
Exec=/home/obsuser/obs-pco-live-timer/.venv/bin/python /home/obsuser/obs-pco-live-timer/run.py
Path=/home/obsuser/obs-pco-live-timer
X-GNOME-Autostart-enabled=true
```

---

## OBS Fullscreen Projector on Boot

The HDMI-connected TV should show the OBS **canvas output** (camera feeds + timer overlays), not the OBS editing interface. The OBS UI is only needed for setup and is accessed via VNC.

### Set up the projector (one-time)

1. Launch OBS
2. Go to **Settings > General** and check **Save projectors on exit**
3. Right-click the **Program** preview (bottom-right in Studio Mode) > **Fullscreen Projector (Program)** > select the HDMI display
4. The canvas now fills the TV screen
5. Close and reopen OBS — the projector should restore automatically

The projector window is a borderless fullscreen window that shows exactly what the OBS canvas renders. It persists across OBS restarts as long as "Save projectors on exit" is enabled.

### Verify after reboot

After a full reboot, confirm:
- OBS auto-starts (via the `.desktop` autostart entry)
- The fullscreen projector appears on the HDMI/TV display
- VNC shows the OBS editing UI on the desktop for remote control

---

## Production Hardening

These settings ensure the TV output stays clean during services — no popups, no cursor, no screen blanking.

### Disable screen blanking and power management

Xfce's power manager and screensaver will blank the HDMI output after inactivity. Disable both:

```bash
# Disable Xfce screensaver
xfce4-screensaver-command --quit 2>/dev/null
sudo apt remove xfce4-screensaver

# Disable DPMS (display power management) via xset
# Add to autostart so it runs on every login
```

Create `/home/obsuser/.config/autostart/disable-dpms.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Disable DPMS
Exec=sh -c "xset s off && xset s noblank && xset -dpms"
X-GNOME-Autostart-enabled=true
```

Also disable power management in the GUI: **Settings > Power Manager > Display** tab — set "Blank after" and "Put to sleep after" to **Never**.

### Hide cursor after 5 seconds of inactivity

Install `unclutter` to auto-hide the mouse cursor:

```bash
sudo apt install unclutter
```

Create `/home/obsuser/.config/autostart/unclutter.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Hide Cursor
Exec=unclutter -idle 5 -root
X-GNOME-Autostart-enabled=true
```

The cursor reappears instantly when the mouse moves (useful during VNC sessions), and hides again after 5 seconds of inactivity.

### Disable all popup notifications

Permanently enable "Do Not Disturb" mode so no notification bubbles appear over the OBS projector:

```bash
xfconf-query --channel xfce4-notifyd --create --property /do-not-disturb --type bool --set true
```

To make sure this persists, add it to autostart:

Create `/home/obsuser/.config/autostart/disable-notifications.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Disable Notifications
Exec=xfconf-query --channel xfce4-notifyd --property /do-not-disturb --set true
X-GNOME-Autostart-enabled=true
```

### Disable software update prompts — security updates only on boot

Remove the GUI update notifier entirely and configure unattended security-only upgrades:

```bash
# Remove the GUI update notifier (the popup source)
sudo apt remove update-notifier

# Ensure unattended-upgrades is installed
sudo apt install unattended-upgrades

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades
```

Edit `/etc/apt/apt.conf.d/50unattended-upgrades` to confirm only security updates are enabled and automatic reboots are off:

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    // "${distro_id}:${distro_codename}-updates";  // keep commented out
};
Unattended-Upgrade::Automatic-Reboot "false";
```

Edit `/etc/apt/apt.conf.d/20auto-upgrades` to update and install daily:

```
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

This installs security patches silently in the background. No popups, no prompts, no reboots. The system stays patched without any user interaction.

---

## RTSP Camera Feeds in OBS

Use the **GStreamer Source** (from the obs-gstreamer plugin installed in Step 3) for each camera feed. In OBS, click **+** under Sources, select **GStreamer Source**, and enter a pipeline string.

### Why GStreamer Source instead of Media Source

| Method | Typical RTSP Latency |
|---|---|
| OBS built-in Media Source | ~1100ms |
| VLC Video Source | ~400ms |
| **GStreamer Source (obs-gstreamer plugin)** | **~60ms** |

For a live production canvas where the video director needs to follow the action, ~60ms is effectively real-time. ~1100ms makes camera switching feel sluggish.

### Important: Disable clock sync

After adding a GStreamer Source, open its properties and **uncheck "Sync appsinks to clock"**. This is critical for low latency — with it enabled, GStreamer adds a synchronization buffer that defeats the purpose of `latency=0`.

### Hikvision cameras (recommended pipeline)

Hikvision RTSP URL format: `rtsp://user:password@camera-ip:554/Streaming/Channels/N`

| Channel | Stream |
|---|---|
| `/Streaming/Channels/1` | Main stream (full resolution) |
| `/Streaming/Channels/2` | Sub stream (lower resolution, less CPU) |

**Low latency (recommended):**
```
uridecodebin uri=rtsp://user:password@camera-ip:554/Streaming/Channels/1 ! queue ! video.
```

**With small buffer for stability (use if you get frame drops):**
```
uridecodebin uri=rtsp://user:password@camera-ip:554/Streaming/Channels/1 latency=40 ! queue ! video.
```

The `uridecodebin` element auto-detects the codec (H.264/H.265) and handles depay/decode automatically — no need to specify `rtph264depay ! h264parse ! avdec_h264` manually.

### Generic H.264 camera — explicit pipeline

For non-Hikvision cameras where you need more control:

```
rtspsrc location=rtsp://camera-ip:554/stream latency=0 buffer-mode=none ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video.
```

### H.264 over TCP (more reliable on congested networks)

```
rtspsrc location=rtsp://camera-ip:554/stream latency=0 protocols=tcp ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video.
```

### H.265 camera — explicit pipeline

```
rtspsrc location=rtsp://camera-ip:554/stream latency=0 buffer-mode=none ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert ! video.
```

### Pipeline tips

- **Uncheck "Sync appsinks to clock"** in the GStreamer Source properties — most important setting for low latency.
- **`uridecodebin`**: Auto-detects codec. Simplest approach — use this unless you need explicit control.
- **`latency=0`**: Minimizes buffering. Increase to `40` or `100` if you get frame drops.
- **`buffer-mode=none`**: Disables jitter buffer. Use `buffer-mode=auto` if the stream stutters.
- **`protocols=tcp`**: Forces TCP instead of UDP. More reliable but slightly higher latency.
- **`avdec_h264`**: Software decode (works everywhere). On the Intel N100, this is fine for 2-3 cameras at 1080p.
- **Sub stream**: Use `/Streaming/Channels/2` (Hikvision) to reduce CPU load if full resolution isn't needed.

### Testing a pipeline before adding to OBS

```bash
gst-launch-1.0 rtspsrc location=rtsp://camera-ip:554/stream latency=0 ! decodebin ! autovideosink
```

If this shows the camera feed in a window, the pipeline works. Copy the full pipeline into OBS's GStreamer Source.

---

## Boot Sequence

When the NUC powers on, everything starts automatically:

1. **NUC powers on** — auto-login to Xfce desktop
2. **x0vncserver starts** — remote control available via VNC
3. **Screen blanking disabled** — HDMI output stays on permanently
4. **Cursor hidden** — disappears after 5 seconds of inactivity
5. **Notifications suppressed** — no popups over the projector
6. **OBS launches** — fullscreen projector restores on the HDMI/TV display
7. **PCO timer starts** — pushes countdown/titles to OBS text sources via WebSocket
8. **RTSP feeds load in OBS** — camera views visible on the TV
9. **Security updates applied** — silently in the background, no prompts

VNC in from a laptop or phone to adjust anything — switch scenes, check a camera, restart the timer — without touching the NUC.

---

## OBS Text Sources Setup

Before running the PCO timer, create these **Text (FreeType2)** sources in OBS. Names must match exactly:

| OBS Source Name | Content Example | Color |
|---|---|---|
| `PCO Countdown` | `05:42` or `-01:30` | Green (>=0) / Red (overtime) |
| `PCO Current Title` | `Worship Set` | White |
| `PCO Current Description` | `Key: G\nBPM: 72` | White |
| `PCO Next Title` | `Message` | White |
| `PCO Next Length` | `(35:00)` | White |
| `PCO Service Type` | `SUNDAY MORNING` | White |
| `PCO Service Date` | `Feb 9, 2025 · 9:00 AM` | White |
| `PCO Plan Title` | `"Week 3: Hope"` | White |
| `PCO Progress` | `4 of 12` | White |
| `PCO Service End` | `Ends 2m behind at 11:47 AM` | Red (behind) / White (ahead or on time) |
| `PCO Item Length` | `05:00` | White |

You don't need to create all 11 sources. Only create the ones you want to display. The app silently skips any sources that don't exist in OBS.

**Font tip:** Use a monospace font (e.g., JetBrains Mono, Noto Mono) for `PCO Countdown` to prevent text from jumping as digits change width.

---

## Troubleshooting

### x0vncserver Not Connecting
- Verify X11 session: `echo $XDG_SESSION_TYPE` should output `x11`
- Check VNC password file exists: `ls ~/.vnc/passwd`
- Check firewall: `sudo ufw allow 5900`

### OBS WebSocket Not Connecting
- Enable WebSocket in OBS: **Tools > WebSocket Server Settings**
- Verify port matches `config.toml` (default: `4455`)
- See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#11-obs-websocket-not-connecting)

### GStreamer Source Not Appearing in OBS
- Verify the plugin file exists: `ls ~/.config/obs-studio/plugins/obs-gstreamer/bin/64bit/obs-gstreamer.so`
- Verify GStreamer runtime is installed: `gst-launch-1.0 --version`
- Rebuild the plugin if you upgraded OBS (the `.so` must match your OBS version)

### RTSP Feed Not Loading
- Test the pipeline outside OBS first: `gst-launch-1.0 rtspsrc location=rtsp://camera-ip:554/stream latency=0 ! decodebin ! autovideosink`
- Check camera is on the same network
- Verify camera RTSP URL and credentials in the camera's web admin panel
- Try adding `protocols=tcp` to `rtspsrc` if UDP packets are being dropped

### Performance Issues on N100
- Close unnecessary Xfce panels/widgets
- Reduce RTSP stream resolution if CPU is maxed
- Check `htop` for resource usage
- Consider enabling Intel QSV hardware decoding in OBS
