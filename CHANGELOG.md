# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and follows [Semantic Versioning](https://semver.org/).

## [0.1.17] - 2026-07-12

Second adversarial-review pass on the download path. No endpoint or API-surface
changes (still `gangtise-openapi-cli` v0.27.0 parity, 90 endpoints).

### Fixed
- **A 302 to a CDN can no longer replay a billed download endpoint.** The upstream
  download request previously let httpx auto-follow the redirect inline; a failure
  on the CDN hop then looked like a connect-phase error on the *upstream* request
  and — for a `no-replay` (per-篇 billed) endpoint — triggered a resend of the
  billing endpoint. The upstream request now stops at the 3xx, and the `Location`
  is handed to the signed-URL fetcher whose retry loop only ever replays the
  unbilled CDN URL. (Deliberate divergence from TS `client.ts`, which follows
  inline and shares this hazard.) The followed URL also now gets the 10× transfer
  deadline it previously bypassed.
- **Signed-URL redaction is now fail-closed.** `_redact_url` kept only
  `scheme://host/path`, but a bare `alice:SECRET@host/p` parses with scheme
  `alice`, so the old netloc-based path leaked `alice://SECRET@…`; an invalid port
  also escaped as an unwrapped `httpx.InvalidURL` carrying the raw value. Anything
  that is not an absolute http(s) URL with a host and valid port now collapses to
  `redacted-url`, and signed URLs are validated before the fetch so a malformed one
  raises a redacted `DownloadError` instead of leaking.
- **Auto-named downloads publish atomically again and suffix correctly.** The
  v0.1.16 `O_CREAT|O_EXCL` reservation created the final path as a 0-byte
  placeholder before the rename (a crash could leave a phantom empty "success"),
  and a collision on `report-1.pdf` produced `report-1-1.pdf` instead of
  `report-2.pdf`. Commit now hard-links the completed `.part` onto the target (the
  full file appears in one step; `-1..-99` suffixes are scanned from the original
  name), falling back to the O_EXCL placeholder only on filesystems without
  hard-link support (still non-clobbering).
- **EDE inner-envelope `999999` now gets the "no data" hint.** The double-envelope
  inner error is unwrapped past the transport, so it kept the generic "retry later"
  hint; it now uses the same "check the query window" hint as the outer code.

### Changed
- `pytest` escalates our `UserWarning`s to errors via `filterwarnings` in
  `pyproject.toml`, so a future partial-result / shape-drift warning fails the suite
  locally and in CI/release (previously only asserted ad hoc).

## [0.1.16] - 2026-07-11

Security and download-integrity fixes from an adversarial review of 0.1.15. No
endpoint or API-surface changes (still `gangtise-openapi-cli` v0.27.0 parity, 90
endpoints).

### Fixed
- **Signed URLs no longer leak into exception messages.** Presigned-URL fetch
  failures used to embed the full URL — including the `X-Amz-Signature` query and
  any `user:password@` authority — in `DownloadError` text, where terminals, CI
  logs and error collectors would record it. Messages now carry only
  `scheme://host[:port]/path` (userinfo, query and fragment stripped; IPv6 hosts
  re-bracketed).
- **Auto-named downloads can no longer overwrite each other.** Two concurrent
  `output=None` downloads whose titles resolve to the same filename raced
  `_unique_path`'s check-then-use window: the later `replace()` silently clobbered
  the earlier file. Auto-derived names now commit via an atomic
  `O_CREAT|O_EXCL` reservation — the loser re-scans for the next `-1..-99` suffix —
  and a failed final move cleans up its placeholder. Works on every filesystem
  (no hard-link dependency); explicit `output=` paths keep documented overwrite
  semantics.
- **Presigned-URL fetches now retry transient network failures** (default policy,
  per-attempt 10× hard deadline). Replaying the signed URL is always safe — the
  billed upstream endpoint is never re-requested; HTTP >= 400 on a signed URL
  still fails fast (signed URLs expire, replaying a 403 is useless).
- **`report_image_download` auto-names now get their extension**: `image/png` /
  `image/jpeg` / `image/gif` / `image/webp` / `image/svg+xml` joined the MIME→ext
  map (TS parity), so an auto-named image lands as `report-image-<id>.jpg`
  instead of extension-less.
