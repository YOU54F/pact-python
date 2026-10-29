"""
V4 plugin scenarios from the Pact compatibility suite.

The plugin features are not yet part of the compatibility suite submodule, so
they are loaded from an external checkout of the suite given by the
`PACT_COMPAT_SUITE` environment variable (the root of the suite, containing
`features/` and `fixtures/`). If it is unset, or the plugin features are
missing, this module is skipped.

The scenarios need the plugins they reference installed in `~/.pact/plugins`
(or `PACT_PLUGIN_DIR`); scenarios tagged `@wip` are not collected.
"""

from __future__ import annotations

import base64
import contextlib
import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import threading
import time
from concurrent import futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytest
import requests
from pytest_bdd import given, parsers, scenario, then, when
from pytest_bdd.feature import get_features

import pact_ffi
from pact import Pact
from pact.verifier import Verifier

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

_SUITE_ENV = os.environ.get("PACT_COMPAT_SUITE")
SUITE_ROOT = Path(_SUITE_ENV) if _SUITE_ENV else None
FEATURES_DIR = SUITE_ROOT / "features" / "V4" / "plugins" if SUITE_ROOT else None

if FEATURES_DIR is None or not FEATURES_DIR.is_dir():
    pytest.skip(
        "PACT_COMPAT_SUITE is not set to a compatibility suite with V4 plugin features",
        allow_module_level=True,
    )

assert SUITE_ROOT is not None
FIXTURES_DIR = SUITE_ROOT / "fixtures"
TIMEOUT = 10


################################################################################
## Scenario collection
################################################################################


def _register_scenarios() -> None:
    """
    Generate a test function for each non-WIP scenario in the plugin features.
    """
    assert FEATURES_DIR is not None
    seen: set[str] = set()
    for feature in get_features([str(FEATURES_DIR)]):
        if "wip" in feature.tags:
            continue
        for name, template in feature.scenarios.items():
            if "wip" in template.tags:
                continue
            slug = re.sub(r"\W+", "_", f"{Path(feature.filename).stem} {name}")
            test_name = f"test_{slug.strip('_').lower()}"
            while test_name in seen:
                test_name += "_"
            seen.add(test_name)

            def _test() -> None:
                """Scenario defined in the compatibility suite."""

            _test.__name__ = test_name
            globals()[test_name] = scenario(feature.filename, name)(_test)


_register_scenarios()


################################################################################
## World
################################################################################


@dataclass
class World:
    """
    State shared between the steps of a single scenario.
    """

    tmp: Path
    pact: Pact | None = None
    interactions: list[Any] = field(default_factory=list)
    installed: dict[str, str] = field(default_factory=dict)
    loaded: set[str] = field(default_factory=set)
    load_error: str | None = None
    server: pact_ffi.PactServerHandle | None = None
    matched: bool | None = None
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    pact_json: dict[str, Any] | None = None
    response: requests.Response | None = None
    tcp_reply: str | None = None
    grpc_reply: bytes | None = None
    grpc_status: str | None = None
    pact_files: list[Path] = field(default_factory=list)
    provider_port: int | None = None
    stoppers: list[Callable[[], None]] = field(default_factory=list)
    verified: bool | None = None
    output: str = ""
    results: dict[str, Any] = field(default_factory=dict)

    def new_pact(self) -> Pact:
        """
        Create the consumer Pact for the scenario.
        """
        self.pact = Pact("c", "p").with_specification("V4")
        self.loaded.clear()
        return self.pact

    def ensure_plugin(self, name: str) -> None:
        """
        Load a plugin into the Pact the first time it is used.
        """
        assert self.pact is not None
        if name not in self.loaded:
            self.pact.using_plugin(name, self.installed.get(name))
            self.loaded.add(name)

    @property
    def interaction(self) -> Any:  # noqa: ANN401
        """
        The interaction currently being defined.
        """
        assert self.interactions, "no interaction is being defined"
        return self.interactions[-1]

    def read_pact(self) -> dict[str, Any]:
        """
        Read the Pact file written by the scenario.
        """
        self.pact_json = json.loads((self.tmp / "c-p.json").read_text())
        return self.pact_json


@pytest.fixture
def world(tmp_path: Path) -> Generator[World, None, None]:
    """
    Provide the scenario state, and tear down anything the scenario started.
    """
    w = World(tmp=tmp_path)
    yield w
    for stop in reversed(w.stoppers):
        with contextlib.suppress(Exception):
            stop()
    w.server = None
    if w.pact is not None:
        with contextlib.suppress(Exception):
            pact_ffi.cleanup_plugins(w.pact._handle)  # noqa: SLF001


