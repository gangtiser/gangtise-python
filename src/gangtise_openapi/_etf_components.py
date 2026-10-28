"""``fund.etf_pcf_components``: the API answers each component's name but not its
code, so the SDK fills ``componentCode`` in from the name. Ported from the TS CLI's
``core/etfComponents.ts`` (v0.49.0). A row that already carries a code keeps it,
which makes this a no-op once the API returns codes again — then remove the module.

A name is looked up — in the whole-market securities list, fetched once per call,
else with ``reference.securities-search`` — and the candidates are checked against
the row's ``close``, a recent daily close of the component's own listing (CLI probe
on 14 ETFs — A share, Hong Kong, US, A+H, bond, gold): first against the realtime
quote's latest price and previous close, then, for rows the quote does not settle,
against the closes of the day the list's prices in that listing's market belong to
(:func:`_list_dates`). The price tells apart the A and H listings of one company,
which an A+H ETF lists as two rows under the same name. Where no price decides (an
ex-dividend day, a suspension, a bond with no quote), an exact name match stands
only in an ETF whose components all trade in one market — the ETF's own exchange
breaking a tie within it; in an ETF holding several markets the row stays null, as
does anything else still open.

Three deliberate differences from the CLI (v0.49.0): a name whose lookup failed
leaves the ETF's market unknown (the CLI treats it as having no listing, so another
row may be matched by name in the wrong market); a listing several searches find is
one candidate, not a tie with itself; and a price that agrees with listings in two
markets is settled once the ETF's market is known, rather than left null at once.

Every extra request is free (securities lists, search, realtime quote, day kline).
The matching itself lives in :class:`_Fill`; the sync and async drivers only send
the requests. Nothing here raises: the component list was fetched (and billed)
already, and is returned whatever the lookups do.
"""

from __future__ import annotations

import bisect
import datetime as dt
import enum
import re
import threading
import warnings
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypeVar

import anyio

from gangtise_openapi._errors import ApiError
from gangtise_openapi._normalize import normalize_rows

if TYPE_CHECKING:
    from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient

_T = TypeVar("_T")
_R = TypeVar("_R")
_Row = dict[str, Any]
_Listing = tuple[str, str]
_Prices = dict[str, list[float]]
_History = dict[str, list[tuple[str, float]]]

# A component's close is the quoted price itself: on 14 ETFs (CLI probe 2026-10-27)
# every confirmed row was equal to the cent, while the same name's listing in another
# market came as close as 0.15% (A and H shares of one company, 0.3% often). The slack
# stays well under that.
_PRICE_TOLERANCE = 0.0005
# Code formats the realtime quote takes; nothing else is sent (bonds, listings in
# other markets, placeholder codes the search returns).
_QUOTABLE = re.compile(r"\d{6}\.(SH|SZ|BJ)|\d{5}\.HK|[A-Z][A-Z0-9.]*\.(O|N|A)", re.ASCII)
_QUOTE_BATCH = 500
# Daily closes are fetched for this many calendar days back: a component list's
# prices lag its trade date (before the open, a day's list carried the A shares'
# closes of two trading days earlier and the Hong Kong rows' of the day before; later
# in a day they move up a day), and the window also spans a long weekend.
_CLOSES_WINDOW_DAYS = 10
# Codes per daily-close request: the window's trading days times this stays under
# the 10000-row cap of a day-kline request.
_CLOSES_BATCH = 1000
_CLOSES_LIMIT = 10_000
# The whole-market sectors of reference.sector-constituents — 全部A股, 全部港股,
# 全部美股: one request each instead of one search per component name.
_MARKET_SECTORS = ("1000000002", "1000002615", "1000002618")
_US_TICKER = re.compile(r"[A-Z][A-Z0-9]{0,6}", re.ASCII)
_SEARCH_TOP = 10
_SHOWN_UNRESOLVED = 20
_BEIJING = dt.timezone(dt.timedelta(hours=8))


@dataclass(frozen=True)
class _Candidate:
    code: str
    name: str
    category: str
    prefix: bool = False


