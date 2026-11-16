# 「网页版」Python Worker + D1 功能覆盖记录

用户于 2026-10-28 指定 Python Worker + D1 为唯一正式「网页版」，后续网页更新以此部署为准。此文件区分代码覆盖与端到端验证，避免把本地合成数据当成真实账号验证。桌面应用与本机账本仍独立。

## 线上端到端验收（未验证项；不代表代码未实现）

- [ ] GitHub Device Flow sign-in, session renewal, logout, and per-user ledger isolation.
- [ ] Complete overview, accounts, transaction history, and localized Chinese/Japanese/English UI.
- [ ] Account/category creation; income, expense, memo-only entry, same-currency transfer, and explicit cross-currency transfer.
- [ ] IndexedDB offline queue, operation-ID idempotency, retry, conflict/error reporting, and manual sync.
- [ ] Desktop SQLite import into an empty cloud ledger; SQLite export/download.
- [ ] Manual ZIP backup download, backup listing, restore, pre-restore backup, integrity checks, and recovery of settings/skills/payment rules/cloud connections.
- [ ] Two independently configured Agents (bookkeeping and food/health), custom OpenAI-compatible endpoints, separate text/vision model assignments, API-key privacy, conversation context, pending confirmations, cancellation, and usage display.
- [ ] Editable Agent Skills, built-in defaults, per-Agent separation, reset, and persistence across sessions/devices.
- [ ] Natural-language bookkeeping, follow-up dialogue, transaction confirmation, image-assisted receipt parsing, and review-state semantics. Receipt images remain temporary and are not archived to cloud, per the user's instruction.
- [ ] Payment-method rules, currency constraints, ordered split-payment routing, and validation against registered accounts.
- [ ] Account reconciliation, credit-limit snapshots/history, repayment records/plans, recurring transactions, and scheduled processing.
- [ ] Fixed assets, depreciation, inclusion/disposal behavior, balance sheet, profit statement, category budgets, savings plan, and date-specific reports.
- [ ] Food purchases, food consumption logs, food grouping/classification, food-review preference, and food-health Agent flow.
- [ ] Transaction edit/delete/review, account/category management, audit-safe pre-change backup, and validation reporting.
- [ ] GitHub/Gitee private backup connection, upload, restore, automatic upload, startup download, conflict handling, and credential rotation.
- [ ] Cloud data persistence across isolate eviction/redeployment; no dependency on the user's PC or home Wi-Fi.

## Runtime adaptation (implemented)

- [x] Replace local filesystem persistence with durable D1-backed storage while preserving the current SQLite ledger schema and migration behavior.
- [x] Replace background threads and subprocess isolation with durable, cancelable request/job orchestration; no Tk or desktop imports in the Worker bundle.
- [x] Replace blocking `urllib` calls with Workers `fetch`-based asynchronous transport for model, GitHub, Gitee, and FX requests.
- [x] Replace local encryption-key files with a Worker-secret-derived encryption key for API credentials and OAuth tokens.
- [x] Preserve SQLite export/import and ZIP restore formats; validate size, hashes, schema, and restore rollback before committing.
- [x] Keep image archival disabled while retaining temporary image-assisted model requests.
- [x] Use the Python+D1 Worker as the official web target and retain its stable Stg URL.

## Current status

