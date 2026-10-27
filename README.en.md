# Household Bookkeeping

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md)

**Current version: 0.2.0 · Initial public release**

A local-first household bookkeeping app built with Python, Tkinter, and SQLite. Desktop bookkeeping, account management, reports, validation, and backups work offline. The optional web client and natural-language entry require services configured by each user.

## Features

- Income, expenses, transfers, balance reconciliation, credit limits, and fixed assets
- Category reports, budgets, recurring entries, cash management, and local backups
- Simplified Chinese, Japanese, and English interface
- Optional local or OpenAI-compatible model for natural-language bookkeeping
- Optional web/PWA client and GitHub/Gitee backup sync
- Generic bookkeeping Skill: `.agents/skills/household-bookkeeping-software-v0-2/SKILL.md`

## Quick start on Windows

Requires Python 3.11 or newer with Tkinter enabled.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
```

Initialization creates an empty ledger at `data/household_bookkeeping.sqlite3`. No accounts, income, budgets, API keys, cloud accounts, or personal preferences are prefilled. Set these up for your own use in the app. To explore the workflow, explicitly run `python -m bookkeeping.cli init --seed-demo` on an empty database; this adds fictional demo data.

The optional web client can be started with:

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

Open `http://127.0.0.1:8000` in a browser on the same computer. Phone access and PWA installation require additional HTTPS setup. Remote models, GitHub login, and cloud sync also require user configuration.

## Data and privacy

This repository contains no personal ledger, database, backups, receipts, migration notes, local configuration, or API credentials. The ledger is stored in the local `data/` directory. On Windows, API configuration is stored in the current user's application data directory. When a remote model is configured, bookkeeping text or images submitted in a request are sent to that provider. Cloud backups happen only after a user connects and enables them.

The initial public release includes the application and its generic bookkeeping Skill. Each user supplies their own accounts, category preferences, budgets, model services, language, GitHub/Gitee authorization, backup destination, and other personal settings.

## Development

```powershell
python -m unittest discover -s tests -v
python -m bookkeeping.cli validate
```

See [CHANGELOG.md](CHANGELOG.md) for release history. Licensed under the [MIT License](LICENSE).
