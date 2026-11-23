"""Client-level behaviour ported from CLI v0.40.0-v0.44.0.

- token cache bound to the credentials that minted it (``issuedFor``)
- auth recovery: a token someone else refreshed first, one login last
- ``login()`` reports the identity requests will actually use
- ``confirm=True`` gates: destructive endpoints, the earning-forecast price estimate
- per-item failures inside a 000000 success (``failList``) → partial
"""

from __future__ import annotations

import asyncio
import gc
import json
import threading
import time
import weakref
from pathlib import Path

import anyio
import httpx
import pytest
import respx

from gangtise_openapi._auth import TokenCache, credential_fingerprint, read_token_cache
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ValidationError

BASE = "https://api.test"
LOGIN = "/application/auth/oauth/open/loginV2"
REALTIME = "/application/open-quote/quote/realtime"
FP = credential_fingerprint("ak", BASE)


def _cfg(tmp_path: Path, *, token: str | None = None, access_key: str | None = "ak") -> Config:
    return Config(
        base_url=BASE,
        access_key=access_key,
        secret_key="sk" if access_key else None,
        token=token,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


def _seed(cfg: Config, token: str, issued_for: str | None = FP) -> None:
    payload: dict[str, object] = {
        "accessToken": token,
        "expiresIn": 3600,
        "time": 0,
        "expiresAt": 9999999999,
    }
    if issued_for is not None:
        payload["issuedFor"] = issued_for
    cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_cache_path.write_text(json.dumps(payload))


def _login_response(token: str = "fresh") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"accessToken": token, "expiresIn": 3600, "time": 0, "uid": 1},
        },
    )


def _ok(data: object) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _auth_fail() -> httpx.Response:
    return httpx.Response(200, json={"code": "0000001008", "status": False, "msg": "token 失效"})


# ─── token cache ↔ credentials ───


def test_cache_of_other_credentials_is_not_used(tmp_path):
    """TS v0.40.0: swapping GANGTISE_ACCESS_KEY must not keep sending the previous
    account's unexpired token — writes would land on the wrong account."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "other-account", issued_for=credential_fingerprint("another-ak", BASE))
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        data = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert data.calls[0].request.headers["Authorization"] == "Bearer fresh"
    written = read_token_cache(cfg.token_cache_path)
    assert written is not None and written.issued_for == FP


def test_cache_without_fingerprint_is_a_miss_when_credentials_are_set(tmp_path):
    """A cache written before ``issuedFor`` existed has an unknown owner."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "legacy", issued_for=None)
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1


def test_cache_without_fingerprint_is_used_when_no_access_key(tmp_path):
    """Without AK there is no second account to confuse it with; refusing the cache
    would only break the token-cache-only workflow."""
    cfg = _cfg(tmp_path, access_key=None)
    _seed(cfg, "legacy", issued_for=None)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN)
        data = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert data.calls[0].request.headers["Authorization"] == "Bearer legacy"


def test_fingerprint_matches_the_cli_digest():
    # sha256("ak1\0https://openapi.gangtise.com")[:16], computed with node's crypto.
    assert credential_fingerprint("ak1", "https://openapi.gangtise.com") == "1dde6c8f82abacc9"


# ─── auth recovery ───


def test_recovery_prefers_a_live_disk_token_before_logging_in(tmp_path):
    """TS v0.44.0: back-to-back logins can end each other's sessions, so a token
    another process already refreshed is tried first (once), then one login."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())

        def data(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                # Another process refreshes the shared cache file meanwhile.
                _seed(cfg, "from-other-process")
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer from-other-process",
    ]


def test_recovery_logs_in_after_an_unproven_token_also_fails(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def data(request: httpx.Request) -> httpx.Response:
            auth = request.headers["Authorization"]
            if auth == "Bearer stale":
                _seed(cfg, "also-dead")
                return _auth_fail()
            if auth == "Bearer also-dead":
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer also-dead",
        "Bearer fresh",
    ]


def test_recovery_stops_when_the_freshly_minted_token_fails_too(tmp_path):
    """No login loop: a token this client's own login minted that is rejected ends
    the recovery."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(return_value=_auth_fail())
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.code == "0000001008"
    assert login.call_count == 1
    assert route.call_count == 2  # the stale token, then the fresh one — no third try


@pytest.mark.anyio
async def test_async_recovery_prefers_a_live_disk_token_before_logging_in(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())

        def data(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                _seed(cfg, "from-other-process")
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert route.call_count == 2


@pytest.mark.anyio
async def test_async_recovery_stops_when_the_freshly_minted_token_fails_too(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(return_value=_auth_fail())
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ApiError):
                await client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert route.call_count == 2


# ─── a login that fails (CLI v0.53.0) ───


def _busy() -> httpx.Response:
    return httpx.Response(503, text="busy")


def test_failed_login_uses_a_token_another_process_cached_meanwhile(tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "from-other-process")
        return _busy()

    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login_route.call_count == 3
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer from-other-process"
    ]


def test_failed_login_with_nothing_cached_fails_after_its_own_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login_route = router.post(LOGIN).mock(return_value=_busy())
        route = router.post(REALTIME)
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.status_code == 503
    assert login_route.call_count == 3
    assert route.call_count == 0


