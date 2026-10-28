"""
Repeated request header matching by the mock server.

[RFC 9110 §5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3)
allows a header which is repeated over several field lines to be combined into
a single comma-separated line. The mock server must therefore treat the
following requests as equivalent, unless the header's values cannot be joined
(as with `Content-Type`):

```http
X-Request: a
X-Request: b
```

```http
X-Request: a, b
```

HTTP clients merge, reorder or reject repeated header lines, so these tests
write the request to a raw socket to control exactly which field lines reach
the mock server.
"""

from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING

import pytest

from pact import Pact, match

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pact.match.matcher import AbstractMatcher
    from pact.pact import PactServer

RFC_9110_WARNING = "RFC 9110 §5.3"
"""
Marker in the warning logged when field lines only match one at a time.
"""

LINK_A = '<https://a.example/x,y>; rel="a"'
LINK_B = '<https://b.example/>; rel="b"'


def first_n(example: str) -> AbstractMatcher[str]:
    """
    Regex matcher for values of the form `first-<digits>`.
    """
    return match.regex(example, regex=r"^first-\d+$")


def send_raw_request(srv: PactServer, header: str, lines: Sequence[str]) -> int:
    """
    Send `GET /headers` with each value in `lines` as its own field line.

    Args:
        srv:
            Running mock server.

        header:
            Name of the repeated header.

        lines:
            Values of the header, one per field line, in order.

    Returns:
        The response status code.
    """
    assert srv.port is not None
    request = (
        "GET /headers HTTP/1.1\r\n"
        f"Host: {srv.host}:{srv.port}\r\n"
        "Connection: close\r\n"
        + "".join(f"{header}: {line}\r\n" for line in lines)
        + "\r\n"
    )
    with socket.create_connection((srv.host, srv.port)) as conn:
        conn.sendall(request.encode())
        with conn.makefile("rb") as response:
            status_line = response.readline().decode()
    return int(status_line.split(" ")[1])


def rfc_9110_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """
    Messages of the RFC 9110 §5.3 warnings forwarded from the FFI.
    """
    return [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("pact.ffi")
        and record.levelno == logging.WARNING
        and RFC_9110_WARNING in record.getMessage()
    ]


@pytest.mark.parametrize(
    ("header", "expected", "lines", "matches"),
    [
        pytest.param(
            "X-Request",
            ["a", "b"],
            ["a", "b"],
            True,
            id="H1-separate-lines",
        ),
        pytest.param(
            "X-Request",
            ["a", "b"],
            ["a, b"],
            True,
            id="H2-combined-line",
        ),
        pytest.param(
            "X-Sunset",
            ["Sat, 01 Jan 2028 00:00:00 GMT", "Sun, 02 Jan 2028 00:00:00 GMT"],
            ["Sat, 01 Jan 2028 00:00:00 GMT", "Sun, 02 Jan 2028 00:00:00 GMT"],
            True,
            id="H3-values-with-commas-separate-lines",
        ),
        pytest.param(
            "Content-Type",
            ["text/plain", "text/html"],
            ["text/plain, text/html"],
            False,
            id="H4-content-type-combined-line",
        ),
        pytest.param(
            "Cache-Control",
            ["no-cache", "no-store"],
            ["no-cache, no-store"],
            True,
            id="H5-cache-control-combined-line",
        ),
        pytest.param(
            "Link",
            [LINK_A, LINK_B],
            [LINK_A, LINK_B],
            True,
            id="H8a-link-separate-lines",
        ),
        pytest.param(
            "Link",
            [LINK_A, LINK_B],
            [f"{LINK_A}, {LINK_B}"],
            True,
            id="H8b-link-combined-line",
        ),
    ],
)
def test_repeated_request_header(
    header: str,
    expected: Sequence[str],
    lines: Sequence[str],
    matches: bool,  # noqa: FBT001
) -> None:
    pact = Pact("consumer", "provider")
    interaction = pact.upon_receiving(f"a request with a repeated {header} header")
    interaction.with_request("GET", "/headers")
    for value in expected:
        interaction.with_header(header, value)
    interaction.will_respond_with(200)

    with pact.serve(raises=False) as srv:
        status = send_raw_request(srv, header, lines)
        mismatches = srv.mismatches

    if matches:
        assert status == 200
        assert mismatches == []
    else:
        assert status != 200
        assert mismatches


def test_repeated_request_header_matcher_per_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    H6a: each field line is matched by the matcher at its own index.
    """
    pact = Pact("consumer", "provider")
    (
        pact
        .upon_receiving("a request with a matcher per repeated header value")
        .with_request("GET", "/headers")
        .with_header("X-Request", first_n("first-1"))
        .with_header("X-Request", first_n("first-2"))
        .will_respond_with(200)
    )

    with pact.serve(raises=False) as srv:
        status = send_raw_request(srv, "X-Request", ["first-42", "first-99"])
        mismatches = srv.mismatches

    assert status == 200
    assert mismatches == []
    assert rfc_9110_warnings(caplog) == []


def test_repeated_request_header_per_line_fallback_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    H6b: a match only found by comparing field lines one at a time is logged.

    The expected `"x , y"` differs from the sent `"x, y"` only in whitespace
    inside a quoted string, so the values only match when the field lines are
    compared one at a time rather than joined.
    """
    pact = Pact("consumer", "provider")
    (
        pact
        .upon_receiving("a request with a quoted repeated header value")
        .with_request("GET", "/headers")
        .with_header("X-Request", '"x , y"')
        .with_header("X-Request", "z")
        .will_respond_with(200)
    )

    with pact.serve(raises=False) as srv:
        status = send_raw_request(srv, "X-Request", ['"x, y"', "z"])
        mismatches = srv.mismatches

    assert status == 200
    assert mismatches == []
    warnings = rfc_9110_warnings(caplog)
    assert len(warnings) == 1
    assert "compared one at a time" in warnings[0]
