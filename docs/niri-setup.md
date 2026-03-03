# Niri + DMS Setup Log

## Environment
- **OS**: Ubuntu 25.10 (Questing Quokka)
- **Display Manager**: SDDM
- **Date**: 2026-03-02
- **Goal**: Maximum productivity scrollable-tiling Wayland desktop

## Installed Versions
- **Niri**: 25.11 (via ppa:avengemedia/danklinux)
- **DMS**: 1.4.3 (via ppa:avengemedia/dms)
- **xwayland-satellite**: 0.8.1 (X11 app compatibility)
- **Terminal**: Alacritty (pre-installed)
- **Portals**: xdg-desktop-portal-gnome + gtk
- **Audio**: PipeWire
- **Polkit**: polkit-kde-agent-1

## Decision Log

### Why Niri?
- Scrollable tiling: infinite horizontal workspace, no cramped splits
- Live config reload (edit config.kdl, changes apply instantly)
- Built-in overview (Mod+D or Mod+Tab) for workspace navigation
- Wayland-native, modern, actively developed

### Why DMS first?
- Single integrated shell replaces ~12 separate tools
- Optimized specifically for Niri
- Material 3 dynamic theming from wallpaper
- Built-in: bar, launcher, notifications, lock screen, clipboard, media controls
- Available via PPA for Ubuntu 25.10

### Fallback: Modular Stack
If DMS doesn't click, swap to:
- Bar: Waybar
- Launcher: Fuzzel
- Notifications: Mako
- Lock: Swaylock
- Clipboard: cliphist + wl-clipboard
- Idle: swayidle

---

## Installation Steps (Completed 2026-03-02)

### Step 1: Add PPAs
```bash
sudo add-apt-repository ppa:avengemedia/danklinux
sudo add-apt-repository ppa:avengemedia/dms
sudo apt update
```

### Step 2: Install packages
```bash
sudo apt install niri dms
```

### Step 3: Post-install setup
```bash
dms setup                          # Generated niri config at ~/.config/niri/config.kdl
systemctl --user enable dms        # DMS autostart enabled
```

### Step 4: Login
- Log out of current session
- Select "Niri" in SDDM session picker
- Log in

---

## Config File Structure

```
~/.config/niri/
  config.kdl              # Main config (our customizations go here)
  dms/
    binds.kdl             # DMS-managed keybindings
    colors.kdl            # Auto-generated theme colors (from wallpaper)
    layout.kdl            # Auto-generated layout (gaps, borders, rounding)
    alttab.kdl            # Alt-tab highlight styling
    cursor.kdl            # Cursor config (empty)
    outputs.kdl           # Monitor config (empty, auto-detected)
    windowrules.kdl       # DMS window rules (empty)
```

**Important**: Files in `dms/` are auto-generated. Put custom overrides in `config.kdl` AFTER the `include` lines at the bottom.

---

## Key Bindings Quick Reference (DMS defaults)

### Essential
| Bind | Action |
|------|--------|
| Mod+Space | DMS App Launcher (Spotlight) |
| Mod+T | Terminal (Alacritty) |
| Mod+D / Mod+Tab | Overview (all workspaces) |
| Mod+Q | Close window |
| Mod+F | Maximize column |
| Mod+Shift+F | Fullscreen |
| Mod+Shift+E | Quit Niri |
| Mod+Alt+L | Lock screen |

### Navigation
| Bind | Action |
|------|--------|
| Mod+H/J/K/L | Focus left/down/up/right (vim-style) |
| Mod+Arrow keys | Same with arrows |
| Mod+U/I | Workspace down/up |
| Mod+1-9 | Jump to workspace N |

### Window Management
| Bind | Action |
|------|--------|
| Mod+Shift+H/J/K/L | Move window left/down/up/right |
| Mod+Shift+1-9 | Move window to workspace N |
| Mod+R | Cycle preset widths (1/3, 1/2, 2/3) |
| Mod+Minus/Equal | Shrink/grow column 10% |
| Mod+C | Center column |
| Mod+W | Tab windows in column |
| Mod+Shift+T | Toggle floating |
| Mod+[ / Mod+] | Consume/expel window from column |

### DMS Features
| Bind | Action |
|------|--------|
| Mod+V | Clipboard manager |
| Mod+N | Notification center |
| Mod+Shift+N | Notepad |
| Mod+M / Ctrl+Alt+Del | Task manager |
| Mod+Comma | DMS Settings |
| Mod+Y | Wallpaper browser |
| Super+X | Power menu |
| Ctrl+Shift+R | Rename workspace |

---

## Configuration Changes

(Will be populated as we customize)

---

## Issues & Fixes

(Will be populated as we encounter them)

---

## Pivot Notes

### Remove DMS, go modular
```bash
systemctl --user disable dms
sudo apt remove dms
sudo apt install waybar fuzzel mako swaylock swayidle cliphist wl-clipboard
```
Then edit `~/.config/niri/config.kdl`:
- Remove all `include "dms/*.kdl"` lines
- Add `spawn-at-startup "waybar"` etc.
- Add keybinds for fuzzel, mako, swaylock manually

### Remove everything
```bash
sudo apt remove niri dms
sudo add-apt-repository --remove ppa:avengemedia/danklinux
sudo add-apt-repository --remove ppa:avengemedia/dms
rm -rf ~/.config/niri
```
