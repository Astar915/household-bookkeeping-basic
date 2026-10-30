# 从本地版迁移到云端：部署避坑指南

本文记录把本地优先的 Python、SQLite 和桌面/PWA 软件迁到 Cloudflare Workers + D1 时容易踩的坑，并以本仓库当前网页版架构为例。它不是“复制文件后点部署”的教程：云端运行时、存储、任务生命周期、身份和费用边界都与本地电脑不同。

## 先认准要部署的版本

本仓库存在桌面版、本地网站、旧 MVP 和旧 Container 方案。目录名字相近不代表它们部署到同一个服务，也不代表功能和数据相同。

| 用途 | 本仓库位置 | 注意 |
| --- | --- | --- |
| 当前 Python + D1 网页版 | `cloudflare-full/python-d1/` 和 `cloudflare-full/public/` | API、页面、D1 与 Workflow 分开部署；这是当前正式网页架构 |
| 旧 Container/R2 方案 | `cloudflare-full/wrangler.jsonc` 及同目录旧部署文件 | 依赖容器、持久化和可能收费的资源；不要把它误当成当前网页配置 |
| 旧简化 MVP | `cloudflare-mvp/` | 有独立 Worker/D1；不要把正式网页版迁移到其数据库 |
| 桌面版/本地网站源代码 | 项目根目录的 `bookkeeping/` | 不是云端 Worker 的部署入口；不要用目录复制覆盖网页源代码 |

在其它项目中，先列出所有部署配置、Worker/服务名称、数据库绑定和域名，确定唯一目标后再改代码。不要只根据网页标题、`stage` 名称或某个旧 URL 判断当前生产环境。

## 本地程序不能原样搬进 Serverless

| 本地程序常见假设 | 云端需要重新设计 |
| --- | --- |
| SQLite 文件和 AppData 长期存在 | Worker 文件系统是临时空间；请求结束后本地临时文件会消失。持久数据必须写入 D1/R2 等持久服务 |
| 后台线程/进程可一直运行 | 浏览器关闭、实例休眠或请求结束都可能中止普通后台任务；需要服务器已经接收的持久任务（本项目使用 Cloudflare Workflows） |
| 所有请求在一台电脑按顺序执行 | 多设备和并发请求会竞争同一份数据；需要数据库事务、版本校验、幂等键和冲突提示 |
| 本机模型/文件/网络可直接访问 | 云端无法访问用户电脑的路径、Ollama 或局域网地址；用户配置的远程模型也会引入 API 费用和隐私边界 |
| 程序更新不改变用户数据 | 代码回滚不会自动回滚 D1 schema 或已提交的数据；数据库迁移必须单独设计和备份 |

可把本地 SQLite 作为每次请求中的临时工作副本，但不能把临时文件当成云端底账。本项目从 D1 恢复基础快照和行变更，使用完丢弃临时 SQLite；不要在 Worker 全局变量里保存账本、会话或任务进度。

## 数据库迁移和恢复

- 本地 D1 与远端 D1 是两套数据库。带 `--local` 的迁移不会更新线上；远程迁移必须使用明确指向目标数据库的配置，并先核对数据库名称和 ID。
- 先备份，再做 schema 迁移。迁移应版本化、可重复执行，并优先使用“增加字段/表、兼容旧代码、部署、再清理旧结构”的扩展/收缩顺序。只回滚 Worker 代码不等于回滚数据库。
- 远端迁移完成后，再部署依赖新结构的代码。迁移中途失败时先检查实际已应用的 migration，不要猜测后直接重复 DROP、重建或覆盖数据库。
- 还原 GitHub/Gitee 备份、从桌面导入和网页登录是不同操作。登录不等于自动上传或导入本地 SQLite；明确账本的唯一真实来源，并在导入前显示冲突、备份和覆盖范围。
- 写入不能依赖“浏览器只会发一次”。请求可能超时但服务端已完成；使用稳定操作 ID、唯一约束和账本版本检查，避免重试生成重复流水或覆盖另一设备的新数据。
- D1 有单行大小、批次和执行限制。大文件/整库快照不要塞进单条记录；分块时保存长度、哈希、版本号和提交状态，恢复前校验完整性。控制台配额也要结合账号内其它项目核对。

## 后台任务和模型调用

