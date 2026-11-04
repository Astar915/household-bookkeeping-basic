# 桌面版与网页版功能对照（0.2.2）

本清单对照当前 `cloudflare-full` 网页版源代码与桌面版 Python/Tk 实现。目标是把适用于桌面端的已新增功能一并补齐，并保留两个运行环境的安全边界。

## 已补到桌面版

| 功能 | 网页版来源 | 桌面版实现 |
| --- | --- | --- |
| USD 账户、流水、汇率和主要记账货币汇总 | `cloudflare-full/python-d1`、`cloudflare-full/public/app.js` | `bookkeeping/storage.py`、`fx_rates.py`、`financial_statements.py`、`balance_reconciliation.py`、`cash_management.py`、`desktop_shell.py`、`gui.py` |
| 总览只显示主要记账货币余额；外币单独列出 | `cloudflare-full/public/app.js` | `bookkeeping/desktop_shell.py` |
| 账户改名且保留旧称呼识别 | `cloudflare-full/public/mobile.js` | `bookkeeping/storage.py`、`bookkeeping/gui.py` |
| 信用卡额度快照可选择把差额计入收支 | `cloudflare-full/public/mobile.js` | `bookkeeping/balance_reconciliation.py`、`bookkeeping/gui.py` |
| 命中/未命中/输出的人民币费用估算与余额提示 | `cloudflare-full/public/app.js` | `bookkeeping/model_usage.py`、`bookkeeping/gui.py` |
| 聊天区任意位置拖入图片、限制大小、Ctrl+Enter 发送 | `cloudflare-full/public/mobile.js` | `bookkeeping/gui.py` |
| 新用户基础设置顺序与可重播教程 | `cloudflare-full/public/mobile.js` | `bookkeeping/desktop_tutorial.py`、`bookkeeping/gui.py`、`bookkeeping/desktop_shell.py` |
| 设置顺序、通俗标签、每月统计日期放入类别页 | `cloudflare-full/public/mobile.js`、`public/index.html` | `bookkeeping/gui.py`、`bookkeeping/localization.py` |
| 预算折线图、放大图表、悬停详情 | `cloudflare-full/public/mobile.js`、`public/mobile.css` | `bookkeeping/savings_planner.py` |
| 本机先保存、后台显示同步状态 | `cloudflare-full/public/mobile.js` | `bookkeeping/gui.py`、`bookkeeping/desktop_shell.py` |
| 数据修改完成后排入云端备份 | 网页版的本地优先写入队列 | `bookkeeping/gui.py`、`fixed_assets.py`、`food_tracking.py`、`savings_planner.py` |

后台同步覆盖：流水新增/修改/删除、账户增删/改名/核对、类别、月度统计设置、支付规则、预算、定期收支、信用卡和还款计划、食材记录、固定资产、已选 Skill、云备份范围和小票图片备份选项。成功写入本机后立即刷新桌面界面，再通过已有 GitHub/Gitee 队列上传；上传期间状态灯显示进行中，上传失败保留本机数据并报告失败。启用新的同步目标时会排入一次当前快照上传；既有远端版本检查继续阻止静默覆盖冲突。

## 有意保留的运行差异

- GitHub/Gitee OAuth 登录、D1 用户隔离、浏览器 IndexedDB 离线队列和 Cloudflare Durable Workflows 只适用于网页版。桌面版不复制网页登录态，使用本地 SQLite 和桌面自己的备份凭据。
- API 服务配置和密钥、界面语言、外观属于设备偏好，留在当前设备，不随 GitHub 仓库、Skill 或默认配置发布。备份包仅按用户选择同步账本数据、Skill 和小票图片；不会把 API 密钥、OAuth token 或账户授权上传。新安装会加载随软件提供的通用记账 Skill；各使用者需要填写自己的 API 地址、模型和密钥。
- 教程在桌面端使用原生步骤窗口，并可从左侧再次打开；它会引导进入实际设置页和余额页，不会拦截桌面操作或替用户填写 API 密钥。

## 源码检查记录

- 核对网页入口：`cloudflare-full/public/app.js`、`public/mobile.js`、`public/index.html`、`public/mobile.css`，以及当前 Python+D1 运行副本 `cloudflare-full/python-d1`。
- 核对桌面业务：`storage.py`、`fx_rates.py`、`financial_statements.py`、`balance_reconciliation.py`、`natural_language.py`、`payment_preferences.py`、`recurring_transactions.py`。
- 核对桌面界面与数据写入：`gui.py`、`desktop_shell.py`、`savings_planner.py`、`fixed_assets.py`、`food_tracking.py`、`localization.py`、`.agents/skills/household-bookkeeping-software-v0-2/SKILL.md`。
- 0.2.2 发布未包含本机 API 密钥、OAuth token、账本数据库、备份、虚拟环境、测试输出或本机 Wrangler 凭据。自动化测试未运行。