class _CountingLock:
    """``threading.Lock`` that counts the callers that have asked for it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = threading.Lock()
        self.asked = 0

    def __enter__(self) -> _CountingLock:
        with self._count:
            self.asked += 1
        self._lock.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._lock.release()


def test_callers_waiting_on_a_failed_login_do_not_run_it_again(tmp_path, monkeypatch):
    """Three requests need a token at once: one login runs its three attempts and the
    two that waited for it fail with its error — not nine attempts in a row."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    lock = _CountingLock()

    def login(request: httpx.Request) -> httpx.Response:
        deadline = time.monotonic() + 5
        while lock.asked < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        return _busy()

    errors: list[BaseException] = []
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def work() -> None:
                try:
                    client._call("quote.realtime", body={"securityList": ["x"]})
                except ApiError as error:
                    errors.append(error)

            threads = [threading.Thread(target=work) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert lock.asked == 3
    assert login_route.call_count == 3
    assert route.call_count == 0
    assert [e.status_code for e in errors] == [503, 503, 503]  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_async_callers_waiting_on_a_failed_login_do_not_run_it_again(tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post(REALTIME)
        statuses: list[int | None] = []
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def login(request: httpx.Request) -> httpx.Response:
                # Answered once the other two requests wait on the lock.
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 2:
                        await anyio.sleep(0.01)
                return _busy()

            login_route = router.post(LOGIN).mock(side_effect=login)

            async def work() -> None:
                try:
                    await client._call("quote.realtime", body={"securityList": ["x"]})
                except ApiError as error:
                    statuses.append(error.status_code)

            async with anyio.create_task_group() as tg:
                for _ in range(3):
                    tg.start_soon(work)
    assert login_route.call_count == 3
    assert route.call_count == 0
    assert statuses == [503, 503, 503]


def test_login_call_and_a_request_share_one_failed_login(tmp_path, monkeypatch):
    """``login()`` runs the login a request is waiting for, or waits for the request's:
    either way one login's three attempts, both failing with it."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    lock = _CountingLock()

    def login(request: httpx.Request) -> httpx.Response:
        deadline = time.monotonic() + 5
        while lock.asked < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        return _busy()

    errors: list[int | None] = []
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def run(fn: object) -> None:
                try:
                    fn()  # type: ignore[operator]
                except ApiError as error:
                    errors.append(error.status_code)

            threads = [
                threading.Thread(target=run, args=(client.login,)),
                threading.Thread(
                    target=run,
                    args=(lambda: client._call("quote.realtime", body={"securityList": ["x"]}),),
                ),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert login_route.call_count == 3
    assert errors == [503, 503]


@pytest.mark.anyio
async def test_async_login_call_and_a_request_share_one_failed_login(tmp_path, monkeypatch):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    errors: list[int | None] = []
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post(REALTIME)
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def login(request: httpx.Request) -> httpx.Response:
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 1:
                        await anyio.sleep(0.01)
                return _busy()

            login_route = router.post(LOGIN).mock(side_effect=login)

            async def run(fn: object) -> None:
                try:
                    await fn()  # type: ignore[operator]
                except ApiError as error:
                    errors.append(error.status_code)

            async with anyio.create_task_group() as tg:
                tg.start_soon(run, client.login)
                tg.start_soon(
                    run, lambda: client._call("quote.realtime", body={"securityList": ["x"]})
                )
    assert login_route.call_count == 3
    assert errors == [503, 503]


@pytest.mark.anyio
async def test_async_a_cancelled_login_is_run_by_the_request_that_waited_on_it(
    tmp_path, monkeypatch
):
    """An earlier login failed; the next one is cancelled half-way. The request waiting on
    that one logs in itself — it must not fail with the earlier login's error."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    sent = {"n": 0}
    hanging = anyio.Event()

    async def login(request: httpx.Request) -> httpx.Response:
        sent["n"] += 1
        if sent["n"] <= 3:
            return _busy()
        if sent["n"] == 4:
            hanging.set()
            await anyio.sleep(30)
        return _login_response("fresh")

    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def call() -> object:
                return await client._call("quote.realtime", body={"securityList": ["x"]})

            with pytest.raises(ApiError):
                await call()
            outcome: list[object] = []
            async with anyio.create_task_group() as tg:
                cancelled = anyio.CancelScope()

                async def first() -> None:
                    with cancelled:
                        await call()

                async def waiter() -> None:
                    outcome.append(await call())

                tg.start_soon(first)
                await hanging.wait()
                tg.start_soon(waiter)
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 1:
                        await anyio.sleep(0.01)
                cancelled.cancel()
    assert outcome == [{"total": 0, "list": []}]
    assert sent["n"] == 5


def test_recovery_does_not_take_back_the_token_just_refused(tmp_path, monkeypatch):
    """A request picks up the token a login has just put in memory, while that login is
    still writing the cache, and the server refuses it. The recovery waits on that same
    login: what it minted is the refused token, so a new login runs instead of the same
    token being sent twice."""
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    lock = _CountingLock()
    minted = iter(["T1", "T2"])
    real_write = client_module.write_token_cache
    sent: dict[str, list[str]] = {"first": [], "second": []}
    started: list[threading.Thread] = []

    def data(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        sent[json.loads(request.content)["securityList"][0]].append(auth)
        return _auth_fail() if auth == "Bearer T1" else _ok({"total": 0, "list": []})

    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(side_effect=lambda request: _login_response(next(minted)))
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def call(which: str) -> None:
                client._call("quote.realtime", body={"securityList": [which]})

            def write(path: Path, cache: object) -> None:
                if not started:
                    # T1 is in memory; the second request takes it, is refused, and waits
                    # on the lock this login still holds.
                    second = threading.Thread(target=call, args=("second",))
                    started.append(second)
                    second.start()
                    deadline = time.monotonic() + 5
                    while lock.asked < 2 and time.monotonic() < deadline:
                        time.sleep(0.01)
                real_write(path, cache)

            monkeypatch.setattr(client_module, "write_token_cache", write)
            call("first")
            started[0].join()
    assert sent["second"] == ["Bearer T1", "Bearer T2"]
    assert sent["first"] == ["Bearer T1", "Bearer T2"]
    assert login.call_count == 2


@pytest.mark.anyio
async def test_async_recovery_does_not_take_back_the_token_just_refused(tmp_path, monkeypatch):
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    minted = iter(["T1", "T2"])
    real_write = client_module.write_token_cache
    proceed = threading.Event()
    sent: dict[str, list[str]] = {"first": [], "second": []}

    def data(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        sent[json.loads(request.content)["securityList"][0]].append(auth)
        return _auth_fail() if auth == "Bearer T1" else _ok({"total": 0, "list": []})

    def write(path: Path, cache: object) -> None:  # runs on a worker thread
        proceed.wait(5)
        real_write(path, cache)

    monkeypatch.setattr(client_module, "write_token_cache", write)
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(side_effect=lambda request: _login_response(next(minted)))
        router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def call(which: str) -> None:
                await client._call("quote.realtime", body={"securityList": [which]})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call, "first")
                with anyio.fail_after(5):
                    while client._memo_cache is None:  # T1 in memory, cache still writing
                        await anyio.sleep(0.01)
                tg.start_soon(call, "second")
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 1:
                        await anyio.sleep(0.01)
                proceed.set()
    assert sent["second"] == ["Bearer T1", "Bearer T2"]
    assert login.call_count == 2


@pytest.mark.anyio
async def test_async_requests_arriving_after_a_cancelled_login_join_its_round(
    tmp_path, monkeypatch
):
    """The login running a round is cancelled while another ``login()`` waits on it. A
    ``login()`` arriving now joins that round instead of opening a second one: both get
    the one token the next login mints — a second login could end the first's session."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    sent = {"n": 0}
    hanging = anyio.Event()

    async def login(request: httpx.Request) -> httpx.Response:
        sent["n"] += 1
        n = sent["n"]
        if n == 1:
            hanging.set()
            await anyio.sleep(30)
        await anyio.sleep(0.05)
        return _login_response(f"T{n}")

    tokens: list[str] = []
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def survivor() -> None:
                tokens.append((await client.login())["authorization"])

            async with anyio.create_task_group() as tg:
                cancelled = anyio.CancelScope()

                async def first() -> None:
                    with cancelled:
                        await client.login()

                tg.start_soon(first)
                await hanging.wait()
                tg.start_soon(survivor)
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 1:
                        await anyio.sleep(0.01)
                cancelled.cancel()
                tg.start_soon(survivor)
    assert tokens == ["Bearer T2", "Bearer T2"]
    assert sent["n"] == 2


def test_a_token_read_from_disk_does_not_replace_one_a_login_just_minted(tmp_path, monkeypatch):
    """A request reads the cache file; before it puts that token in memory, ``login()``
    mints a fresh one. The older token from the file must not overwrite it."""
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    _seed(cfg, "older")
    real_read = client_module.read_token_cache
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        with GangtiseClient(_config=cfg) as client:
            reported: list[dict[str, object]] = []

            def read(path: Path) -> object:
                snapshot = real_read(path)
                if not reported:
                    reported.append(client.login())  # lands while the file was being read
                return snapshot

            monkeypatch.setattr(client_module, "read_token_cache", read)
            assert client._get_token() == "fresh"
            assert client._get_token() == "fresh"
    assert reported[0]["authorization"] == "Bearer fresh"
    assert reported[0]["cache"]["access_token"] == "fresh"  # type: ignore[index]


def test_login_reports_the_cache_its_own_login_minted(tmp_path, monkeypatch):
    """Whatever is in memory by the time it returns, ``login()`` reports what it minted."""
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    real_write = client_module.write_token_cache
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        with GangtiseClient(_config=cfg) as client:

            def write(path: Path, cache: object) -> None:
                client._memo_cache = None  # memory changes under the login's feet
                real_write(path, cache)

            monkeypatch.setattr(client_module, "write_token_cache", write)
            out = client.login()
    assert out["authorization"] == "Bearer fresh"
    assert out["cache"]["access_token"] == "fresh"


@pytest.mark.anyio
async def test_async_a_token_read_from_disk_does_not_replace_one_a_login_just_minted(
    tmp_path, monkeypatch
):
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    _seed(cfg, "older")
    real_read = client_module.read_token_cache
    reading, proceed = threading.Event(), threading.Event()

    def read(path: Path) -> object:  # runs on a worker thread
        snapshot = real_read(path)
        if not reading.is_set():
            reading.set()
            proceed.wait(5)
        return snapshot

    monkeypatch.setattr(client_module, "read_token_cache", read)
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        async with AsyncGangtiseClient(_config=cfg) as client:
            got: list[str] = []

            async def query() -> None:
                got.append(await client._get_token())

            async with anyio.create_task_group() as tg:
                tg.start_soon(query)
                with anyio.fail_after(5):
                    while not reading.is_set():
                        await anyio.sleep(0.01)
                out = await client.login()
                proceed.set()
            assert await client._get_token() == "fresh"
    assert got == ["fresh"]
    assert out["cache"]["access_token"] == "fresh"


def test_requests_recovering_one_refused_token_share_one_new_login(tmp_path, monkeypatch):
    """Two requests take the token a login has just minted, while it is still writing the
    cache, and both are refused. They share one new login: when it fails, three attempts
    in all, not three each."""
    import gangtise_openapi._client as client_module

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    lock = _CountingLock()
    answers = iter([_login_response("T1"), _busy(), _busy(), _busy(), _busy(), _busy(), _busy()])
    real_write = client_module.write_token_cache
    statuses: list[int | None] = []
    workers: list[threading.Thread] = []

    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(side_effect=lambda request: next(answers))
        route = router.post(REALTIME).mock(return_value=_auth_fail())
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def call() -> None:
                try:
                    client._call("quote.realtime", body={"securityList": ["x"]})
                except ApiError as error:
                    statuses.append(error.status_code)

            def write(path: Path, cache: object) -> None:
                if not workers:
                    workers.extend(threading.Thread(target=call) for _ in range(2))
                    for worker in workers:
                        worker.start()
                    deadline = time.monotonic() + 5
                    while lock.asked < 3 and time.monotonic() < deadline:
                        time.sleep(0.01)
                real_write(path, cache)

            monkeypatch.setattr(client_module, "write_token_cache", write)
            client.login()
            for worker in workers:
                worker.join()
    assert login.call_count == 4  # T1, then one shared login of three attempts
    assert statuses == [503, 503]
    assert route.call_count == 2


@pytest.mark.anyio
async def test_async_requests_recovering_one_refused_token_share_one_new_login(
    tmp_path, monkeypatch
):
    import gangtise_openapi._client as client_module

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    answers = iter([_login_response("T1"), _busy(), _busy(), _busy(), _busy(), _busy(), _busy()])
    real_write = client_module.write_token_cache
    proceed = threading.Event()

    def write(path: Path, cache: object) -> None:  # runs on a worker thread
        proceed.wait(5)
        real_write(path, cache)

    monkeypatch.setattr(client_module, "write_token_cache", write)
    statuses: list[int | None] = []
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(side_effect=lambda request: next(answers))
        router.post(REALTIME).mock(return_value=_auth_fail())
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def call() -> None:
                try:
                    await client._call("quote.realtime", body={"securityList": ["x"]})
                except ApiError as error:
                    statuses.append(error.status_code)

            async with anyio.create_task_group() as tg:
                tg.start_soon(client.login)
                with anyio.fail_after(5):
                    while client._memo_cache is None:  # T1 in memory, cache still writing
                        await anyio.sleep(0.01)
                tg.start_soon(call)
                tg.start_soon(call)
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 2:
                        await anyio.sleep(0.01)
                proceed.set()
    assert login.call_count == 4
    assert statuses == [503, 503]


@pytest.mark.anyio
async def test_async_a_cancelled_login_never_writes_its_token_over_a_newer_one(
    tmp_path, monkeypatch
):
    """``asyncio.wait_for`` gives up on a login while its cache write runs on a worker
    thread; the next ``login()`` mints T2. Whenever that first write lands, the file ends up
    holding T2 — the token a new client starts from."""
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    minted = iter(["T1", "T2"])
    real_write = client_module.write_token_cache
    writing_t1, release_t1, t1_done = threading.Event(), threading.Event(), threading.Event()

    def write(path: Path, cache: TokenCache) -> None:  # runs on a worker thread
        if cache.access_token == "T1":
            writing_t1.set()
            release_t1.wait(5)
        real_write(path, cache)
        if cache.access_token == "T1":
            t1_done.set()

    monkeypatch.setattr(client_module, "write_token_cache", write)
    second: list[dict[str, object]] = []
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=lambda request: _login_response(next(minted)))
        async with AsyncGangtiseClient(_config=cfg) as client:
            first = asyncio.create_task(asyncio.wait_for(client.login(), timeout=5))
            with anyio.fail_after(5):
                while not writing_t1.is_set():
                    await anyio.sleep(0.01)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            async def login_again() -> None:
                second.append(await client.login())

            async with anyio.create_task_group() as tg:
                tg.start_soon(login_again)
                await anyio.sleep(0.1)  # T2 minted; its write waits for T1's
                release_t1.set()
            # The abandoned write has landed too, whichever order the two came in.
            assert await anyio.to_thread.run_sync(t1_done.wait, 5)
    assert second[0]["authorization"] == "Bearer T2"
    on_disk = read_token_cache(cfg.token_cache_path)
    assert on_disk is not None and on_disk.access_token == "T2"


def _racy_client(cfg: Config) -> GangtiseClient:
    """A client whose in-memory token another thread clears right after any read of it —
    as a recovery on another thread may do between a check and a second read."""

    class Racy(GangtiseClient):
        clear_after_read = False

        @property  # type: ignore[override]
        def _memo_cache(self) -> TokenCache | None:
            value = self.__dict__.get("_memo")
            if self.clear_after_read and value is not None:
                self.__dict__["_memo"] = None
            return value

        @_memo_cache.setter
        def _memo_cache(self, value: TokenCache | None) -> None:
            self.__dict__["_memo"] = value

    return Racy(_config=cfg)


def _cache(token: str) -> TokenCache:
    return TokenCache(
        access_token=token, expires_in=3600, time=0, expires_at=9999999999, issued_for=FP
    )


def test_a_token_cleared_right_after_the_check_is_still_the_one_used(tmp_path):
    client = _racy_client(_cfg(tmp_path))
    client._memo_cache = _cache("fresh")
    client.clear_after_read = True  # type: ignore[attr-defined]
    assert client._get_token() == "fresh"


def test_a_token_cleared_right_after_the_recheck_is_still_the_one_used(tmp_path, monkeypatch):
    import gangtise_openapi._client as client_module

    cfg = _cfg(tmp_path)
    _seed(cfg, "older")
    client = _racy_client(cfg)
    real_read = client_module.read_token_cache

    def read(path: Path) -> object:
        snapshot = real_read(path)
        client._memo_cache = _cache("fresh")  # a login lands while the file is read
        client.clear_after_read = True  # type: ignore[attr-defined]
        return snapshot

    monkeypatch.setattr(client_module, "read_token_cache", read)
    assert client._get_token() == "fresh"


def test_waiters_take_a_recovery_login_that_returns_the_same_token(tmp_path, monkeypatch):
    """Both requests were refused before the recovery login began. It answers with the
    same token, which the server now takes: the second waiter uses it as well, instead of
    reading it as its refused token and logging in once more."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    lock = _CountingLock()
    both_refused = threading.Barrier(2, timeout=5)
    logged_in = threading.Event()
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])

    def login(request: httpx.Request) -> httpx.Response:
        deadline = time.monotonic() + 5
        while lock.asked < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        logged_in.set()
        return next(answers)

    def data(request: httpx.Request) -> httpx.Response:
        if not logged_in.is_set():
            both_refused.wait()
            return _auth_fail()
        return _ok({"total": 0, "list": []})

    outcomes: list[object] = []
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def call() -> None:
                try:
                    outcomes.append(client._call("quote.realtime", body={"securityList": ["x"]}))
                except ApiError as error:
                    outcomes.append(error.status_code)

            threads = [threading.Thread(target=call) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert outcomes == [{"total": 0, "list": []}] * 2
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_waiters_take_a_recovery_login_that_returns_the_same_token(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    refused = {"n": 0}
    both_refused = anyio.Event()
    logged_in = {"done": False}
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])
    outcomes: list[object] = []
    with respx.mock(base_url=BASE) as router:
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def login(request: httpx.Request) -> httpx.Response:
                with anyio.fail_after(5):
                    while client._lock.statistics().tasks_waiting < 1:
                        await anyio.sleep(0.01)
                logged_in["done"] = True
                return next(answers)

            async def data(request: httpx.Request) -> httpx.Response:
                if not logged_in["done"]:
                    refused["n"] += 1
                    if refused["n"] == 2:
                        both_refused.set()
                    with anyio.fail_after(5):
                        await both_refused.wait()
                    return _auth_fail()
                return _ok({"total": 0, "list": []})

            login_route = router.post(LOGIN).mock(side_effect=login)
            router.post(REALTIME).mock(side_effect=data)

            async def call() -> None:
                try:
                    outcomes.append(
                        await client._call("quote.realtime", body={"securityList": ["x"]})
                    )
                except ApiError as error:
                    outcomes.append(error.status_code)

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                tg.start_soon(call)
    assert outcomes == [{"total": 0, "list": []}] * 2
    assert login_route.call_count == 1


def test_requests_sharing_a_failed_login_each_get_their_own_error(tmp_path, monkeypatch):
    """One failed login, three requests: three error objects, each with its own call stack
    and notes — not one object whose traceback grows with every request that raises it."""
    import traceback

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    lock = _CountingLock()

    def login(request: httpx.Request) -> httpx.Response:
        deadline = time.monotonic() + 5
        while lock.asked < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        return _busy()

    errors: list[ApiError] = []
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def one_request() -> None:
                try:
                    client._call("quote.realtime", body={"securityList": ["x"]})
                except ApiError as error:
                    errors.append(error)

            threads = [threading.Thread(target=one_request) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert len({id(e) for e in errors}) == 3
    assert {e.status_code for e in errors} == {503}
    for error in errors:
        assert "".join(traceback.format_exception(error)).count("in one_request") == 1
    if hasattr(errors[0], "add_note"):
        errors[0].add_note("seen by request 0")
        assert not any("seen by request 0" in getattr(e, "__notes__", []) for e in errors[1:])


def _late_refusal(tmp_path: Path) -> tuple[Config, dict[str, object]]:
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    return cfg, {"logged_in": False}


def test_a_late_refusal_takes_the_login_that_followed_it_even_with_the_same_token(
    tmp_path, monkeypatch
):
    """Both requests went out with T0. The first is refused, recovers — the login answers
    with T0 again, which the server now takes — and succeeds. Only then does the second
    request's refusal arrive: a login of this client has succeeded since it took its
    token, so it retries with that one instead of logging in once more."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg, state = _late_refusal(tmp_path)
    first_done = threading.Event()
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])

    def login(request: httpx.Request) -> httpx.Response:
        state["logged_in"] = True
        return next(answers)

    def data(request: httpx.Request) -> httpx.Response:
        which = json.loads(request.content)["securityList"][0]
        if which == "late" and not state.get("late_refused"):
            first_done.wait(5)
            state["late_refused"] = True
            return _auth_fail()
        if not state["logged_in"]:
            return _auth_fail()
        return _ok({"total": 0, "list": [which]})

    results: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._get_token()  # both requests start from T0, read before any login

            def call(which: str) -> None:
                try:
                    results[which] = client._call("quote.realtime", body={"securityList": [which]})
                except ApiError as error:
                    results[which] = error.status_code
                if which == "early":
                    first_done.set()

            threads = [threading.Thread(target=call, args=(w,)) for w in ("late", "early")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert results == {
        "early": {"total": 0, "list": ["early"]},
        "late": {"total": 0, "list": ["late"]},
    }
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_a_late_refusal_takes_the_login_that_followed_it_even_with_the_same_token(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg, state = _late_refusal(tmp_path)
    first_done = anyio.Event()
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])

    def login(request: httpx.Request) -> httpx.Response:
        state["logged_in"] = True
        return next(answers)

    async def data(request: httpx.Request) -> httpx.Response:
        which = json.loads(request.content)["securityList"][0]
        if which == "late" and not state.get("late_refused"):
            with anyio.fail_after(5):
                await first_done.wait()
            state["late_refused"] = True
            return _auth_fail()
        if not state["logged_in"]:
            return _auth_fail()
        return _ok({"total": 0, "list": [which]})

    results: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._get_token()

            async def call(which: str) -> None:
                try:
                    results[which] = await client._call(
                        "quote.realtime", body={"securityList": [which]}
                    )
                except ApiError as error:
                    results[which] = error.status_code
                if which == "early":
                    first_done.set()

            async with anyio.create_task_group() as tg:
                tg.start_soon(call, "late")
                tg.start_soon(call, "early")
    assert results == {
        "early": {"total": 0, "list": ["early"]},
        "late": {"total": 0, "list": ["late"]},
    }
    assert login_route.call_count == 1


def _who_and_token(request: httpx.Request) -> tuple[str, str]:
    return (
        json.loads(request.content)["securityList"][0],
        request.headers["Authorization"].removeprefix("Bearer "),
    )


def test_a_late_refusal_is_not_handed_a_login_token_already_refused(tmp_path, monkeypatch):
    """A holds T1 in flight. This client logs in (T2); T2 is revoked, and C, refused with
    it, is logging in anew. A's T1 is refused only now. A tries T2 from the cache file once
    (it cannot know), and once that is refused, waits for C's login — T2 is not handed back
    to it as "a login that came after its token"."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T1")
    lock = _CountingLock()
    valid: set[str] = set()
    tokens = iter(["T2", "T3"])
    release_a, c_logging_in = threading.Event(), threading.Event()
    sent: list[tuple[str, str]] = []

    def login(request: httpx.Request) -> httpx.Response:
        token = next(tokens)
        if token == "T3":
            c_logging_in.set()
            deadline = time.monotonic() + 5
            while lock.asked < 3 and time.monotonic() < deadline:  # B, C, then A waits on it
                time.sleep(0.01)
        valid.add(token)
        return _login_response(token)

    def data(request: httpx.Request) -> httpx.Response:
        who, token = _who_and_token(request)
        sent.append((who, token))
        if who == "A" and token == "T1":
            release_a.wait(5)
        return _ok({"total": 0, "list": [who]}) if token in valid else _auth_fail()

    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._lock = lock  # type: ignore[assignment]

            def call(who: str) -> None:
                try:
                    client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.code

            a = threading.Thread(target=call, args=("A",))
            a.start()
            deadline = time.monotonic() + 5
            while not sent and time.monotonic() < deadline:
                time.sleep(0.01)
            call("B")  # T1 refused: logs in, T2
            valid.clear()  # T2 revoked
            c = threading.Thread(target=call, args=("C",))
            c.start()
            assert c_logging_in.wait(5)
            release_a.set()
            a.join()
            c.join()
    assert out == {"A": "ok", "B": "ok", "C": "ok"}
    assert [t for w, t in sent if w == "A"] == ["T1", "T2", "T3"]
    assert login_route.call_count == 2


@pytest.mark.anyio
async def test_async_a_late_refusal_is_not_handed_a_login_token_already_refused(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T1")
    valid: set[str] = set()
    tokens = iter(["T2", "T3"])
    release_a, c_logging_in = anyio.Event(), anyio.Event()
    sent: list[tuple[str, str]] = []
    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def login(request: httpx.Request) -> httpx.Response:
                token = next(tokens)
                if token == "T3":
                    c_logging_in.set()
                    with anyio.fail_after(5):  # A waits on this login
                        while client._lock.statistics().tasks_waiting < 1:
                            await anyio.sleep(0.01)
                valid.add(token)
                return _login_response(token)

            async def data(request: httpx.Request) -> httpx.Response:
                who, token = _who_and_token(request)
                sent.append((who, token))
                if who == "A" and token == "T1":
                    with anyio.fail_after(5):
                        await release_a.wait()
                return _ok({"total": 0, "list": [who]}) if token in valid else _auth_fail()

            login_route = router.post(LOGIN).mock(side_effect=login)
            router.post(REALTIME).mock(side_effect=data)

            async def call(who: str) -> None:
                try:
                    await client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.code

            async with anyio.create_task_group() as tg:
                tg.start_soon(call, "A")
                with anyio.fail_after(5):
                    while not sent:
                        await anyio.sleep(0.01)
                await call("B")
                valid.clear()
                tg.start_soon(call, "C")
                with anyio.fail_after(5):
                    await c_logging_in.wait()
                release_a.set()
    assert out == {"A": "ok", "B": "ok", "C": "ok"}
    assert [t for w, t in sent if w == "A"] == ["T1", "T2", "T3"]
    assert login_route.call_count == 2


def test_a_late_refusal_takes_the_token_that_superseded_the_login_one(tmp_path, monkeypatch):
    """A holds T0 in flight. This client logs in (T1); then another process logs in, and
    the server takes its T2 instead of T1 — B moves on to T2 from the cache file. A's T0 is
    refused only now: it takes T2, as 0.5.8 did, not the superseded T1."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    valid: set[str] = set()
    release_a = threading.Event()
    sent: list[tuple[str, str]] = []

    def data(request: httpx.Request) -> httpx.Response:
        who, token = _who_and_token(request)
        sent.append((who, token))
        if who == "A" and token == "T0":
            release_a.wait(5)
        return _ok({"total": 0, "list": [who]}) if token in valid else _auth_fail()

    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(return_value=_login_response("T1"))
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:

            def call(who: str) -> None:
                try:
                    client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.code

            a = threading.Thread(target=call, args=("A",))
            a.start()
            deadline = time.monotonic() + 5
            while not sent and time.monotonic() < deadline:
                time.sleep(0.01)
            client.login()  # T1
            _seed(cfg, "T2")  # another process logs in; the server now takes only T2
            valid.add("T2")
            call("B")
            release_a.set()
            a.join()
    assert out == {"A": "ok", "B": "ok"}
    assert [t for w, t in sent if w == "A"] == ["T0", "T2"]
    assert [t for w, t in sent if w == "B"] == ["T1", "T2"]
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_a_late_refusal_takes_the_token_that_superseded_the_login_one(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    valid: set[str] = set()
    release_a = anyio.Event()
    sent: list[tuple[str, str]] = []

    async def data(request: httpx.Request) -> httpx.Response:
        who, token = _who_and_token(request)
        sent.append((who, token))
        if who == "A" and token == "T0":
            with anyio.fail_after(5):
                await release_a.wait()
        return _ok({"total": 0, "list": [who]}) if token in valid else _auth_fail()

    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(return_value=_login_response("T1"))
        router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def call(who: str) -> None:
                try:
                    await client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.code

            async with anyio.create_task_group() as tg:
                tg.start_soon(call, "A")
                with anyio.fail_after(5):
                    while not sent:
                        await anyio.sleep(0.01)
                await client.login()
                _seed(cfg, "T2")
                valid.add("T2")
                await call("B")
                release_a.set()
    assert out == {"A": "ok", "B": "ok"}
    assert [t for w, t in sent if w == "A"] == ["T0", "T2"]
    assert login_route.call_count == 1


def test_a_recovery_reading_the_cache_slowly_takes_the_login_that_landed_meanwhile(
    tmp_path, monkeypatch
):
    """A and B are refused T0 together. While B reads the cache file, A's recovery login
    returns T0 again, which the server now takes. When B's read comes back with T0 — the
    token it was refused — B takes that login, instead of comparing strings and logging in
    once more."""
    import gangtise_openapi._client as client_module

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    both_refused = threading.Barrier(2, timeout=5)
    logged_in, a_done, b_refused = threading.Event(), threading.Event(), threading.Event()
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])
    real_read = client_module.read_token_cache

    def read(path: Path) -> object:
        if threading.current_thread().name == "B" and b_refused.is_set():
            a_done.wait(5)  # a slow read: A's recovery finishes meanwhile
        return real_read(path)

    def login(request: httpx.Request) -> httpx.Response:
        logged_in.set()
        return next(answers)

    def data(request: httpx.Request) -> httpx.Response:
        who, _ = _who_and_token(request)
        if not logged_in.is_set():
            both_refused.wait()
            if who == "B":
                b_refused.set()
            return _auth_fail()
        return _ok({"total": 0, "list": [who]})

    monkeypatch.setattr(client_module, "read_token_cache", read)
    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._get_token()  # both start from T0

            def call(who: str) -> None:
                try:
                    client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.status_code
                if who == "A":
                    a_done.set()

            threads = [threading.Thread(target=call, args=(w,), name=w) for w in ("A", "B")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
    assert out == {"A": "ok", "B": "ok"}
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_a_recovery_reading_the_cache_slowly_takes_the_login_that_landed_meanwhile(
    tmp_path, monkeypatch
):
    import contextvars

    import gangtise_openapi._client as client_module

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "T0")
    who_var: contextvars.ContextVar[str] = contextvars.ContextVar("who", default="")
    a_done = threading.Event()  # set from the event loop, waited on in a worker thread
    state = {"refused": 0, "logged_in": False, "b_refused": False}
    both_refused = anyio.Event()
    answers = iter([_login_response("T0"), _busy(), _busy(), _busy()])
    real_read = client_module.read_token_cache

    def read(path: Path) -> object:  # runs on a worker thread, in the caller's context
        if who_var.get() == "B" and state["b_refused"]:
            a_done.wait(5)
        return real_read(path)

    def login(request: httpx.Request) -> httpx.Response:
        state["logged_in"] = True
        return next(answers)

    async def data(request: httpx.Request) -> httpx.Response:
        who, _ = _who_and_token(request)
        if not state["logged_in"]:
            state["refused"] += 1
            if state["refused"] == 2:
                both_refused.set()
            with anyio.fail_after(5):
                await both_refused.wait()
            if who == "B":
                state["b_refused"] = True
            return _auth_fail()
        return _ok({"total": 0, "list": [who]})

    monkeypatch.setattr(client_module, "read_token_cache", read)
    out: dict[str, object] = {}
    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._get_token()

            async def call(who: str) -> None:
                who_var.set(who)
                try:
                    await client._call("quote.realtime", body={"securityList": [who]})
                    out[who] = "ok"
                except ApiError as error:
                    out[who] = error.status_code
                if who == "A":
                    a_done.set()

            async with anyio.create_task_group() as tg:
                tg.start_soon(call, "A")
                tg.start_soon(call, "B")
    assert out == {"A": "ok", "B": "ok"}
    assert login_route.call_count == 1


def test_a_failed_login_is_not_kept_by_the_client(tmp_path, monkeypatch):
    """Nothing of a failed call — its frames, the body it was sending — outlives it in the
    client: the shared failure belongs to the requests that waited on that login."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)

    class Payload:
        pass

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post(LOGIN).mock(return_value=_busy())
        router.post(REALTIME)
        with GangtiseClient(_config=cfg) as client:

            def call() -> weakref.ref[Payload]:
                payload = Payload()
                with pytest.raises(ApiError):
                    client._call("quote.realtime", body={"securityList": ["x"]})
                return weakref.ref(payload)

            ref = call()
            gc.collect()
            assert ref() is None
            assert client._login_round is None


def test_the_cache_read_after_a_failed_login_holds_the_lock(tmp_path, monkeypatch):
    """Read and written back under the lock, so a login of this client cannot land in
    between and have its fresh token replaced by an older one from the file."""
    import gangtise_openapi._client as client_module

    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    held: list[bool] = []
    real_read = client_module.read_token_cache

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "from-other-process")
        return _busy()

    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:

            def read(path: Path) -> object:
                held.append(client._lock.locked())
                return real_read(path)

            monkeypatch.setattr(client_module, "read_token_cache", read)
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert held == [False, True]  # the fast-path read, then the fallback under the lock


@pytest.mark.anyio
async def test_async_failed_login_uses_a_token_another_process_cached_meanwhile(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "from-other-process")
        return _busy()

    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._call("quote.realtime", body={"securityList": ["x"]})
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer from-other-process"
    ]