- `setTimeout`、浏览器 Promise、`sendBeacon` 或页面上的“后台上传”提示都不能保证关掉网页后任务会继续。只有服务器持久接收并创建了任务之后，Workflow 才能脱离当前页面继续；确认界面应区分“排队中、服务器已接收、完成、失败”。尚未接收的变更留在 IndexedDB/离线队列，下次打开再发送，并提供撤销或冲突恢复。
- Workflow 会重试或恢复执行。任务必须能安全重放：固定 operation ID，保存输入摘要和版本，外部 API 的已完成响应要可校验地回放；敏感响应加密存储，只保存必要的响应头。绝不能在每次重试时无条件再次提交账目或重复调用付费模型。
- 云端模型调用和记账提交分开。模型只产生候选字段，程序校验账户、类别、金额和日期；需要用户确认的交易在确认前不得写入。模型超时或 Worker 失败时，先核对 operation 状态，不要让用户盲目重复发送。
- 模型图片/文本会发送到用户配置的模型提供方，并可能消耗其 API 配额。压力测试、健康检查、部署命令不应暗中调用真实模型。用 stub/mock 或专门测试凭据；真实模型测试须事先明确授权。
- 本地 Workflow 模拟器即使能创建 Workflow，也不代表它真的启动了实例。本项目的 `WORKFLOW_LOCAL_INLINE=1` 是本地同步替代路径，只用于验证业务代码，不能证明远端持久 Workflow、重试或关页后继续运行。

## CPU、图片和 503

- CPU 时间和请求墙钟时间不是一回事：等待模型网络响应会增加墙钟时间，但通常不会持续消耗 Worker CPU。到控制台看目标 Worker 的 invocation 详情、CPU 时间、异常原文和部署版本；不要只从浏览器的 HTTP 500/503 推断原因。
- Worker 的 CPU 上限与计划、Worker 配置和当前平台规则有关。部署前到账号控制台核实实际值；不要照抄旧文档里的套餐结论，也不要通过升级套餐或提高 CPU 上限掩盖低效代码。任何可能收费的资源先确认价格和预算。
- 图片大小限制不能只看压缩后的文件。对原始字节、像素数、长边、附件总数都设上限。避免在服务器上重复做 EXIF 旋转、缩放、PNG/JPEG 重编码、逐像素 Python 扫描和高强度压缩；对浏览器已规范化的图片走有界快速路径，同时保留服务端格式、尺寸和元数据校验。
- 本项目曾遇到图片记账 503。Worker invocation 的异常是 `Worker exceeded CPU time limit`；请求没有成功提交账本。根因在图片进入模型前重复解码/重压缩和小票图像扫描，而不是简单的界面刷新故障。通用修复方向是减少重复处理、限制上传，并从 Worker 日志确认 CPU 消耗；不要针对某一张图片添加特例。
- API 网关显示 503 可能代表私有 Python 引擎启动/CPU 失败，不等于数据库里一定没有写入。响应应明确“本次未提交”还是“结果未知”；未知时先用 operation ID 查询状态，不能鼓励重复记账。

## 登录、备份和密钥不是一回事

- 区分应用登录、OAuth 授权、GitHub/Gitee 备份同步、个人访问令牌（PAT）和模型 API Key。桌面版使用 PAT 备份，不会自动成为网页 OAuth 登录能力。
- OAuth 回调地址、scope、Client ID/Secret 必须与部署 URL 完全一致。Gitee 身份若需要映射到已有账本，应以稳定的供应商用户 ID 显式关联，不能只按昵称或邮箱猜测，也不能悄悄创建/合并账本。
- Client Secret、会话签名密钥、加密密钥和模型 Key 放在 Worker Secret/安全环境配置里，不写进 `wrangler` 源码、README、日志、截图、提交或浏览器 JS。`.dev.vars` 等本地密钥文件必须被忽略；提交前检查 `git status` 和 staged diff。
- 前端资产通常公开可下载。把认证逻辑、密钥或管理操作仅隐藏按钮不构成访问控制；每个 API 请求都要在服务器端认证、授权和校验资源归属。

## 域名、区域可达性和缓存

- `workers.dev` 在目标用户所在网络未必可访问；尤其应从真实使用者所在地区、运营商和设备提前验证。自定义域名也不自动保证可达；若涉及中国大陆运营，迁移前核对域名、接入服务和适用的备案/合规要求。
- 认证回调、Cookie 的 Secure/SameSite、CORS、反向代理和 HTTPS 必须以最终正式域名逐项核对。不要从 localhost 测试成功就推断线上 OAuth、Cookie 或跨域请求正确。
- PWA Service Worker 可能继续提供旧的 HTML/JS/CSS。上线后确认 cache key/版本更新策略、重新加载与旧客户端升级路径；排查时同时记录浏览器资源版本和 Worker 版本，避免把“仍看到旧页面”误判为部署失败。
- 一个名称里有 `stage` 的网址也可能已经被指定为正式工作区。测试和发布前都核对完整域名，不能只凭“stg/stage/production”字样操作另一个 Worker。