################################################################################
## Helpers
################################################################################


def plugin_contents(text: str) -> str:
    """
    Resolve `fixture:` references in plugin contents to absolute paths.
    """
    return text.replace('"fixture:', f'"{FIXTURES_DIR}/')


def body_cell(text: str) -> bytes:
    """
    Resolve a `file: ...` cell to the fixture bytes, or use the text as is.
    """
    if text.startswith("file: "):
        return (FIXTURES_DIR / text.removeprefix("file: ")).read_bytes()
    return text.encode()


def table_rows(datatable: list[list[str]]) -> list[dict[str, str]]:
    """
    Convert a Gherkin data table with a header row into a list of dicts.
    """
    header, *rows = datatable
    return [dict(zip(header, row, strict=True)) for row in rows]


def plugin_dir() -> Path:
    """
    Directory plugins are installed into.
    """
    env = os.environ.get("PACT_PLUGIN_DIR")
    return Path(env) if env else Path.home() / ".pact" / "plugins"


def first_interaction(world: World) -> dict[str, Any]:
    """
    First interaction of the Pact file read by the scenario.
    """
    assert world.pact_json is not None, "no Pact file has been read"
    return world.pact_json["interactions"][0]


def part_of(interaction: dict[str, Any], part: str) -> dict[str, Any]:
    """
    Part of an interaction: `contents` is the interaction itself.
    """
    if part == "contents":
        return interaction
    value = interaction[part]
    if isinstance(value, list):
        return value[0]
    return value


def part_contents(part: dict[str, Any]) -> dict[str, Any]:
    """
    The body (HTTP) or contents (message) of a part.
    """
    return part["contents"] if "contents" in part else part["body"]


def start_thread_server(world: World, server: socketserver.BaseServer) -> int:
    """
    Serve a socketserver on a background thread, stopped at teardown.
    """
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def stop() -> None:
        server.shutdown()
        server.server_close()

    world.stoppers.append(stop)
    return server.server_address[1]  # type: ignore[return-value]


def connect(port: int) -> socket.socket:
    """
    Connect to a local port, falling back to IPv6 loopback.
    """
    try:
        return socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT)
    except OSError:
        return socket.create_connection(("::1", port), timeout=TIMEOUT)


def grpc_call(port: int, method: str, data: bytes) -> tuple[str, bytes | None]:
    """
    Make a raw unary gRPC call, returning the status name and response bytes.
    """
    grpc = pytest.importorskip("grpc")
    status, reply = "UNAVAILABLE", None
    for target in (f"127.0.0.1:{port}", f"[::1]:{port}"):
        with grpc.insecure_channel(target) as channel:
            call = channel.unary_unary(method)
            try:
                reply = call(data, timeout=TIMEOUT)
            except grpc.RpcError as e:
                status = e.code().name
            else:
                return "OK", reply
        if status != "UNAVAILABLE":
            break
    return status, reply


def run_verifier(world: World, transport: str | None = None) -> None:
    """
    Verify the scenario's Pact files against the provider.
    """
    port = world.provider_port
    assert port is not None, "no provider started"
    verifier = Verifier("p", host="127.0.0.1")
    verifier.add_transport(protocol="http", port=port, path="/", scheme="http")
    if transport:
        scheme = "http" if transport == "grpc" else "tcp"
        verifier.add_transport(protocol=transport, port=port, scheme=scheme)
    for file in world.pact_files:
        verifier.add_source(file)
    try:
        verifier.verify()
    except RuntimeError:
        world.verified = False
    else:
        world.verified = True
    world.output = verifier.output(strip_ansi=True)
    world.results = verifier.results


################################################################################
## Given
################################################################################


@given(
    parsers.re(
        r'the "(?P<name>[^"]*)" plugin version "(?P<version>[^"]*)" is installed'
    )
)
def plugin_installed(world: World, name: str, version: str) -> None:
    """
    Check a plugin version is installed, and remember the version.
    """
    path = plugin_dir() / f"{name}-{version}"
    if not path.is_dir():
        pytest.skip(f"plugin {name} {version} is not installed in {path.parent}")
    world.installed[name] = version