def test_recovery_whose_login_fails_replays_with_a_token_cached_meanwhile(tmp_path, monkeypatch):
    """The rejected token's recovery logs in; that fails, but another process has cached
    a token while it was tried: the request's one unproven replay goes to that token."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "from-other-process")
        return _busy()

    def data(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer stale":
            return _auth_fail()
        return _ok({"total": 0, "list": []})

    with respx.mock(base_url=BASE) as router:
        login_route = router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login_route.call_count == 3
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer from-other-process",
    ]


def test_recovery_whose_login_fails_after_the_unproven_replay_ends(tmp_path, monkeypatch):
    """The one replay with a token this client did not mint is spent: a failed login
    ends the request with its own error, whatever the cache holds by then."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "third")
        return _busy()

    def data(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer stale":
            _seed(cfg, "also-dead")
        return _auth_fail()

    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.status_code == 503
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer also-dead",
    ]


@pytest.mark.anyio
async def test_async_recovery_whose_login_fails_replays_with_a_token_cached_meanwhile(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")

    def login(request: httpx.Request) -> httpx.Response:
        _seed(cfg, "from-other-process")
        return _busy()

    def data(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer stale":
            return _auth_fail()
        return _ok({"total": 0, "list": []})

    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(side_effect=login)
        route = router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._call("quote.realtime", body={"securityList": ["x"]})
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer from-other-process",
    ]


# ─── login() ───


def test_login_with_env_token_reports_it_and_contacts_nothing(tmp_path):
    """TS v0.40.0: GANGTISE_TOKEN wins for every other call, so reporting a freshly
    minted token would name an account no request uses — and a token-only setup (no
    AK/SK) has nothing to log in with."""
    cfg = _cfg(tmp_path, token="env-tok", access_key=None)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN)
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert login.call_count == 0
    assert out == {"authorization": "Bearer env-tok", "cache": None, "source": "env-token"}


