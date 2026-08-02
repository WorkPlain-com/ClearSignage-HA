#!/usr/bin/env bash
# Build the app image locally for one architecture (Epic 119 Pass 4).
#
# The same two steps CI runs: pin the source, then build. Kept as a script rather than a
# README instruction because the build is worthless if the source step is skipped — the
# Dockerfile would COPY a stale src/ and nobody would notice until the image ran.
set -euo pipefail

ARCH="${1:-aarch64}"
REF="${CLEARSIGNAGE_REF:-main}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

BUILD_FROM="$(
    python3 -c "import sys,yaml;print(yaml.safe_load(open(sys.argv[1]))['build_from'][sys.argv[2]])" \
        "${HERE}/clearsignage/build.yaml" "${ARCH}"
)"

CLEARSIGNAGE_REF="${REF}" "${HERE}/scripts/fetch-source.sh"

docker build \
    --build-arg "BUILD_FROM=${BUILD_FROM}" \
    --build-arg "CLEARSIGNAGE_REF=$(cat "${HERE}/clearsignage/src/CLEARSIGNAGE_REF")" \
    --tag "clearsignage-ha:${ARCH}" \
    "${HERE}/clearsignage"