@dataclass
class _Etf:
    """``market``: set only when everything known about this ETF's components points
    to one market; ``None`` for an ETF that holds several (an A+H ETF), or before
    that is known."""

    exchange: str
    market: str | None = None
    used: set[str] = field(default_factory=set)


class _Open(enum.Enum):
    """What :func:`_by_price` answers when the price settles nothing (``None`` is a
    settled answer: the row stays null)."""

    OPEN = enum.auto()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _agrees(close: float, price: float) -> bool:
    return price > 0 and abs(close - price) / price <= _PRICE_TOLERANCE


def _squash(name: str) -> str:
    return re.sub(r"\s+", "", name)


def _base(name: str) -> str:
    """The exchange's short name drops the share-class suffix the search keeps
    ("小米集团-W")."""
    return re.sub(r"-[A-Z]+\Z", "", _squash(name))


def _ticker(code: str) -> str:
    return code[: code.rfind(".")]


def _exchange(code: str) -> str:
    return code[code.rfind(".") + 1 :]


def _market(code: str) -> str:
    suffix = _exchange(code)
    if suffix in ("SH", "SZ", "BJ"):
        return "CN"
    return "US" if suffix in ("O", "N", "A") else suffix


def _is_quotable(candidate: _Candidate) -> bool:
    return candidate.category in ("stock", "dr") and bool(_QUOTABLE.fullmatch(candidate.code))


def _to_candidates(rows: Any) -> list[_Candidate]:
    return [
        _Candidate(row["gtsCode"], row["gtsName"], str(row.get("category")))
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict)
        and isinstance(row.get("gtsCode"), str)
        and isinstance(row.get("gtsName"), str)
        and row.get("category") != "index"
    ]


def _exact(found: list[_Candidate], key: str) -> list[_Candidate]:
    return [c for c in found if _base(c.name) == _base(key) or _ticker(c.code) == key]


def _wants_us_suffix(key: str, exact: list[_Candidate]) -> bool:
    """A US ticker the fuzzy search misses is asked for again with its exchange
    suffix: "TRI" finds TRI.LON by ticker but not Thomson Reuters' TRI.O."""
    return bool(_US_TICKER.fullmatch(key)) and not any(_market(c.code) == "US" for c in exact)


def _by_ticker(rows: Any, key: str) -> list[_Candidate]:
    return [c for c in _to_candidates(rows) if _ticker(c.code) == key]


def _with_prefixes(found: list[_Candidate], exact: list[_Candidate], key: str) -> list[_Candidate]:
    """The listings a component name can stand for: exact name (or ticker) matches,
    and names that only start with it — the exchange truncates long names ("比亚迪电"),
    and a Hong Kong listing can carry a longer name than the A share ("中国石油" /
    "中国石油股份"). A prefix match needs its price to agree (see :func:`_by_price` /
    :func:`_by_name`). A listing is one candidate however many searches find it (the
    ``.O`` and the ``.N`` search can both answer TRI.O): counted twice, it would tie
    with itself and leave the row null."""
    name = _base(key)
    listed: dict[str, _Candidate] = {}
    for c in exact:
        listed.setdefault(c.code, c)
    if len(name) >= 2:
        for c in found:
            if c.code not in listed and _base(c.name).startswith(name):
                listed[c.code] = replace(c, prefix=True)
    return list(listed.values())


def _narrow(candidates: list[_Candidate], etf: _Etf) -> str | None:
    """Among several that fit equally. A tie across markets (the A and the H listing
    of one name) is broken only for an ETF whose components all trade in one market;
    in an ETF that holds more than one, the name cannot say which listing a row is,
    and the row stays null. A tie within one market (a bond on two exchanges) goes to
    the ETF's own exchange."""
    left = candidates
    if len({_market(c.code) for c in left}) > 1:
        if not etf.market:
            return None
        left = [c for c in left if _market(c.code) == etf.market]
    if len(left) > 1:
        same = [c for c in left if _exchange(c.code) == etf.exchange]
        if same:
            left = same
    return left[0].code if len(left) == 1 else None


