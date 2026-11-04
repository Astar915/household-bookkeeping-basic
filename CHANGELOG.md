# Changelog / 更新履歴 / 更新日志

## 0.2.2 — 2026-11-04 — Desktop feature parity and safer background sync / デスクトップ版の機能統合と同期改善 / 桌面版功能补齐与后台同步改进

- **English:** Bring the desktop app closer to the current web app: add USD and configurable main-currency reporting, account renaming, optional credit-limit difference entries, CNY-estimated model usage, whole-chat image drop, Ctrl+Enter sending, and a replayable first-run guide. Reorder settings into General, Agent, Categories, and Backup; move the monthly start-day control under Categories; improve budget charts. Queue successful account, balance, category, budget, recurring, credit, food, fixed-asset, payment-rule, transaction, Skill, backup-scope, and receipt-image backup changes for background cloud upload. Keep API profiles and keys, interface language, and appearance on the device; preserve cloud conflict checks.
- **日本語：** デスクトップ版にUSD・メイン通貨の集計、口座名変更、利用枠差額を記帳する選択肢、人民元見積もりのモデル使用量、チャット全体への画像ドロップ、Ctrl+Enter送信、再表示できる初回ガイドを追加しました。設定を一般・Agent・カテゴリ・バックアップの順に整理し、毎月の集計日をカテゴリへ移動、予算グラフを改善しました。口座、残高、カテゴリ、予算、定期取引、カード、食事、固定資産、支払ルール、取引、Skill、バックアップ範囲、小票画像のバックアップ設定をバックグラウンド同期に追加しました。APIサービスとキー、画面言語、外観は端末内に保持し、クラウド競合チェックを維持します。
- **简体中文：** 桌面版补齐当前网页版功能：支持 USD 和主要记账货币汇总、账户改名、信用卡额度差额是否入账、人民币估算的模型用量、整个聊天区拖入图片、Ctrl+Enter 发送，以及可重看的首次使用教程。设置顺序调整为通用设置、Agent、记账类别、备份；每月统计日期移入记账类别；改进预算折线图。账户、余额、类别、预算、定期收支、信用卡、食材、固定资产、支付规则、流水、Skill、备份范围和小票图片备份选项的更改都会排入后台云端同步。API 服务及密钥、界面语言和外观仍只保存在本机，并保留云端版本冲突保护。
- **Scope note / 対象範囲 / 范围说明:** Browser OAuth, IndexedDB, and D1 durable jobs remain web-runtime features. The desktop uses its own local SQLite and background backup queue; no web login credentials or API keys are copied into this release.

## 0.2.1 — 2026-10-29 — Billing cycle and cloud restore improvements / 請求期間とクラウド復元の改善 / 账期与云端恢复改进

- **English:** Add configurable monthly billing cycles and refresh the overview, financial statements, and budget reports to match. Improve budget charts with taller trends, clearer category pies, and hover details. Startup cloud checks now show live progress and an explicit result; cloud restore keeps a recovery backup and falls back to SQLite's online backup when Windows temporarily locks the ledger file.
- **日本語：** 月次請求期間を設定可能にし、概要・財務レポート・予算を新しい期間で再集計します。予算グラフの傾向表示を高くし、カテゴリ円グラフとホバー詳細を改善しました。起動時のクラウド確認に進捗と結果を表示し、復元前バックアップを保持します。Windowsで台帳ファイルが一時的にロックされている場合はSQLiteバックアップで復元します。
- **简体中文：** 新增可配置的月度账期，并同步刷新总览、财务报表和预算统计；加高预算趋势图，改善分类饼图和悬停详情。启动云端检查显示实时进度和明确结果；云端恢复保留恢复前备份，并在 Windows 暂时锁定账本文件时改用 SQLite 在线备份回写。
- **Documentation update, 2026-10-30:** Add a Chinese-language guide to the pitfalls of migrating a local application to Cloudflare Workers + D1, including data persistence, migrations, durable jobs, CPU limits, authentication, deployment order, cost controls, and safe validation.
- **ドキュメント更新（2026-10-30）：** ローカルアプリをCloudflare Workers + D1へ移行する際の注意点をまとめた中国語ガイドを追加しました。永続化、DB移行、Durable Jobs、CPU制限、認証、公開順序、費用管理、安全な検証方法を説明します。
- **文档更新（2026-10-30）：** 新增《从本地版迁移到云端：部署避坑指南》，梳理数据持久化、数据库迁移、持久任务、CPU限制、登录与密钥、发布顺序、费用控制和安全验证。

## 0.2.0 — 2026-10-27 — Initial public release / 初回公開 / 首次公开版本

- **English:** First public source release of the local-first household bookkeeping app and its generic bookkeeping Skill. New ledgers start empty; users configure accounts, budgets, model services, language, and sync destinations themselves.
- **日本語：** ローカル保存型家計簿アプリと汎用記帳 Skill の初回公開。新しい台帳は空の状態で作成され、口座、予算、モデル接続、言語、同期先は利用者が設定します。
- **简体中文：** 本地优先家庭记账软件及通用记账 Skill 的首次公开发布。新账本默认为空，账户、预算、模型服务、语言和同步目标由使用者自行配置。
