# ClearSignage

Run one or more ClearSignage screens inside Home Assistant. Each screen is a complete,
independent signage player — its own content library, its own playlists, its own PIN —
and is managed on itself, the same way a Raspberry Pi appliance is.

## Installing

1. Settings → Add-ons → Add-on store → ⋮ → **Repositories**, and add this repository's URL.
2. Install **ClearSignage** and start it.
3. Open it from the sidebar. The first screen is added from that page.

## Configuration

| Option | Default | What it is |
|---|---|---|
| `host_ip` | *(blank)* | The address other screens use to reach this machine. Blank means the address on the default route, which is right on almost every home network. |
| `vhost_port` | `80` | The port each screen's `.local` name answers on. |
| `log_level` | `info` | |

**`host_ip` is worth a second look if peer sync does not work.** This machine may have
several addresses — a Docker bridge, a VPN, a second NIC — and screens elsewhere on the
network need the one they can actually reach. The app logs the address it chose at start-up.

**`vhost_port` is the one thing here likely to collide.** Port 80 is the default so a
typed URL has no port in it. If another add-on already uses it, change this — the screens
and the Home Assistant panel are unaffected either way, only the friendly names move.

## Reaching a screen

Three ways, and they are not equivalent:

- **From the Home Assistant sidebar.** Home Assistant has already signed you in, so this
  is the path that can change what is on a screen. It also works from outside your home
  through Nabu Casa, with no port forwarding.
- **`http://<name>.local`** — e.g. `http://lobby.local` — from a browser on the same
  network. Convenient for a wall tablet. You will be asked for the screen's PIN.
- **`http://<host>:810N`** — how *other screens* find and sync with this one. Not meant
  for people.

## What is different from a Raspberry Pi

This runs the same ClearSignage as an appliance, so content, playlists, schedules,
designs, apps and peer sync all behave identically. What is absent is absent because the
capability genuinely is not here, not because it was left out:

- **No display output.** A Pi drives an HDMI screen. Here the *browser* is the screen —
  put a screen's display on a dashboard, or open it full-screen on a wall tablet.
- **No Wi-Fi, network or reboot settings.** Those belong to Home Assistant and the
  machine it runs on. Restart the app from Home Assistant instead.
- **No software updates from inside a screen.** Home Assistant updates this app; an
  in-place update would be thrown away the next time it restarts.
- **No "sold out" / booking taps from the screen itself.** On an appliance those are
  authorised by *standing at the panel*, which a hosted screen has no way to check. Here
  they are authorised by your Home Assistant login instead — so use the sidebar, not the
  `.local` address, when you want to change something.

## Putting a screen on a dashboard

Add a **Webpage** card and point it at that screen's display. Use `?playlist_only=1` —
without it a composed screen would try to render itself inside itself:

```yaml
type: iframe
url: /api/hassio_ingress/<token>/i/1/display?playlist_only=1
aspect_ratio: 16x9
```

The ingress token changes; the reliable way to get the URL is to open the screen from the
sidebar and copy it from the address bar, then append `display?playlist_only=1`.

Use that ingress path rather than the screen's `.local` name. A browser will not embed
`http://` content in a page served over `https://`, so a card pointing at
`http://lobby.local` shows an empty box on any Home Assistant reached over TLS — which
includes every Nabu Casa install. The `.local` name is for typing into an address bar.

For a whole screen on the wall, put one card in a **Panel** view (`type: panel` — a
Sections view, the default, is not what you want here):

```yaml
views:
  - title: Lobby
    type: panel
    cards:
      - type: iframe
        url: /api/hassio_ingress/<token>/i/1/display?playlist_only=1
        aspect_ratio: 16x9
        hide_background: true
```

*Checked against Home Assistant 2026.7.*

## Your content

Everything lives in the app's `/data` — one directory per screen. Removing a screen from
the fleet page leaves its content on disk, so removing one by mistake is recoverable;
uninstalling the app is not.