def _by_price(
    row: _Row,
    candidates: list[_Candidate],
    prices: _Prices,
    etf: _Etf,
    unchecked: Callable[[_Candidate], bool],
) -> list[_Candidate] | _Open:
    """The listings whose price agrees with the row's close: exact matches first, then
    prefix matches (:meth:`_Fill._settle` picks among them). ``OPEN`` when none
    agrees — and when a listing of the tier has no price to check (none, or 0 while
    suspended) and ``unchecked`` says it could still be the row: a match beside it
    settles nothing."""
    close = _number(row.get("close"))
    if close is None:
        return _Open.OPEN
    left = [c for c in candidates if c.code not in etf.used]
    for tier in ([c for c in left if not c.prefix], [c for c in left if c.prefix]):
        if any(not any(p > 0 for p in prices.get(c.code, ())) and unchecked(c) for c in tier):
            return _Open.OPEN
        matched = [c for c in tier if any(_agrees(close, p) for p in prices.get(c.code, ()))]
        if matched:
            return matched
    return _Open.OPEN


def _by_name(candidates: list[_Candidate], etf: _Etf) -> str | None:
    """No price agrees — an ex-dividend day moves the previous close off the listed
    one, a suspension quotes 0, a bond has no quote, a quote request failed. In an ETF
    that trades in one market, an exact name match in that market stands. In one that
    holds several, nothing does: a quote that disagrees does not rule a listing out
    (ex-dividend, suspended), and a missing one does not rule it in. A prefix match
    never stands on its name alone."""
    if not etf.market:
        return None
    pool = [
        c
        for c in candidates
        if not c.prefix and c.code not in etf.used and _market(c.code) == etf.market
    ]
    return _narrow(pool, etf) if pool else None


def _rejects_a_code(error: Exception) -> bool:
    """One code the quote does not know fails its whole batch with 120001."""
    return isinstance(error, ApiError) and error.code == "120001"


def _in_batches(codes: list[str], size: int) -> list[list[str]]:
    return [codes[i : i + size] for i in range(0, len(codes), size)]


def _list_dates(
    rows: list[_Row], candidates: dict[str, list[_Candidate]], history: _History
) -> dict[str, str]:
    """The trading day this ETF's list prices are the closes of, per market — one
    list can carry its A shares' closes of one day and its H shares' of another: the
    day on which the most rows with a single exact listing in that market equal that
    listing's close. A market gets none unless at least two rows agree on one day and
    no other day ties with it."""
    votes: dict[str, dict[str, int]] = {}
    for row in rows:
        close = _number(row.get("close"))
        if close is None:
            continue
        exact = [c for c in candidates.get(row["componentName"], []) if not c.prefix]
        if len(exact) != 1:
            continue
        tally = votes.setdefault(_market(exact[0].code), {})
        for date, day_close in history.get(exact[0].code, []):
            if _agrees(close, day_close):
                tally[date] = tally.get(date, 0) + 1
    dates: dict[str, str] = {}
    for where, tally in votes.items():
        ranked = sorted(tally.items(), key=lambda item: -item[1])
        if ranked and ranked[0][1] >= 2 and (len(ranked) < 2 or ranked[1][1] != ranked[0][1]):
            dates[where] = ranked[0][0]
    return dates


def _closes_on(dates: dict[str, str], history: _History) -> _Prices:
    """Each code's close on its market's date, or its last close before it (a market
    closed that day, or a suspension)."""
    out: _Prices = {}
    for code, series in history.items():
        date = dates.get(_market(code))
        if not date:
            continue
        before = [close for day, close in series if day <= date]
        if before:
            out[code] = [before[-1]]
    return out


def _carries_code(row: _Row) -> bool:
    """A row the API answered with a code of its own; ``None`` or ``""`` is no code."""
    return isinstance(row.get("componentCode"), str) and row["componentCode"] != ""


def _needs_code(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and not _carries_code(row)
        and isinstance(row.get("componentName"), str)
    )


