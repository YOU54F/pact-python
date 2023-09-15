"""Test Pact consumer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator

import pytest
from pact import Consumer, Format, Like, Provider
from yarl import URL

from src.consumer import User, UserConsumer

if TYPE_CHECKING:
    from pact.pact import Pact

log = logging.getLogger(__name__)

MOCK_URL = URL("http://localhost:1234")
PACT_DIR = (Path(__file__).parent / "pacts").resolve()


@pytest.fixture()
def user_consumer() -> UserConsumer:
    """
    Returns an instance of the UserConsumer class.

    As we do not want to stand up all of the consumer's dependencies, we direct
    the consumer to use Pact's mock provider. This allows us to define what
    requests the consumer will make to the provider, and what responses the
    provider will return.
    """
    return UserConsumer(str(MOCK_URL))


@pytest.fixture(scope="module")
def pact(broker: URL) -> Generator[Pact, Any, None]:
    """
    Set up Pact.

    In order to test the consumer in isolation, Pact sets up a mock version of
    the provider. This mock provider will expect to receive defined requests
    and will respond with defined responses.

    The fixture here simply defines the Consumer and Provide, and sets up the
    mock provider. With each test, we define the expected request and response
    from the provider as follows:

    ```python
    pact.given("UserA exists and is not an admin") \
        .upon_receiving("A request for UserA") \
        .with_request("get", "/users/123") \
        .will_respond_with(200, body=Like(expected))
    ```
    """
    consumer = Consumer("UserServiceClient")
    pact = consumer.has_pact_with(
        Provider("UserService"),
        pact_dir=PACT_DIR,
        publish_to_broker=True,
        # Mock service configuration
        host_name=MOCK_URL.host,
        port=MOCK_URL.port,
        # Broker configuration
        broker_base_url=str(broker),
        broker_username=broker.user,
        broker_password=broker.password,
    )

    pact.start_service()
    yield pact
    pact.stop_service()


def test_get_existing_user(pact: Pact, user_consumer: UserConsumer) -> None:
    """
    Test request for an existing user.

    This test defines the expected request and response from the provider. The
    provider will be expected to return a response with a status code of 200,
    """
    expected: dict[str, Any] = {
        "id": Format().integer,
        "name": "Verna Hampton",
        "created_on": Format().iso_8601_datetime(),
    }

    pact.given("user 123 exists") \
        .upon_receiving("a request for user 123") \
        .with_request("get", "/users/123") \
        .will_respond_with(200, body=Like(expected))  # fmt: skip

    with pact:
        user = user_consumer.get_user(123)

        assert isinstance(user, User)
        assert user.name == "Verna Hampton"

        pact.verify()


def test_get_unknown_user(pact: Pact, user_consumer: UserConsumer) -> None:
    expected = {"error": "User not found"}

    pact.given("user 123 doesn't exist") \
        .upon_receiving("a request for user 123") \
        .with_request("get", "/users/123") \
        .will_respond_with(404, body=Like(expected))  # fmt: skip

    with pact:
        user = user_consumer.get_user(123)

        assert isinstance(user, dict)
        assert user["error"] == "User not found"

        pact.verify()
