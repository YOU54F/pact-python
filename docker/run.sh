#!/bin/sh

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 PYTHON_VERSION [PLATFORM_ARCH] [OS] [OS_VERSION]"
    echo
    echo "Example:"
    echo "$0 3.11                   Run using Python 3.11, default Alpine 3.17"
    echo "$0 3.9 arm64              Run using Python 3.9, Platform arch arm64, OS Alpine, OS Version 3.17"
    echo "$0 3.9 arm64 debian       Run using Python 3.9, Platform arch arm64, OS Debian, OS Version bookworm"
    echo "$0 3.9 amd64 alpine 3.17  Run using Python 3.9, Platform arch amd64, OS Alpine, OS Version 3.17"
    echo "debian uses official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images"
    exit 1
fi

PY=$1
PLATFORM_ARCH=${2:-amd64}
OS=${3:-alpine}
OS_VERSION=""
if [ $OS == 'alpine' ]; then
    OS_VERSION=${4:-3.17}
    DOCKER_IMAGE="pactfoundation:python${PY}-${OS}-${OS_VERSION}-${PLATFORM_ARCH}"
else
    DOCKER_IMAGE="pactfoundation:python${PY}-${OS}-${PLATFORM_ARCH}"
fi
echo "Running container for Python: ${PY}, Distro: ${OS}, Distro Version: ${OS_VERSION}, Platform Arch: ${PLATFORM_ARCH}"
if [ $OS == 'alpine' ] && [ $PLATFORM_ARCH == 'arm64' ]; then
       docker run --rm -it \
        --platform="linux/${PLATFORM_ARCH}" \
        -e PACT_LIB_VERSION=0.4.5 \
        -v "$(pwd)":/home \
        -t "$DOCKER_IMAGE"
        # bash
        # -t "$DOCKER_IMAGE" bash -c 'python -m hatch run test && python -m hatch run test tests/test_ffi.py -rP && pact/bin/pact-broker version'
else
    docker run --rm -it \
        --platform="linux/${PLATFORM_ARCH}" \
        -v "$(pwd)":/home \
        -t "$DOCKER_IMAGE"
        # bash
        # -t "$DOCKER_IMAGE" bash -c 'python -m hatch run test && python -m hatch run test tests/test_ffi.py -rP && pact/bin/pact-broker version'
fi
