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
clearsignage/release.yaml    the upstream commit this release was reviewed against
```

## Building

`jenkinsfile-ha` is the pipeline. It builds both architectures with buildx and qemu, joins
them into one multi-arch manifest with `imagetools create`, and pushes it to the
`image:` named in `config.yaml`. Parameters:

- `CLEARSIGNAGE_REF` — which upstream branch to build from: **`prod`** (default), `beta`,
  or `main`. A published image reaches customers' Home Assistant installs, so it defaults
  to the branch that has been through the release gate rather than to development.
- `CLEARSIGNAGE_REF_OVERRIDE` — an exact tag or commit SHA, used instead of the branch
  when set. This is how a previously published image is reproduced: the pipeline records
  the resolved commit as the image revision, so rebuilding one means naming that commit.
- `PUSH` — off builds both architectures and throws them away, the honest way to test a
  Dockerfile change without publishing it.

## Releasing

1. Merge the intended changes in the upstream ClearSignage repository and run its full
   test suite.
2. Pin the resulting full commit SHA in `clearsignage/release.yaml` (and pass that SHA, or
   the reviewed release tag recorded beside it, as `CLEARSIGNAGE_REF_OVERRIDE`).
3. Increment `version` in `clearsignage/config.yaml`. That is the **only** place the app
   version lives: the Supervisor parses this manifest and tracks an installed app by it,
   so it has to be a literal there, and the pipeline and the image labels read it from
   there. Nothing else keeps a copy to edit in step.
4. Run Jenkins with `PUSH=true`. It builds and publishes both `aarch64` and `amd64`, and
   refuses to publish at all unless the commit it built is the one `release.yaml` records
   as reviewed — so step 2 cannot be skipped. A branch ref is still fine for an opt-in
   `PUSH=false` development build, which skips that check.
5. Inspect `${IMAGE}:${APP_VERSION}` with `docker buildx imagetools inspect`, checking
   both platforms and the `org.opencontainers.image.revision` label.
6. Only after that inspection, upgrade the Home Assistant installation to the new app
   version.

Locally, one architecture at a time:

```bash
CLEARSIGNAGE_REF=<branch-tag-or-sha> ./scripts/build.sh aarch64
```

**Prebuilt, not built on the user's machine.** The Supervisor can build an app locally and
for a public add-on that is the friendlier default. It is the wrong choice here for one
concrete reason: this image is built from a *private* repository, so a local build would
put ClearSignage credentials on every customer's Home Assistant. Publishing keeps the
source private, turns a ten-minute compile on a CM4 into a pull, and means every install
runs the bytes that were tested rather than whatever resolves on the day. The cost is that
each install needs read credentials for the registry — Home Assistant stores those itself,
per registry hostname, so they never appear in this repository.

`fetch-source.sh` copies only `hosted/`, `device/` and `shared/` and drops every `tests/`
directory. The appliance's image builder, its systemd units, the Android port and the
cloud Worker are all absent, because a hosted instance is none of those things. The
resolved commit is written to `clearsignage/src/CLEARSIGNAGE_REF` and baked into the
image as an OCI label, so a running app can say exactly what it is. The pipeline deletes
that tree afterwards rather than leaving private source on a shared agent.

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

Add `ghcr.io` credentials to Home Assistant's Docker registries first — the image is
private and the install otherwise fails at the pull. Then Settings → Apps → Install app →
⋮ → **Repositories**, and add this repository's URL. See `clearsignage/DOCS.md` for what
an operator needs to know.

### Internal testing (current phase)

There is no public install yet — the `clearsignage-ha` package on ghcr.io is a private
package, and it stays that way for this phase. "Just add the repo by URL" is not enough
on its own: the Supervisor always pulls the `image:` in `config.yaml` on install, so a
tester's Home Assistant still needs its own read credentials for the private package
(the "Installing" step above), same as a real customer install would. `PUSH=false` on the
Jenkins job is there for the case where you want to validate a Dockerfile or `build.yaml`
change without touching the registry at all — it builds both architectures and discards
them instead of publishing.

## Not yet verified

Nothing here has run on real Home Assistant OS. `host_dbus` reaching the host's avahi,
binding port 80, the Supervisor's `X-Ingress-Path` and `X-Remote-User-Id` headers, and
whether the base image's s6 version wants `services.d` or `s6-rc.d` are all assumptions
this packaging is shaped around and has not met. That is Epic 119 Pass 6.
