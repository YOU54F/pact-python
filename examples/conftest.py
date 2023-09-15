"""
pytest configuration.

Pytest provides a number of ways to hook in to the tests. In this instance, we
use this to run the `pact-broker` container image.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Generator

import pytest
from testcontainers.compose import DockerCompose
from yarl import URL

EXAMPLE_DIR = Path(__file__).parent.resolve()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Define additional command lines to customise the examples."""
    parser.addoption(
        "--run-broker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Whether to run broker in this test or not. "
            "If disabled, the broker URL must be provided."
        ),
    )

    parser.addoption(
        "--broker-url",
        help=(
            "The URL of the broker to use. This option must be provided if "
            "--no-run-broker is used."
        ),
        type=str,
    )

    # parser.addoption(
    #     "--publish-pact",

    # parser.addoption(


@pytest.fixture(scope="session")
def broker(request: pytest.FixtureRequest) -> Generator[URL, Any, None]:
    """
    Fixture to run the Pact broker.

    If the Pact broker is being run from the container, it will be started and
    stopped automatically.

    Otherwise, it is assumed that the broker is already running and this checks
    that the broker URL has been provided.
    """
    run_broker: bool = request.config.getoption("--run-broker")
    broker_url: str | None = request.config.getoption("--broker-url")

    if run_broker and broker_url:
        msg = "The --run-broker and --broker-url options are mutually exclusive."
        raise ValueError(msg)

    if not run_broker and not broker_url:
        msg = "The --broker-url option must be provided if --no-run-broker is not used."
        raise ValueError(msg)

    # If we have been given a broker URL, there's nothing more to do here and we
    # can return early.
    if broker_url:
        yield URL(broker_url)
        return

    with DockerCompose(
        EXAMPLE_DIR,
        compose_file_name=["docker-compose.yml"],
        pull=True,
    ) as _:
        yield URL("http://pactbroker:pactbroker@localhost:9292")
    return
