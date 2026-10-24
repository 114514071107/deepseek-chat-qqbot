# d31827c 数量及用户工作台验收部署

日期：2026-10-25（Asia/Shanghai）。本地 dev `d31827c4462126a9156e0f1801f861953a7bc901`。沿用本验收任务已有部署/启动及 QQ 许可，源码审阅与离线前置实际通过后发布；无推送或 main 合并。[完整验收结论](../reviews/2026-10-25-sticker-count-order-reacceptance.md)区分 A 通过与 B 未完成。

旧运行 26/26 匹配 `1da1746`；旧 Bot/Console worker 已退出，无目标实例进程及服务监听。本轮没有停止其他进程，记录为启动新实例。受保护本机发布目录为 `D:\dsbot\deployment-backups\20261025-sticker-count-order-release`，沿用旧发布目录受限 ACL，包含 before/、staged/、data-snapshot/、release-manifest.json、对应源码 zip、prepare/validate/install/rollback 脚本和实际核验 JSON。

停写后 **390 份数据文件逐份 SHA256 核验通过**，覆盖插件数据、框架 data 根文件/config，另保留部署配置、凭据和旧代码。28 项配套发布中 7 份变化：插件 main.py/chat_style.py/reply_completion.py，Console server.js/index.html，以及新增 console 与 public 下各一个 user-workbench.js。安装前后校验来源/暂存/旧运行文件，安装后及收尾 **28/28 哈希一致**；框架配置、dsh_soul_conf、runtime.json、加密凭据均保持原哈希，无数据迁移。

使用现有 `start-bot.ps1 -RuntimeRoot D:\dsbot -WithConsole -TimeoutSeconds 60`。Bot worker 于 **05:46:03**、Console 于 **05:46:13** 启动，PID 分别 106872、78908，启动时间/可执行路径/nonce/目标 root 身份匹配。插件加载钩子、AstrBot started 和 QQ websocket 启动正常；QQ 实际四条入站、五图两文出站进一步证明连接。收尾 bot_running=true，心跳年龄 0.09 秒，两端口监听；认证首页 200、无认证 people 401、认证跨来源 403。

本地对应源码包来自精确 `git archive d31827c`，不代表远端已发布。未推送、合并 main、安装依赖、清理聊天/媒体或调整真实管理开关。服务保持本版运行。A 的四个真实 QQ 用例通过；B 生产关联操作未写入映射即遇电脑工具强制停止，尚待继续，不能把启动就绪当整单通过。

回退时先重新核对当前目标 worker 的完整身份并停止本实例，确认目标端口/进程已退出；校验本发布 before/ 文件与 manifest.previous_sha256 后使用本发布 `rollback-code.ps1` 恢复旧代码，再按现有入口启动。只回退代码与源码入口，不用数据快照覆盖后续聊天，不删除新媒体/映射或重放 unknown。新增 B 模块可保留，旧 server/index 不引用；旧版 `1da1746` 会恢复已知数量缺陷。未核对身份或哈希不符时不继续覆盖。本轮没有实际回退。
