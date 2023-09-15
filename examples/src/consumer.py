"""
Pact consumer testing implementation.

This modules defines a simple
[consumer](https://docs.pact.io/getting_started/terminology#service-consumer)
with Pact. As Pact is a consumer-driven framework, the consumer defines the
contract which the provider must then satisfy.

The consumer is the application which makes requests to another service (the
provider) and receives a response to process. In this example, we have a simple
[`User`](User) class and the consumer fetches a user's information from a HTTP
endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any

import requests


@dataclass()
class User:
    """User data class."""

    id: int  # noqa: A003
    name: str
    created_on: datetime

    def __repr__(self) -> str:
        """Return the user's name."""
        return f"User({self.id}:{self.name})"


class UserConsumer:
    """
    Example consumer.

    This class defines a simple consumer which will interact with a provider
    over HTTP to fetch a user's information, and then return an instance of the
    [`User`](User) class.
    """

    def __init__(self, base_uri: str) -> None:
        """
        Initialise the consumer.

        Args:
            base_uri: The uri of the provider to test.
        """
        self.base_uri = base_uri

    def get_user(self, user_id: int) -> User | dict[str, str]:
        """
        Fetch a user by ID from the server.

        Args:
            user_id: The ID of the user to fetch.

        Returns:
            The user if found.

            In all other cases, an error dictionary is returned with the key
            `error` and the value as the error message.

        Raises:
            requests.HTTPError: If the server returns a non-200 response.
        """
        uri = f"{self.base_uri}/users/{user_id}"
        response = requests.get(uri, timeout=5)
        if response.status_code == HTTPStatus.NOT_FOUND:
            return {"error": "User not found"}

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            return {"error": str(error)}

        try:
            data: dict[str, Any] = response.json()
            return User(
                id=data["id"],
                name=data["name"],
                created_on=datetime.fromisoformat(data["created_on"]),
            )
        except (KeyError, ValueError) as error:
            return {"error": str(error)}
