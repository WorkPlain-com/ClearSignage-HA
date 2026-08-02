// Build and publish the ClearSignage Home Assistant app image (Epic 119 Pass 4).
//
// The Supervisor can build an app on the user's own machine, and for a public add-on that
// is the friendlier default. It is the wrong choice here for one concrete reason: this
// image is built from a **private** repository, so a local build would need ClearSignage
// credentials to exist on every customer's Home Assistant. Publishing a prebuilt image
// keeps the source private, makes installation a pull rather than a ten-minute compile on
// a CM4, and means every install runs the bytes that were tested rather than whatever
// resolves on the day.
//
// One multi-arch manifest, not per-arch tags. The `{arch}` placeholder in `image:` is
// deprecated; a manifest list lets the Supervisor pull the right layer by itself.
pipeline {
    agent any

    parameters {
        string(
            name: 'CLEARSIGNAGE_REF',
            defaultValue: 'main',
            description: 'ClearSignage branch, tag or commit to build from. Pinned into the image.'
        )
        booleanParam(
            name: 'PUSH',
            defaultValue: true,
            description: 'Push the manifest. Off builds both architectures and throws them away — ' +
                'the honest way to test a Dockerfile change without publishing it.'
        )
    }

    environment {
        REGISTRY = 'ghcr.io'
        IMAGE    = 'ghcr.io/workplain-com/clearsignage-ha'
        // A GitHub PAT with read:packages + write:packages. The same credential the
        // Supervisor is given on each Home Assistant, so a rotation is one change here
        // and one per install rather than a per-arch sprawl.
        GHCR     = credentials('ghcr-clearsignage')
    }

    stages {
        stage('Verify tools') {
            // buildx and qemu are the whole reason this can build aarch64 on an x86
            // agent. Checked first because the failure is otherwise a confusing
            // "exec format error" several minutes into a build.
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    docker --version
                    docker buildx version
                    docker run --privileged --rm tonistiigi/binfmt --install arm64,amd64
                    docker buildx inspect clearsignage >/dev/null 2>&1 \
                        || docker buildx create --name clearsignage --use --bootstrap
                    docker buildx use clearsignage
                '''
            }
        }

        stage('Validate packaging') {
            // These are cheap and catch the failures that would otherwise surface at
            // install time on somebody's Home Assistant — a manifest the Supervisor
            // rejects, an option with no schema entry.
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    python3 -m venv .venv
                    .venv/bin/pip install --quiet pytest pyyaml
                    .venv/bin/python -m pytest tests -q
                '''
            }
        }

        stage('Fetch ClearSignage source') {
            // Pinned, and the resolved SHA is what gets labelled — so a running app can
            // say exactly which commit it is, which "built from main" never can.
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail
                    CLEARSIGNAGE_REF="${CLEARSIGNAGE_REF}" ./scripts/fetch-source.sh
                '''
                script {
                    env.RESOLVED_REF = sh(
                        script: 'cat clearsignage/src/CLEARSIGNAGE_REF',
                        returnStdout: true
                    ).trim()
                    env.APP_VERSION = sh(
                        script: "python3 -c \"import yaml;print(yaml.safe_load(open('clearsignage/config.yaml'))['version'])\"",
                        returnStdout: true
                    ).trim()
                }
                echo "Building ClearSignage ${env.RESOLVED_REF} as app version ${env.APP_VERSION}"
            }
        }

        stage('Build and publish') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -euo pipefail

                    # The HA base images differ per architecture, so BUILD_FROM cannot be
                    # one value across a multi-arch build. Two builds, one manifest.
                    AARCH64_FROM="$(python3 -c "import yaml;print(yaml.safe_load(open('clearsignage/build.yaml'))['build_from']['aarch64'])")"
                    AMD64_FROM="$(python3 -c "import yaml;print(yaml.safe_load(open('clearsignage/build.yaml'))['build_from']['amd64'])")"

                    if [ "${PUSH}" = "true" ]; then
                        echo "${GHCR_PSW}" | docker login "${REGISTRY}" -u "${GHCR_USR}" --password-stdin
                        OUTPUT="--push"
                    else
                        OUTPUT="--output=type=cacheonly"
                    fi

                    build_one() {
                        docker buildx build \
                            --platform "$1" \
                            --build-arg "BUILD_FROM=$2" \
                            --build-arg "CLEARSIGNAGE_REF=${RESOLVED_REF}" \
                            --tag "${IMAGE}:${APP_VERSION}-$3" \
                            ${OUTPUT} \
                            clearsignage
                    }

                    build_one linux/arm64 "${AARCH64_FROM}" aarch64
                    build_one linux/amd64 "${AMD64_FROM}"   amd64

                    if [ "${PUSH}" = "true" ]; then
                        # The manifest is what config.yaml's `image:` resolves; the two
                        # per-arch tags above exist only to assemble it.
                        docker buildx imagetools create \
                            --tag "${IMAGE}:${APP_VERSION}" \
                            --tag "${IMAGE}:latest" \
                            "${IMAGE}:${APP_VERSION}-aarch64" \
                            "${IMAGE}:${APP_VERSION}-amd64"
                        docker buildx imagetools inspect "${IMAGE}:${APP_VERSION}"
                    fi
                '''
            }
        }
    }

    post {
        always {
            sh 'docker logout ${REGISTRY} || true'
            // The fetched source is a full ClearSignage checkout; leaving it on the agent
            // would leave private source lying around between builds.
            sh 'rm -rf clearsignage/src .venv || true'
        }
    }
}
