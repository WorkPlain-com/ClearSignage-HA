#!/usr/bin/env python3
"""Delete GHCR image versions older than the current and previous releases."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


RELEASE_TAG = re.compile(r"^(\d+(?:\.\d+)+)(?:-(aarch64|amd64))?$")


def release_from_tags(tags: list[str]) -> str | None:
    """Return the release represented by a GHCR version's tags, if any."""
    releases = {match.group(1) for tag in tags if (match := RELEASE_TAG.fullmatch(tag))}
    if len(releases) > 1:
        raise ValueError(f"GHCR version unexpectedly contains several releases: {tags}")
    return next(iter(releases), None)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def versions_to_delete(versions: list[dict[str, object]], current: str) -> list[int]:
    """Select tagged release objects while preserving N and N-1.

    Untagged objects are intentionally ignored: they can be platform manifests referenced
    by one of the two retained multi-architecture indexes.
    """
    releases = {
        release
        for item in versions
        if (release := release_from_tags(item.get("metadata", {}).get("container", {}).get("tags", [])))
    }
    if current not in releases:
        raise ValueError(f"new release {current} was not found in GHCR; refusing to prune")

    current_key = version_key(current)
    older = sorted(
        (release for release in releases if version_key(release) < current_key),
        key=version_key,
    )
    retained = {current}
    if older:
        retained.add(older[-1])
    doomed_releases = set(older) - retained

    selected = []
    for item in versions:
        tags = item.get("metadata", {}).get("container", {}).get("tags", [])
        release = release_from_tags(tags)
        if release in doomed_releases:
            selected.append(int(item["id"]))
    return selected


def request(url: str, token: str, method: str = "GET") -> urllib.response.addinfourl:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers, method=method))


def main() -> int:
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} OWNER PACKAGE CURRENT_VERSION", file=sys.stderr)
        return 2

    owner, package, current = sys.argv[1:]
    token = os.environ.get("GHCR_TOKEN")
    if not token:
        print("GHCR_TOKEN is required", file=sys.stderr)
        return 2

    base = "https://api.github.com/orgs/{}/packages/container/{}/versions".format(
        urllib.parse.quote(owner, safe=""), urllib.parse.quote(package, safe="")
    )
    versions: list[dict[str, object]] = []
    page = 1
    while True:
        with request(f"{base}?per_page=100&page={page}", token) as response:
            batch = json.load(response)
        versions.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    doomed = versions_to_delete(versions, current)
    for version_id in doomed:
        with request(f"{base}/{version_id}", token, method="DELETE"):
            pass
        print(f"Deleted GHCR package version {version_id}")
    print(f"Pruned {len(doomed)} package versions; retained release {current} and its predecessor")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as error:
        print(f"GHCR pruning failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