class _Fill:
    """The matching, step by step; the drivers feed it the lookups' answers."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.pending: list[_Row] = [row for row in rows if _needs_code(row)]
        self.names = list(dict.fromkeys(row["componentName"] for row in self.pending))
        self.candidates: dict[str, list[_Candidate]] = {}
        self.codes: dict[int, str | None] = {}
        # Names whose lookup failed: they may trade in any market.
        self.failed: set[str] = set()
        # Rows whose price agrees with listings in more than one market, waiting for
        # the ETF's market (place_by_name).
        self.tied: dict[int, list[_Candidate]] = {}
        self.etfs: list[tuple[list[_Row], _Etf]] = []
        self.lagging: list[tuple[list[_Row], _Etf]] = []

    def _of(self, row: _Row) -> list[_Candidate]:
        return self.candidates.get(row["componentName"], [])

    def _place(self, row: _Row, code: str | None, etf: _Etf) -> None:
        self.codes[id(row)] = code
        if code:
            etf.used.add(code)

    def _settle(self, row: _Row, matched: list[_Candidate], etf: _Etf) -> None:
        """The listings the row's price agrees with. A tie across markets (an A share
        and an H share at the same number) waits for :meth:`place_by_name`, where the
        ETF's market can break it; any other outcome is final."""
        code = _narrow(matched, etf)
        if code is None and len({_market(c.code) for c in matched}) > 1:
            self.tied[id(row)] = matched
        else:
            self._place(row, code, etf)

    def take_candidates(self, found: list[list[_Candidate] | None]) -> None:
        """Each name's candidates, in ``names`` order; ``None`` for a failed lookup."""
        for name, listed in zip(self.names, found, strict=True):
            self.candidates[name] = listed or []
            if listed is None:
                self.failed.add(name)

    def quotable(self) -> list[str]:
        return list(
            dict.fromkeys(
                c.code for found in self.candidates.values() for c in found if _is_quotable(c)
            )
        )

    def place_by_price(self, prices: _Prices) -> None:
        """Prices first, over every row: a listing its own price confirms is taken
        before a row of the same name (the other share class of an A+H pair) can claim
        it by name alone. A listing the quote misses is checked against its daily
        closes in :meth:`place_lagging`."""
        for fund_code in dict.fromkeys(row.get("fundCode") for row in self.pending):
            own = [row for row in self.pending if row.get("fundCode") == fund_code]
            etf = _Etf(exchange=_exchange(str(fund_code)))
            self.etfs.append((own, etf))
            for row in own:
                matched = _by_price(row, self._of(row), prices, etf, _is_quotable)
                if matched is not _Open.OPEN:
                    self._settle(row, matched, etf)

    def _open(self, own: list[_Row]) -> list[_Row]:
        return [
            row
            for row in own
            if id(row) not in self.codes
            and id(row) not in self.tied
            and _number(row.get("close")) is not None
            and any(_is_quotable(c) for c in self._of(row))
        ]

    def lagging_codes(self) -> list[str]:
        """A list whose prices lag the quote by a day or more leaves its rows
        unplaced, as do a suspension and an ex-dividend day: the codes whose daily
        closes :meth:`place_lagging` needs."""
        self.lagging = [(own, etf) for own, etf in self.etfs if self._open(own)]
        return list(
            dict.fromkeys(
                c.code
                for own, _etf in self.lagging
                for row in own
                for c in self._of(row)
                if _is_quotable(c)
            )
        )

    def place_lagging(self, history: _History) -> None:
        """The open rows, checked against the daily closes of the day the list's
        prices in each market belong to."""
        for own, etf in self.lagging:
            on_date = _closes_on(_list_dates(own, self.candidates, history), history)
            for row in self._open(own):
                close = float(row["close"])

                # A listing without a close on its market's day (that market has none,
                # or the listing no daily closes) is ruled out only when none of its
                # recent closes agrees.
                def unchecked(c: _Candidate, close: float = close) -> bool:
                    series = history.get(c.code)
                    recent = series is None or any(_agrees(close, p) for _day, p in series)
                    return _is_quotable(c) and recent

                matched = _by_price(row, self._of(row), on_date, etf, unchecked)
                if matched is not _Open.OPEN:
                    self._settle(row, matched, etf)

    def _eliminate(self, own: list[_Row], etf: _Etf) -> None:
        """Price ties the listings other rows have taken settle without the ETF's
        market: what is left of a tie in one market (or nothing at all) is final.
        Repeated until nothing moves, so the outcome does not hang on row order — and
        done before the market is judged, which may rest on what it settles."""
        moved = True
        while moved:
            moved = False
            for row in own:
                if id(row) not in self.tied or id(row) in self.codes:
                    continue
                left = [c for c in self.tied[id(row)] if c.code not in etf.used]
                if len({_market(c.code) for c in left}) <= 1:
                    self._place(row, _narrow(left, etf) if left else None, etf)
                    moved = True

    def place_by_name(self) -> None:
        for own, etf in self.etfs:
            self._eliminate(own, etf)
            # The markets this ETF holds, as far as anything shows: listings its prices
            # confirmed, and names whose exact listings all trade in one market. Only
            # when all of it points to one market is that market trusted for what the
            # prices could not settle — and not when a name's lookup failed: that
            # component may trade anywhere, so the markets are unknown.
            markets = {_market(code) for code in etf.used}
            for row in own:
                held = {_market(c.code) for c in self._of(row) if not c.prefix}
                if len(held) == 1:
                    markets |= held
            if len(markets) == 1 and not any(row["componentName"] in self.failed for row in own):
                etf.market = next(iter(markets))
            # The ties still open span markets; only the ETF's one market breaks them,
            # and only for a listing in it — so nothing placed from here on adds a market
            # to the evidence above. Ties first: a listing a row's price agrees with goes
            # to it before a row of the same name claims it by name alone.
            for row in own:
                if id(row) in self.tied and id(row) not in self.codes:
                    left = [
                        c
                        for c in self.tied[id(row)]
                        if c.code not in etf.used and _market(c.code) == etf.market
                    ]
                    self._place(row, _narrow(left, etf) if left else None, etf)
            for row in own:
                if id(row) not in self.codes:
                    self._place(row, _by_name(self._of(row), etf), etf)

    def result(self) -> tuple[list[Any], list[_Row]]:
        """The rows with ``componentCode`` filled in, and the rows left without one
        (cash lines, commodities, names without a confident match)."""
        unresolved: list[_Row] = []
        filled: list[Any] = []
        for row in self.rows:
            if id(row) not in self.codes:
                filled.append(row)
                continue
            code = self.codes[id(row)]
            if not code:
                unresolved.append(
                    {key: row.get(key) for key in ("fundCode", "serialNumber", "componentName")}
                )
            # Where the API used to put it, so the DataFrame columns read as before.
            out: _Row = {}
            for key, value in row.items():
                if key == "componentCode":
                    continue
                out[key] = value
                if key == "serialNumber":
                    out["componentCode"] = code
            out.setdefault("componentCode", code)
            filled.append(out)
        return filled, unresolved


