"""
Tests for matchers combined with a logical OR.

These require a Pact FFI with support for the `pact:matcher:combine`
integration JSON attribute (pact-reference#601).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import requests

from pact import Pact, match
from pact.error import RequestMismatch
from pact.match.matcher import (
    IntegrationJSONEncoder,
    MatchingRuleJSONEncoder,
    OrMatcher,
)

if TYPE_CHECKING:
    from pathlib import Path

UUID = "e1d6e6a8-3f0a-4d5e-9c8b-6f3a2d1c0b9a"


def integration_json(value: object) -> Any:  # noqa: ANN401
    return json.loads(json.dumps(value, cls=IntegrationJSONEncoder))


def matching_rule(value: object) -> Any:  # noqa: ANN401
    return json.loads(json.dumps(value, cls=MatchingRuleJSONEncoder))


class TestIntegrationJson:
    """Integration JSON and matching rules emitted for OR matchers."""

    def test_any_of(self) -> None:
        assert integration_json(match.any_of(match.str("Fred"), match.null())) == {
            "pact:matcher:type": [
                {"pact:matcher:type": "type", "value": "Fred"},
                {"pact:matcher:type": "null"},
            ],
            "pact:matcher:combine": "OR",
            "value": "Fred",
        }

    def test_or_operator(self) -> None:
        assert integration_json(match.str("Fred") | match.null()) == integration_json(
            match.any_of(match.str("Fred"), match.null())
        )

    def test_alternative_attributes_are_kept(self) -> None:
        result = integration_json(
            match.any_of(match.regex("123", regex=r"^\d+$"), match.uuid())
        )
        assert result["pact:matcher:type"][0] == {
            "pact:matcher:type": "regex",
            "regex": r"^\d+$",
            "value": "123",
        }
        assert result["pact:matcher:type"][1]["pact:matcher:type"] == "regex"
        assert result["value"] == "123"

    def test_flattened(self) -> None:
        nested = match.any_of(
            match.int(1) | match.null(),
            match.any_of(match.str("a"), match.bool(True)),
        )
        chained = match.int(1) | match.null() | match.str("a") | match.bool(True)
        for matcher in (nested, chained):
            result = integration_json(matcher)
            assert [m["pact:matcher:type"] for m in result["pact:matcher:type"]] == [
                "integer",
                "null",
                "type",
                "boolean",
            ]
            assert result["value"] == 1

    def test_value_inferred_from_first_matcher_with_value(self) -> None:
        result = integration_json(match.null() | match.int(42))
        assert result["value"] == 42

    def test_explicit_value(self) -> None:
        result = integration_json(match.any_of(match.int(1), match.null(), value=None))
        assert result["value"] is None

    def test_no_value(self) -> None:
        result = integration_json(match.null() | match.uuid())
        assert "value" not in result

    def test_nullable_matcher(self) -> None:
        assert integration_json(match.nullable(match.int(42))) == {
            "pact:matcher:type": [
                {"pact:matcher:type": "integer", "value": 42},
                {"pact:matcher:type": "null"},
            ],
            "pact:matcher:combine": "OR",
            "value": 42,
        }

    def test_nullable_object(self) -> None:
        result = integration_json(
            match.nullable({"street": "Main St", "number": match.int(42)})
        )
        assert result == {
            "pact:matcher:type": [
                {"pact:matcher:type": "type"},
                {"pact:matcher:type": "null"},
            ],
            "pact:matcher:combine": "OR",
            "value": {
                "street": "Main St",
                "number": {"pact:matcher:type": "integer", "value": 42},
            },
        }

    def test_nullable_or_matcher_is_flattened(self) -> None:
        result = integration_json(match.nullable(match.int(1) | match.str("a")))
        assert [m["pact:matcher:type"] for m in result["pact:matcher:type"]] == [
            "integer",
            "type",
            "null",
        ]

    def test_nested_in_body(self) -> None:
        result = integration_json({"a": {"b": match.nullable(match.int(1))}})
        assert result["a"]["b"]["pact:matcher:combine"] == "OR"

    def test_matching_rule(self) -> None:
        assert matching_rule(match.any_of(match.int(1), match.null())) == {
            "combine": "OR",
            "matchers": [{"match": "integer", "value": 1}, {"match": "null"}],
        }

    def test_requires_two_alternatives(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            match.any_of(match.int(1))

    def test_rejects_non_matcher(self) -> None:
        with pytest.raises(TypeError, match="Expected a matcher"):
            OrMatcher(match.int(1), 2)  # type: ignore[arg-type]

    def test_rejects_matcher_value(self) -> None:
        with pytest.raises(TypeError, match="cannot be a matcher"):
            match.any_of(match.int(1), match.null(), value=match.int(2))

    def test_rejects_and_inside_or(self) -> None:
        with pytest.raises(TypeError, match="AndMatcher"):
            match.any_of(match.int(1) & match.number(1), match.null())

    def test_rejects_or_inside_and(self) -> None:
        with pytest.raises(TypeError, match="OrMatcher"):
            match.int(1) & (match.int(1) | match.null())

    def test_or_with_non_matcher(self) -> None:
        with pytest.raises(TypeError):
            match.int(1) | 2  # type: ignore[operator]


@pytest.fixture
def pact() -> Pact:
    return Pact("or-consumer", "or-provider").with_specification("V4")


def _body_interaction(pact: Pact) -> None:
    (
        pact
        .upon_receiving("a request with nullable fields")
        .with_request("POST", "/users")
        .with_body(
            {
                "name": match.nullable(match.str("Fred")),
                "id": match.regex("123", regex=r"^\d+$") | match.uuid(),
                "address": match.nullable({
                    "street": match.str("Main St"),
                    "number": match.int(42),
                }),
            },
            "application/json",
        )
        .will_respond_with(200)
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"name": "Fred", "id": "123", "address": {"street": "x", "number": 1}},
            id="first-alternatives",
        ),
        pytest.param(
            {"name": None, "id": UUID, "address": None},
            id="second-alternatives",
        ),
    ],
)
def test_body_alternatives_match(pact: Pact, body: dict[str, Any]) -> None:
    _body_interaction(pact)
    with pact.serve() as srv:
        response = requests.post(f"{srv.url}/users", json=body, timeout=5)
        assert response.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"name": 1, "id": "123", "address": None},
            id="name-not-string-or-null",
        ),
        pytest.param(
            {"name": "Fred", "id": "abc", "address": None},
            id="id-not-digits-or-uuid",
        ),
        pytest.param(
            {"name": "Fred", "id": "123", "address": {"street": "x", "number": "1"}},
            id="nested-rule-still-applies",
        ),
    ],
)
def test_body_no_alternative_matches(pact: Pact, body: dict[str, Any]) -> None:
    _body_interaction(pact)
    with pact.serve(raises=False) as srv:
        response = requests.post(f"{srv.url}/users", json=body, timeout=5)
        assert response.status_code == 500
        assert len(srv.mismatches) == 1
        assert isinstance(srv.mismatches[0], RequestMismatch)


def test_pact_file_has_or_rules(pact: Pact, tmp_path: Path) -> None:
    _body_interaction(pact)
    with pact.serve() as srv:
        response = requests.post(
            f"{srv.url}/users",
            json={"name": "Fred", "id": "123", "address": None},
            timeout=5,
        )
        assert response.status_code == 200
    pact.write_file(tmp_path)

    contents = json.loads((tmp_path / "or-consumer-or-provider.json").read_text())
    rules = contents["interactions"][0]["request"]["matchingRules"]["body"]
    assert rules["$.name"] == {
        "combine": "OR",
        "matchers": [{"match": "type"}, {"match": "null"}],
    }
    assert rules["$.id"]["combine"] == "OR"
    assert [m["match"] for m in rules["$.id"]["matchers"]] == ["regex", "regex"]
    assert rules["$.address"] == {
        "combine": "OR",
        "matchers": [{"match": "type"}, {"match": "null"}],
    }
    assert rules["$.address.number"]["matchers"] == [{"match": "integer"}]


@pytest.mark.parametrize(
    ("value", "status"),
    [
        pytest.param("123", 200, id="digits"),
        pytest.param(UUID, 200, id="uuid"),
        pytest.param("abc", 500, id="neither"),
    ],
)
def test_header_alternatives(pact: Pact, value: str, status: int) -> None:
    (
        pact
        .upon_receiving("a request with an OR header")
        .with_request("GET", "/")
        .with_header("X-Id", match.regex("123", regex=r"^\d+$") | match.uuid())
        .will_respond_with(200)
    )
    with pact.serve(raises=False) as srv:
        response = requests.get(srv.url, headers={"X-Id": value}, timeout=5)
        assert response.status_code == status
        assert len(srv.mismatches) == (status != 200)


@pytest.mark.parametrize(
    ("value", "status"),
    [
        pytest.param("123", 200, id="digits"),
        pytest.param(UUID, 200, id="uuid"),
        pytest.param("abc", 500, id="neither"),
    ],
)
def test_query_alternatives(pact: Pact, value: str, status: int) -> None:
    (
        pact
        .upon_receiving("a request with an OR query parameter")
        .with_request("GET", "/")
        .with_query_parameter("id", match.regex("123", regex=r"^\d+$") | match.uuid())
        .will_respond_with(200)
    )
    with pact.serve(raises=False) as srv:
        response = requests.get(srv.url, params={"id": value}, timeout=5)
        assert response.status_code == status
        assert len(srv.mismatches) == (status != 200)