- **999999 on a no-replay endpoint no longer hints "retry later".** The SDK
  deliberately did not retry (the request may have executed and billed); the hint
  now says to verify the result/billing before manually retrying.

### Changed
- Paginated-endpoint test fixtures normalized to the real `{total, list}` shape;
  the suite now passes with `-W error::UserWarning`, so a future genuine
  shape-drift warning cannot hide in fixture noise.

## [0.1.15] - 2026-07-11

Sync with `gangtise-openapi-cli` v0.24.0–v0.27.0: billing-safe retry policies, 4 new
endpoints (86 → 90), local validation for silently-truncating params, and reliability
hardening across polling, sharding, pagination, and downloads.

### Changed
- **Billing safety (important).** 16 per-call-billed endpoints — the 7 synchronous AI
  generators, `earnings_review`/`viewpoint_debate` get-id, `hot_topic`,
  `knowledge_batch`, `concept_info`/`concept_securities`, and the
  `summary`/`foreign_report`/`my_conference` downloads — now use a **no-replay retry
  policy**: 5xx / response timeouts / API code 999999 are no longer automatically
  resent (the platform bills per call with no cache-hit exemption, so a replay
  double-bills). Only connect-phase errors (the request provably never reached the
  server), 429 rate limits and the token self-heal still retry. Cheap per-row list
  endpoints keep the full default retry.
- **EDE indicator endpoints no longer retry 999999.** The server answers a no-data
  query (holiday / future date / uncovered security) with HTTP 500 + code 999999;
  each empty query used to burn 3 requests + ~4s. The error hint now points at
  checking the query window instead of "retry later".
- **7 synchronous AI generation endpoints get a 120s timeout floor**
  (`one_pager`, `investment_logic`, `peer_comparison`, `theme_tracking`,
  `research_outline`, `management_discuss_*` ×2) — long generations no longer hit
  the 30s default timeout; an explicitly higher client timeout still wins (max).
- **429 responses honor `Retry-After`** (delta-seconds or HTTP-date, capped at 60s),
  taking precedence over exponential backoff on both the JSON and download paths.
- **Local caps for params the server silently truncates** (probed on the CLI side):
  `top`/`limit` — the six `reference` searches ≤ 10, `report_image_list` /
  `knowledge_batch` ≤ 20, `edb_search` ≤ 200, `indicator.search` ≤ 100 — and
  category whitelists for `securities_search` / `institution_search` /
  `official_account_search` (a typo used to masquerade as "no results"). Violations
  raise `ValidationError` before any request is issued.
- **Full-market kline sharding aborts after a hard error**: remaining shards are not
  dispatched (saving quota) and are recorded in `failedShards`; a 2xx shard without
  a `list` array now also lands in `failedShards` with its window. Shards that hit
  the per-shard row cap are listed in **`truncatedShards`** with concrete date
  windows (mirroring `failedShards`) so consumers can re-pull narrower ranges.
