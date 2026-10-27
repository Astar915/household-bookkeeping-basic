# Household Bookkeeping

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md)

**Current version: 0.2.0 · Initial public release**

Household Bookkeeping is an open-source, local-first app for managing personal and family finances. Use it to record income, expenses, and transfers; manage accounts and credit cards; and review budgets, balances, and period reports. The desktop app uses Python, Tkinter, and SQLite. Your ledger stays on your computer by default. The app does not connect to banks or make payments or repayments.

You can enter transactions in natural language, for example, “Lunch yesterday, 850 JPY, paid in cash,” or attach a receipt image. Natural-language entry is optional and requires a local Ollama model or an OpenAI-compatible model service that you configure. Review the suggested details before confirming; the app asks follow-up questions when required information is missing.

## What it can do

- Record income, expenses, account transfers, and balance counts, with JPY and CNY tracked separately
- Manage bank, cash, wallet, prepaid, transit, points, and credit-card accounts
- Search transactions by date and manually edit or delete an incorrect entry
- Review balance sheets, income statements, category spending, and budget progress; the default accounting period runs from the 15th through the 14th
- Manage recurring transactions, credit-limit snapshots, and local repayment schedules; credit-card debt figures are ledger estimates, not live bank data
- Register fixed assets and view their monthly depreciated book value
- Create local backups; the desktop app can also be connected to a private GitHub or Gitee repository for sync
- Optionally run a web/PWA client; natural-language entry, cloud sync, and web hosting each require configuration

## Windows desktop app: install and launch

You need Windows, Git (or the GitHub ZIP download), and **Python 3.11 or newer** with Tkinter included.

Run these commands in PowerShell:

```powershell
git clone https://github.com/Astar915/household-bookkeeping-basic.git
cd household-bookkeeping-basic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
```

If you use GitHub's **Download ZIP** option, extract the archive and open PowerShell in the extracted project folder. Skip the `git clone` and `cd household-bookkeeping-basic` commands.

Initialization creates an empty ledger at `data/household_bookkeeping.sqlite3`. To explore the interface, you can use `python -m bookkeeping.cli init --seed-demo` **instead of** the normal initialization on a new, empty ledger. It adds fictional demo data. Do not use demo initialization on a ledger that already contains your data.

After installing the dependencies, you can also double-click `launch-bookkeeping.vbs` in the project folder to open the desktop window.

## First-use guide

1. **Add accounts and opening balances.** Manage accounts from **Assets**. Cash, bank, wallet, prepaid, and transit accounts can be maintained under **More → Cash Management**. Add credit cards separately under **More → Credit Card Management**, using credit-limit snapshots you have verified. Enter only your own accounts and actual balances.
2. **Choose a language and configure an agent.** Change the interface language in Settings. To use natural-language entry, add Ollama or an OpenAI-compatible service under **Settings → API Services**, then assign it to the Bookkeeping Agent under **Agent and Skill Settings**. With local Ollama, requests stay on your computer; a remote provider receives the text or images you submit.
3. **Record a transaction.** Open **Record → Bookkeeping** and describe the date, purpose, amount, currency, and account. Answer follow-up questions if the app needs more information. Check the suggested transaction and confirm it to save it to the local ledger. Receipt recognition can help read an image, but you should still verify the amount and payment account.
4. **Review your ledger.** Use the transactions page to find, filter, and correct entries. Use **More → Household Financial Reports** for the balance sheet and income statement, and the home page for budget progress. Enter cash counts and credit-limit snapshots from actual records; the app does not query your bank.
5. **Back up your data.** Create a local backup under **Settings → Ledger and Backups**. To sync across devices, connect GitHub or Gitee yourself and review the scope and recovery behavior in the linked documentation first.

The desktop app can open and manage a local ledger without a model service, but natural-language entry inside the app requires one. Without a model, you can enter transactions directly with the CLI's `income`, `expense`, and `transfer` commands; run the relevant command with `--help` to see its required fields.

## Optional web/PWA client

From the project folder, install the web dependencies and start the local service:

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

On the same computer, open `http://127.0.0.1:8000` in a browser. Sign in with GitHub; no separate app account registration is required. The service listens on the local computer by default. Phone access requires additional local-network and HTTPS setup. Public hosting also requires HTTPS, persistent storage, and server-side protections. See [Web deployment and sync](docs/WEB_SYNC_SETUP.md) and [GitHub sign-in](docs/GITHUB_WEB_LOGIN.md).

The web ledger and the desktop SQLite ledger are separate by default. To use desktop data on the web, explicitly import the ledger in the web app or restore it using the documented backup flow. Signing in does not import or overwrite desktop data. See the [iPhone/PWA test guide](docs/IPHONE_PWA_TEST.md) for local phone testing.

## Data and privacy

- The repository does not include user ledgers, accounts, budgets, API keys, cloud authorization, or personal preferences. New users set these up for themselves.
- The desktop ledger is stored locally in `data/`. On Windows, API connection settings are stored in the current user's application-data directory.
- When you use a remote model, the bookkeeping text, images, and related context submitted in a request are sent to that provider. Do not enter online-banking passwords or full card numbers.
- GitHub/Gitee sync is opt-in. A sync bundle contains the ledger, payment rules, the currently loaded Skill, and archived receipt images; it is not additionally encrypted. See [GitHub sync](docs/GITHUB_SYNC.md) and [Gitee sync](docs/GITEE_SYNC.md).
- The web app stores web ledgers in the server's data directory. The operator is responsible for protecting server data and configuring HTTPS. Desktop data is not uploaded to the web service without a user action.

## CLI and development

The CLI entry point is `python -m bookkeeping.cli`. For example:

```powershell
python -m bookkeeping.cli --help
python -m bookkeeping.cli expense --help
python -m bookkeeping.cli chat
python -m bookkeeping.cli validate
```

`chat` uses a configured local Ollama model or an OpenAI-compatible service supplied through environment variables. See [Natural-language API configuration](docs/NATURAL_LANGUAGE_API.md) for details and data boundaries. Developers can run:

```powershell
python -m unittest discover -s tests -v
```

See [CHANGELOG.md](CHANGELOG.md) for release history. Licensed under the [MIT License](LICENSE).
