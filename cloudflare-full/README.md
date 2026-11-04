# 家庭记账「网页版」

用户已指定 Python Worker + D1 作为唯一正式网页版。**后续网页版功能修改和发布都以 `python-d1/` 为目标**；稳定访问地址为 [网页版](https://household-bookkeeping-python-d1-stage.household-bookkeeping-cloud-test.workers.dev/)。桌面程序继续作为独立本地版本。

## 正式网页版部署目标

- API 与账本数据：`python-d1/`，Cloudflare Python Worker + D1。
- 后台任务：`python-d1/workflow/`，Cloudflare Workflows。
- 页面文件：`public/`。未来网页版的修改直接更新这里和 `python-d1/`；不要从桌面目录自动同步或覆盖网页源文件。
- 正式 Wrangler 配置：`python-d1/wrangler.web.jsonc` 和 `python-d1/workflow/wrangler.web.jsonc`。
- 旧的密码简化 Worker 不再作为产品版本。移除 Worker 时保留其 D1 数据库，避免误删账本或配置。
- 正式网页版只用 D1，目前没有 R2 绑定或 R2 存储需求；不要为它启用 R2。

根目录的 `wrangler.jsonc` 是尚需 Workers Paid 的 Container 旧方案，**不要用它发布网页版**。新版 Python+D1 不依赖 Container。Cloudflare 已确认本账号为 Workers Free；目前网页版使用免费计划默认 CPU 限制，不要升级到 Workers Paid，也不要部署 Container。

发布顺序：先用 `python-d1/wrangler.web.jsonc` 检查并应用 D1 迁移，再用 `python-d1/workflow/wrangler.web.jsonc` 发布后台 Worker，最后从 `python-d1/` 用 `pywrangler deploy --config wrangler.web.jsonc` 发布网页版 API。部署命令不会更改 MVP D1 数据库。

## Container 旧方案说明

以下 Container 实现仅作为技术参考保留，不是网页版的后续更新目标。它依赖 Cloudflare Workers Paid 与容器用量，不要因其文件仍在仓库中而部署或升级套餐。

---

## Container 旧方案架构

此目录复用 `bookkeeping/web_static/` 的完整手机 PWA 和原有 Python Web API。GitHub 登录、桌面 GitHub 备份恢复、自然语言双 Agent、账户、流水、预算、报表、信用卡、固定资产、饮食、收据及离线队列继续使用原实现。

Cloudflare Worker 负责 HTTPS 与静态网页；Durable Object 将请求串行送到原 Python 服务容器。每次成功写入后，服务会生成一致性账本快照并保存到私有 R2 桶；休眠后会先恢复快照再开放请求。GitHub 同步包仍按现有规则排除 API 密钥、本机偏好和授权令牌。

## R2 免费额度保护

- 应用在滚动 32 天内最多执行 100,000 次 Class A 和 1,000,000 次 Class B 操作，约为 R2 每月免费额度 1,000,000 / 10,000,000 的十分之一，为同账号其他项目预留更多空间。
- 单个账本快照最多 1 GiB；当前设计只保存一个私有快照对象。新建桶请保持 Standard 存储并关闭对象版本控制，避免旧快照版本持续占用空间。
- 达到应用安全线后，Worker 会在处理账本变更前拒绝云端写入，手机端离线队列继续保留，额度窗口滚动恢复后可重试。该保护只统计本软件产生的 R2 操作；Cloudflare 免费额度按账号共享，账号内其他 R2 项目也会消耗额度。
- Cloudflare 的预算提醒只发送通知，不会自动暂停服务。此应用保护不限制 Workers Paid 或容器本身的费用。
- 云端版暂不把识图记账的原图归档到服务器，也不把已有小票图片打进 GitHub/Gitee 同步包；识图仍可临时发送给你自己配置的视觉模型。已存在的图片不会自动删除，仍可能包含在 R2 的完整账本快照内。

旧 Container 方案依赖 Docker、Workers Paid 和 R2。其历史发布步骤已停用；用户已指定免费计划上的 Python+D1 为正式网页版，因此不要部署这个旧方案、创建 R2 资源或更改套餐。

## 数据安全

- R2 只通过 Worker 私有绑定访问；容器归档仅覆盖 `/data`，导出时对 SQLite 文件执行 SQLite backup，避免复制到半写入的 WAL 状态。
- 恢复归档会限制文件类型、路径和展开大小；容器仅接受 Worker 内部随机令牌控制的初始化/导出请求。
- 用户的账本、同步配置、票据、技能和加密后的模型配置都保存在每次云快照内。模型 API 密钥不会写入开源代码或桌面 GitHub 同步包。
- 容器休眠或重新部署时从 R2 恢复；若云端快照失败，接口会返回 `X-Bookkeeping-Cloud-Saved: false`，网页显示提醒。
- Container 旧方案曾从桌面程序同步 PWA；此同步路径已不再用于「网页版」，避免改动或覆盖桌面版本。
