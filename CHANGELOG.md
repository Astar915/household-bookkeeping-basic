# Changelog / 更新履歴 / 更新日志

## 0.2.1 — 2026-10-29 — Billing cycle and cloud restore improvements / 請求期間とクラウド復元の改善 / 账期与云端恢复改进

- **English:** Add configurable monthly billing cycles and refresh the overview, financial statements, and budget reports to match. Improve budget charts with taller trends, clearer category pies, and hover details. Startup cloud checks now show live progress and an explicit result; cloud restore keeps a recovery backup and falls back to SQLite's online backup when Windows temporarily locks the ledger file.
- **日本語：** 月次請求期間を設定可能にし、概要・財務レポート・予算を新しい期間で再集計します。予算グラフの傾向表示を高くし、カテゴリ円グラフとホバー詳細を改善しました。起動時のクラウド確認に進捗と結果を表示し、復元前バックアップを保持します。Windowsで台帳ファイルが一時的にロックされている場合はSQLiteバックアップで復元します。
- **简体中文：** 新增可配置的月度账期，并同步刷新总览、财务报表和预算统计；加高预算趋势图，改善分类饼图和悬停详情。启动云端检查显示实时进度和明确结果；云端恢复保留恢复前备份，并在 Windows 暂时锁定账本文件时改用 SQLite 在线备份回写。

## 0.2.0 — 2026-10-27 — Initial public release / 初回公開 / 首次公开版本

- **English:** First public source release of the local-first household bookkeeping app and its generic bookkeeping Skill. New ledgers start empty; users configure accounts, budgets, model services, language, and sync destinations themselves.
- **日本語：** ローカル保存型家計簿アプリと汎用記帳 Skill の初回公開。新しい台帳は空の状態で作成され、口座、予算、モデル接続、言語、同期先は利用者が設定します。
- **简体中文：** 本地优先家庭记账软件及通用记账 Skill 的首次公开发布。新账本默认为空，账户、预算、模型服务、语言和同步目标由使用者自行配置。
