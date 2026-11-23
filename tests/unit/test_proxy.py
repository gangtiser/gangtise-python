"""GANGTISE_PROXY and the hints on a connection that was never made (CLI v0.53.0).

Only GANGTISE_PROXY routes the SDK's requests: the standard proxy variables
(HTTPS_PROXY / HTTP_PROXY / ALL_PROXY) are often set for other traffic, and following
them changes the address the platform sees requests come from.
"""

from __future__ import annotations

import json
import shutil
import socket
import ssl
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config, load_config, resolve_proxy_url
from gangtise_openapi._download import download_to_path
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import (
    PROXY_AUTH_HINT,
    ApiError,
    ConfigError,
    DownloadError,
    connection_hint,
    failed_before_tunnel,
)
from gangtise_openapi._facade import _Facade
from gangtise_openapi._transport import (
    build_sync_client,
    is_retryable_error,
    is_transient_error,
    request_json,
)
from gangtise_openapi._transport_async import build_async_client, request_json_async

STANDARD = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
ENDPOINT = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in (*STANDARD, "NO_PROXY", "no_proxy", "GANGTISE_PROXY"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ─── GANGTISE_PROXY ───


@pytest.mark.parametrize(
    "value",
    ["http://proxy.test:8080", "https://proxy.test:8443", "http://u:p%40ss@proxy.test:3128"],
)
def test_proxy_url_is_read_from_gangtise_proxy(clean_env, value):
    clean_env.setenv("GANGTISE_PROXY", f"  {value} ")
    assert resolve_proxy_url() == value
    assert load_config().proxy == value


def test_blank_proxy_is_unset(clean_env):
    clean_env.setenv("GANGTISE_PROXY", "  ")
    assert load_config().proxy is None


@pytest.mark.parametrize(
    "value",
    [
        "socks5://user:s3cret@proxy.test:1080",
        "proxy.test:8080",
        "http://",
        "http://user:s3cret@proxy.test:port",
        "http://[::1",
        "http://999.9.9.9:8080",
        "http://user:s3cret@proxy.test:99999",
        "http://user:s3cret@proxy.test\t:8080",
        "http://user:s3cret@proxy example.test:8080",
    ],
)
def test_malformed_proxy_is_refused_without_echoing_it(clean_env, value):
    clean_env.setenv("GANGTISE_PROXY", value)
    with pytest.raises(ConfigError, match="GANGTISE_PROXY") as exc:
        load_config()
    assert "s3cret" not in str(exc.value)
    assert "proxy.test" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None


class _Answer(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length") or 0))
        data = {"via": self.server.name, "path": self.path}  # type: ignore[attr-defined]
        body = json.dumps({"code": "000000", "status": True, "data": data}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def servers() -> Iterator[tuple[str, str]]:
    """Two local servers: the API, and a forward proxy that answers in its place."""
    started = []
    for name in ("direct", "proxy"):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Answer)
        server.name = name  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started.append(server)
    try:
        yield tuple(f"http://127.0.0.1:{s.server_address[1]}" for s in started)  # type: ignore[misc]
    finally:
        for server in started:
            server.shutdown()
            server.server_close()


def _cfg(base_url: str) -> Config:
    return Config(base_url=base_url, proxy=resolve_proxy_url(), timeout_ms=5000)


def test_standard_proxy_variables_are_not_followed(clean_env, servers):
    direct, proxy = servers
    for name in STANDARD:
        clean_env.setenv(name, proxy)
    # The setup does reroute a client that reads the environment.
    with httpx.Client(base_url=direct) as plain:
        assert plain.post("/p").json()["data"]["via"] == "proxy"
    with build_sync_client(_cfg(direct)) as http:
        assert request_json(http, ENDPOINT, body={}, token="t")["via"] == "direct"


def test_gangtise_proxy_routes_the_requests(clean_env, servers):
    direct, proxy = servers
    clean_env.setenv("GANGTISE_PROXY", proxy)
    with build_sync_client(_cfg(direct)) as http:
        out = request_json(http, ENDPOINT, body={}, token="t")
    assert out == {"via": "proxy", "path": f"{direct}/p"}


@pytest.mark.anyio
async def test_async_standard_proxy_variables_are_not_followed(clean_env, servers):
    direct, proxy = servers
    for name in STANDARD:
        clean_env.setenv(name, proxy)
    async with build_async_client(_cfg(direct)) as http:
        out = await request_json_async(http, ENDPOINT, body={}, token="t")
    assert out["via"] == "direct"


@pytest.mark.anyio
async def test_async_gangtise_proxy_routes_the_requests(clean_env, servers):
    direct, proxy = servers
    clean_env.setenv("GANGTISE_PROXY", proxy)
    async with build_async_client(_cfg(direct)) as http:
        out = await request_json_async(http, ENDPOINT, body={}, token="t")
    assert out["via"] == "proxy"


# ─── connection hints ───


def test_hint_without_a_proxy_points_at_gangtise_proxy(clean_env):
    hint = connection_hint(httpx.ConnectError("refused"), proxied=False)
    assert hint is not None
    assert hint.startswith("连不上接口地址")
    assert "GANGTISE_PROXY=http://" in hint and "系统代理" in hint and "reset()" in hint


def test_hint_names_a_standard_proxy_variable_but_not_its_value(clean_env):
    clean_env.setenv("ALL_PROXY", "http://user:s3cret@corp.test:3128")
    hint = connection_hint(httpx.ConnectTimeout("timed out"), proxied=False)
    assert hint is not None
    assert "ALL_PROXY" in hint and "SDK 不读它" in hint
    assert "s3cret" not in hint and "corp.test" not in hint


def test_hint_with_a_proxy_is_about_the_proxy(clean_env):
    refused = connection_hint(httpx.ConnectError("refused"), proxied=True)
    timed_out = connection_hint(httpx.ConnectTimeout("timed out"), proxied=True)
    assert refused is not None and refused.startswith("连不上 GANGTISE_PROXY 指向的代理")
    assert timed_out is not None and "建立连接超时" in timed_out


def test_hint_follows_the_client_not_a_proxy_set_after_it(clean_env):
    """The client read its Config when it was created: a GANGTISE_PROXY set since is not
    in use, and the hint says so instead of sending the reader after that proxy."""
    clean_env.setenv("GANGTISE_PROXY", "http://proxy.test:8080")
    hint = connection_hint(httpx.ConnectError("refused"), proxied=False)
    assert hint is not None and "创建之后才设的" in hint and "reset()" in hint


def test_hint_for_a_tunnel_the_proxy_refused(clean_env):
    auth = connection_hint(httpx.ProxyError("407 Proxy Authentication Required"), proxied=True)
    blocked = connection_hint(httpx.ProxyError("403 Forbidden"), proxied=True)
    assert auth is not None and "要求认证" in auth and "URL 编码" in auth
    assert blocked is not None and "没有接通到接口地址" in blocked and "403" in blocked


def test_hint_at_the_file_step_is_about_the_download_address(clean_env):
    hint = connection_hint(httpx.ConnectError("refused"), proxied=False, file_step=True)
    assert hint is not None and hint.startswith("连不上文件的下载地址")
    blocked = connection_hint(httpx.ProxyError("502 Bad Gateway"), proxied=True, file_step=True)
    assert blocked is not None and "文件的下载地址" in blocked
    assert "GANGTISE_BASE_URL" not in blocked


def test_no_hint_for_a_tls_failure_or_a_response_timeout(clean_env):
    try:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        except ssl.SSLError as cause:
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]") from cause
    except httpx.ConnectError as error:
        tls = error
    for proxied in (False, True):
        assert connection_hint(tls, proxied=proxied) is None
        assert connection_hint(httpx.ReadTimeout("slow"), proxied=proxied) is None
        assert connection_hint(httpx.RemoteProtocolError("dropped"), proxied=proxied) is None


def test_configure_tells_a_proxy_change_from_the_same_settings(clean_env):
    facade = _Facade()
    try:
        direct = facade.configure(access_key="ak", secret_key="sk")
        assert direct.config.proxy is None
        clean_env.setenv("GANGTISE_PROXY", "http://proxy.test:8080")
        with pytest.raises(ConfigError, match="different settings"):
            facade.configure(access_key="ak", secret_key="sk")
        proxied = facade.configure(access_key="ak", secret_key="sk", replace=True)
        assert proxied.config.proxy == "http://proxy.test:8080"
    finally:
        facade.reset()


class _BadProxy:
    """A port that takes the tunnel request (CONNECT) and then: hangs up, answers with
    something that is not HTTP (a SOCKS port), or never answers."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.connections = 0
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._open: list[socket.socket] = []
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._sock.getsockname()[1]}"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self.connections += 1
            if self.mode == "hang-up":
                conn.close()
            elif self.mode == "not-http":
                conn.recv(1024)
                conn.sendall(b"\x05\x00not http\r\n\r\n")
                conn.close()
            else:
                self._open.append(conn)  # silent: held open, never answered

    def close(self) -> None:
        for conn in self._open:
            conn.close()
        self._sock.close()


@pytest.fixture
def bad_proxy(request: pytest.FixtureRequest) -> Iterator[_BadProxy]:
    proxy = _BadProxy(request.param)
    try:
        yield proxy
    finally:
        proxy.close()


def _via(proxy: str) -> Config:
    return Config(base_url="https://api.example.test", proxy=proxy, timeout_ms=1000)


@pytest.mark.parametrize(
    ("bad_proxy", "said", "connections"),
    [
        ("hang-up", "没有按 HTTP 代理应答", 3),
        ("not-http", "没有按 HTTP 代理应答", 3),
        # A whole timeout without an answer is not waited out twice more.
        ("silent", "在限时内没有应答隧道请求", 1),
    ],
    indirect=["bad_proxy"],
)
@pytest.mark.skipif(not hasattr(BaseException, "add_note"), reason="notes need Python 3.11+")
def test_a_tunnel_the_proxy_did_not_open_is_hinted(
    clean_env, monkeypatch, bad_proxy, said, connections
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    with build_sync_client(_via(bad_proxy.url)) as http, pytest.raises(httpx.HTTPError) as exc:
        request_json(http, ENDPOINT, body={}, token="t", proxied=True)
    assert len(exc.value.__notes__) == 1 and said in exc.value.__notes__[0]
    assert bad_proxy.connections == connections


@pytest.mark.anyio
@pytest.mark.parametrize("bad_proxy", ["silent"], indirect=True)
@pytest.mark.skipif(not hasattr(BaseException, "add_note"), reason="notes need Python 3.11+")
async def test_async_a_tunnel_the_proxy_did_not_answer_is_hinted(clean_env, bad_proxy):
    async with build_async_client(_via(bad_proxy.url)) as http:
        with pytest.raises(httpx.ReadTimeout) as exc:
            await request_json_async(http, ENDPOINT, body={}, token="t", proxied=True)
    assert "在限时内没有应答隧道请求" in exc.value.__notes__[0]
    assert bad_proxy.connections == 1


@pytest.mark.parametrize("bad_proxy", ["hang-up"], indirect=True)
def test_no_replay_endpoint_resends_when_the_tunnel_was_dropped(clean_env, monkeypatch, bad_proxy):
    """Dropped before the tunnel opened, the request never reached the API: safe to send
    again even where a request the server may have run is never resent."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    no_replay = EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-replay"
    )
    with build_sync_client(_via(bad_proxy.url)) as http, pytest.raises(httpx.HTTPError):
        request_json(http, no_replay, body={}, token="t", proxied=True)
    assert bad_proxy.connections == 3