@given(parsers.re(r'the "(?P<name>[^"]*)" plugin is not installed'))
def plugin_not_installed(name: str) -> None:
    """
    Check no version of a plugin is installed.
    """
    root = plugin_dir()
    found = root.is_dir() and any(p.name.startswith(f"{name}-") for p in root.iterdir())
    assert not found, f"plugin {name} is installed"


@given("an HTTP interaction is being defined for a consumer test")
def http_interaction(world: World) -> None:
    """
    Start a new HTTP interaction in a new Pact.
    """
    world.interactions.append(world.new_pact().upon_receiving("plugin interaction 1"))


@given("another HTTP interaction is being defined for the same consumer test")
def another_http_interaction(world: World) -> None:
    """
    Start another HTTP interaction in the same Pact.
    """
    assert world.pact is not None
    n = len(world.interactions) + 1
    world.interactions.append(world.pact.upon_receiving(f"plugin interaction {n}"))


@given(parsers.re(r'the HTTP request is "(?P<method>[^"]*)" "(?P<path>[^"]*)"'))
def http_request(world: World, method: str, path: str) -> None:
    """
    Set the request method and path.
    """
    world.interaction.with_request(method, path)


@given(
    parsers.re(
        r'the HTTP (?P<part>request|response) body is set with the "(?P<name>[^"]*)"'
        r' plugin for "(?P<content_type>[^"]*)" with:'
    )
)
def http_body_plugin(
    world: World,
    part: str,
    name: str,
    content_type: str,
    docstring: str,
) -> None:
    """
    Set a request or response body using a plugin.
    """
    world.ensure_plugin(name)
    world.interaction.with_plugin_contents(
        plugin_contents(docstring),
        content_type,
        part="Request" if part == "request" else "Response",
    )


@given(
    parsers.re(
        r'the HTTP response body is "(?P<body>[^"]*)"'
        r' with content type "(?P<content_type>[^"]*)"'
    )
)
def http_response_body(world: World, body: str, content_type: str) -> None:
    """
    Set a plain response body.
    """
    world.interaction.with_body(body_cell(body).decode(), content_type, part="Response")


@given("a message interaction is being defined for a consumer test")
def message_interaction(world: World) -> None:
    """
    Start a new asynchronous message interaction in a new Pact.
    """
    world.interactions.append(
        world.new_pact().upon_receiving("plugin message 1", "Async")
    )


@given("a synchronous message interaction is being defined for a consumer test")
def sync_message_interaction(world: World) -> None:
    """
    Start a new synchronous message interaction in a new Pact.
    """
    world.interactions.append(
        world.new_pact().upon_receiving("plugin message 1", "Sync")
    )


@given(
    parsers.re(
        r'the (?:synchronous )?message contents are set with the "(?P<name>[^"]*)"'
        r' plugin for "(?P<content_type>[^"]*)" with:'
    )
)
def message_contents_plugin(
    world: World,
    name: str,
    content_type: str,
    docstring: str,
) -> None:
    """
    Set the message contents using a plugin.
    """
    world.ensure_plugin(name)
    world.interaction.with_plugin_contents(
        plugin_contents(docstring), content_type, part="Request"
    )


def _write_provider_pact(
    world: World,
    rows: list[dict[str, str]],
    define: Callable[[Pact, dict[str, str]], None],
) -> None:
    """
    Write a Pact file for the provider side, one interaction per table row.
    """
    pact = Pact("c", "p").with_specification("V4")
    for row in rows:
        plugin = row["plugin"]
        with contextlib.suppress(RuntimeError):
            pact.using_plugin(plugin, world.installed.get(plugin))
        define(pact, row)
    directory = world.tmp / f"provider-{len(world.pact_files)}"
    pact.write_file(directory, overwrite=True)
    pact_ffi.cleanup_plugins(pact._handle)  # noqa: SLF001
    world.pact_files.append(directory / "c-p.json")


@given(
    parsers.re(
        r'a Pact file with an HTTP "(?P<method>[^"]*)" "(?P<path>[^"]*)"'
        r" interaction with plugin contents:"
    )
)
def provider_http_pact(
    world: World,
    method: str,
    path: str,
    datatable: list[list[str]],
) -> None:
    """
    Write a Pact file with an HTTP interaction using plugin contents.
    """

    def define(pact: Pact, row: dict[str, str]) -> None:
        interaction = pact.upon_receiving("plugin interaction").with_request(
            method, path
        )
        part: Literal["Request", "Response"]
        for col, part in (("request", "Request"), ("response", "Response")):
            if row.get(col):
                interaction.with_plugin_contents(
                    plugin_contents(row[col]), row["content type"], part=part
                )

    _write_provider_pact(world, table_rows(datatable), define)


