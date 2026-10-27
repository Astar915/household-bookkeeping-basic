# 家庭记账系统

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md)

**当前版本：0.2.0 · 初始公开版本**

家庭记账系统是一款以本地账本为中心的开源家庭财务管理软件。它帮助个人或家庭记录收入、支出和转账，管理多个账户与信用卡，并查看账期报表、预算和余额变化。桌面版使用 Python、Tkinter 和 SQLite；账本保存在自己的电脑上，不连接银行，也不会替你实际付款或还款。

记账可以通过自然语言完成，例如“昨天午饭 850 JPY，使用现金”。你也可以附上收据图片。自然语言识别是可选功能，需要配置本机 Ollama 或自己选择的 OpenAI 兼容模型服务；提交前请检查识别结果，信息不够时软件会继续询问。

## 能做什么

- 记录收入、支出、账户间转账和余额盘点，支持 JPY、CNY 分币种核算
- 管理银行、现金、钱包、预付卡、交通卡、积分和信用卡账户
- 查看账单流水，按日期筛选，并手动编辑或删除错误记录
- 查看资产负债表、利润表、分类支出和预算进度；账期默认为每月 15 日至次月 14 日
- 管理定期收支、信用卡额度快照与本地还款计划；信用卡欠款是账内估算，不是银行实时数据
- 登记固定资产并查看按月折旧后的账面价值
- 用本地备份保护账本；桌面版也可选择连接 GitHub 或 Gitee 私有仓库同步
- 可选使用网页/PWA 版本；自然语言记账、云同步和网页服务需要各自配置

## Windows 桌面版：安装与启动

需要 Windows、Git（或下载 GitHub ZIP）以及 **Python 3.11 或更新版本**，并确保 Python 安装包含 Tkinter。

在 PowerShell 中运行：

```powershell
git clone https://github.com/Astar915/household-bookkeeping-basic.git
cd household-bookkeeping-basic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
```

如果通过 GitHub 的 **Download ZIP** 下载，请先解压，并在解压后的项目目录打开 PowerShell；这种方式下跳过上面的 `git clone` 和 `cd household-bookkeeping-basic` 两行。

初始化会创建一个空账本：`data/household_bookkeeping.sqlite3`。如果只想先体验界面，可以在**新的空账本**上用 `python -m bookkeeping.cli init --seed-demo` 代替普通初始化；这会写入虚构的演示数据。不要对已有账本使用演示初始化。

完成依赖安装后，也可以双击项目根目录的 `launch-bookkeeping.vbs` 启动桌面窗口。

## 第一次使用

1. **添加账户和期初余额。** 在“资产”中管理账户；现金、银行、钱包、预付/券和交通卡等资金账户可在“更多 → 现金管理”中维护。信用卡单独在“更多 → 信用卡管理”中登记，并填写你掌握的额度快照。只录入自己的实际账户与余额。
2. **设置语言和记账服务。** 界面语言可在设置中更改。若要用自然语言记账，在“设置 → API 服务”添加本机 Ollama 或你选择的 OpenAI 兼容服务，再到“Agent 配置与 Skill”分配给记账 Agent。仅使用本机 Ollama 时，内容留在本机；远程服务会收到提交的文字或图片。
3. **记录一笔收支。** 打开“记录 → 记账”，用自然语言说明发生日期、用途、金额、币种和账户；缺少必要信息时先回答软件的追问。检查候选记录并确认后，记录才写入本地账本。图片识别可帮助读取收据，不应代替你核对金额和实际付款账户。
4. **核对和查看。** 在“账单”中查找、筛选或修正流水；在“更多 → 家庭财务报表”查看资产负债表与利润表，在首页查看预算进度。现金余额盘点和信用卡额度快照应按实际记录，软件不会查询银行。
5. **创建备份。** 打开“设置 → 账本与备份”手动创建本地备份。需要多设备同步时，再自行连接 GitHub 或 Gitee；同步范围、恢复行为及限制请先阅读对应说明。

如果暂时没有配置模型服务，桌面程序仍可打开并查看、管理本地账本；软件内的自然语言记账需要先配置模型服务。不使用模型时，也可以通过 CLI 的 `income`、`expense` 和 `transfer` 命令直接记账，运行对应命令的 `--help` 查看必填字段。

## 可选：网页/PWA 版本

在项目根目录安装网页依赖并启动本机服务：

```powershell
python -m pip install -r requirements-web.txt
python -m bookkeeping.web
```

同一台电脑的浏览器打开 `http://127.0.0.1:8000`，首次登录使用 GitHub 授权，无需注册软件账号。服务默认只监听本机；手机访问需要额外的局域网与 HTTPS 配置，公网部署也需要自行配置 HTTPS、持久数据目录和服务器保护。详细步骤见 [网页部署与同步](docs/WEB_SYNC_SETUP.md) 和 [GitHub 登录说明](docs/GITHUB_WEB_LOGIN.md)。

网页账本与桌面本地 SQLite 默认相互独立。需要在网页端使用桌面数据时，请在网页端明确导入账本，或按备份说明恢复；登录不会自动导入或覆盖桌面数据。iPhone/PWA 的本机测试步骤见 [iPhone 测试说明](docs/IPHONE_PWA_TEST.md)。

## 数据与隐私

- 下载的项目不包含用户的账本、账户、预算、API 密钥、云端授权或个人偏好。首次使用者需要自行建立这些数据。
- 桌面账本默认保存在本机 `data/` 目录。API 连接配置保存在当前 Windows 用户的应用数据目录。
- 使用远程模型时，本轮提交的记账文字、图片及相关上下文会发送给所选服务商；请勿输入网银密码或完整卡号。
- GitHub/Gitee 同步需由用户自行连接。同步包包含账本、支付规则、当前加载的 Skill 和已归档收据图片；它没有额外加密。详情见 [GitHub 同步说明](docs/GITHUB_SYNC.md) 与 [Gitee 同步说明](docs/GITEE_SYNC.md)。
- 网页版会把网页账本保存到运行服务的数据目录；部署者负责保护服务器数据和配置 HTTPS。桌面数据不会在没有用户操作时自动上传到网页服务。

## 命令行与开发

CLI 主入口是 `python -m bookkeeping.cli`。例如：

```powershell
python -m bookkeeping.cli --help
python -m bookkeeping.cli expense --help
python -m bookkeeping.cli chat
python -m bookkeeping.cli validate
```

`chat` 使用已配置的本机 Ollama 或环境变量中的 OpenAI 兼容服务；相关配置和数据边界见 [自然语言 API 说明](docs/NATURAL_LANGUAGE_API.md)。开发者可运行：

```powershell
python -m unittest discover -s tests -v
```

版本历史见 [CHANGELOG.md](CHANGELOG.md)。本项目以 [MIT License](LICENSE) 发布。