## 本仓库的发布顺序

从 `cloudflare-full/` 执行。不要用该目录根部的旧 `wrangler.jsonc` 发布；它属于旧 Container 路线。先确认配置、目标 Worker、D1 数据库和当前分支，再选最窄发布命令：

1. **只改 `public/` 静态页面：**

   ```powershell
   node node_modules/wrangler/bin/wrangler.js deploy --config python-d1/wrangler.web.jsonc
   ```

   这会发布 JavaScript 网关和静态资产，不重新部署两个 Python 引擎。

2. **改 `python-d1/src/` 或引擎配置：**

   ```powershell
   npm run deploy:web
   ```

   脚本依次部署 engine-a、engine-b、web 网关。任何一步失败都意味着发布可能只完成一部分；修好后检查三者当前版本并完成剩余发布，不要把上传成功误认为全部上线。

3. **改 Workflow：**

   ```powershell
   npm run deploy:web:workflow
   ```

   API、两个引擎和 Workflow 是独立 Worker；改其中一份源码不代表其它 Worker 自动更新。

4. **新增/修改 D1 schema：**先核对远端目标，再查看和应用远程迁移；确认迁移已完成后才部署依赖新 schema 的代码：

   ```powershell
   pnpm exec wrangler d1 migrations list DB --remote --config python-d1/wrangler.web.jsonc
   pnpm exec wrangler d1 migrations apply DB --remote --config python-d1/wrangler.web.jsonc
   ```

   不要把 `--local` 结果当成线上迁移，也不要对旧 MVP 数据库运行正式网页版迁移。

5. **首次部署/身份配置：**按项目说明单独设置 D1 migration、Workflow、Service Binding 和必需 Secrets。`npm run deploy:web` 不会自动应用远端 D1 migration，也不会部署 Workflow；不要把密钥复制到命令记录或源文件。部署后记录每个 Worker 的版本 ID。

在另一个项目中，请把上面的目录、配置和命令替换成实际值；不要复制本仓库的 D1 ID、Worker 名称或 Secret。

## 验证方式与费用边界

- 功能验证从独立的合成账号和合成账本开始，不用真实用户账本做并发、压力或删除测试。优先在本地 D1/隔离的测试部署使用模型 stub；真实线上请求可能消耗 Worker、D1、模型或其它供应商额度。
- 把“能打开首页”“API 返回 200”“流水持久保存”“刷新后仍显示”“另一设备读取”“删除任务可恢复”分成不同验收项。只测一个 200 响应不能证明数据已可靠保存。
- 做小规模、逐步加压的测试：先记录基线和每类操作 CPU/墙钟时间，再增加并发；出现错误立刻停止并保留 request/operation ID、版本、状态码和耗时。测试完成清理合成数据，并核对清理结果。
- 不把用户真实 API Key、账本内容、图片或账户信息放进公开 issue、截图、日志或压力测试脚本。日志只记录最少的关联 ID 和错误类别。
- 本仓库当前网页使用 Python Worker + D1 + Workflow；没有为当前网页启用 Container 或 R2 的必要。旧 Container/R2 方案涉及额外费用与不同恢复机制，不要因为存储/速度问题就直接开启；先量化瓶颈、确认费用，再单独评估架构。

## 上线前检查表

- [ ] 唯一目标域名、Worker 名称、D1 ID、环境配置均已核对。
- [ ] 本地账本导入、云端底账和备份恢复分别说明；上线前有可校验备份。
- [ ] 远端 migration 与代码兼容，迁移顺序明确，回滚不依赖“退回 Worker 版本”。
- [ ] 后台任务可持久恢复，重试有幂等键，浏览器关闭时状态明确。
- [ ] 服务器端每个路由执行身份、权限、版本和输入校验；密钥不进入公开文件。
- [ ] 在目标地区验证域名、登录回调、Cookie、HTTPS 和静态缓存更新。
- [ ] 查过实际 CPU、D1 和模型服务限额/费用；没有未经确认的付费升级或真实模型测试。
- [ ] 用合成账本核验记账、刷新、跨设备读取、冲突、删除、失败恢复和备份还原。
- [ ] 发布记录包含代码提交、D1 迁移、各 Worker 版本 ID、验证结果和已知限制。

## 参考文件

- [当前网页版架构与发布说明](../cloudflare-full/README.md)
- [Python Worker + D1 实现及本地/远程操作说明](../cloudflare-full/python-d1/README.md)
- [项目版本历史](../CHANGELOG.md)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Cloudflare Workers CPU profiling](https://developers.cloudflare.com/workers/observability/dev-tools/cpu-usage/)