def _beijing_window() -> tuple[str, str]:
    now = dt.datetime.now(_BEIJING)
    start = now - dt.timedelta(days=_CLOSES_WINDOW_DAYS)
    return start.date().isoformat(), now.date().isoformat()


def _merged(parts: list[dict[str, _T]]) -> dict[str, _T]:
    out: dict[str, _T] = {}
    for part in parts:
        out.update(part)
    return out


def _announce(label: str, pending: int, unresolved: list[_Row]) -> None:
    left = [f"{u['fundCode']} {u['componentName']}" for u in unresolved]
    shown = ", ".join(left[:_SHOWN_UNRESOLVED]) + (", …" if len(left) > _SHOWN_UNRESOLVED else "")
    warnings.warn(
        f"{label}: the API returns component names only; componentCode is the SDK's match "
        "for each name (looked up in the securities list, and checked against the "
        f"component's close where it can be quoted): {pending - len(left)} of {pending} "
        "rows."
        + (
            f" Left null (cash lines, commodities, names without a confident match): {shown}"
            if left
            else ""
        )
        + " Pass component_code=False for the API's rows as returned.",
        stacklevel=5,
    )


def _filled_result(data: Any, fill: _Fill, label: str) -> Any:
    rows, unresolved = fill.result()
    _announce(label, len(fill.pending), unresolved)
    return {**data, "list": rows}


def _pending_fill(data: Any) -> _Fill | None:
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    fill = _Fill(rows)
    return fill if fill.pending else None


def _rows(payload: Any) -> list[Any]:
    data = normalize_rows(payload)
    rows = data if isinstance(data, list) else (data or {}).get("list")
    return rows if isinstance(rows, list) else []


