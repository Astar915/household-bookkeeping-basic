<div align="center">
  <img src="assets/household-bookkeeping.png" alt="家計簿" width="96" />
  <h1>🏡 家計簿｜一つ一つの支出が、ちゃんと見える</h1>
  <p><strong>「お金はどこへ？」を減らして、家計に安心を。</strong></p>
  <p>自然な文章で記帳し、口座・予算・レポートを一か所に。台帳は初期設定では自分の PC に保存されます。</p>
  <p>
    <a href="https://github.com/Astar915/household-bookkeeping-basic/releases/latest">🪟 Windows ポータブル版</a> ·
    <a href="#初めて使うとき">🧭 初めて使うとき</a> ·
    <a href="#データとプライバシー">🔐 データとプライバシー</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Windows-Portable-0078D4?style=for-the-badge&logo=windows" alt="Windows ポータブル版" />
    <img src="https://img.shields.io/badge/Ledger-Local--first-7C3AED?style=for-the-badge" alt="ローカル優先" />
    <img src="https://img.shields.io/badge/AI-Optional-EC4899?style=for-the-badge" alt="AI は任意" />
    <img src="https://img.shields.io/badge/License-MIT-16A34A?style=for-the-badge" alt="MIT License" />
  </p>
  <p><strong>現在のバージョン：0.2.0 · 初回公開リリース</strong></p>
</div>

> 💬 **記帳はこれだけ：**「昨日の夕食、850 JPY、現金で支払い」。候補を確認して確定すると保存されます。自然言語入力には利用者が設定するモデルサービスが必要ですが、AI なしでもローカル台帳を開いて管理できます。

## ✨ できること

- 💸 収入、支出、振替、残高確認を記録（JPY と CNY は別々に管理）
- 💳 銀行、現金、ウォレット、交通系 IC、ポイント、クレジットカード、固定資産を管理
- 📊 明細、貸借対照表、損益計算書、カテゴリ別支出、予算を確認
- 🧾 誤った取引を編集・削除。レシート画像の読み取りも補助
- 💾 ローカルバックアップを作成。複数端末で使う場合だけ GitHub/Gitee を接続
- 🌙 中国語・英語・日本語に対応。ライト、ダーク、システム連動を選択

## 🧭 初めて使うとき

1. **ダウンロードして起動**：下の Windows ポータブル版の手順を確認します。Python は不要です。
2. **自分の口座と実際の残高を登録**：「資産」や「その他」で銀行、ウォレット、クレジットカードなどを設定します。新規利用時は空の台帳から始まります。
3. **取引を記録**：「記録 → 家計簿」を開き、日付、用途、金額、通貨、口座を入力します。候補を確認して確定するとローカル台帳に保存されます。
4. **いつでも確認**：「明細」で検索・修正、「その他 → 家計財務レポート」でレポートを確認し、ホーム画面で予算の進捗を見ます。
5. **端末を変える前にバックアップ**：「設定 → 台帳とバックアップ」でローカルバックアップを作成します。GitHub/Gitee 同期は任意です。接続前に説明を確認してください。

> 🔒 銀行とは接続せず、支払いや返済を実行することもありません。台帳は初期設定ではこの PC に保存されます。リモートモデルやクラウドへデータが送信されるのは、利用者が設定して使用した場合のみです。

## ⬇️ Windows ポータブル版（プログラミング不要）

**ダウンロード、展開、ダブルクリックの3ステップ：**

