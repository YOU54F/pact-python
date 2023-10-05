ARG PY
ARG OS_VERSION=3.17
FROM python:${PY}-alpine${OS_VERSION}

ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /home
 # following deps [gcompat libc6-compat bash] required only for pact-ruby-standalone.
RUN apk update \
    && apk upgrade \
    && apk add --no-cache --update gcc build-base linux-headers musl-locales libffi-dev gcompat libc6-compat bash \
    && pip install --progress-bar=off --upgrade pip \
    && pip install --progress-bar=off --upgrade psutil \
    && pip install --progress-bar=off --upgrade hatch

CMD ["sh", "-c", "python -m hatch run test"]
