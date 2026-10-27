# 家庭记账系统

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md)

**当前版本：0.2.0 · 初始公开版本**

一个以本地账本为中心的家庭记账应用，使用 Python、Tkinter 和 SQLite。桌面记账、账户管理、报表、校验和备份可以离线使用；可选网页端和自然语言记账需要自行配置相应服务。

## 功能

- 收入、支出、转账、余额盘点、信用卡额度和固定资产管理
- 分类报表、预算、定期收支、现金管理和本地备份
- 中文、日语和英语界面
- 可选的本地或 OpenAI 兼容模型记账
- 可选网页/PWA 客户端与 GitHub/Gitee 备份同步
- 包含通用记账 Skill：`.agents/skills/household-bookkeeping-software-v0-2/SKILL.md`

## Windows 快速开始

需要 Python 3.11 或更新版本，并启用 Tkinter。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
```

初始化会创建空账本，路径为 `data/household_bookkeeping.sqlite3`。软件不会预填账户、收入、预算、API 密钥、云端账号或个人偏好；请在应用中按自己的情况设置。需要体验流程时，可在空数据库中显式使用 `python -m bookkeeping.cli init --seed-demo` 写入虚构演示数据。

网页端可选安装依赖并运行：

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

然后在本机浏览器访问 `http://127.0.0.1:8000`。手机从局域网访问和 PWA 安装需要额外的 HTTPS 配置；远程模型、GitHub 登录和云同步也需要使用者自行配置。

## 数据与隐私

此仓库不包含个人账本、数据库、备份、小票、迁移记录、本机配置或 API 凭据。账本在本机 `data/` 目录中；Windows 上 API 配置保存在当前用户的应用数据目录。使用远程模型时，本轮提交给记账功能的文字或图片会发送到使用者配置的服务商。云备份仅在使用者自行连接并启用后发生。

首次公开发布的源代码只提供应用和通用记账 Skill。账户、类别偏好、预算、模型服务、语言、GitHub/Gitee 授权、备份目标及其他个人设置均由下载者自行创建。

## 开发

```powershell
python -m unittest discover -s tests -v
python -m bookkeeping.cli validate
```

版本历史见 [CHANGELOG.md](CHANGELOG.md)。本项目以 [MIT License](LICENSE) 发布。
