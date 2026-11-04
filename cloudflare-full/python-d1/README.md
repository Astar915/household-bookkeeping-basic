# 「网页版」Python Worker + D1

用户已指定此 Python Worker + D1 部署为唯一正式「网页版」，访问地址为 [网页版](https://household-bookkeeping-python-d1-stage.household-bookkeeping-cloud-test.workers.dev/)。今后的网页版功能修改、数据库迁移和发布都以 `cloudflare-full/python-d1/` 与 `cloudflare-full/public/` 为目标；不要从桌面代码自动同步或覆盖网页文件。桌面程序仍是独立本地版本。

共享的数据库合并代码保留可选的行观测钩子；桌面端不传入这些钩子。功能覆盖情况和仍未完成的线上端到端验证见 `../PYTHON_D1_PARITY.md`。

## 正式网页版发布与运行时隔离

在 `cloudflare-full` 下运行 `npm run deploy:web`，依次发布两个私有 Python 引擎和同网址的 JavaScript 网关。修改 Python 后不可仅发布 `wrangler.web.jsonc`，否则引擎代码不会更新。私有引擎配置为 `wrangler.engine-a.jsonc` 和 `wrangler.engine-b.jsonc`，共享原 D1；不得开启公开或预览网址。原有密钥保留在网关，只通过内部 Service Binding 传递，无须复制到文件或更换密钥。部署不启用付费套餐、容器、R2 或模型调用。

此结构隔离线上已复现的 Cloudflare Python `NoGilError` / HTTP 500 / 1101：网页静态资源不再启动 Python，GET/HEAD 遇到运行时失败可切换另一引擎；记账、上传等写入不自动重发。平台缺陷记录见 [workerd #6624](https://github.com/cloudflare/workerd/issues/6624)。这属于应用层故障隔离，不代表修复了 Cloudflare 的解释器。

2026-10-29 验证：31 项网页版专项测试、264 项项目测试通过；线上独立合成账本 3 次写入后紧接着的 6 次读取均返回 200，流水数依次为 1、2、3，测试账号已清理。真实账号页面刷新后显示 53 条及新记的 1 JPY 消费，未重记或调用真实模型。可运行 `scripts/smoke_remote_refresh.py` 重做隔离线上验证；它只创建并清理随机命名的 `refresh-fixture-*` 合成账号，不使用已有用户的会话或账目。

## Migration strategy

- Keep the existing mobile PWA files and SQLite business schema.
- Run the Python ledger rules against a temporary per-request SQLite file in the Worker memory filesystem.
- Store user files and a periodic SQLite base as checksummed, versioned chunks in D1. After row-delta mode starts, persist changed SQLite rows in D1 instead of uploading the full database on every ledger write; temporary Worker files are discarded after each request.
- Use D1 tables for users/sessions, GitHub Device Flow state, durable jobs, and Agent conversation state.
- Adapt network calls to the Workers `fetch` API, and replace thread/process-based work with durable job records and cancellation checkpoints.
- Keep receipt-image archive storage disabled while retaining image-assisted model requests.

此 Worker 通过 D1 处理网页版请求。生产称呼「网页版」指向这个已部署的 Python+D1 Worker；待验证项目仍须如实记录，但不再将 Container 方案作为默认发布目标。

### Ledger write volume

The D1 adapter keeps an immutable SQLite base snapshot and layers committed row upserts/deletes over it. The base is refreshed when row-delta mode is first enabled, when the SQLite schema changes, or when accumulated deltas exceed 2,000 rows or 2 MiB. Agent transactions are captured during the isolated-database merge as well as direct ledger writes. Automatic full ZIP backups are limited to one per day; users can still create manual backups.

This reduces D1 writes for ordinary ledger changes. Each request still restores the SQLite base, applies its current row deltas, and computes the existing workspace/report data in Python. It does not by itself establish that normal reads fit Workers Free's 10 ms CPU limit.

### Cloud download and Workflow regression checks

The Worker-specific GitHub/Gitee clients accept a replay opener. `ModelRequestRequired` must escape provider-failure handling so the Workflow can fetch and resume the same request. Replayed HTTP responses expose status and case-insensitive headers, including GitHub's conditional-request ETag.

Response headers needed for replay are allowlisted and stored inside the existing encrypted response chunks. The opaque generation prefix `http1_` identifies the header/body record format; older generations still decode as raw response bodies. This requires no D1 schema migration. Cookies and authorization response headers are excluded.

A successful cloud restore normalizes the web-only SQLite schema and explicitly replaces the D1 base and schema digest, clearing previous row deltas. Ordinary ledger writes retain the existing incremental path. Restore still creates a recovery backup and preserves the unsynced-change and offline-queue checks.

A fingerprint mismatch is a source-selection result (`conflict`), not a failed network request. The Worker persists a pending choice and pauses automatic downloads. Sign-in then offers keeping and opening the web ledger for review, or creating a full recovery backup before explicitly restoring GitHub. Closing the choice keeps the web ledger. Refreshing cannot bypass a pending choice, and keeping remains in effect until an explicit cloud restore succeeds. A fingerprint includes ledger entries and selected settings/Skills; a mismatch alone does not prove that the user manually changed a transaction.

The dedicated `github-sync` secret is authoritative for the access/refresh token pair after sign-in. Repository and checkpoint preferences can come from `mobile-config`, but stale embedded credentials must not override a new sign-in. New device-flow credentials record their public Client ID and flow type; sign-in and refresh use the same public App configuration. Authentication failures retain the reconnect action on the error screen instead of hiding the only recovery route.

The initial page shows a session-restoration screen while `/api/session` validates the existing secure, persistent browser cookie. Only a confirmed signed-out session opens the main sign-in page. A returning user's backup failure stays on an authenticated welcome/status screen with a separately labeled GitHub backup reconnect action. IP addresses are not used as identity, and backup authorization expiry does not clear the app session.

### Gitee sign-in

Gitee sign-in is optional until an OAuth application is configured. Create a Gitee OAuth application with callback URL `https://household-bookkeeping-python-d1-stage.household-bookkeeping-cloud-test.workers.dev/api/auth/gitee/callback` and the `user_info` scope, then add `GITEE_CLIENT_ID` and `GITEE_CLIENT_SECRET` as secrets to the public gateway Worker `household-bookkeeping-python-d1-stage`. Do not add them to the private Python engines or commit them. Once both secrets are present, `/api/config` enables the Gitee sign-in and account-link buttons without another deployment.

Gitee sign-in can access an existing ledger only after the user signs in with that ledger's GitHub account and explicitly links Gitee from the top bar. The app matches the stable Gitee numeric ID, never a display name, and does not create or merge a ledger from an unlinked Gitee account. GitHub backup authorization remains separate from the sign-in provider. The OAuth app's passwords stay on Gitee; the website only receives the short-lived authorization response and does not retain the Gitee access token.

Run the isolated regression suite from the repository root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s cloudflare-full/python-d1/tests -v
```

The suite uses synthetic SQLite ledgers and provider responses with external network access blocked. It covers HTTP suspension/replay, encrypted response chunk round-trips, ETag/304 fast checks, token refresh, checksum/conflict protection, and complete download/backup/restore/D1 commit followed by another login. It does not exercise the real user's GitHub credentials or Cloudflare runtime resource limits.

## Local development

Requires Node.js and `uv` as documented by Cloudflare Python Workers. From the `cloudflare-full` directory, apply the local D1 schema, then enter `python-d1` to run the Worker through Pywrangler (plain `wrangler dev` does not bundle the Python runtime SDK):

```powershell
pnpm exec wrangler d1 migrations apply DB --local --config python-d1/wrangler.local.jsonc
Set-Location python-d1
.venv\Scripts\pywrangler.exe dev --config wrangler.local.jsonc --port 8789 --var WORKFLOW_LOCAL_INLINE:1
```

Migration `0004_ledger_row_deltas.sql` creates the local D1 tables required by row-delta persistence. This command applies it only to Wrangler's local database; remote migrations and deployments remain separate actions.

正式网页部署使用 `wrangler.web.jsonc`，其中 D1 绑定指向已部署的 Stg 数据库。`wrangler.jsonc` 与 `wrangler.local.jsonc` 仅供独立的本地开发流程使用，不要用占位配置执行远程迁移或发布。

Set a local-only `python-d1/.dev.vars` file with a random `TOKEN_ENCRYPTION_KEY` before testing GitHub login. Never commit that file. The production value must be installed as a Worker secret during a later, separately approved deployment.

Wrangler's local Workflow emulator currently accepts Workflow creation but does not start instances (also reproduced with a minimal JavaScript Workflow). For local-only smoke runs, use `wrangler.local.jsonc` and pass `--var WORKFLOW_LOCAL_INLINE:1`. This runs the same replay-safe Python job unit synchronously so ledger actions can be exercised locally, but it does not verify durable Workflow orchestration. `.dev.vars` is for secrets; this non-secret switch is supplied only on the local command. Do not set it for deployment: deployed requests use the slim JavaScript durable Workflow and deterministic operation IDs.

## 发布「网页版」

Python API Worker 通过脚本名绑定 JavaScript Workflow Worker。正式配置是 `wrangler.web.jsonc` 与 `workflow/wrangler.web.jsonc`；两个 Worker 需保持 `APP_JOB_SHARED_SECRET` 相同，Python API 还需设置 `TOKEN_ENCRYPTION_KEY`。共享密钥保护用于推进后台任务的内部 service-binding 路由。远端 D1 迁移必须先于 Worker 发布。配置内的 D1 ID 指向当前网页版账本数据库，不要替换为 MVP 的 D1。

Cloudflare 已确认当前账号使用 Workers Free。正式配置不启用 Container、不提高 CPU 限制，也不升级 Workers Paid；Free 的默认 CPU 上限是 10ms，超出时请求可能失败，不能通过升级套餐自动绕过用户的费用要求。

PowerShell 中从 `cloudflare-full` 目录执行：

```powershell
pnpm exec wrangler d1 migrations list DB --remote --config python-d1/wrangler.web.jsonc
pnpm exec wrangler d1 migrations apply DB --remote --config python-d1/wrangler.web.jsonc
pnpm exec wrangler deploy --config python-d1/workflow/wrangler.web.jsonc
Set-Location python-d1
.venv\Scripts\pywrangler.exe deploy --config wrangler.web.jsonc
```

Worker 发布不会删除旧 MVP D1。移除旧 MVP Worker 时保留 `household-bookkeeping-test` 数据库，直到确认无需恢复其中的账户或设置。

With the local Worker running, verify the authenticated D1 path without using a real GitHub account or modifying remote data:

```powershell
pnpm smoke:python
```

The script is restricted to loopback URLs, seeds a synthetic identity into local D1, exercises account/category creation, idempotent transaction sync, durable backup, SQLite export and bundle restore, then deletes the synthetic user's data.