@pytest.mark.parametrize("bad_proxy", ["hang-up"], indirect=True)
def test_no_replay_download_resends_when_the_tunnel_was_dropped(
    clean_env, monkeypatch, tmp_path, bad_proxy
):
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    cfg = Config(
        base_url="https://api.example.test",
        token="t",
        proxy=bad_proxy.url,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=1000,
    )
    with GangtiseClient(_config=cfg) as client, pytest.raises(DownloadError) as exc:
        download_to_path(
            client=client,
            endpoint_key="insight.summary.download",  # no-replay, billed per document
            query={"summaryId": "s1"},
            output=tmp_path / "out.pdf",
            fallback_name="s1",
        )
    assert bad_proxy.connections == 3
    assert "没有按 HTTP 代理应答" in str(exc.value)


@pytest.mark.parametrize("bad_proxy", ["silent"], indirect=True)
def test_a_tunnel_left_unanswered_is_not_resent_but_a_poll_waits_through_it(clean_env, bad_proxy):
    """Not sent again within the request — but an already-paid task being polled must not
    be given up on for it, any more than for another timeout."""
    with build_sync_client(_via(bad_proxy.url)) as http, pytest.raises(httpx.ReadTimeout) as exc:
        request_json(http, ENDPOINT, body={}, token="t", proxied=True)
    assert not is_retryable_error(exc.value)
    assert is_transient_error(exc.value)


