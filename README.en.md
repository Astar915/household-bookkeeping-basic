<div align="center">
  <img src="assets/household-bookkeeping.png" alt="Household Bookkeeping" width="96" />
  <h1>🏡 Household Bookkeeping · Every entry, crystal clear</h1>
  <p><strong>Less “Where did the money go?” More peace of mind.</strong></p>
  <p>Record transactions in plain language and bring accounts, budgets, and reports together. Your ledger stays on your computer by default.</p>
  <p>
    <a href="https://github.com/Astar915/household-bookkeeping-basic/releases/latest">🪟 Get the Windows portable app</a> ·
    <a href="#first-use">🧭 First use</a> ·
    <a href="#data-and-privacy">🔐 Data and privacy</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Windows-Portable-0078D4?style=for-the-badge&logo=windows" alt="Windows portable app" />
    <img src="https://img.shields.io/badge/Ledger-Local--first-7C3AED?style=for-the-badge" alt="Local first" />
    <img src="https://img.shields.io/badge/AI-Optional-EC4899?style=for-the-badge" alt="AI is optional" />
    <img src="https://img.shields.io/badge/License-MIT-16A34A?style=for-the-badge" alt="MIT License" />
  </p>
  <p><strong>Current version: 0.2.0 · Initial public release</strong></p>
</div>

> 💬 **Bookkeeping can be this simple:** “Dinner yesterday, 850 JPY, paid in cash.” Review the suggested entry and confirm to save. Natural-language entry needs a model service you configure; you can still open and manage your local ledger without AI.

## ✨ What you can do

- 💸 Record income, expenses, transfers, and balance counts; JPY and CNY stay separate
- 💳 Manage bank, cash, wallet, transit, points, credit-card, and fixed-asset records
- 📊 Review transactions, balance sheets, income statements, category spending, and budgets
- 🧾 Edit or delete an incorrect entry; attach receipt images to help with recognition
- 💾 Create local backups; connect GitHub or Gitee only if you want multi-device sync
- 🌙 Use Chinese, English, or Japanese, with light, dark, and system appearance options

## 🧭 First use

1. **Download and open the app.** Follow the portable Windows steps below; Python is not required.
2. **Add your accounts and real balances.** Set up bank, wallet, and credit-card accounts under **Assets** and **More**. New installations start with an empty ledger.
3. **Record an entry.** Open **Record → Bookkeeping** and enter the date, purpose, amount, currency, and account. Review the suggestion and confirm it before it is saved locally.
4. **Review anytime.** Filter or correct entries under **Ledger**; find reports under **More → Household Financial Reports** and budget progress on the home page.
5. **Back up before changing devices.** Create a local backup under **Settings → Ledger and Backups**. GitHub/Gitee sync is optional; read its guide before connecting.

> 🔒 The app does not connect to banks or make payments. Your ledger stays on this computer by default; data is sent to a remote model or cloud only when you configure and use those services.

## ⬇️ Portable Windows app (no coding)

**Download, extract, double-click:**

1. [Download the Windows portable ZIP](https://github.com/Astar915/household-bookkeeping-basic/releases/latest/download/HouseholdBookkeeping-Windows-x64.zip).
2. Extract **all files** from the ZIP into a folder. Keep the EXE beside its _internal folder.
3. Double-click <code>HouseholdBookkeeping.exe</code>. You do not need Python, Git, or developer tools.

The first launch creates an empty ledger. Your ledger and settings are stored under <code>%APPDATA%\HouseholdBookkeeping-Portable</code>, outside the app bundle. To use natural-language entry, configure a model under **Settings → API Services**. The app can open and manage the local ledger without one.

> 🪟 Windows may show an “Unknown publisher” warning because this build is not code-signed. Download it only from this repository’s Releases and check that the filename is <code>HouseholdBookkeeping-Windows-x64.zip</code>.

### 🧑‍💻 Developers: run from source

You need Windows and **Python 3.11 or newer** with Tkinter. Clone the repository or download and extract its GitHub ZIP. Open PowerShell in the project folder:

~~~powershell
git clone https://github.com/Astar915/household-bookkeeping-basic.git
cd household-bookkeeping-basic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
~~~

With the ZIP download, skip <code>git clone</code> and <code>cd</code>. To explore fictional demo data, replace the initialization command only on a new empty ledger with <code>python -m bookkeeping.cli init --seed-demo</code>. **Never run demo initialization on an existing ledger.** After installing dependencies, you can also double-click <code>launch-bookkeeping.vbs</code>.

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