def test_login_with_credentials_always_logs_in(tmp_path):
    """A valid cache must not stand in: after a credential swap it would report the
    previous account."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "cached")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert login.call_count == 1
    assert out["source"] == "login"
    assert out["authorization"] == "Bearer fresh"
    assert out["cache"]["access_token"] == "fresh"
    assert out["cache"]["issued_for"] == FP


@pytest.mark.anyio
async def test_async_login_with_env_token_reports_it(tmp_path):
    cfg = _cfg(tmp_path, token="env-tok", access_key=None)
    async with AsyncGangtiseClient(_config=cfg) as client:
        out = await client.login()
    assert out["source"] == "env-token"


# ─── confirm gates ───


def test_destructive_endpoint_refused_without_confirm_and_nothing_sent(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]})
    assert route.call_count == 0
    assert "confirm=True" in str(exc.value)
    assert "stock_pool_list" in str(exc.value)
    assert "poolIdList=['1']" in str(exc.value)


def test_destructive_endpoint_passes_with_confirm(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool").mock(
            return_value=_ok({"successList": ["1"], "failList": []})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]}, confirm=True)
    assert route.call_count == 1
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_destructive_endpoint_refused_without_confirm(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/drive/deleteFolder")
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ValidationError):
                await client._call("vault.drive.delete-folder", body={"folderId": "1"})
    assert route.call_count == 0


def test_earning_forecast_priced_above_guard_is_refused(tmp_path):
    """TS v0.44.0: weekdays x 3 rows x 0.5 credits; ten years ≈ 3900 credits."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    body = {"securityList": ["600519.SH"], "startDate": "2016-01-01", "endDate": "2026-01-01"}
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/earning-forecast")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call("fundamental.earning-forecast", body=body)
    assert route.call_count == 0
    assert "1000-credit guard" in str(exc.value)


