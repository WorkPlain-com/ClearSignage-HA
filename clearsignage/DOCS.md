# ClearSignage

Run one or more ClearSignage screens inside Home Assistant. Each screen is a complete,
independent signage player — its own content library, its own playlists, its own PIN —
and is managed on itself, the same way a Raspberry Pi appliance is.

This machine is also your **venue**: the one place that holds a connection to something
like your till, reads the prices from it, and sends them out to the screens that show
them. Screens never hold that connection themselves — they receive prices, never access.
It is also where this building's **occupancy** is counted and kept.

## Installing

1. **Add the registry credentials.** This app is a prebuilt image in a private registry,
   so Home Assistant needs a login before it can pull it. Add `ghcr.io` with the username
   and token you were given, under the Docker registries settings in the app store's ⋮
   menu. Do this *first*: without it the install fails at the pull with an
   authentication error, which reads like a broken repository rather than a missing
   credential.
2. Settings → Apps → Install app → ⋮ → **Repositories**, and add this repository's URL.
3. Install **ClearSignage** and start it.
4. Open it from the sidebar. The first screen is added from that page.

The credential is read access only, and it is stored by Home Assistant rather than in
this repository — so rotating it is a change on each install and nothing here.

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
- **`http://<host>:810N`** — how *other screens* find and sync with this one, and the
  address to put a screen's `/display` on a dashboard (see below). Not somewhere to go
  looking for settings.

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

Add a **Webpage** card and point it at that screen's display. The fleet page shows each
screen's address ready to paste — open ClearSignage from the sidebar and copy it from the
"Put on a dashboard" column:

```yaml
type: iframe
url: http://192.168.1.50:8101/display?playlist_only=1
aspect_ratio: 16x9
```

Two things about that URL. `?playlist_only=1`, because without it a composed screen tries
to render itself inside itself. And `8101` is screen 1 — screen 2 is `8102`, and so on.

**Do not use the address in your own address bar.** That one is an ingress path, and an
ingress path belongs to *your Home Assistant session* rather than to the screen. Anyone
else who opens the dashboard — most importantly a wall tablet signed in as a different
user — gets **401** from it, which looks exactly like a broken screen. The display
address above needs no sign-in at all: a screen's display carries no controls and no
secrets, which is what makes it safe to hand out.

### If your Home Assistant is reached over HTTPS

A browser will not embed `http://` content in a page served over `https://`, so on a Nabu
Casa install — or any Home Assistant behind TLS — the card above shows an empty box. Use
the ingress path there instead, and accept that it only works for the person signed in:

```yaml
type: iframe
url: /api/hassio_ingress/<token>/i/1/display?playlist_only=1
aspect_ratio: 16x9
```

The token changes; get it by opening the screen from the sidebar, copying the URL from the
address bar, and appending `display?playlist_only=1`.

For a whole screen on the wall, put one card in a **Panel** view (`type: panel` — a
Sections view, the default, is not what you want here):

```yaml
views:
  - title: Lobby
    type: panel
    cards:
      - type: iframe
        url: http://192.168.1.50:8101/display?playlist_only=1
        aspect_ratio: 16x9
        hide_background: true
```

*Checked against Home Assistant 2026.7.*

## Your till, and other live data

Open **Till** from the Screens page to connect your point-of-sale account. You sign in to
the provider once, in your own browser; what comes back is stored here and refreshed
automatically, and your screens are sent the prices only.

**Your Home Assistant backups will contain that connection.** A backup includes this app's
data, and many people sync backups to cloud storage — so treat one the way you would treat
the password to the account itself. If a backup is ever shared or exposed, disconnect the
till on the Till page: that revokes what the backup contains.

You can also add screens that are not run by this machine. **Other screens** on the Screens
page finds ClearSignage screens elsewhere on your network and joins them to this venue, so
they receive its prices too. Joining is always explicit — nothing is enrolled by being
discovered — and letting one go afterwards affects only that screen.

## Counting how busy a space is

Open **Occupancy** from the Screens page. Add a space — a room you think of as one place —
say how many it holds, and add a camera at each door people come in through. Adding a camera
gives you a code to paste into it once; after that the camera counts on its own and this
machine keeps the totals and the hour-by-hour history.

**The camera sends numbers, never pictures.** No image is stored anywhere, there is no face
recognition and nothing follows anybody between cameras. The only picture that ever leaves a
camera is the single frame you drag the doorway line across while aiming it, and that is
shown to you and then dropped.

Two things worth knowing before you start:

- **One camera watches one doorway.** Two cameras that can both see the same door will count
  everybody through it twice, and nothing here can tell that apart from a genuinely busy pair
  of doors.
- **Counting drifts.** People walk through in pairs and deliveries block the view. A space
  can start counting again each night, and you can always set the number to what you have
  just counted by hand.

Any screen this venue has joined can show it: add a **How busy it is** board and pick the
space. Every number on that board is optional, so it can be one large figure in a window or
the lot on a back-office screen.

## Your content

Everything lives in the app's `/data` — one directory per screen, plus this venue's own
connections. Removing a screen from the fleet page leaves its content on disk, so removing
one by mistake is recoverable; uninstalling the app is not.
