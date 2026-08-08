"""What this repository can actually be wrong about (Epic 119 Pass 4).

It ships no logic — the decisions live in ClearSignage's ``hosted`` package, which has its
own suite. What it *can* get wrong is the contract between the two: a manifest the
Supervisor rejects, an option the app ignores because its schema entry is missing, or a
path in the Dockerfile that no longer exists upstream. Those are the failures that only
show up on a real Home Assistant, at install time, so they are worth catching here.

The image build itself is not tested. Building it needs Docker and a base image per
architecture, and a test that skipped whenever those were absent would be the same silent
skip that let eight designer tests sit red on ClearSignage's main for a year.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "clearsignage"
CONFIG = yaml.safe_load((APP / "config.yaml").read_text())
BUILD = yaml.safe_load((APP / "build.yaml").read_text())
RELEASE = yaml.safe_load((APP / "release.yaml").read_text())
PIPELINE = (REPO / "jenkinsfile-ha").read_text()


def _dockerfile_directives() -> str:
    """Return the Dockerfile with comments stripped.

    Scanning the raw text would match the comments that *explain* why feh and a second
    avahi are absent — the prose asserting the property would fail the assertion. Written
    down because the first version of these tests did exactly that.
    """
    lines = (APP / "Dockerfile").read_text().splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def _service_script(name: str, *, uncommented: bool = False) -> str:
    """Return an s6 service script, optionally with comment lines stripped.

    Same trap as `_dockerfile_directives`: these scripts explain in prose which binaries
    they must *not* call, so a test asserting the absence of one would match the sentence
    saying so. The shebang is kept — it is the interpreter, not a comment.
    """
    text = (APP / "rootfs/etc/services.d/clearsignage" / name).read_text()
    if not uncommented:
        return text
    lines = text.splitlines()
    return "\n".join(
        line
        for line in lines
        if line.startswith("#!") or not line.lstrip().startswith("#")
    )


def test_every_yaml_file_parses():
    for path in sorted(REPO.rglob("*.yaml")):
        if ".git" in path.parts or "src" in path.parts:
            continue
        assert isinstance(yaml.safe_load(path.read_text()), dict), path


def test_release_metadata_pins_this_app_version_to_a_commit():
    assert RELEASE["app_version"] == CONFIG["version"]
    assert re.fullmatch(r"[0-9a-f]{40}", RELEASE["clearsignage_revision"])
    assert RELEASE["clearsignage_ref"]


def test_pipeline_defaults_to_main_and_pins_the_resolved_revision():
    parameter = re.search(
        r"name: 'CLEARSIGNAGE_REF'.*?defaultValue: '([^']*)'", PIPELINE, re.S
    )
    assert parameter and parameter.group(1) == "main"
    assert 'CLEARSIGNAGE_REF="${CLEARSIGNAGE_REF:-main}"' in PIPELINE
    assert 'cat clearsignage/src/CLEARSIGNAGE_REF' in PIPELINE
    assert '--build-arg "CLEARSIGNAGE_REF=${RESOLVED_REF}"' in PIPELINE


def test_pipeline_labels_the_image_with_the_resolved_revision():
    assert '--label "org.opencontainers.image.revision=${RESOLVED_REF}"' in PIPELINE


def test_the_manifest_has_what_the_supervisor_requires():
    for key in ("name", "version", "slug", "description", "arch"):
        assert key in CONFIG, key
    assert re.fullmatch(r"[a-z0-9_]+", CONFIG["slug"])


def test_the_architectures_are_the_two_that_have_wheels():
    """32-bit Arm is absent on purpose: the device pins resolve to manylinux
    aarch64/x86_64 wheels, and HA OS dropped 32-bit anyway."""
    assert set(CONFIG["arch"]) == {"aarch64", "amd64"}
    assert set(BUILD["build_from"]) == set(CONFIG["arch"])


def test_ingress_is_on_and_has_a_port():
    """Ingress is the entry path that carries authority (DP64)."""
    assert CONFIG["ingress"] is True
    assert isinstance(CONFIG["ingress_port"], int)


def test_the_privileges_the_epic_requires_are_asked_for():
    """host_network for peer sync and discovery (DP65); host_dbus for avahi (DP66).

    Both are load-bearing rather than convenient — a peer addresses the host, not a
    container port, and HA OS already owns 5353.
    """
    assert CONFIG["host_network"] is True
    assert CONFIG["host_dbus"] is True


def test_no_privilege_is_asked_for_that_the_epic_does_not_justify():
    """An app asking for more than it needs is how a private repo becomes a liability."""
    assert "privileged" not in CONFIG, CONFIG.get("privileged")
    assert "devices" not in CONFIG
    assert "host_pid" not in CONFIG
    # /data is mounted for every app without asking; this app wants nothing else — not
    # Home Assistant's config, not its SSL, not its media.
    assert "map" not in CONFIG


def test_every_option_has_a_schema_entry():
    """A mismatch is how an app silently ignores what the operator typed."""
    assert set(CONFIG["options"]) == set(CONFIG["schema"])


@pytest.mark.parametrize("key", sorted(CONFIG["schema"]))
def test_each_schema_type_is_one_the_supervisor_understands(key):
    spec = CONFIG["schema"][key]
    assert re.fullmatch(
        r"(str|int|float|bool|port|email|url|password|match\(.*\)|list\(.*\))\??", spec
    ), (key, spec)


def test_the_default_log_level_is_one_of_the_allowed_values():
    allowed = CONFIG["schema"]["log_level"][len("list(") : -1].split("|")
    assert CONFIG["options"]["log_level"] in allowed


def test_the_watchdog_points_at_the_port_we_actually_serve():
    assert f"[PORT:{CONFIG['ingress_port']}]" in CONFIG["watchdog"]


def test_every_option_is_explained_to_the_operator():
    """An option nobody can interpret is an option nobody will set correctly."""
    translations = yaml.safe_load((APP / "translations" / "en.yaml").read_text())
    assert set(translations["configuration"]) == set(CONFIG["options"])
    for key, entry in translations["configuration"].items():
        assert entry.get("name"), key
        assert entry.get("description"), key


def test_the_run_script_execs_the_supervisor_rather_than_backgrounding_it():
    """s6 supervises PID 1 of the service; a backgrounded process is unsupervised."""
    run = (APP / "rootfs/etc/services.d/clearsignage/run").read_text()
    assert re.search(r"^exec .*-m hosted$", run, re.M), run[-200:]


def test_the_finish_script_brings_the_whole_app_down():
    """Otherwise s6 restarts one service and the app looks healthy with no screens."""
    finish = (APP / "rootfs/etc/services.d/clearsignage/finish").read_text()
    assert "/run/s6/basedir/bin/halt" in finish


def test_the_finish_script_calls_nothing_s6_overlay_v3_does_not_ship():
    """`s6-test` is a v2 binary: it moved into execline as `eltest`, and the base image
    ships only the latter. Calling it crash-looped the container with "unable to spawn
    s6-test" and no way for the app to ever come down cleanly.

    `/var/run/s6/services` is the same mistake in path form — v3's scandir is
    `/run/service` — so both are checked here rather than rediscovered on a screen.
    """
    finish = _service_script("finish", uncommented=True)
    assert "s6-test" not in finish
    assert "/var/run/s6/services" not in finish


def test_the_dockerfile_installs_no_display_stack():
    """A hosted instance has no screen to drive (DP63); the browser is the display.

    Installing X, feh, mpv or chromium here would be shipping an appliance's display
    stack into an image that can never use it.
    """
    directives = _dockerfile_directives().lower()
    for absent in ("xserver", "xorg", "feh", "imv", "mpv", "chromium", "cage", "plymouth"):
        assert absent not in directives, absent


def test_the_dockerfile_installs_what_mdns_needs():
    """avahi-publish claims each screen's name through the host's daemon (DP66)."""
    directives = _dockerfile_directives()
    assert "avahi-utils" in directives
    # ...and not a second daemon, which would contend with HA OS's for 5353 and lose.
    assert "avahi-daemon" not in directives


def test_the_dockerfile_installs_every_command_the_run_script_calls():
    """The run script's default path reads the host address from `ip`, and neither
    Debian's rootfs nor the Home Assistant base image ships it.

    Its absence was invisible in the worst way: `ip` exited 127, `set -o pipefail` made
    the assignment fail, `set -e` exited the service, and the redirect to /dev/null meant
    the container died having logged nothing at all.
    """
    directives = _dockerfile_directives()
    run = _service_script("run", uncommented=True)
    if re.search(r"\bip route\b", run):
        assert "iproute2" in directives


def test_the_app_dir_points_at_the_package_uvicorn_is_told_to_import():
    """The supervisor spawns each screen with ``cwd=CLEARSIGNAGE_APP_DIR`` and an
    environment it builds from scratch, so nothing on this image's PYTHONPATH reaches a
    screen — that working directory is the only thing that can make ``app.main:app``
    importable, exactly as the appliance's signage-api.service cds to SIGNAGE_APP_DIR.

    Pointing it at the copy root instead of the directory holding the package left every
    screen dying with ModuleNotFoundError, which reaches the operator as a 502 from
    ingress and says nothing about why.
    """
    directives = _dockerfile_directives()
    copied_to = re.search(r"^COPY\s+src/\s+(\S+)", directives, re.M)
    assert copied_to, directives
    app_dir = re.search(r"CLEARSIGNAGE_APP_DIR=(\S+)", directives)
    assert app_dir, directives

    # fetch-source.sh is what guarantees the shape of the tree that gets copied: it
    # refuses to finish unless device/app/main.py is there.
    fetch = (REPO / "scripts/fetch-source.sh").read_text()
    assert "device/app/main.py" in fetch, fetch

    root = copied_to.group(1).rstrip("/")
    assert app_dir.group(1).rstrip("/") == f"{root}/device"


def test_the_run_script_agrees_with_the_dockerfile_about_where_the_app_is():
    """Two defaults for one path is one of them being wrong later."""
    from_dockerfile = re.search(r"CLEARSIGNAGE_APP_DIR=(\S+)", _dockerfile_directives())
    assert from_dockerfile
    fallback = re.search(
        r"CLEARSIGNAGE_APP_DIR=\"\$\{CLEARSIGNAGE_APP_DIR:-([^}]+)\}\"",
        _service_script("run", uncommented=True),
    )
    assert fallback
    assert fallback.group(1).rstrip("/") == from_dockerfile.group(1).rstrip("/")


def test_host_ip_detection_cannot_kill_the_service_before_it_explains_itself():
    """`set -e` plus a bare command substitution is a silent exit; the operator sees a
    container that started and vanished. The detection may fail — it must not be fatal,
    because the check right after it is what tells them to set host_ip by hand."""
    run = _service_script("run", uncommented=True)
    detection = re.search(r"^.*\bip route\b.*$", run, re.M)
    assert detection, run
    assert "|| true" in detection.group(0), detection.group(0)


def test_an_unset_host_ip_is_not_advertised_to_peers_as_the_string_null():
    """bashio::config returns the literal "null" for a cleared option, and every screen
    would announce that verbatim as the address peers should reach this host at."""
    run = _service_script("run", uncommented=True)
    assert '"null"' in run or "'null'" in run


def test_the_dependency_set_is_pinned_to_the_appliance_s_own_constraints():
    """"It worked on the Pi" only means something if both install the same artifacts."""
    directives = _dockerfile_directives()
    assert "device/requirements.txt" in directives
    assert "-c /opt/clearsignage/device/constraints.txt" in directives


def test_the_source_is_fetched_not_vendored():
    """DP34's line, applied here: another product's source does not live in this repo."""
    assert not (APP / "src").exists() or not (APP / "src" / "device" / ".git").exists()
    fetch = (REPO / "scripts" / "fetch-source.sh").read_text()
    for path in ("hosted", "device", "shared"):
        assert path in fetch
    # The appliance-only trees are deliberately not copied.
    for absent in ("android", "cloud-provisioner", "infra"):
        assert f'"{absent}"' not in fetch


def test_the_pythonpath_matches_where_the_source_is_copied():
    """The one line that decides whether either half of the app can import at all."""
    directives = _dockerfile_directives()
    assert "COPY src/ /opt/clearsignage/" in directives
    for entry in ("/opt/clearsignage", "/opt/clearsignage/device", "/opt/clearsignage/shared"):
        assert entry in directives


def test_the_image_is_a_prebuilt_multi_arch_manifest():
    """Local builds would need private-repo credentials on every customer's machine.

    And the `{arch}` placeholder is the deprecated form — a manifest list lets the
    Supervisor pull the right layer itself, so a per-arch image name here would be
    fighting the platform.
    """
    assert CONFIG["image"].startswith("ghcr.io/")
    assert "{arch}" not in CONFIG["image"]


def test_the_pipeline_builds_both_architectures_into_one_manifest():
    """A manifest naming one architecture installs on half the fleet and nobody notices
    until the other half tries."""
    pipeline = (REPO / "jenkinsfile-ha").read_text()
    assert "linux/arm64" in pipeline
    assert "linux/amd64" in pipeline
    assert "imagetools create" in pipeline
    # The image the pipeline pushes must be the one the manifest tells HA to pull.
    assert CONFIG["image"] in pipeline


def test_the_pipeline_does_not_leave_private_source_on_the_agent():
    """The fetched tree is a full ClearSignage checkout."""
    pipeline = (REPO / "jenkinsfile-ha").read_text()
    assert "rm -rf clearsignage/src" in pipeline
    assert "docker logout" in pipeline


def test_the_operator_is_told_to_add_registry_credentials_first():
    """A private image makes this a prerequisite, not a footnote.

    Without the credential the install fails at the pull with an authentication error,
    which reads like a broken repository — an operator would go back and re-check the URL
    they just added. The instruction has to be there, and it has to come first.
    """
    docs = (APP / "DOCS.md").read_text()
    registry = CONFIG["image"].split("/")[0]
    assert registry in docs
    assert docs.index(registry) < docs.index("Repositories")