1. [Windows ポータブル版 ZIP をダウンロード](https://github.com/Astar915/household-bookkeeping-basic/releases/latest/download/HouseholdBookkeeping-Windows-x64.zip)
2. ZIP の**すべてのファイル**をフォルダーに展開します。EXE だけを別の場所に移動しないでください。
3. <code>HouseholdBookkeeping.exe</code> をダブルクリックします。Python、Git、開発ツールは不要です。

初回起動時に空の台帳が自動作成されます。台帳と設定は <code>%APPDATA%\HouseholdBookkeeping-Portable</code> に保存され、アプリ本体には含まれません。自然言語入力を使う場合は「設定 → API サービス」でモデルを設定してください。未設定でもローカル台帳の閲覧・管理はできます。

> 🪟 コード署名がないため、Windows が「発行元不明」と表示する場合があります。このリポジトリの Releases からのみダウンロードし、ファイル名が <code>HouseholdBookkeeping-Windows-x64.zip</code> であることを確認してください。

### 🧑‍💻 開発者：ソースから起動

Windows と Tkinter を含む **Python 3.11 以降**が必要です。Git でクローンするか、GitHub ZIP をダウンロードして展開します。プロジェクトフォルダーで PowerShell を開いて実行してください。

~~~powershell
git clone https://github.com/Astar915/household-bookkeeping-basic.git
cd household-bookkeeping-basic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
~~~

GitHub ZIP を使う場合は <code>git clone</code> と <code>cd</code> を省略します。架空のデモデータを試す場合は、新しい空の台帳に限り、初期化コマンドを <code>python -m bookkeeping.cli init --seed-demo</code> に置き換えてください。**既存の台帳でデモ初期化を実行しないでください。** 依存関係のインストール後は、プロジェクト内の <code>launch-bookkeeping.vbs</code> をダブルクリックして起動することもできます。

## 任意機能：Web/PWA クライアント

プロジェクトフォルダーで Web 用依存関係をインストールし、ローカルサービスを起動します。

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

同じ PC のブラウザーで `http://127.0.0.1:8000` を開きます。初回ログインは GitHub 認証を使用し、アプリ専用アカウントの登録は不要です。サービスは初期設定では PC 内からのみアクセスできます。スマートフォンからのアクセスには、LAN と HTTPS の追加設定が必要です。インターネット公開には HTTPS、永続ストレージ、サーバー保護も必要です。詳しくは[Web の公開と同期](docs/WEB_SYNC_SETUP.md)および[GitHub ログイン](docs/GITHUB_WEB_LOGIN.md)をご覧ください。

Web 台帳とデスクトップの SQLite 台帳は初期状態では別々です。Web でデスクトップデータを使うには、Web アプリで明示的に台帳をインポートするか、説明書の手順でバックアップを復元してください。ログインによってデスクトップデータが自動で取り込まれたり上書きされたりすることはありません。スマートフォンでのローカルテストについては[iPhone/PWA テストガイド](docs/IPHONE_PWA_TEST.md)をご覧ください。

## データとプライバシー

- リポジトリには利用者の台帳、口座、予算、API キー、クラウド認証情報、個人設定は含まれません。初回利用時に各自で設定してください。
- デスクトップ台帳はローカルの `data/` に保存されます。Windows の API 接続設定は、現在のユーザーのアプリデータ領域に保存されます。
- リモートモデルを使う場合、リクエストに入力した家計簿の文章、画像、関連するコンテキストがサービス提供者に送信されます。ネットバンキングのパスワードやカード番号全桁は入力しないでください。
- GitHub/Gitee 同期は利用者が接続した場合のみ行われます。同期パッケージには台帳、支払ルール、現在読み込まれている Skill、保存したレシート画像が含まれます。追加の暗号化はされません。[GitHub 同期](docs/GITHUB_SYNC.md)と[Gitee 同期](docs/GITEE_SYNC.md)をご確認ください。
- Web 版の台帳はサービス側のデータディレクトリに保存されます。サーバーデータの保護と HTTPS の設定は運用者の責任です。利用者が操作しない限り、デスクトップデータが Web サービスにアップロードされることはありません。

## CLI と開発

CLI の入口は `python -m bookkeeping.cli` です。例：

```powershell
python -m bookkeeping.cli --help
python -m bookkeeping.cli expense --help
python -m bookkeeping.cli chat
python -m bookkeeping.cli validate
```

`chat` は設定済みのローカル Ollama、または環境変数で指定した OpenAI 互換サービスを使用します。設定方法とデータの扱いは[自然言語 API の説明](docs/NATURAL_LANGUAGE_API.md)をご覧ください。開発者は次のコマンドでテストできます。

```powershell
python -m unittest discover -s tests -v
```

変更履歴は [CHANGELOG.md](CHANGELOG.md) をご覧ください。[MIT License](LICENSE) で公開しています。
