# ClearSignage — Home Assistant app

Private Home Assistant app repository for ClearSignage (Epic 119 Pass 4).

**Packaging only.** No product logic lives here. The supervisor that runs the screens is
ClearSignage's own `hosted/` package, and it has its own test suite; this repo is the
manifest, the image, and the start-up seam between them. That split is deliberate — the
epic's Pass 4 says this repo "never grows a `config.yaml` it cannot test", and the
converse holds too: ClearSignage never grows a Dockerfile it cannot run.

## Layout

```
repository.yaml              Home Assistant sees this as an app repository
clearsignage/
  config.yaml                the app manifest
  build.yaml                 base image per architecture
  Dockerfile                 the image
  DOCS.md                    what an operator reads in the app's Documentation tab
  translations/en.yaml       option labels and help text
  rootfs/etc/services.d/…    s6 service: run + finish
scripts/
  fetch-source.sh            pin and fetch ClearSignage into the build context
  build.sh                   fetch + docker build, for one architecture
tests/test_packaging.py      what this repo can be wrong about
```

## Building

```bash
CLEARSIGNAGE_REF=<branch-tag-or-sha> ./scripts/build.sh aarch64
```

`fetch-source.sh` copies only `hosted/`, `device/` and `shared/` and drops every `tests/`
directory. The appliance's image builder, its systemd units, the Android port and the
cloud Worker are all absent, because a hosted instance is none of those things. The
resolved commit is written to `clearsignage/src/CLEARSIGNAGE_REF` and baked into the
image as an OCI label, so a running app can say exactly what it is.

## Testing

```bash
python -m pytest tests
```

These check the contract between the two repos — the failures that would otherwise
appear at install time on somebody's Home Assistant. **The image build is not tested
here.** It needs Docker and a base image per architecture, and a test that skipped
whenever those were missing would repeat the mistake that let eight of ClearSignage's
designer tests sit red on `main` for a year.

## Installing

Settings → Add-ons → Add-on store → ⋮ → **Repositories**, then add this repository's URL.
See `clearsignage/DOCS.md` for what an operator needs to know.

## Not yet verified

Nothing here has run on real Home Assistant OS. `host_dbus` reaching the host's avahi,
binding port 80, the Supervisor's `X-Ingress-Path` and `X-Remote-User-Id` headers, and
whether the base image's s6 version wants `services.d` or `s6-rc.d` are all assumptions
this packaging is shaped around and has not met. That is Epic 119 Pass 6.