@pytest.mark.parametrize("bad_proxy", ["silent"], indirect=True)
def test_a_tunnel_failure_being_handled_does_not_mark_the_next_error(clean_env, bad_proxy):
    """Only the request's own chain counts: a direct timeout raised while the caller is
    still handling a tunnel failure is an ordinary timeout."""
    with build_sync_client(_via(bad_proxy.url)) as http, pytest.raises(httpx.ReadTimeout) as exc:
        request_json(http, ENDPOINT, body={}, token="t", proxied=True)
    try:
        raise exc.value
    except httpx.ReadTimeout:
        try:
            raise httpx.ReadTimeout("slow")
        except httpx.ReadTimeout as direct:
            assert direct.__context__ is exc.value
            assert not failed_before_tunnel(direct)
            assert is_retryable_error(direct)
            assert connection_hint(direct, proxied=True) is None


@pytest.fixture
def tls_api(tmp_path: Path) -> Iterator[tuple[int, Path, dict[str, int]]]:
    """An https API on localhost that takes requests and never answers them."""
    if shutil.which("openssl") is None:
        pytest.skip("needs openssl to make a certificate")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
            "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    seen = {"connections": 0}
    held: list[socket.socket] = []

    def serve() -> None:
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            seen["connections"] += 1
            try:
                held.append(context.wrap_socket(conn, server_side=True))
            except (OSError, ssl.SSLError):
                conn.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        yield sock.getsockname()[1], cert, seen
    finally:
        for conn in held:
            conn.close()
        sock.close()


