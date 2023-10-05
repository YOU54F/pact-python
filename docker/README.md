# Introduction

This is for contributors who want to make changes and test for all different
versions of python currently supported. If you don't want to set up and install
all the different python versions locally (and there are some difficulties with
that) you can just run them in docker using containers.

# Setup

To build a container say for Python 3.11, change to the root directory of the
project and run:

```bash
(PY=3.11 PLATFORM_ARCH=amd64 docker build --build-arg PY="$PY" --platform=linux/${PLATFORM_ARCH} -t pactfoundation:python${PY} -f docker/Dockerfile .)
```

This uses an Alpine based image (currently 3.17), which is available as of
2023-04 for Python versions 3.7 - 3.11.

To build for Python versions which require a different Alpine image, such as if
trying to build against Python 3.6, an extra `ALPINE` arg can be provided:

```bash
(PY=3.11 PLATFORM_ARCH=amd64 docker build --build-arg PY="$PY" --platform=linux/${PLATFORM_ARCH} --build-arg ALPINE=3.18 -t pactfoundation:python${PY} -f docker/Dockerfile .)
```

You can official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images by using the `docker/Dockerfile.debian` Dockerfile

```bash
(PY=3.11 PLATFORM_ARCH=amd64 docker build --build-arg PY="$PY" --platform=linux/${PLATFORM_ARCH} -t pactfoundation:python${PY} -f docker/Dockerfile.debian .)
```

To then run the tests and exit:

```bash
docker run -it --rm -v "$(pwd)":/home pactfoundation:python3.11
```

If you need to debug you can change the command to:

```bash
docker run -it --rm -v "$(pwd)":/home pactfoundation:python3.11 sh
```

This will open a container with a prompt. From the `/home` location in the
container you can run the same tests manually:

```bash
hatch run test
```

You can also run convenience script to build and run:

```bash
docker/build.sh 3.11
```

where `3.11` is the python environment version.

and run it with

```bash
docker/run.sh 3.11
```

Run it with no arguments to see the current help file

```console
Usage: docker/build.sh PYTHON_VERSION [PLATFORM_ARCH] [OS] [OS_VERSION]

Example:
docker/build.sh 3.11                   Build using Python 3.11, default Alpine 3.17
docker/build.sh 3.9 arm64              Build using Python 3.9, Platform arch arm64, OS Alpine, OS Version 3.17
docker/build.sh 3.9 arm64 debian       Build using Python 3.9, Platform arch arm64, OS Debian, OS Version bookworm
docker/build.sh 3.9 amd64 alpine 3.17  Build using Python 3.9, Platform arch amd64, OS Alpine, OS Version 3.17
debian uses official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images
```

## Building

Usage

```bash
docker/build.sh PYTHON_VERSION [PLATFORM_ARCH] [OS] [OS_VERSION]
```

Defaults

```bash
docker/build.sh 3.11 amd64 alpine 3.17
```

Use official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images

```bash
docker/build.sh 3.11 amd64 debian
```

Build arm64

```bash
docker/build.sh 3.11 arm64 debian
```

## Running

Usage

```bash
docker/run.sh PYTHON_VERSION [PLATFORM_ARCH] [OS] [OS_VERSION]
```

Defaults

```bash
docker/run.sh 3.11 amd64 alpine 3.17
```

Use official https://hub.docker.com/_/python [PYTHON_VERSION]-slim images

```bash
docker/run.sh 3.11 amd64 debian
```

Build arm64

```bash
docker/run.sh 3.11 arm64 debian
```

## Cleaning up

When you volume mount the current working directors as per the instructions above, they will conflict
if you switch container os's/versions or clash with your local runs.

To clear out files covered by the `.gitignore` file, you can run the following to see what would be
removed

```sh
git clean -fdxn
```

and remove them all with

```sh
git clean -fdx
```