def test_earning_forecast_small_range_or_confirm_goes_through(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_ok({"fieldList": [], "list": []})
        )
        with GangtiseClient(_config=cfg) as client:
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "2026-01-01", "endDate": "2026-03-31"},
            )
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "2016-01-01", "endDate": "2026-01-01"},
                confirm=True,
            )
    assert route.call_count == 2


def test_earning_forecast_unreadable_date_is_refused_not_priced_at_zero(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/earning-forecast")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "01-07-2026"},
            )
    assert route.call_count == 0
    assert "could not be priced" in str(exc.value)


# ─── per-item failures inside a success ───


def test_fail_list_marks_partial_and_warns(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    data = {
        "successList": [{"securityCode": "600519.SH"}],
        "failList": [{"securityCode": "BAD.XX", "failReason": "证券代码不存在"}],
    }
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/stock-pool/addStock").mock(return_value=_ok(data))
        with (
            GangtiseClient(_config=cfg) as client,
            pytest.warns(UserWarning, match=r"1 item\(s\) failed.*BAD\.XX（证券代码不存在）"),  # noqa: RUF001
        ):
            out = client._call(
                "vault.stock-pool.add-stock",
                body={"poolId": "1", "securityList": ["600519.SH", "BAD.XX"]},
            )
    assert out["partial"] is True


def test_empty_fail_list_stays_clean(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/stock-pool/addStock").mock(
            return_value=_ok({"successList": [{"securityCode": "600519.SH"}], "failList": []})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client._call(
                "vault.stock-pool.add-stock", body={"poolId": "1", "securityList": ["600519.SH"]}
            )
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_fail_list_marks_partial(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/drive/moveFile").mock(
            return_value=_ok({"successList": [], "failList": [{"fileId": "9"}]})
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.warns(UserWarning, match="1 item"):
                out = await client._call(
                    "vault.drive.move-file", body={"fileIdList": ["9"], "folderId": "1"}
                )
    assert out["partial"] is True


def test_call_refuses_a_download_endpoint_before_sending(tmp_path):
    """Through the JSON path a billed download would go out and only then fail to
    parse the file bytes."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.get("/application/open-insight/summary/v2/download/file")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError):
            client._call("insight.summary.download", query={"summaryId": "1"})
    assert route.call_count == 0


@pytest.mark.parametrize("value", ["false", "False", 0, 1, None, "yes"])
def test_confirm_must_be_a_real_bool(tmp_path, value):
    """It releases deletions and >1000-credit fetches: a truthy string from a config
    file must not pass as confirmation (and a falsy non-bool is a bug worth naming)."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError, match="confirm"):
            client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]}, confirm=value)
    assert route.call_count == 0


