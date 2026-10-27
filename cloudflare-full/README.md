# 家庭记账完整手机网页云端版

此目录复用 `bookkeeping/web_static/` 的完整手机 PWA 和原有 Python Web API。GitHub 登录、桌面 GitHub 备份恢复、自然语言双 Agent、账户、流水、预算、报表、信用卡、固定资产、饮食、收据及离线队列继续使用原实现。

Cloudflare Worker 负责 HTTPS 与静态网页；Durable Object 将请求串行送到原 Python 服务容器。每次成功写入后，服务会生成一致性账本快照并保存到私有 R2 桶；休眠后会先恢复快照再开放请求。GitHub 同步包仍按现有规则排除 API 密钥、本机偏好和授权令牌。

## R2 免费额度保护

- 应用在滚动 32 天内最多执行 100,000 次 Class A 和 1,000,000 次 Class B 操作，约为 R2 每月免费额度 1,000,000 / 10,000,000 的十分之一，为同账号其他项目预留更多空间。
- 单个账本快照最多 1 GiB；当前设计只保存一个私有快照对象。新建桶请保持 Standard 存储并关闭对象版本控制，避免旧快照版本持续占用空间。
- 达到应用安全线后，Worker 会在处理账本变更前拒绝云端写入，手机端离线队列继续保留，额度窗口滚动恢复后可重试。该保护只统计本软件产生的 R2 操作；Cloudflare 免费额度按账号共享，账号内其他 R2 项目也会消耗额度。
- Cloudflare 的预算提醒只发送通知，不会自动暂停服务。此应用保护不限制 Workers Paid 或容器本身的费用。
- 云端版暂不把识图记账的原图归档到服务器，也不把已有小票图片打进 GitHub/Gitee 同步包；识图仍可临时发送给你自己配置的视觉模型。已存在的图片不会自动删除，仍可能包含在 R2 的完整账本快照内。

## 本机检查

需要 Docker Desktop、Node.js、Cloudflare Wrangler 和 Python 3.13 镜像构建环境。发布前先从桌面端同步最新手机界面，再构建容器：

```powershell
pnpm install
pnpm sync:pwa
pnpm exec wrangler login
pnpm exec wrangler r2 bucket create household-bookkeeping-cloud-ledger --location apac
pnpm exec wrangler dev
```

容器在本地由 Wrangler/Docker 启动；部署 Cloudflare Containers 需要 Workers Paid（官方基础计划为每月 5 美元，超出套餐包含量后按实际用量计费）。正式部署使用当前 Worker 名称，会替换简化测试版的网页/API；原 D1 测试数据不删除。先在本地和部署预览验证后再切换线上站点。

## 数据安全

- R2 只通过 Worker 私有绑定访问；容器归档仅覆盖 `/data`，导出时对 SQLite 文件执行 SQLite backup，避免复制到半写入的 WAL 状态。
- 恢复归档会限制文件类型、路径和展开大小；容器仅接受 Worker 内部随机令牌控制的初始化/导出请求。
- 用户的账本、同步配置、票据、技能和加密后的模型配置都保存在每次云快照内。模型 API 密钥不会写入开源代码或桌面 GitHub 同步包。
- 容器休眠或重新部署时从 R2 恢复；若云端快照失败，接口会返回 `X-Bookkeeping-Cloud-Saved: false`，网页显示提醒。
- `pnpm sync:pwa` 从桌面程序的 `bookkeeping/web_static/` 同步全部 PWA 文件，避免网页与桌面版的手机界面逐渐分叉。
