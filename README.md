<div align="center">
  <img src="assets/household-bookkeeping.png" alt="家庭记账" width="96" />
  <h1>🏡 家庭记账｜每一笔，都清清楚楚</h1>
  <p><strong>少一点“钱去哪了”，多一点心里有数。</strong></p>
  <p>像聊天一样记账，把账户、预算和报表放在一起；账本默认留在自己的电脑，选择权一直在你手里。</p>
  <p>
    <a href="https://github.com/Astar915/household-bookkeeping-basic/releases/latest">🪟 下载 Windows 免安装版</a> ·
    <a href="#第一次使用">🧭 第一次使用</a> ·
    <a href="#数据与隐私">🔐 数据与隐私</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Windows-免安装版-0078D4?style=for-the-badge&logo=windows" alt="Windows 免安装版" />
    <img src="https://img.shields.io/badge/账本-本地优先-7C3AED?style=for-the-badge" alt="本地优先" />
    <img src="https://img.shields.io/badge/AI-可选配置-EC4899?style=for-the-badge" alt="AI 可选配置" />
    <img src="https://img.shields.io/badge/License-MIT-16A34A?style=for-the-badge" alt="MIT License" />
  </p>
  <p><strong>当前版本：0.2.0 · 初始公开版本</strong></p>
</div>

> 💬 **记账可以很简单：**“昨晚晚餐 850 日元，现金支付。”检查候选记录，确认后保存。自然语言记账需要你自行配置本机 Ollama 或兼容模型；不用 AI，也能打开并管理本地账本。

## ✨ 这本账能帮你做什么

- 💸 记录收入、支出、转账和余额盘点，JPY、CNY 分开核算
- 💳 管理银行、现金、钱包、交通卡、积分、信用卡和固定资产
- 📊 查看账单、资产负债表、利润表、分类支出和预算进度
- 🧾 编辑或删除录错的流水，收据图片可辅助识别
- 💾 创建本地备份；需要多设备同步时，再自行连接 GitHub 或 Gitee
- 🌙 支持中、英、日界面，以及白天、暗色和跟随系统外观

## 🧭 第一次使用

1. **下载并打开软件**：Windows 用户按下方“免安装启动”操作，不需要安装 Python。
2. **登记自己的账户和真实余额**：在“资产”及“更多”中设置银行、钱包、信用卡等账户。新用户从空账本开始。
3. **记一笔**：打开“记录 → 记账”，输入日期、用途、金额、币种和账户；检查识别结果，确认后才会写入本地账本。
4. **随时核对**：在“账单”中筛选或修正记录；在“更多 → 家庭财务报表”看报表，在首页看预算进度。
5. **先备份，再换设备**：在“设置 → 账本与备份”创建本地备份。GitHub/Gitee 同步是可选项，连接前请先看同步说明。

> 🔒 软件不会连接银行，也不会替你付款或还款。默认情况下，账本留在这台电脑；只有你主动配置远程模型或云同步时，相关内容才会发送到对应服务。

## ⬇️ Windows 免安装版（零编程）

**下载、解压、双击，三步打开：**

1. [点此下载 Windows 绿色版 ZIP](https://github.com/Astar915/household-bookkeeping-basic/releases/latest/download/HouseholdBookkeeping-Windows-x64.zip)
2. 解压 ZIP 中的**全部文件**到一个文件夹，不要单独移动 EXE。
3. 双击 <code>HouseholdBookkeeping.exe</code>。无需安装 Python、Git 或其他开发工具。

首次运行会自动创建空账本。账本和设置保存在当前 Windows 用户的 <code>%APPDATA%\HouseholdBookkeeping-Portable</code>，不会打包在 EXE 里。想用自然语言记账时，再到“设置 → API 服务”配置模型；未配置模型也可以打开软件、浏览和维护本地数据。

> 🪟 如果 Windows 提示“未知发布者”，是因为当前版本没有代码签名。请只从本仓库的 Releases 下载，并确认文件名为 <code>HouseholdBookkeeping-Windows-x64.zip</code> 后再运行。

### 🧑‍💻 开发者：从源码启动

需要 Windows、Python 3.11 或更新版本（安装时包含 Tkinter）；可用 Git 克隆，也可下载 GitHub ZIP 后解压。在项目目录打开 PowerShell：

~~~powershell
git clone https://github.com/Astar915/household-bookkeeping-basic.git
cd household-bookkeeping-basic
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m bookkeeping.cli init
.\.venv\Scripts\pythonw.exe -m bookkeeping.gui
~~~

如果使用 GitHub ZIP，跳过 <code>git clone</code> 和 <code>cd</code> 两行。只在新空账本上体验演示数据时，可把初始化命令替换为 <code>python -m bookkeeping.cli init --seed-demo</code>；**不要对已有账本运行演示初始化**。依赖安装完成后，也可以双击项目目录中的 <code>launch-bookkeeping.vbs</code>。

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