def test_call_refuses_an_upload_endpoint_with_a_json_body(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/drive/uploadFile")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError, match="upload"):
            client._call("vault.drive.upload", body={"spaceType": 1})
    assert route.call_count == 0


def test_concurrent_first_calls_build_one_http_client(tmp_path):
    """An unguarded lazy init built one client per racing thread."""
    import threading
    import time

    from gangtise_openapi import _client as client_module

    built: list[object] = []
    real = client_module.build_sync_client
    gate = threading.Barrier(8)

    def slow_build(config):
        built.append(config)
        time.sleep(0.05)  # widen the check-then-set window
        return real(config)

    client = GangtiseClient(_config=_cfg(tmp_path, token="tok"))
    orig = client_module.build_sync_client
    client_module.build_sync_client = slow_build
    try:

        def worker():
            gate.wait()
            client._http_client()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        client_module.build_sync_client = orig
        client.close()
    assert len(built) == 1


def test_non_utf8_token_cache_is_a_miss_not_a_crash(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.token_cache_path.write_bytes(b"\xff\xfe\x00garbage")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1


def test_corrupt_title_cache_never_costs_the_paid_rows(tmp_path):
    """flush() re-reads the file to merge. A non-UTF-8 file there must not raise: it
    would do so AFTER the (billed) list call succeeded, losing the rows paid for."""
    from gangtise_openapi.domains.insight import Insight

    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    cfg.title_cache_path.write_bytes(b"\xff\xfe\x00garbage")
    rows = [{"reportId": "1", "title": "年报"}, {"reportId": "2", "title": "\udc80孤立代理"}]
    with respx.mock(base_url=BASE) as router:
        # The server's JSON escapes a lone surrogate (``\\udc80``); json.loads decodes
        # it back into one, which is what the title cache then has to write.
        payload = {"code": "000000", "status": True, "data": {"total": 2, "list": rows}}
        router.post("/application/open-insight/broker-report/getList").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(payload).encode(),
                headers={"content-type": "application/json"},
            )
        )
        with GangtiseClient(_config=cfg) as client:
            out = Insight(client).research_list(size=2, raw=True)
    assert [r["reportId"] for r in out["list"]] == ["1", "2"]


