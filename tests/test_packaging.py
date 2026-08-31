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

import importlib.util
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


def _load_pruner():
    path = REPO / "scripts" / "prune-ghcr-releases.py"
    spec = importlib.util.spec_from_file_location("prune_ghcr_releases", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_release_metadata_pins_a_reviewed_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", RELEASE["clearsignage_revision"])
    assert RELEASE["clearsignage_ref"]


def test_the_two_pinned_fields_name_the_same_release():
    """A half-done re-pin is how this file goes wrong, and it fails late.

    `clearsignage_revision` is what the pipeline compares the built commit against;
    `clearsignage_ref` is what a person passes as `CLEARSIGNAGE_REF_OVERRIDE` to build
    that commit. Editing one and leaving the other reads as re-pinned and publishes
    nothing: the build clones one commit and the gate refuses it against the other, on
    the agent, after a full private checkout — instead of here, before anything is
    fetched.

    Only asserted when the ref is itself a SHA, because a reviewed release tag is a
    legitimate value there and cannot be compared to one.
    """
    ref = RELEASE["clearsignage_ref"]
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        return
    assert ref == RELEASE["clearsignage_revision"], (
        "release.yaml names two different commits; the pipeline would build "
        f"{ref} and refuse to publish it against {RELEASE['clearsignage_revision']}"
    )


def test_the_app_version_is_stated_in_exactly_one_place():
    """One number to bump, and the manifest is where it has to be.

    The Supervisor parses `config.yaml` and tracks an installed app by the version in it,
    so that one cannot be generated or templated — which makes it the source and every
    other copy a liability. `release.yaml` used to carry one, kept in step by a test that
    forced an edit rather than a review; the publish-time revision check replaced it.

    Asserted over every YAML file rather than the one that used to have it, because the
    next copy will be added somewhere else.
    """
    assert CONFIG["version"], "the manifest states no version"

    for path in sorted(REPO.rglob("*.yaml")):
        if ".git" in path.parts or "src" in path.parts or path.name == "config.yaml":
            continue
        loaded = yaml.safe_load(path.read_text()) or {}
        repeated = {
            key: value
            for key, value in loaded.items()
            if isinstance(value, str) and value == CONFIG["version"]
        }
        assert not repeated, (
            f"{path.relative_to(REPO)} repeats the app version in {sorted(repeated)}; "
            f"read it from clearsignage/config.yaml instead"
        )


def test_the_pipeline_refuses_to_publish_a_commit_nobody_reviewed():
    """release.yaml's own sentence, made true.

    It has always said publishing is allowed only when the requested ref resolves to the
    reviewed commit, and nothing checked it — the pipeline never opened the file. A claim
    in a comment that no code enforces is worse than no claim, because the review it
    describes can be skipped by simply not doing it.

    Gated on PUSH, and that is asserted too: a `PUSH=false` build is how a Dockerfile
    change is tested against any branch, so gating that would make the dry run useless.
    """
    assert "release.yaml" in PIPELINE, "the pipeline never reads the reviewed pin"
    assert "clearsignage_revision" in PIPELINE
    assert "if (params.PUSH) {" in PIPELINE, "the check must not run on a dry-run build"
    assert "Refusing to publish" in PIPELINE


def test_pipeline_defaults_to_prod_and_pins_the_resolved_revision():
    """A published image is a release, so it is built from released code.

    This defaulted to `main`, which was right while main was the only branch that
    existed. Once releases are cut from beta and prod, an add-on built from main
    ships customers device code that has been through no release gate and is ahead
    of what the rest of the fleet is running.
    """
    choices = re.search(r"name: 'CLEARSIGNAGE_REF',\s*choices: \[([^\]]*)\]", PIPELINE)
    assert choices, "CLEARSIGNAGE_REF is no longer a branch choice"
    listed = [value.strip().strip("'") for value in choices.group(1).split(",")]
    assert listed[0] == "prod", f"the first choice is the Jenkins default; got {listed}"
    assert listed == ["prod", "beta", "main"]

    assert 'cat clearsignage/src/CLEARSIGNAGE_REF' in PIPELINE
    assert '--build-arg "CLEARSIGNAGE_REF=${RESOLVED_REF}"' in PIPELINE


def test_an_unset_parameter_falls_back_to_the_current_default():
    """The fallback has to move with the default, or the change does not take.

    A job configuration created before the parameter existed passes nothing, and
    Jenkins does not backfill it. If the shell fallback still said `main`, those
    jobs would go on building main while the UI claimed the default was prod —
    the change would look applied and not be.
    """
    assert "${CLEARSIGNAGE_REF:-prod}" in PIPELINE
    assert "CLEARSIGNAGE_REF:-main" not in PIPELINE

    script = (REPO / "scripts" / "fetch-source.sh").read_text(encoding="utf-8")
    assert 'REF="${CLEARSIGNAGE_REF:-prod}"' in script, (
        "fetch-source.sh is runnable by hand and carries its own default; it must "
        "agree with the pipeline's"
    )


def test_an_exact_commit_can_still_be_built():
    """Reproducing a published image means naming its commit, which a choice cannot.

    The pipeline records the resolved commit as the image revision, so that
    capability is the point of recording it. `fetch-source.sh` already has the
    SHA-fetch fallback; the override is what reaches it.
    """
    assert "name: 'CLEARSIGNAGE_REF_OVERRIDE'" in PIPELINE
    # The override wins over the branch, and both fall back to the default.
    assert '"${CLEARSIGNAGE_REF_OVERRIDE:-${CLEARSIGNAGE_REF:-prod}}"' in PIPELINE


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


def test_the_run_script_execs_the_venue_rather_than_backgrounding_it():
    """s6 supervises PID 1 of the service; a backgrounded process is unsupervised.

    ``-m clearvenue``, not ``-m hosted`` (DP92): a venue is the supervisor *plus* the
    surfaces that make it the building's source of truth — the till, enrolment, the
    replication lane. Running the supervisor alone is what left an operator here with the
    Screens page and nothing else, so the module named is the whole of that fix.
    """
    run = (APP / "rootfs/etc/services.d/clearsignage/run").read_text()
    assert re.search(r"^exec .*-m clearvenue$", run, re.M), run[-200:]


def test_the_run_script_says_which_platform_is_hosting_the_venue():
    """Left unset, ``clearvenue.hosts`` resolves Ubuntu Core — the wrong answer here.

    That default is deliberate upstream (it is the platform the venue snap ships on), and
    it is exactly why this file has to state its own: an unstated venue on Home Assistant
    would mount a sign-in of its own over an operator the Supervisor has already
    authenticated, and try to bind a privileged port it does not own.
    """
    run = (APP / "rootfs/etc/services.d/clearsignage/run").read_text()
    assert re.search(r"^CLEARVENUE_HOST=home-assistant$", run, re.M), run[:400]
    assert "export CLEARVENUE_HOST" in run, "set but never exported reaches no child"


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


def test_the_pipeline_keeps_only_the_current_and_previous_image_releases():
    assert "stage('Prune old releases')" in PIPELINE
    assert "expression { params.PUSH }" in PIPELINE
    assert '"${APP_VERSION}"' in PIPELINE

    pruner = _load_pruner()
    versions = []
    version_id = 1
    for release in ("0.1.87", "0.1.88", "0.1.89"):
        for suffix in ("", "-aarch64", "-amd64"):
            tags = [f"{release}{suffix}"]
            if release == "0.1.89" and not suffix:
                tags.append("latest")
            versions.append(
                {"id": version_id, "metadata": {"container": {"tags": tags}}}
            )
            version_id += 1
    # An untagged platform manifest may still be referenced by a retained index.
    versions.append({"id": 10, "metadata": {"container": {"tags": []}}})

    assert pruner.versions_to_delete(versions, "0.1.89") == [1, 2, 3]


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


def test_the_image_contains_the_package_the_run_script_execs():
    """The two files that must agree, and the way they can silently stop agreeing.

    ``fetch-source.sh`` decides what goes into the image; ``run`` decides what is started
    from it. Nothing else connects them, so a package dropped from the copy list — or a
    module renamed upstream — produces an image that builds cleanly, passes every other
    test here, and then exits with ``No module named clearvenue`` on somebody's Home
    Assistant.

    Asserted both ways round: the package is copied, *and* the fetch script checks it
    arrived. The second is what turns an upstream rename into a failed build rather than
    a published image.
    """
    fetch = (REPO / "scripts" / "fetch-source.sh").read_text(encoding="utf-8")
    run = (APP / "rootfs/etc/services.d/clearsignage/run").read_text(encoding="utf-8")

    execed = re.search(r"^exec .*-m (\w+)$", run, re.M)
    assert execed, "the run script execs no module at all"
    package = execed.group(1)

    copied = re.search(r"^for path in ([^;]+); do$", fetch, re.M)
    assert copied, "fetch-source.sh no longer states which paths it copies"
    assert package in copied.group(1).split(), (
        f"the run script starts {package!r}, which fetch-source.sh does not copy: "
        f"the image would build without it"
    )
    assert f'"${{DEST}}/{package}/__main__.py"' in fetch, (
        f"{package} is copied but never verified, so an upstream rename would publish "
        f"an image that cannot start"
    )