def _quote_prices(payload: Any) -> _Prices:
    """Previous close and latest price per code the realtime quote knows."""
    out: _Prices = {}
    for quote in _rows(payload):
        if not isinstance(quote, dict) or not isinstance(quote.get("securityCode"), str):
            continue
        prices = [
            p
            for p in (_number(quote.get("preClose")), _number(quote.get("latestPrice")))
            if p is not None
        ]
        if prices:
            out[quote["securityCode"]] = prices
    return out


def _daily_closes(payload: Any) -> _History:
    """Daily closes per code, oldest first."""
    out: _History = {}
    for bar in _rows(payload):
        if not isinstance(bar, dict):
            continue
        code, day, close = bar.get("securityCode"), bar.get("tradeDate"), _number(bar.get("close"))
        if isinstance(code, str) and isinstance(day, str) and close is not None:
            out.setdefault(code, []).append((day, close))
    for series in out.values():
        series.sort(key=lambda item: item[0])
    return out


def _closes_body(codes: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "securityList": codes,
        "startDate": start_date,
        "endDate": end_date,
        "fieldList": ["securityCode", "tradeDate", "close"],
        "limit": _CLOSES_LIMIT,
    }


def _sector_listings(data: Any) -> list[_Listing]:
    rows = data.get("list") if isinstance(data, dict) else None
    return [
        (row["gtsCode"], row["gtsName"])
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict)
        and isinstance(row.get("gtsCode"), str)
        and isinstance(row.get("gtsName"), str)
    ]


class _TableSearch:
    """Search over the three markets' listings, shaped like securities-search rows:
    the listings carrying the name (or ticker, or code) exactly, plus those whose name
    starts with it. ``None`` when none carries it exactly — a bond, a name the exchange
    truncated, a cash line — so the caller asks the search service, which knows more
    than stocks."""

    def __init__(self, listings: list[_Listing]) -> None:
        self._by_base: dict[str, list[_Listing]] = {}
        self._by_ticker: dict[str, list[_Listing]] = {}
        self._by_code: dict[str, _Listing] = {}
        for listing in listings:
            self._by_base.setdefault(_base(listing[1]), []).append(listing)
            self._by_ticker.setdefault(_ticker(listing[0]), []).append(listing)
            self._by_code[listing[0]] = listing
        self._order = {name: i for i, name in enumerate(self._by_base)}
        self._sorted = sorted(self._by_base)

    def _starting_with(self, name: str) -> list[str]:
        """The other names that start with ``name``, in table order."""
        found = []
        index = bisect.bisect_left(self._sorted, name)
        while index < len(self._sorted) and self._sorted[index].startswith(name):
            if self._sorted[index] != name:
                found.append(self._sorted[index])
            index += 1
        return sorted(found, key=self._order.__getitem__)

    def __call__(self, keyword: str) -> list[_Row] | None:
        key = _squash(keyword)
        name = _base(key)
        coded = self._by_code.get(key)
        exact = [
            *self._by_base.get(name, []),
            *self._by_ticker.get(key, []),
            *([coded] if coded else []),
        ]
        if not exact:
            return None
        prefix = (
            [listing for other in self._starting_with(name) for listing in self._by_base[other]]
            if len(name) >= 2
            else []
        )
        return [
            {"gtsCode": code, "gtsName": gts_name, "category": "stock"}
            for code, gts_name in dict.fromkeys([*exact, *prefix])
        ]


# ---------------------------------------------------------------- sync driver