def test_no_replay_endpoint_is_replayed_once_after_an_auth_rejection(tmp_path):
    """A rejected token means the request never ran, so even a billed no-replay
    endpoint (ai.one-pager, 50/call) is sent again with the recovered token — once."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def one_pager(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                return _auth_fail()
            return _ok({"date": "2026-09-30", "content": "x"})

        route = router.post("/application/open-ai/agent/one-pager").mock(side_effect=one_pager)
        with GangtiseClient(_config=cfg) as client:
            out = client._call("ai.one-pager", body={"securityCode": "600519.SH"})
    assert out["content"] == "x"
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer fresh",
    ]


def test_auth_replay_shares_one_transient_retry_budget(tmp_path, monkeypatch):
    """One transient-retry budget across auth replays: 5xx, auth, 5xx, 5xx, 5xx goes
    out 4 times, as in TS — a fresh budget per replay would send it 5 times."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    answers = iter(
        [
            httpx.Response(503, text="busy"),  # retry 1 of 2
            _auth_fail(),  # replay with a recovered token — not a retry
            httpx.Response(503, text="busy"),  # retry 2 of 2
            httpx.Response(503, text="busy"),  # budget spent: surfaces
            _ok({"total": 0, "list": []}),
        ]
    )
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(side_effect=lambda request: next(answers))
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.status_code == 503
    assert route.call_count == 4


