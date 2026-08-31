#!/usr/bin/env python3
"""Decide whether this build is allowed to publish an image.

A release should be one edit: bump `version` in `clearsignage/config.yaml` and run the
pipeline. That is safe for the branch the pipeline defaults to, because `prod` is
ClearSignage's *released* branch — a commit only gets there through that repository's own
release gate — so building prod publishes code somebody has already signed off, whatever
prod happens to be on the day.

Everything else is the case where nothing has vouched for the code yet: `beta` and `main`
move on their own, and an exact commit given by hand is whatever was typed. Publishing one
of those is allowed only when `clearsignage/release.yaml` records that exact commit, so
the repository carries a written statement of what is being shipped and why it is not
coming from prod.

Kept out of `jenkinsfile-ha` so the rule can be tested — the Jenkinsfile cannot be — in
the same way `prune-ghcr-releases.py` keeps the retention rule out of it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

RELEASED_BRANCH = "prod"


def publish_refusal(
    *,
    push: bool,
    branch: str,
    override: str,
    built_revision: str,
    pinned_revision: str,
) -> str | None:
    """Return why publishing is refused, or None when it is allowed.

    `override` is an exact tag or commit that was asked for by hand; when it is set the
    branch choice was not used at all.
    """
    if not push:
        # A PUSH=false build is how a Dockerfile change is tested against any branch.
        # Nothing is published, so there is nothing to gate.
        return None

    if not built_revision.strip():
        # The commit is read from the fetched checkout and stamped onto the image as
        # org.opencontainers.image.revision. Blank means the fetch did not leave what it
        # was supposed to, and an image that cannot say what it is should not be one
        # customers are running.
        return (
            "Refusing to publish: this build recorded no ClearSignage commit, so the "
            "image could not say which source it was built from."
        )

    if not override.strip() and branch.strip() == RELEASED_BRANCH:
        return None

    asked_for = override.strip() or branch.strip()
    if built_revision.strip() == pinned_revision.strip():
        return None

    return (
        f"Refusing to publish: this build is ClearSignage {built_revision.strip()}, "
        f"asked for as {asked_for!r}.\n"
        f"Publishing from anywhere but {RELEASED_BRANCH!r} is allowed only for the commit "
        f"clearsignage/release.yaml records, which is {pinned_revision.strip()}.\n"
        f"Build {RELEASED_BRANCH} to ship released code, or pin this commit in "
        f"release.yaml if it is the one you mean to ship."
    )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "on"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", required=True, help="whether this build publishes")
    parser.add_argument("--branch", required=True, help="the branch choice used")
    parser.add_argument("--override", default="", help="an exact tag or commit, if given")
    parser.add_argument("--built-revision", required=True, help="the commit that was fetched")
    parser.add_argument("--release-file", required=True, type=Path)
    args = parser.parse_args(argv)

    release = yaml.safe_load(args.release_file.read_text(encoding="utf-8")) or {}

    refusal = publish_refusal(
        push=_as_bool(args.push),
        branch=args.branch,
        override=args.override,
        built_revision=args.built_revision,
        pinned_revision=str(release.get("clearsignage_revision", "")),
    )

    if refusal:
        print(refusal, file=sys.stderr)
        return 1

    if _as_bool(args.push):
        print(f"Publishing ClearSignage {args.built_revision.strip()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