class _Tunnel:
    """A proxy that does open tunnels (CONNECT host:port → a plain TCP pipe)."""

    def __init__(self) -> None:
        self.tunnels = 0
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._sock.getsockname()[1]}"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._open, args=(conn,), daemon=True).start()

    def _open(self, conn: socket.socket) -> None:
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(4096)
        _, port = head.split()[1].decode().rsplit(":", 1)
        upstream = socket.create_connection(("127.0.0.1", int(port)))
        self.tunnels += 1
        conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        threading.Thread(target=self._pipe, args=(conn, upstream), daemon=True).start()
        self._pipe(upstream, conn)

    @staticmethod
    def _pipe(src: socket.socket, dst: socket.socket) -> None:
        try:
            while data := src.recv(65536):
                dst.sendall(data)
        except OSError:
            pass

    def close(self) -> None:
        self._sock.close()


def test_a_silent_api_behind_an_open_tunnel_is_no_tunnel_failure(clean_env, monkeypatch, tls_api):
    """The tunnel opened and the request went through it: the server may have run it, so a
    no-replay request is not resent, and no proxy hint is given."""
    port, cert, seen = tls_api
    clean_env.setenv("SSL_CERT_FILE", str(cert))
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    proxy = _Tunnel()
    no_replay = EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-replay"
    )
    cfg = Config(base_url=f"https://localhost:{port}", proxy=proxy.url, timeout_ms=1000)
    try:
        with build_sync_client(cfg) as http, pytest.raises(httpx.ReadTimeout) as exc:
            request_json(http, no_replay, body={}, token="t", proxied=True)
    finally:
        proxy.close()
    assert proxy.tunnels == 1 and seen["connections"] == 1
    assert not failed_before_tunnel(exc.value)
    assert not getattr(exc.value, "__notes__", None)