def test_auth_code_inside_a_500_is_recovered_at_once_and_keeps_the_budget(tmp_path, monkeypatch):
    """An auth code wrapped in HTTP 500 is recovered at once, as in the CLI. Retried
    as a 500 with the dead token, it would spend the shared budget, and one ordinary
    500 after the recovery would then fail the call."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    auth_500 = httpx.Response(
        500, json={"code": "0000001008", "status": False, "msg": "token 失效"}
    )
    answers = iter([auth_500, httpx.Response(500, text="busy"), _ok({"total": 0, "list": []})])
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(side_effect=lambda request: next(answers))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer fresh",
        "Bearer fresh",
    ]


def test_login_answer_without_a_token_is_a_named_api_error(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_ok({"expiresIn": 3600}))
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError, match="accessToken"):
            client.login()


def test_login_answer_with_a_bad_expiry_reads_as_expired(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(
            return_value=_ok({"accessToken": "t", "expiresIn": None, "time": "x"})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert out["cache"]["expires_in"] == 0


@pytest.mark.parametrize("timeout", [0, 0.5, -1, 7200, float("nan"), "30"])
def test_timeout_in_code_is_held_to_the_env_bounds(timeout):
    from gangtise_openapi._errors import ConfigError

    with pytest.raises(ConfigError, match="timeout must be"):
        GangtiseClient(access_key="ak", secret_key="sk", timeout=timeout)


def test_timeout_in_code_inside_the_bounds_is_kept():
    assert GangtiseClient(access_key="ak", secret_key="sk", timeout=45).config.timeout_ms == 45_000


def test_an_env_token_with_a_bearer_prefix_is_the_same_token(tmp_path):
    """``GANGTISE_TOKEN="Bearer x"`` and a cached ``x`` are one token: a rejected one must
    not be "replayed" as if it were a different, unproven token."""
    cfg = Config(
        base_url=BASE,
        access_key="ak",
        secret_key="sk",
        token="Bearer dead",
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
    )
    _seed(cfg, "dead")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def data(request):
            if request.headers["Authorization"] == "Bearer dead":
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer dead",
        "Bearer fresh",
    ]