class CodeLookup:
    """The lookups over a live client: names looked up in the securities table first
    (fetched once per lookup) and in securities-search when the table does not carry
    them; the realtime quote's previous close and latest price; daily closes."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._loaded = False
        self._table: _TableSearch | None = None

    def _local(self) -> _TableSearch | None:
        with self._lock:
            if not self._loaded:
                self._table = self._load_table()
                self._loaded = True
        return self._table

    def _load_table(self) -> _TableSearch | None:
        """``None`` when a market fails or comes back empty — a table without one
        market would place the H row of an A+H name in the A market — and the lookup
        then falls back to searching."""
        listings: list[_Listing] = []
        try:
            for sector_id in _MARKET_SECTORS:
                found = _sector_listings(
                    self._client._call(
                        "reference.sector-constituents", body={"sectorId": sector_id}
                    )
                )
                if not found:
                    return None
                listings += found
        except Exception:
            return None
        return _TableSearch(listings)

    def search(self, keyword: str) -> Any:
        table = self._local()
        hits = table(keyword) if table else None
        if hits is not None:
            return hits
        data = self._client._call(
            "reference.securities-search", body={"keyword": keyword, "top": _SEARCH_TOP}
        )
        return data.get("list") if isinstance(data, dict) else []

    def quotes(self, codes: list[str]) -> _Prices:
        return _quote_prices(self._client._call("quote.realtime", body={"securityList": codes}))

    def closes(self, codes: list[str], start_date: str, end_date: str) -> _History:
        return _daily_closes(
            self._client._call("quote.day-kline", body=_closes_body(codes, start_date, end_date))
        )


def _run(items: Sequence[_T], fn: Callable[[_T], _R], concurrency: int) -> list[_R]:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(items)))) as pool:
        return list(pool.map(fn, items))


def _splitting(codes: list[str], fetch: Callable[[list[str]], dict[str, _T]]) -> dict[str, _T]:
    """A batch failing on 120001 (one unknown code) is halved — one half after the
    other — until the codes that fail are on their own; they are left unquoted. Any
    other failure (throttling, auth, an outage) leaves the batch unquoted as it is:
    splitting would only multiply the requests."""
    try:
        return fetch(codes)
    except Exception as error:
        if len(codes) == 1 or not _rejects_a_code(error):
            return {}
        half = (len(codes) + 1) // 2
        first = _splitting(codes[:half], fetch)
        return {**first, **_splitting(codes[half:], fetch)}


def _candidates_for(name: str, lookup: CodeLookup) -> list[_Candidate] | None:
    """``None`` when a lookup failed (not the same as finding nothing)."""
    try:
        key = _squash(name)
        found = _to_candidates(lookup.search(key))
        exact = _exact(found, key)
        if _wants_us_suffix(key, exact):
            for suffix in ("O", "N"):
                exact += _by_ticker(lookup.search(f"{key}.{suffix}"), key)
        return _with_prefixes(found, exact, key)
    except Exception:
        return None


def fill_component_codes(fill: _Fill, lookup: CodeLookup, *, concurrency: int) -> _Fill:
    fill.take_candidates(_run(fill.names, lambda name: _candidates_for(name, lookup), concurrency))
    fill.place_by_price(
        _merged(
            _run(
                _in_batches(fill.quotable(), _QUOTE_BATCH),
                lambda batch: _splitting(batch, lookup.quotes),
                concurrency,
            )
        )
    )
    wanted = fill.lagging_codes()
    if wanted:
        start, end = _beijing_window()
        fill.place_lagging(
            _merged(
                _run(
                    _in_batches(wanted, _CLOSES_BATCH),
                    lambda batch: _splitting(batch, lambda c: lookup.closes(c, start, end)),
                    concurrency,
                )
            )
        )
    fill.place_by_name()
    return fill


def add_component_codes(data: Any, client: GangtiseClient, *, label: str) -> Any:
    """The component list with ``componentCode`` filled in — ``None`` where nothing
    matched with confidence — and a ``UserWarning`` that the codes are the SDK's own
    matching, naming the rows left ``None``. The answer keeps its shape."""
    fill = _pending_fill(data)
    if fill is None:
        return data
    concurrency = client.config.page_concurrency
    return _filled_result(
        data, fill_component_codes(fill, CodeLookup(client), concurrency=concurrency), label
    )


# ---------------------------------------------------------------- async driver


class AsyncCodeLookup:
    """Async mirror of :class:`CodeLookup`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client
        self._lock = anyio.Lock()
        self._loaded = False
        self._table: _TableSearch | None = None

    async def _local(self) -> _TableSearch | None:
        async with self._lock:
            if not self._loaded:
                self._table = await self._load_table()
                self._loaded = True
        return self._table

    async def _load_table(self) -> _TableSearch | None:
        listings: list[_Listing] = []
        try:
            for sector_id in _MARKET_SECTORS:
                found = _sector_listings(
                    await self._client._call(
                        "reference.sector-constituents", body={"sectorId": sector_id}
                    )
                )
                if not found:
                    return None
                listings += found
        except Exception:
            return None
        return _TableSearch(listings)

    async def search(self, keyword: str) -> Any:
        table = await self._local()
        hits = table(keyword) if table else None
        if hits is not None:
            return hits
        data = await self._client._call(
            "reference.securities-search", body={"keyword": keyword, "top": _SEARCH_TOP}
        )
        return data.get("list") if isinstance(data, dict) else []

    async def quotes(self, codes: list[str]) -> _Prices:
        return _quote_prices(
            await self._client._call("quote.realtime", body={"securityList": codes})
        )

    async def closes(self, codes: list[str], start_date: str, end_date: str) -> _History:
        return _daily_closes(
            await self._client._call(
                "quote.day-kline", body=_closes_body(codes, start_date, end_date)
            )
        )