def test_an_untrusted_certificate_gets_no_network_hint(clean_env, monkeypatch, tls_api):
    """A real verification failure, as httpcore raises it: its pool re-raises the mapped
    error ``from None``, so the ssl error is only in ``args[0]``. Not a network problem —
    no advice to check the address or set a proxy, directly or through a tunnel."""
    port, _, _ = tls_api
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    direct = Config(base_url=f"https://localhost:{port}", timeout_ms=2000)
    with build_sync_client(direct) as http, pytest.raises(httpx.ConnectError) as exc:
        request_json(http, ENDPOINT, body={}, token="t")
    assert "CERTIFICATE_VERIFY_FAILED" in str(exc.value)
    assert not getattr(exc.value, "__notes__", None)
    proxy = _Tunnel()
    try:
        tunnelled = Config(base_url=f"https://localhost:{port}", proxy=proxy.url, timeout_ms=2000)
        with build_sync_client(tunnelled) as http, pytest.raises(httpx.ConnectError) as exc:
            request_json(http, ENDPOINT, body={}, token="t", proxied=True)
    finally:
        proxy.close()
    assert not getattr(exc.value, "__notes__", None)


@pytest.mark.anyio
async def test_async_an_untrusted_certificate_gets_no_network_hint(clean_env, monkeypatch, tls_api):
    port, _, _ = tls_api
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    async with build_async_client(
        Config(base_url=f"https://localhost:{port}", timeout_ms=2000)
    ) as http:
        with pytest.raises(httpx.ConnectError) as exc:
            await request_json_async(http, ENDPOINT, body={}, token="t")
    assert "CERTIFICATE_VERIFY_FAILED" in str(exc.value)
    assert not getattr(exc.value, "__notes__", None)


class _ForwardWithFileAuth(BaseHTTPRequestHandler):
    """A forward proxy: the download request is answered with a redirect to a plain-http
    file address, which the proxy will only fetch with credentials."""

    def do_GET(self) -> None:
        if "/download/" in self.path:
            self.send_response(302)
            self.send_header("location", "http://127.0.0.1:9/files/s1.pdf")
        else:
            self.send_response(407)
            self.send_header("proxy-authenticate", 'Basic realm="proxy"')
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def test_a_407_on_the_file_fetch_gets_the_credentials_hint(clean_env, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ForwardWithFileAuth)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = Config(
        base_url="http://127.0.0.1:9",
        token="t",
        proxy=f"http://127.0.0.1:{server.server_address[1]}",
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
    )
    try:
        with GangtiseClient(_config=cfg) as client, pytest.raises(DownloadError) as exc:
            download_to_path(
                client=client,
                endpoint_key="insight.summary.download",
                query={"summaryId": "s1"},
                output=tmp_path / "out.pdf",
                fallback_name="s1",
            )
    finally:
        server.shutdown()
        server.server_close()
    assert "HTTP 407" in str(exc.value) and PROXY_AUTH_HINT in str(exc.value)