@given(
    parsers.re(
        r'a Pact file with a "(?P<description>[^"]*)"'
        r" (?P<kind>message|synchronous message) interaction"
        r'(?: over the "(?P<transport>[^"]*)" transport)? with plugin contents:'
    )
)
def provider_message_pact(
    world: World,
    description: str,
    kind: str,
    transport: str | None,
    datatable: list[list[str]],
) -> None:
    """
    Write a Pact file with a message interaction using plugin contents.
    """

    def define(pact: Pact, row: dict[str, str]) -> None:
        pact.upon_receiving(
            description, "Async" if kind == "message" else "Sync"
        ).with_plugin_contents(
            plugin_contents(row["contents"]), row["content type"], part="Request"
        )

    _write_provider_pact(world, table_rows(datatable), define)
    if transport:
        file = world.pact_files[-1]
        data = json.loads(file.read_text())
        data["interactions"][0]["transport"] = transport
        file.write_text(json.dumps(data))


@given(
    parsers.re(
        r'a provider is started that returns "(?P<body>[^"]*)"'
        r' with content type "(?P<content_type>[^"]*)"'
    )
)
def http_provider(world: World, body: str, content_type: str) -> None:
    """
    Start an HTTP provider returning a fixed body.
    """
    payload = body_cell(body)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _reply(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _reply  # noqa: N815

        def log_message(self, *_args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    world.provider_port = start_thread_server(world, server)


@given(
    parsers.re(
        r'a provider is started that can generate the "(?P<description>[^"]*)"'
        r' message with "(?P<body>[^"]*)" and content type'
        r' "(?P<content_type>[^"]*)"'
    )
)
def message_provider(
    world: World,
    description: str,
    body: str,
    content_type: str,
) -> None:
    """
    Start a message provider, answering the verifier's message requests.
    """
    payload = body_cell(body)
    metadata = base64.b64encode(
        json.dumps({"contentType": content_type}).encode()
    ).decode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                asked = json.loads(self.rfile.read(length) or b"{}").get("description")
            except ValueError:
                asked = None
            if asked == description:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Pact-Message-Metadata", metadata)
                data = payload
            else:
                self.send_response(404)
                data = f"no message {asked!r}".encode()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    world.provider_port = start_thread_server(world, server)


@given(
    parsers.re(
        r'a TCP provider is started that replies to "(?P<line>[^"]*)"'
        r' with "(?P<reply>[^"]*)"'
    )
)
def tcp_provider(world: World, line: str, reply: str) -> None:
    """
    Start a line-based TCP provider.
    """

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw in self.rfile:
                got = raw.decode().rstrip("\r\n")
                answer = reply if got == line else "MATTerrorMATT"
                self.wfile.write(f"{answer}\n".encode())
                self.wfile.flush()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    world.provider_port = start_thread_server(world, server)


@given(
    parsers.re(
        r'a gRPC provider is started that answers "(?P<method>[^"]*)"'
        r' with "(?P<body>[^"]*)"'
    )
)
def grpc_provider(world: World, method: str, body: str) -> None:
    """
    Start a gRPC provider answering a single method with fixed bytes.
    """
    grpc = pytest.importorskip("grpc")
    payload = body_cell(body)

    class Handler(grpc.GenericRpcHandler):
        def service(self, handler_call_details: Any) -> Any:  # noqa: ANN401
            if handler_call_details.method == method:
                return grpc.unary_unary_rpc_method_handler(lambda _req, _ctx: payload)
            return None

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    server.add_generic_rpc_handlers((Handler(),))
    world.provider_port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    world.stoppers.append(lambda: server.stop(None))


@given("no provider is listening")
def no_provider(world: World) -> None:
    """
    Pick a port that was free a moment ago.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        world.provider_port = s.getsockname()[1]


################################################################################
## When
################################################################################


@when(parsers.re(r'the "(?P<name>[^"]*)" plugin is loaded for the test'))
def load_plugin(world: World, name: str) -> None:
    """
    Load a plugin without a version.
    """
    _load_plugin(world, name, None)


@when(
    parsers.re(
        r'the "(?P<name>[^"]*)" plugin version "(?P<version>[^"]*)"'
        r" is loaded for the test"
    )
)
def load_plugin_version(world: World, name: str, version: str) -> None:
    """
    Load a specific plugin version.
    """
    _load_plugin(world, name, version)


def _load_plugin(world: World, name: str, version: str | None) -> None:
    assert world.pact is not None
    try:
        world.pact.using_plugin(name, version)
    except RuntimeError as e:
        # The FFI only returns an error code; the detail (such as the
        # requested version) is in the last error message.
        world.load_error = f"{e} {pact_ffi.get_error_message() or ''}"


@when("the Pact file for the test is generated")
def pact_file_generated(world: World) -> None:
    """
    Write the consumer Pact file and read it back.
    """
    assert world.pact is not None
    world.pact.write_file(world.tmp, overwrite=True)
    world.read_pact()


@when("the plugins are cleaned up")
def plugins_cleaned_up(world: World) -> None:
    """
    Shut down the plugins used by the Pact.
    """
    assert world.pact is not None
    pact_ffi.cleanup_plugins(world.pact._handle)  # noqa: SLF001


def _start_mock_server(world: World, transport: str) -> None:
    assert world.pact is not None
    world.server = pact_ffi.create_mock_server_for_transport(
        world.pact._handle,  # noqa: SLF001
        "127.0.0.1",
        0,
        transport,
        None,
    )


@when(
    parsers.re(
        r"the mock server is started with"
        r" (?:the plugin interaction|all the interactions)"
    )
)
def mock_server_started(world: World) -> None:
    """
    Start an HTTP mock server for the Pact.
    """
    _start_mock_server(world, "http")


@when(parsers.re(r'a mock server is started for the "(?P<transport>[^"]*)" transport'))
def transport_mock_server_started(world: World, transport: str) -> None:
    """
    Start a mock server for a plugin-provided transport.
    """
    _start_mock_server(world, transport)


@when(
    parsers.re(
        r'a "(?P<method>[^"]*)" request is made to "(?P<path>[^"]*)"'
        r'(?: with content type "(?P<content_type>[^"]*)"'
        r' and body "(?P<body>[^"]*)")?'
    )
)
def request_made(
    world: World,
    method: str,
    path: str,
    content_type: str | None,
    body: str | None,
) -> None:
    """
    Make a request to the HTTP mock server.
    """
    assert world.server is not None
    world.response = requests.request(
        method,
        f"http://127.0.0.1:{world.server.port}{path}",
        data=body_cell(body) if body is not None else None,
        headers={"Content-Type": content_type} if content_type else None,
        timeout=TIMEOUT,
    )


@when(parsers.re(r'the line "(?P<line>[^"]*)" is sent to the mock server over TCP'))
def tcp_line_sent(world: World, line: str) -> None:
    """
    Send a line to the mock server and read one line back.
    """
    assert world.server is not None
    try:
        with connect(world.server.port) as s:
            s.sendall(f"{line}\n".encode())
            with s.makefile("rb") as f:
                world.tcp_reply = f.readline().decode().rstrip("\r\n") or None
    except OSError:
        world.tcp_reply = None


@when(
    parsers.re(
        r'the gRPC method "(?P<method>[^"]*)" is called on the mock server'
        r'(?: with "(?P<body>[^"]*)"| with an empty message)'
    )
)
def grpc_method_called(world: World, method: str, body: str | None) -> None:
    """
    Call a gRPC method on the mock server.
    """
    assert world.server is not None
    data = body_cell(body) if body is not None else b""
    world.grpc_status, world.grpc_reply = grpc_call(world.server.port, method, data)


@when("the pact test is done")
def pact_test_done(world: World) -> None:
    """
    Record the mock server results, write the Pact file and shut it down.
    """
    assert world.server is not None
    world.matched = pact_ffi.mock_server_matched(world.server)
    world.mismatches = pact_ffi.mock_server_mismatches(world.server)
    if world.matched:
        pact_ffi.write_pact_file(world.server, world.tmp, overwrite=True)
        world.read_pact()
    # Dropping the handle shuts down the mock server.
    world.server = None


@when("the verification is run")
def verification_run(world: World) -> None:
    """
    Run the verifier against the HTTP provider.
    """
    run_verifier(world)


@when(parsers.re(r'the verification is run with the "(?P<transport>[^"]*)" transport'))
def transport_verification_run(world: World, transport: str) -> None:
    """
    Run the verifier over a plugin-provided transport.
    """
    run_verifier(world, transport)


################################################################################
## Then
################################################################################


@then(
    parsers.re(
        r'loading the plugin will fail with an error that mentions "(?P<text>[^"]*)"'
    )
)
def load_failed(world: World, text: str) -> None:
    """
    Check the plugin failed to load with an informative error.
    """
    assert world.load_error is not None, "the plugin loaded"
    assert text in world.load_error, world.load_error


@then("the test will not have panicked")
def not_panicked(world: World) -> None:
    """
    Check the failure was reported as an error rather than a panic.
    """
    assert "panic" not in (world.load_error or "").lower(), world.load_error


@then("a 200 success response is returned")
def success_response(world: World) -> None:
    """
    Check the mock server responded successfully.
    """
    assert world.response is not None
    assert world.response.status_code == 200, world.response.text


@then(parsers.re(r'the response body will be "(?P<body>[^"]*)"'))
def response_body(world: World, body: str) -> None:
    """
    Check the mock server response body.
    """
    assert world.response is not None
    expected = body_cell(body)
    actual = world.response.content
    if actual != expected:
        assert json.loads(actual) == json.loads(expected)


@then(parsers.re(r'the line "(?P<line>[^"]*)" will be received from the mock server'))
def tcp_line_received(world: World, line: str) -> None:
    """
    Check the line returned by the TCP mock server.
    """
    assert world.tcp_reply == line


@then(parsers.re(r'the gRPC call will return "(?P<body>[^"]*)"'))
def grpc_returned(world: World, body: str) -> None:
    """
    Check the gRPC call succeeded with the expected message.
    """
    assert world.grpc_status == "OK", world.grpc_status
    assert world.grpc_reply == body_cell(body)


@then(parsers.re(r'the gRPC call will fail with status "(?P<status>[^"]*)"'))
def grpc_failed(world: World, status: str) -> None:
    """
    Check the gRPC call failed with the given status.
    """
    assert world.grpc_status == status


@then(parsers.re(r"the mock server status will be (?P<status>OK|mismatches)"))
def mock_server_status(world: World, status: str) -> None:
    """
    Check whether the mock server matched all requests.
    """
    if status == "OK":
        assert world.matched, world.mismatches
    else:
        assert not world.matched
        assert world.mismatches


def _strings(value: object) -> Generator[str, None, None]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


@then(
    parsers.re(r'the mismatches will contain a mismatch with error "(?P<error>[^"]*)"')
)
def mismatch_with_error(world: World, error: str) -> None:
    """
    Check a mismatch mentions the error.
    """
    assert any(error in s for s in _strings(world.mismatches)), world.mismatches


@then("the mock server will write out a Pact file for the interaction when done")
def mock_server_wrote_pact(world: World) -> None:
    """
    Check the mock server wrote a Pact file.
    """
    assert world.pact_json is not None
    assert len(world.pact_json["interactions"]) == 1


@then(
    parsers.re(
        r'the Pact file metadata will list the "(?P<name>[^"]*)" plugin'
        r' with version "(?P<version>[^"]*)"'
    )
)
def metadata_lists_plugin(world: World, name: str, version: str) -> None:
    """
    Check the Pact metadata lists the plugin.
    """
    assert world.pact_json is not None
    plugins = world.pact_json["metadata"].get("plugins", [])
    assert any(
        p.get("name") == name and p.get("version") == version for p in plugins
    ), plugins


@then(
    parsers.re(
        r'the first interaction in the Pact file will have a type of "(?P<kind>[^"]*)"'
    )
)
def interaction_type(world: World, kind: str) -> None:
    """
    Check the interaction type.
    """
    assert first_interaction(world)["type"] == kind


@then(
    parsers.re(
        r'the first interaction in the Pact file will have "(?P<key>[^"]*)"'
        r" = '(?P<value>.*)'"
    )
)
def interaction_has_value(world: World, key: str, value: str) -> None:
    """
    Check a value of the interaction.

    Transports are compared by name, as some implementations record them as
    `transport/<name>`.
    """
    expected = json.loads(value)
    actual = first_interaction(world).get(key)
    if key == "transport" and isinstance(actual, str):
        actual = actual.rsplit("/", 1)[-1]
    assert actual == expected


@then(
    parsers.re(
        r"the first interaction in the pact file (?P<part>request|response|contents)"
        r' content type will be "(?P<content_type>[^"]*)"'
    )
)
def part_content_type(world: World, part: str, content_type: str) -> None:
    """
    Check the content type of an interaction part.
    """
    contents = part_contents(part_of(first_interaction(world), part))
    assert contents["contentType"] == content_type, contents


@then(
    parsers.re(
        r"the first interaction in the pact file (?:(?P<part>request|response) )?"
        r'contents will be "(?P<expected>[^"]*)"'
    )
)
def part_contents_value(world: World, part: str | None, expected: str) -> None:
    """
    Check the contents of an interaction part.

    If no part is given, the message contents are checked.
    """
    contents = part_contents(part_of(first_interaction(world), part or "contents"))
    value = contents["content"]
    if contents.get("encoded") == "base64":
        value = base64.b64decode(value).decode()
    assert value == expected


@then(
    parsers.re(
        r"the first interaction in the pact file will have plugin configuration"
        r' for "(?P<name>[^"]*)"'
    )
)
def has_plugin_configuration(world: World, name: str) -> None:
    """
    Check the interaction has plugin configuration.
    """
    config = first_interaction(world).get("pluginConfiguration") or {}
    assert name in config, config


@then("the second interaction in the pact file will not have plugin configuration")
def second_has_no_plugin_configuration(world: World) -> None:
    """
    Check the second interaction has no plugin configuration.
    """
    assert world.pact_json is not None
    assert not world.pact_json["interactions"][1].get("pluginConfiguration")


@then(parsers.re(r"the pact file will contain (?P<n>\d+) interactions"))
def interaction_count(world: World, n: str) -> None:
    """
    Check the number of interactions.
    """
    assert world.pact_json is not None
    assert len(world.pact_json["interactions"]) == int(n)


@then(
    parsers.re(
        r"the first interaction in the pact file will contain (?P<n>\d+)"
        r" response messages?"
    )
)
def response_message_count(world: World, n: str) -> None:
    """
    Check the number of response messages.
    """
    assert len(first_interaction(world)["response"]) == int(n)


@then(
    parsers.re(
        r"the first interaction (?P<part>request|response|contents) in the pact file"
        r' will have a matching rule for "(?P<key>[^"]*)" of type "(?P<rule>[^"]*)"'
    )
)
def has_matching_rule(world: World, part: str, key: str, rule: str) -> None:
    """
    Check a body matching rule on an interaction part.
    """
    rules = part_of(first_interaction(world), part).get("matchingRules", {})
    matchers = rules.get("body", {}).get(key, {}).get("matchers", [])
    assert any(m.get("match") == rule for m in matchers), rules


@then(parsers.re(r'no "(?P<name>[^"]*)" plugin process will still be running'))
def no_plugin_process(name: str) -> None:
    """
    Check the plugin process has exited.
    """
    pattern = f"{plugin_dir()}/{name}-"
    deadline = time.monotonic() + TIMEOUT
    while True:
        running = subprocess.run(  # noqa: S603
            ["pgrep", "-f", pattern],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if running.returncode != 0:
            return
        if time.monotonic() > deadline:
            pytest.fail(f"{name} plugin still running: {running.stdout.decode()}")
        time.sleep(0.2)


@then("the verification will be successful")
def verification_successful(world: World) -> None:
    """
    Check the verification passed.
    """
    assert world.verified, world.output
    assert world.results.get("result") is True, world.output


@then("the verification will NOT be successful")
def verification_not_successful(world: World) -> None:
    """
    Check the verification failed.
    """
    assert world.verified is False, world.output


@then(parsers.re(r'the verification results will contain a "(?P<error>[^"]*)" error'))
def verification_error(world: World, error: str) -> None:
    """
    Check the verification results contain a mismatch of the given kind.
    """
    kinds = {
        "Body had differences": {"BodyMismatch", "BodyTypeMismatch"},
        "Metadata had differences": {"MetadataMismatch"},
    }.get(error, {error})
    found = {
        m.get("type")
        for result in world.results.get("interactionResults", [])
        for m in (result.get("mismatch") or {}).get("mismatches", [])
    }
    assert found & kinds, (found, world.output)


@then(parsers.re(r'the verification output will contain "(?P<text>[^"]*)"'))
def verification_output(world: World, text: str) -> None:
    """
    Check the verification output mentions the text.
    """
    assert text in world.output, world.output