2026-10-29 deployed diagnostics reproduced a platform exception outside Python
application error handling: HTTP 500 / edge 1101, `NoGilError: Attempted to use
PyProxy when Python GIL not held`, including on a job poll with only 3 ms CPU.
This matches [workerd #6624](https://github.com/cloudflare/workerd/issues/6624).
Frontend retries and a successful read immediately after deployment did not
resolve it. The official URL now uses a JavaScript gateway with two private
Python service bindings and the original shared D1 database. A failed GET/HEAD
can use the other runtime; mutations are never automatically replayed by the
gateway. Static assets do not initialize Python. Engines have no public or
preview URLs or independent Cron; the gateway dispatches the existing Cron.
Original secrets remain on the official Worker and are forwarded only through
private bindings, overriding any caller-supplied transport headers. Deploy all
three components with `npm run deploy:web`; this adds no paid service or plan.
This isolates a platform failure; it does not claim to patch Pyodide itself.

The Python Worker implements D1-backed GitHub sessions, overview/workspace/transaction reads, account/category and idempotent offline-sync writes, SQLite import/export, ZIP backup/restore, replayable OpenAI-compatible Agent calls, replayable GitHub/Gitee backup transport, D1-queued automatic uploads, and Cron-driven due-entry processing. The durable job runner is split into a JavaScript Workflow Worker and the Python API Worker; its private job-step route uses a shared secret and Workflow history stores status markers only. The Worker dry-run previously bundled the Workflow script at about 2 KiB and the Python API at about 12 MiB. Local `pnpm smoke:python` passes synthetic-session auth, localized workspace load, account/category creation, idempotent transaction sync and job retry behavior, same-user second-session reads, cross-user isolation, model settings/Skill persistence and key redaction, ZIP backup download, SQLite export/import into an empty account, bundle restore, credit limit/schedule/repayment, reconciliation, budgets, payment rules, fixed assets, recurring entries, food purchase/consumption/grouping, and transaction edit/review/delete.

The local smoke uses `WORKFLOW_LOCAL_INLINE=1` because Wrangler's local Workflow emulator accepted instance creation but did not run instances in this environment. It exercises the same replay-safe Python job unit but does not verify cross-Worker durable Workflow orchestration. Real GitHub Device Flow, real model requests, GitHub/Gitee backup transport, every settings combination, multi-device conflicts, and remote Cron execution still need end-to-end validation. These remaining items are clearly marked below; they do not change the user's choice of official web target.

Recent implementation work now sends offline/manual sync and direct transaction writes through durable jobs. Their FX rate lookups use the same replayable Workers `fetch` boundary as model and backup calls; Agent-created transactions, reconciliation, transaction editing, user-triggered due processing, and Cron due processing can also yield and replay when they need a fresh rate. A synthetic replay test covers the D1 Python copy of the FX resolver. This verifies the local adapter path only: real Frankfurter responses and deployed Workflow retries remain unchecked until staging.

## Storage and Free plan limits

2026-10-29 view refresh regression: the web UI now refreshes workspace and
bootstrap data from one D1 revision via `includeBootstrap=1`, rather than parallel
snapshot downloads. Rendering no longer starts another network request. Forced
refreshes wait for a fresh read after any older in-flight read; account switches,
report-date changes, and out-of-order date-filter responses discard stale data.
Only GET reads retry once on transient failures. Failed refreshes preserve the
latest view and report the refresh failure without resubmitting a completed job.
Synthetic tests cover these races, transient HTTP 500, completed-Agent refresh,
filtered transaction lists, combined-response consistency, and API-key redaction.

2026-10-29 Agent regression: the deployed caller supplied `request_now` but the
isolated D1 request adapter did not accept it, causing `TypeError` before any
provider call. The D1 adapter and natural-language session now carry the original
job timestamp through every replay in JST. Synthetic end-to-end D1 tests verify
model-request yield/replay, yesterday's date across midnight, one 990 JPY expense,
incremental row-delta persistence after reopen, and clarification without a write
when the payment account is missing. No real provider request or user transaction
was used for this verification; real model responses remain separately unverified.

- D1 limits each string, BLOB, or row to 2,000,000 bytes. Snapshot files are split into 96 KiB chunks; encrypted durable job payloads and model replies use 192 KiB plaintext chunks. The local smoke now round-trips a synthetic 4 MiB job payload through encryption, D1, and cleanup. Receipt images are not archived; compressed images are only carried by temporary Agent jobs.
- D1's documented database cap is 500 MB on Workers Free and 10 GB on Workers Paid. The per-user 450 MiB application guard is not a promise that a shared Free database can hold 450 MiB for every user.
- This account is confirmed on Workers Free. Free allows 10 ms CPU per HTTP request and Cron invocation. This application reloads a user's SQLite snapshot into Python/Pyodide for domain operations, so local success does not prove every request fits the Free CPU limit. Do not upgrade Workers Paid or enable paid Container usage; if a future request exceeds 10 ms, it must fail within the existing Free plan. The deployed D1 snapshot is about 9.5 MB.
- References: [D1 limits](https://developers.cloudflare.com/d1/platform/limits/), [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), and [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/).