class _AskForCredentials(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.send_response(407)
        self.send_header("proxy-authenticate", 'Basic realm="proxy"')
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def test_a_407_from_a_forward_proxy_gets_the_credentials_hint(clean_env):
    """An http:// base URL is forwarded, not tunnelled: the proxy's 407 arrives as an
    ordinary response."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AskForCredentials)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cfg = Config(
            base_url="http://127.0.0.1:9",
            proxy=f"http://127.0.0.1:{server.server_address[1]}",
            timeout_ms=5000,
        )
        with build_sync_client(cfg) as http, pytest.raises(ApiError) as exc:
            request_json(http, ENDPOINT, body={}, token="t", proxied=True)
    finally:
        server.shutdown()
        server.server_close()
    assert exc.value.status_code == 407
    assert exc.value.hint == PROXY_AUTH_HINT


def test_a_timeout_handled_leaves_no_cycle_holding_the_request(clean_env, monkeypatch):
    """Checking a timeout for a tunnel failure must not keep the request alive past its
    handling: before Python 3.13, reading the locals of the frame still handling the error
    would pin them to it (error -> traceback -> frame -> locals -> error), the upload's
    bytes among them, until the next garbage collection. (httpx's MockTransport, not respx:
    respx links a side effect's error and its wrapper both ways, a cycle of its own.)"""
    import gc
    import weakref

    from gangtise_openapi._transport import UploadFile

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    upload = EndpointDef(key="x", method="POST", path="/u", kind="upload", description="d")
    refs: list[weakref.ref[UploadFile]] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def send(http: httpx.Client) -> None:
        body = UploadFile(filename="f.pdf", data=b"%PDF" * 1000)
        refs.append(weakref.ref(body))
        request_json(http, upload, body=body, token="t")

    gc.disable()
    try:
        transport = httpx.MockTransport(timeout)
        with (
            httpx.Client(base_url="https://api.test", transport=transport, timeout=5) as http,
            pytest.raises(httpx.ReadTimeout),
        ):
            send(http)
        assert refs[0]() is None
    finally:
        gc.enable()


def _login_tmp(tmp_path: Path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
    )


@pytest.mark.skipif(not hasattr(BaseException, "add_note"), reason="notes need Python 3.11+")
def test_raised_network_error_carries_the_hint_once(clean_env, tmp_path, monkeypatch):
    """The login is the first request a fresh client sends, so that is where an
    unreachable API shows first."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test") as router:
        login = router.post("/application/auth/oauth/open/loginV2").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with (
            GangtiseClient(_config=_login_tmp(tmp_path)) as client,
            pytest.raises(httpx.ConnectError) as exc,
        ):
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 3
    notes = getattr(exc.value, "__notes__", [])
    assert len(notes) == 1 and notes[0].startswith("连不上接口地址")


@pytest.mark.skipif(not hasattr(BaseException, "add_note"), reason="notes need Python 3.11+")
def test_the_hint_is_about_the_proxy_the_client_uses(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    with respx.mock(base_url="https://api.test") as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with GangtiseClient(_config=_login_tmp(tmp_path)) as client:
            clean_env.setenv("GANGTISE_PROXY", "http://proxy.test:8080")
            with pytest.raises(httpx.ConnectError) as exc:
                client._call("quote.realtime", body={"securityList": ["x"]})
    assert client.config.proxy is None
    assert "创建之后才设的" in exc.value.__notes__[0]


def test_download_error_message_carries_the_hint(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._download._retry_delay", lambda e, a: 0.0)
    cfg = _login_tmp(tmp_path)
    with respx.mock(base_url="https://api.test") as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"accessToken": "t", "expiresIn": 3600, "time": 0},
                },
            )
        )
        router.get("/application/open-insight/broker-report/download/file").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with GangtiseClient(_config=cfg) as client, pytest.raises(DownloadError) as exc:
            download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=tmp_path / "out.pdf",
                fallback_name="report-r1",
            )
    assert "download failed: refused — 连不上接口地址" in str(exc.value)
