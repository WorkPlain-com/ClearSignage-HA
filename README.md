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
  next-image-version.py      choose YYYYMMDD.NN and stamp it into the manifest
  check-publish-allowed.py   what may be published, and from where
  prune-ghcr-releases.py     keep the current and previous releases, delete the rest
  ghcr_api.py                the one way these two reach the GHCR package
tests/test_packaging.py      what this repo can be wrong about
clearsignage/release.yaml    the one commit publishable from somewhere other than prod
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

**Run the Jenkins job with `PUSH=true`.** That is the whole of it — nothing in this
repository is edited by hand to cut a release.

Two things make that true. The version is chosen by the pipeline, and the branch is
already released code:

- **The version** is `YYYYMMDD.NN` from the build's UTC date — the same scheme
  ClearSignage releases use, chosen the same way: the counter comes from the tags already
  in the GHCR package, not from a number in this repo, so it cannot collide with a version
  somebody is already running. `scripts/next-image-version.py` chooses it, stamps it into
  `clearsignage/config.yaml`, and the pipeline commits that line back to `main` after the
  push. Home Assistant reads the version from the manifest **in this repository**, so
  recording it is part of publishing: until it is committed, the Supervisor goes on
  offering the version the file still names.
- **The branch** defaults to `prod`, which is ClearSignage's released branch — a commit
  only reaches it through that repository's own release gate — so building prod ships code
  that has already been signed off, whatever prod is on the day.

Then, before anyone upgrades:

1. Inspect `${IMAGE}:${APP_VERSION}` with `docker buildx imagetools inspect`, checking
   both platforms and the `org.opencontainers.image.revision` label — that label is the
   exact upstream commit the image was built from.
2. Only after that inspection, upgrade the Home Assistant installation to the new app
   version.

If the build publishes the image but cannot push the version commit — most likely a branch
protection rule on `main` that the Jenkins credential cannot satisfy — it fails loudly and
says so. No rebuild is needed in that case: set `version` in `clearsignage/config.yaml` to
the version it published and commit that.

**Publishing something other than `prod`** — a `beta` or `main` build, or an exact commit
passed as `CLEARSIGNAGE_REF_OVERRIDE` — is the case where nothing has vouched for the
code, and it is refused unless that commit is written into `clearsignage/release.yaml`
first (**both** fields; they name one release). The rule is
`scripts/check-publish-allowed.py`, and `tests/test_packaging.py` drives it. A `PUSH=false`
build of any branch is never gated: it publishes nothing.

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

`fetch-source.sh` copies only `hosted/`, `device/`, `shared/` and `clearvenue/` — the
venue role this app starts (DP92) — and drops every `tests/` directory. The appliance's
image builder, its systemd units, the Android port and the cloud Worker are all absent,
because a hosted instance is none of those things. The
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