async def _run_async(
    items: Sequence[_T], fn: Callable[[_T], Awaitable[_R]], concurrency: int
) -> list[_R]:
    results: list[Any] = [None] * len(items)
    semaphore = anyio.Semaphore(max(1, concurrency))

    async def run_one(index: int, item: _T) -> None:
        async with semaphore:
            results[index] = await fn(item)

    async with anyio.create_task_group() as tg:
        for index, item in enumerate(items):
            tg.start_soon(run_one, index, item)
    return results


async def _splitting_async(
    codes: list[str], fetch: Callable[[list[str]], Awaitable[dict[str, _T]]]
) -> dict[str, _T]:
    """Async mirror of :func:`_splitting`."""
    try:
        return await fetch(codes)
    except Exception as error:
        if len(codes) == 1 or not _rejects_a_code(error):
            return {}
        half = (len(codes) + 1) // 2
        first = await _splitting_async(codes[:half], fetch)
        return {**first, **await _splitting_async(codes[half:], fetch)}


async def _candidates_for_async(name: str, lookup: AsyncCodeLookup) -> list[_Candidate] | None:
    """Async mirror of :func:`_candidates_for`."""
    try:
        key = _squash(name)
        found = _to_candidates(await lookup.search(key))
        exact = _exact(found, key)
        if _wants_us_suffix(key, exact):
            for suffix in ("O", "N"):
                exact += _by_ticker(await lookup.search(f"{key}.{suffix}"), key)
        return _with_prefixes(found, exact, key)
    except Exception:
        return None


async def fill_component_codes_async(
    fill: _Fill, lookup: AsyncCodeLookup, *, concurrency: int
) -> _Fill:
    """Async mirror of :func:`fill_component_codes`."""

    async def candidates(name: str) -> list[_Candidate] | None:
        return await _candidates_for_async(name, lookup)

    async def quoted(batch: list[str]) -> _Prices:
        return await _splitting_async(batch, lookup.quotes)

    fill.take_candidates(await _run_async(fill.names, candidates, concurrency))
    batches = _in_batches(fill.quotable(), _QUOTE_BATCH)
    fill.place_by_price(_merged(await _run_async(batches, quoted, concurrency)))
    wanted = fill.lagging_codes()
    if wanted:
        start, end = _beijing_window()

        async def closes(codes: list[str]) -> _History:
            return await lookup.closes(codes, start, end)

        async def dated(batch: list[str]) -> _History:
            return await _splitting_async(batch, closes)

        history = await _run_async(_in_batches(wanted, _CLOSES_BATCH), dated, concurrency)
        fill.place_lagging(_merged(history))
    fill.place_by_name()
    return fill


async def add_component_codes_async(data: Any, client: AsyncGangtiseClient, *, label: str) -> Any:
    """Async mirror of :func:`add_component_codes`."""
    fill = _pending_fill(data)
    if fill is None:
        return data
    concurrency = client.config.page_concurrency
    filled = await fill_component_codes_async(
        fill, AsyncCodeLookup(client), concurrency=concurrency
    )
    return _filled_result(data, filled, label)