- **AI async polling tolerates transient errors**: one 5xx / network blip (after the
  transport's own retries) consumes a single poll attempt instead of voiding the
  whole multi-minute wait; terminal errors (no credits, bad params) still abort.
- `GANGTISE_PAGE_CONCURRENCY` is parsed defensively: invalid / non-positive values
  fall back to the default 5, and values are capped at 32 (a negative value used to
  silently degrade to a single serial worker).

### Added
- **4 new endpoints** (registry 88 → 92 incl. the 2 local lookup tables):
  - `insight.qa_list` — investor Q&A per security (interactive platform / earnings
    call / survey sources, 11 question categories, auto-pagination at 500/page;
    0.1 credit/row).
  - `insight.report_image_list` / `insight.report_image_download` — search research
    report images by keyword (returns `chunkId` + metadata; free) and download the
    original JPEG by `chunkId` (0.1 credit/image).
  - `reference.official_account_search` — WeChat official-account ID search
    (feeds `accountId` into `insight.official_account_list`; free).
- `ERROR_HINTS` entry for code `100003` (invalid enum parameter value).
- Sample scripts (sync + async) and `sample/API_PARAMETERS.md` entries for all four
  new methods.

### Fixed
- EDE matrix columns named `date` / `security` / `name` no longer overwrite the
  metadata columns — they get a code suffix like any other duplicate.
- Auto-derived download filenames raise `DownloadError` once 100 same-named files
  exist instead of silently overwriting the first one.
- A paginated endpoint whose first page arrives in an unexpected shape (e.g. `total`
  as a string) now emits a `UserWarning` instead of silently degrading to one page.
- Presigned-URL downloads get an overall hard deadline (10× the request timeout):
  idle-type read timeouts reset on every byte, so a slow-drip CDN could previously
  hang a download indefinitely.

## [0.1.14] - 2026-07-07

Type-experience, performance, and validation improvements from a review pass — no
endpoint or API-surface changes (still `gangtise-openapi-cli` v0.23.0 parity, 86
endpoints).

### Changed
- **Domain filter parameters are now typed** `str | int | Sequence[str | int]` (the
  new `FilterValue` alias) instead of `Any`. A security code, industry ID, rating,
  … — single value or list — now gets IDE completion and mypy checking, while both
  ints (`industry=1`, `fiscal_year=2025`) and strings stay valid, matching what the
  API accepts.
- **Matrix endpoints build DataFrames 2-5x faster.** Columnar `{fieldList, list}`
  responses (financial statements, EDE indicators, …) are built directly from the
  column matrix instead of transposing to per-row dicts and back; output is
  byte-for-byte identical (values and dtypes).
- **Pagination `from` / `size` reject `bool`** (an `int` subclass) with
  `ValidationError`, matching the quote `limit` guard, instead of passing as `0`/`1`.
- Package classifier bumped to `Development Status :: 4 - Beta`.

### Added
- `User-Agent: gangtise-openapi-python/<version>` on every request (sync + async),
  so server-side logs can distinguish the Python SDK from the npm CLI.

### Internal
- Coverage tooling (`pytest-cov`), CI matrix widened to Python 3.11 / 3.12, and a
  columnar-DataFrame regression suite (`tests/unit/test_common.py`).

## [0.1.13] - 2026-07-06

Synced with `gangtise-openapi-cli` v0.23.0.

### Changed
- **Default API host migrated** `https://open.gangtise.com` →
  `https://openapi.gangtise.com` (equivalent across endpoints in practice; the old
  host still works — set `GANGTISE_BASE_URL=https://open.gangtise.com` to pin it).
- **`vault.wechat_chatroom_list`** now consumes the server's new `{total, list}`
  response, fanning out pages by `total` like every other paginated endpoint. The
  bespoke sequential (no-`total`, `chatRoomList`) pagination path was removed.
- **Pagination truncation is now visible.** Every paginated endpoint flags the result
  `partial` (visible with `raw=True`) and emits a `UserWarning` when the server's
  reported `total` drifts above the rows actually returned, or when the `MAX_PAGES`
  (1000) safety cap truncates the fan-out. Both cases were previously silent.
- **`limit` on the quote endpoints is validated locally.** A value outside `1..10000`,
  or a non-integer (`1.5`, `True`, `"10"`, …), now raises `ValidationError` before any
  request instead of reaching the server or leaking a raw `TypeError` from the range
  comparison.

### Added
- **`quote.fund_flow`** — A-share daily fund flow (SH/SZ/BJ; small/medium/large/xlarge
  order inflow/outflow amounts and ratios + main net inflow; free). Pass a specific
  `security` (one or a list) or `aShares` for the whole market — full-market requests
  are date-sharded by day and merged concurrently and require both `start_date` and
  `end_date` (a missing range raises `ValidationError`). Single-security requests are
  not paginated; a row count reaching the sent `limit` (default 6000, max 10000) flags
  the result `partial` and warns. Sync + async.
- **`reference.institution_search`** — institution ID search across five categories
  (`domesticBroker`/`foreignInstitution`/`leadInstitution`/`opinionInstitution`/
  `foreignOpinionInstitution`); results carry `usageScopes` and cover the
  broker/institution inputs of the existing endpoints. Free. Sync + async.
- **`vault.my_conference_list`** gained a `source` parameter (recording source; numeric
  `1`=企微会议助理 `2`=会议服务微信群) → `sourceList` in the body.

### Fixed
- **Silent-truncation guard for non-paginated quote endpoints** (`fund_flow`
  single-security, `minute_kline`, and explicit multi-security
  `day_kline`/`-hk`/`-us`/`index_day_kline`): these report `total` as the returned row
  count, so a count equal to the sent `limit` now flags the result `partial` (visible
  with `raw=True`) and emits a `UserWarning` instead of silently dropping rows. `limit`
  now defaults to 6000, sent explicitly so the request limit and the truncation cap
  always match.
- **Full-market shard merge**: the merged result's `total` now reflects the combined
  row count (previously carried a single shard's smaller `total`), and a shard that hits
  its per-request cap flags the whole result `partial`. The merge also keeps the first
  non-empty `fieldList`, so a trailing empty shard can no longer blank the columns.
- **Download follows presigned-URL redirects.** A download endpoint that answers with a
  `302` to a presigned object-store URL is now followed to fetch the actual file
  (the `200` + JSON `{url}` variant was already handled); httpx drops the `Authorization`
  bearer on the cross-origin hop so it never reaches the storage host. Ports the last
  outstanding CLI v0.22.0 download behavior.

## [0.1.12] - 2026-07-02

### Changed
- **`insight.announcement_list` date-only strings now use local midnight** (same
  anchor as `"YYYY-MM-DD 00:00:00"`) instead of UTC midnight, matching TS HEAD
  and avoiding boundary-day drift for users outside UTC.

### Fixed
- **Module-level async facade** no longer reuses an `httpx.AsyncClient` across
  separate `asyncio.run()` event loops, and `reset()`/`configure(replace=True)`
  now close the cached async client when possible.
- **Auto-named downloads** now suffix colliding names (`report.pdf`,
  `report-1.pdf`) instead of silently overwriting the first file, and truncate
  overlong UTF-8 filenames while preserving the extension.
- **`Content-Disposition` filename parsing** now decodes RFC 5987
  `filename*=UTF-8''...` values case-insensitively, so percent-encoded Chinese
  filenames land decoded.
- **Download auth retry** now reuses a token already refreshed by another
  request instead of forcing another login, matching the JSON request path.
- **Pagination** now enforces `MAX_PAGES` while generating fan-out requests,
  marks async malformed/`None` fan-out pages as `partial`, marks sequential
  shape loss as `partial`, and stops after an empty/short first page instead of
  repeating the same offset.
- **`fundamental.earning_forecast` default window** now anchors `start_date` to
  the provided `end_date` when only `end_date` is supplied.
- **`normalize_token`** canonicalizes `bearer ...` / `BEARER ...` to
  `Bearer ...` instead of producing `Bearer bearer ...`.
- **Async download cleanup** removes `.part-*` files synchronously in `finally`,
  so cancellation cannot skip the unlink.

### Security
- Release CI now syncs with `uv --locked`, checks that README/CHANGELOG mention
  the tag before publishing, and pins the PyPI publish action to a commit SHA
  instead of the mutable `release/v1` branch.

## [0.1.11] - 2026-06-29

### Changed
- **`vault.wechat_chatroom_list`** now fetches **all** chatrooms when `size` is
  omitted (previously capped at 20). This endpoint returns no `total`, so the
  client pages sequentially until a short page (server caps each page at 50)
  signals the end; pass `size=N` to cap the result at the first N rows. Scripts
  that relied on the implicit 20-row default will now receive every group. Ports
  CLI v0.21.0 (`5e306b3`).

### Fixed
- **Download filenames** now strip control characters and NUL (`\x00`–`\x1f`)
  in addition to the existing path-unsafe set, so a server-supplied name can't
  break the file write or smuggle terminal escape sequences. TS parity
  (CLI v0.21.0).
- **Title cache** drops a half-corrupt entry (an endpoint whose `titles` field is
  not a dict) on load instead of carrying it forward, which could otherwise crash
  the next list call that records titles.
- **Malformed 2xx responses no longer silently drop rows**: when a fan-out
  pagination page or a sharded K-line response returns `200` with an unexpected
  shape (neither a paginated list nor the K-line matrix), the result is now flagged
  `partial` and a warning is emitted, instead of quietly omitting those rows. This
  makes the success-but-malformed path symmetric with the hard-failure path and the
  sequential collector.

### Security
- **Token cache and title cache** files are now created `0600` atomically (`os.open`
  with mode `0600`, then atomic rename) instead of write-then-`chmod`, eliminating the
  brief window where the file briefly existed with umask-default (often world-readable)
  permissions. Ports the CLI v0.21.0 token-cache hardening; the title cache can hold
  non-public report titles.

## [0.1.10] - 2026-06-27

### Added
- **Indicator (EDE) domain** — `gangtise.indicator.*` (sync + async): `search`
  finds data-indicator codes by keyword; `cross_section` returns a
  multi-indicator × multi-security matrix for a single date; `time_series`
  returns a multi-indicator × single-security (or single-indicator ×
  multi-security) matrix over a date range. The live `values` matrix is
  flattened into wide rows (one row per security / per date, indicator names as
  columns), and the inner double-envelope is unwrapped — surfacing an `ApiError`
  on an inner failure code instead of a null payload. `indicator_param={"qte_close":
  {"adjustmentType": "2"}}` sets per-indicator options (e.g. 前复权). Ports CLI
  v0.19.0 (`5af5540`).
- **US-market endpoints** (CLI v0.20.0, `9881ea2`): `insight.announcement_us_list`
  / `announcement_us_download` (mirror the HK announcement wrappers, with
  `file_type` 1=original PDF, 2=Markdown); `fundamental.income_statement_us` /
  `balance_sheet_us` / `cash_flow_us`.
- **`ai.stock_summary_list`** (个股看点) — refined research summary per security;
  requires `security` (codes or market keyword `aShares` / `hkStocks`) and raises
  `ValidationError` on an empty value to avoid an all-market credit blow-up.
- **`reference.chiefs_search`** — search chief-analyst IDs by name / institution /
  team.

### Changed
- **`ai.hot_topic`** now sends `with_related_securities` / `with_close_reading` as
  explicit booleans, so passing `False` sends `false` (previously the field was
  omitted and the server applied its default). TS parity (`!== false`).
- **`insight.announcement_hk_download`** gains `file_type` (1=original default,
  2=Markdown), matching the CLI.
- **Missing-credential error** now names which of `GANGTISE_ACCESS_KEY` /
  `GANGTISE_SECRET_KEY` is absent and explains shell `export`
  (and `gangtise.configure(...)`), replacing the single generic message.

### Fixed
- **Pagination is now fail-soft**: when a fan-out page hits a non-retryable error
  (rate limit, no-permission), the already-fetched pages are kept and a
  `UserWarning` is emitted, instead of discarding everything by raising. The raw
  payload is tagged `partial=True` with `failedPages` (`raw=True`); the default
  DataFrame drops those keys, so the warning is the signal on that path —
  mirroring the existing K-line shard tolerance. Sync + async; CLI v0.20.0.
- **`ai.knowledge_batch`** raises `ValidationError` on an empty `query` instead of
  sending an empty `queries` list to the server.

## [0.1.9] - 2026-06-17

### Added
- **Insight official-account (WeChat) endpoints**: `official_account_list`
  paginates 产业公众号 articles by keyword / account / security / category (enum) /
  industry, with `search_type` (1=title, 2=fulltext) and `rank_type` (1=composite,
  2=time-desc); `official_account_download` fetches an article as txt (default,
  `file_type=1`) or HTML (`file_type=2`) by `article_id`. Both wrappers ship sync
  + async, with title-cache filename resolution on download. Ports CLI v0.18.0
  (`4ce9556`).

## [0.1.8] - 2026-06-16

### Fixed
- **Auto-recover from server-side token invalidation** (`0000001008`): when the
  server revokes a token that still looks valid by local expiry — e.g. the
  account logged in elsewhere, displacing this session — the SDK now forces a
  re-login and replays the request once, across both the `_call` and download
  paths (sync + async), instead of failing every request until a manual
  re-login. Adds the matching Chinese error hint. Ports CLI v0.17.2 (`1915227`).

## [0.1.7] - 2026-06-16

### Fixed
- **Concurrent download temp-file collision**: `download_to_path` /
  `download_to_path_async` streamed to a deterministic `<target>.part` temp
  file. Two concurrent downloads resolving to the same target filename (the same
  id downloaded twice, two documents with identical titles, or the same explicit
  `output=`) wrote into one handle — interleaving bytes — while each task's
  cleanup unlinked the other's file, surfacing as
  `DownloadError: ... No such file or directory`. Temp files now carry a per-call
  unique suffix (`.part-<uuid>`), giving each download the isolation the token /
  title caches already had.

### Changed
- **Async download no longer blocks the event loop** on filesystem metadata
  operations: `mkdir` / `replace` / `unlink` in the async write path now run via
  `anyio.to_thread.run_sync` (the streamed body write already used
  `anyio.open_file`).
- **Row extraction consolidated**: `reference.securities_search` and
  `alternative.edb_search` (sync + async) now use the shared `_extract_rows`
  helper instead of bespoke `isinstance` ladders — identical output on the shapes
  these endpoints return, plus columnar-matrix fallback for free.
- Test suite expanded 413 → 431: deterministic concurrent-download regression
  tests, fundamental matrix-shape transpose coverage (`valuation_analysis` /
  `top_holders` / `main_business`), async body-mapping tests for the fundamental
  statement wrappers, async quote shard/body tests, and the async
  `earnings_review` `410110` poll-retry path.

## [0.1.6] - 2026-06-15

Sync with upstream CLI v0.16.0 (`f2d2a00`, `041fc60`) and v0.17.0 (`010ac02`);
plus three bugs found in a systematic SDK audit.

### Added
- **`reference` constant/concept/sector APIs** (5 new endpoints, sync + async):
  - `reference.constant_category()` — list constant categories and which API
    params accept them (`GET /application/open-reference/constants/category`).
  - `reference.constant_list(category=...)` — all constant values of a
    category (citicIndustry / swIndustry / gangtiseIndustry / domesticCity /
    aShareAnnouncementCategory / hkShareAnnouncementCategory / regionCategory).
    The API's `constants` array is normalized to `list` (TS `normalizeRows`
    parity); tree categories keep `children` nested — use `raw=True` to recurse.
  - `reference.concept_search(keyword=..., top=10)` — theme/concept ID search
    (IDs shared with `alternative.concept_*` and `ai.theme_tracking`).
  - `reference.sector_search(keyword=None, top=10)` — sector ID search with
    `hierarchy` disambiguation.
  - `reference.sector_constituents(sector_id=...)` — full constituent list of
    a sector (`gtsCode`/`gtsName`).
- **`location` filter** on the four schedule lists (`insight.roadshow_list` /
  `site_visit_list` / `strategy_list` / `forum_list`): city/province ID from
  `reference.constant_list(category="domesticCity")`, sent as `locationList`.

### Fixed
- **Schedule filter tightening** (TS v0.17.0 parity): each of the four schedule
  endpoints now exposes only the filters its API spec actually supports.
  Previously, all four shared an identical broad signature; unsupported kwargs
  (e.g. `strategy_list(market=...)`) were silently sent to the server, which
  returned empty rows instead of an error. Now unsupported kwargs raise
  `TypeError` at the call site, matching the TS `v0.17.0` per-command field
  matrix. Specific changes by endpoint:
  - `roadshow_list` — `object_` removed (roadshow doesn't accept it).
  - `site_visit_list` — keeps `object_`; `market` limited to
    `aShares/hkStocks/usChinaConcept` (no `usStocks`).
  - `strategy_list` — narrowed to `institution` + `location` only.
  - `forum_list` — narrowed to `research_area` + `location` only.
- **`insight.announcement_list` / `announcement_hk_list`** (TS v0.17.0 parity):
  `announcement_type` param removed — the server always ignored it.
- **`ai.knowledge_batch` empty `resource_type`**: passing `resource_type=[]`
  previously sent `"resourceTypes": []` on the wire; the TS CLI omits the field
  when the list is empty (`.length` guard). Fixed with `_as_list(...) or None`.
- **`_quote_sharding.is_all_market` with mixed lists**: `security=["all",
  "000001.SZ"]` incorrectly triggered full-market sharding. TS only shards when
  `securityList` is exactly `["all"]`; fixed to `list(security) == ["all"]`.
- **Error hint text** for `410110`/`410111` aligned to TS `errors.ts` (mentions
  `*-check` command and "终态" for the terminal failure code).

### Removed
- **Six API-covered local lookup tables** (TS v0.16.0 parity):
  `lookup.research_areas` / `industries` / `regions` /
  `announcement_categories` / `industry_codes` / `theme_ids` and their bundled
  data files. Those IDs are now served live by `reference.constant_list`,
  `reference.concept_search`, and `reference.sector_constituents`. Only
  `lookup.broker_orgs` and `lookup.meeting_orgs` remain local. Endpoint
  registry goes from 75 to 74 entries.

## [0.1.5] - 2026-06-12

### Fixed
- **Token handling under concurrency**: N concurrent callers hitting a stale
  token now trigger exactly one login (TS `refreshPromise` parity); a rejected
  `GANGTISE_TOKEN` env token is skipped after its first failure instead of
  permanently tripling every call; the token-cache temp file is now unique per
  writer (multi-process safe); `__enter__`/`__aenter__` reuse a lazily created
  HTTP client instead of leaking the old pool.
- **Async error contract**: paginated/sharded fan-out failures now raise the
  original `ApiError` instead of anyio's `ExceptionGroup`, so `except ApiError`
  behaves identically in sync and async code.
- **Kline sharding** (TS `c4306fe` parity): a failed shard no longer discards
  all fetched data — surviving shards merge with `partial: true` +
  `failedShards` flags and a `UserWarning`; only an all-shards failure raises.
- **Download path** (TS parity): auth self-heal (8000014/8000015 → refresh →
  retry once), transient-error retry with backoff, presigned-`{url}` responses
  are now fetched instead of raising, 4xx JSON envelopes preserve the business
  code and Chinese hint, `.part` temp files are cleaned up on stream failure,
  and the async variant no longer blocks the event loop while writing to disk.
- **Facade**: `gangtise.configure(...)` now propagates to `gangtise.async_`
  (previously the async facade silently re-read env vars only).
- **TS parity details**: `fundamental.earning_forecast` injects the CLI's
  default one-year date window when dates are omitted; `insight` timestamp
  conversion matches `toTimestamp13` (seconds-level ints ×1000, naive datetimes
  in local tz); `ERROR_HINTS` caught up with TS v0.15.1 (410004, 430004,
  430007, 433007, 10011401).
- Cache persistence failures (token cache / title cache) no longer break an
  otherwise-successful request or download.
- Docs referenced a non-existent `lookup.theme_ids_list()` — corrected to
  `lookup.theme_ids()`.

### Changed
- **Performance**: columnar kline payloads build the DataFrame directly from
  the matrix (2–3× faster, ~half the peak memory at large row counts);
  all-market day-kline sharding skips pure-weekend windows (~29% fewer
  requests on a 1-year backfill).
- IDE experience: facade domain attributes are now statically typed (mypy /
  IDE autocomplete works on `gangtise.quote.*`), `dir()` lists domains, and
  every public wrapper method has a Chinese docstring with endpoint key and
  enum values.
- CI now tests the support boundary (Python 3.10 + 3.13).

### Tests
- +179 tests (222 → 401): async wire-body regression coverage for every
  vault/insight/ai wrapper (domain coverage 64% → 94%), async transport error
  paths, poll exhaustion, token-refresh concurrency, download error paths and
  filename-resolution tiers, facade registry integrity, and 4 new live smokes
  (7 total) covering quote/fundamental/insight/alternative read paths.

## [0.1.4] - 2026-05-30

### Added
- **`alternative.concept_info`** — latest profile of a concept (theme index):
  definition, investment logic, industry space, competitive landscape, and a
  `keyEvents` list. Queried by `concept_id`; returns the single latest
  cross-section object as a dict (no history).
  (`POST /application/open-alternative/concept/info`)
- **`alternative.concept_securities`** — constituent securities of a concept
  (theme index, F8), grouped. Each security carries `isKey` (key-stock flag)
  and `inclusionReason`. The default DataFrame flattens the groups
  one-row-per-security with a `groupName` column; `raw=True` returns the nested
  grouped payload. A concept with no constituents returns an empty DataFrame
  with the same columns. (`POST /application/open-alternative/concept/securities`)
- `concept_id` shares the theme-id namespace used by `ai.theme_tracking` —
  discover IDs by name via `gangtise.lookup.theme_ids()` (e.g. 机器人 →
  `121000130`). Both sync and async wrappers were added.

### Changed
- `quote.index_day_kline` now surfaces the upstream-added `securityName` column
  (e.g. "上证指数"). No wrapper change was required — the dynamic-schema path
  shipped in 0.1.3 passes through every field the API returns.

### Performance
- **Title cache no longer grows without bound.** The cache (used to resolve
  download filenames) merged every list call's titles forever and re-stamped
  the entry's `ts` on each merge, so the 24h TTL never pruned hot endpoints — on
  disk it had reached ~58 MB / 600k+ titles, re-parsed on every client init
  (~900 ms) and fully rewritten on every non-`raw` list call (~360 ms). Titles
  are now capped per endpoint (`TITLE_CACHE_MAX_PER_ENDPOINT`, 10k most-recent),
  oversized entries are trimmed on load, and a list call that surfaces no new
  titles no longer marks the cache dirty (no rewrite). On a real 58 MB cache the
  next write shrinks to ~1.7 MB, with client-init parse time cut proportionally.

## [0.1.3] - 2026-05-29

### Fixed
- **`quote.realtime` and `quote.minute_kline` returned all-None DataFrames.**
  Both endpoints return a columnar matrix `{fieldList, list:[[...]]}` but the
  rows were tabulated against a hardcoded schema whose names did not match the
  API, so every cell came out null. They now transpose each row against the
  response `fieldList` (shared `_quote_rows_and_fields` helper).
- **`quote.day_kline` column names corrected.** The hardcoded schema invented
  `turnover` / `changePct` and dropped real fields; A-share day K-line has no
  `turnover` column — the real fields are `pctChange` and `adjustFactor`.
- **`reference.securities_search` returned mostly-None columns.** The schema
  used `code/name/market/...` but the API returns
  `gtsCode/gtsName/category/matchScore/matchType`.
- All three hardcoded quote schemas and the field-alias remap removed; quote and
  securities-search now return the API's field names verbatim (`schema=None`),
  matching the columnar fix shipped for the fundamental endpoints in 0.1.2.

## [0.1.2] - 2026-05-29

### Fixed
- **DataFrame conversion for columnar responses.** Many data endpoints (fundamental
  income-statement / balance-sheet / cash-flow, valuation-analysis, main-business)
  return a columnar matrix `{fieldList, list:[[...]]}`. A new `normalize_rows`
  (ported from the TS CLI) transposes it into named columns; previously these
  produced an empty DataFrame or one with integer column names.
- `fundamental.valuation_analysis` column schema corrected to the real fields
  (`tradeDate, value, percentileRank, average, median, upper1Std, lower1Std`).
- `GANGTISE_VERBOSE` now actually emits debug logs — a stderr handler is attached
  for both sync and async transport (previously the level was set but no handler
  existed, so records were dropped). `Config.verbose` is honored by the client.
- Async client no longer blocks the event loop on token / title-cache disk I/O
  (offloaded via `anyio.to_thread`).
- Title cache prunes entries past its TTL on load, bounding on-disk growth.
- Sample `fundamental_valuation_analysis` used an invalid indicator
  (`pe_ttm` → `peTtm`).

### Added
- `fundamental.earning_forecast` now returns a DataFrame (flattened analyst
  consensus, one row per update date × forecast year). Defaults to the latest
  update snapshot; pass `latest=False` for the full history or `raw=True` for the
  nested payload.
- Async transport now logs request timing, mirroring the sync path.

### Changed
- Domain helpers (`_as_list`, `_strip_none`, `_extract_rows`) consolidated into
  `domains/_common.py` (previously duplicated across every domain module).
- Pagination logs a warning when results are truncated at `MAX_PAGES`.
- Dropped an unused `config` parameter from the transport request functions.

## [0.1.1] - 2026-05-28

## [0.1.0] - 2026-05-28
