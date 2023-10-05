#!/bin/sh

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 PYTHON_VERSION [PLATFORM_ARCH] [OS] [OS_VERSION]"
    echo
    echo "Example:"
    echo "$0 3.11                   Build using Python 3.11, default Alpine 3.17"
    echo "$0 3.9 arm64              Build using Python 3.9, Platform arch arm64, OS Alpine, OS Version 3.17"
    echo "$0 3.9 arm64 debian       Build using Python 3.9, Platform arch arm64, OS Debian, OS Version bookworm"
    echo "$0 3.9 amd64 alpine 3.17  Build using Python 3.9, Platform arch amd64, OS Alpine, OS Version 3.17"
    echo "debian uses official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images"
    exit 1
fi

PY=$1
PLATFORM_ARCH=${2:-amd64}
OS=${3:-alpine}
DOCKER_FILE="docker/Dockerfile"
OS_VERSION=""
if [ $OS == 'alpine' ]; then
    OS_VERSION=${4:-3.17}
    DOCKER_IMAGE="pactfoundation:python${PY}-${OS}-${OS_VERSION}-${PLATFORM_ARCH}"
else
    DOCKER_IMAGE="pactfoundation:python${PY}-${OS}-${PLATFORM_ARCH}"
    DOCKER_FILE=$DOCKER_FILE.$OS
fi
echo "Building env for Python: ${PY}, Distro: ${OS}, Distro Version: ${OS_VERSION}, Platform Arch: ${PLATFORM_ARCH}"

docker build \
    --build-arg PY="$PY" \
    --build-arg OS_VERSION="${OS_VERSION}" \
    --platform="linux/${PLATFORM_ARCH}" \
    -t "$DOCKER_IMAGE" -f "$DOCKER_FILE" .

echo
echo "Image successfully built and tagged as: ${DOCKER_IMAGE}"
