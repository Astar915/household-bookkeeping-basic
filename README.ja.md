# 家計簿

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md)

**現在のバージョン：0.2.0 · 初回公開リリース**

Python、Tkinter、SQLite で作られた、ローカル保存を基本とする家計簿アプリです。デスクトップでの記帳、口座管理、レポート、検証、バックアップはオフラインで利用できます。Web クライアントと自然言語入力は、利用者自身によるサービス設定が必要です。

## 主な機能

- 収入、支出、振替、残高照合、クレジットカード枠、固定資産の管理
- カテゴリ別レポート、予算、定期取引、現金管理、ローカルバックアップ
- 簡体字中国語、日本語、英語の UI
- ローカルまたは OpenAI 互換モデルによる任意の自然言語記帳
- Web/PWA クライアントと GitHub/Gitee バックアップ同期（任意）
- 汎用の記帳 Skill：`.agents/skills/household-bookkeeping-software-v0-2/SKILL.md`

## Windows での起動

Python 3.11 以降と Tkinter が必要です。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
```

初期化すると `data/household_bookkeeping.sqlite3` に空の台帳が作成されます。口座、収入、予算、API キー、クラウドアカウント、個人設定は初期登録されません。アプリでご自身の内容を設定してください。操作例を試す場合は、空の台帳に対して `python -m bookkeeping.cli init --seed-demo` を明示的に実行してください。架空のデモデータが登録されます。

Web クライアントを使う場合は、次のコマンドで起動します。

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

同じ PC のブラウザで `http://127.0.0.1:8000` を開きます。スマートフォンからのアクセスと PWA のインストールには追加の HTTPS 設定が必要です。リモートモデル、GitHub ログイン、クラウド同期も利用者自身で設定してください。

## データとプライバシー

このリポジトリには個人の台帳、データベース、バックアップ、レシート、移行記録、ローカル設定、API 認証情報は含まれません。台帳はローカルの `data/` に保存されます。Windows の API 設定は現在のユーザーのアプリデータ領域に保存されます。リモートモデルを設定した場合、記帳リクエストに入力した文章や画像はそのサービス提供者に送信されます。クラウドバックアップは利用者が接続して有効にした場合のみ行われます。

初回公開版に含まれるのはアプリ本体と汎用の記帳 Skill です。口座、カテゴリ設定、予算、モデル接続、言語、GitHub/Gitee 認証、バックアップ先などはダウンロードした方が設定します。

## 開発

```powershell
python -m unittest discover -s tests -v
python -m bookkeeping.cli validate
```

変更履歴は [CHANGELOG.md](CHANGELOG.md) をご覧ください。[MIT License](LICENSE) で公開しています。
