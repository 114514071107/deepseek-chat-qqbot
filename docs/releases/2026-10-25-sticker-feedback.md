# 1da1746 纯表情反馈补修部署与复验

日期：2026-10-25（Asia/Shanghai）。本地 dev 功能提交 `1da1746023bd3da9922297ec31306673b23c493a`。沿用同一验收任务已获的离线通过后部署、启动及 QQ 实测授权。没有推送远端或合并 main。

## 发布及运行核验

- 先审阅差异并实际通过原三项 3/3、专项 12/12、完整 Python 205/205（190.835 秒）、余额 2/2、Node 13/13、56 份 AST/JS/差异和双 PowerShell 矩阵，再部署。新 QQ 数量问题及其独立失败探针另见[验收记录](../reviews/2026-10-25-sticker-feedback-reacceptance.md)。
- 旧运行文件 26/26 匹配 `8301c98`，无 active user 请求。由精确 `git archive 1da1746` 生成对应源码包，暂存清单 26 文件，其中 main.py/chat_style.py 两份部署内容变化；源码秘密检查与暂存语法通过。
- 受保护备份目录 `D:\dsbot\deployment-backups\20261025-sticker-feedback-release`，沿用既有发布目录受限 ACL，仅当前账号和 SYSTEM。目录含 before/、data-snapshot/、staged/、清单、源码包及实际使用的 prepare/validate/install/stop-owned/rollback 脚本。
- 核对 Bot/Console worker 的 PID、启动时间、可执行路径、nonce、RuntimeRoot、InternalWorker 身份，仅停止本实例两个 worker，由各自 KILL_ON_JOB_CLOSE Job 回收子进程；端口关闭后再做停写快照，没有按进程名批量停止其他应用。
- **382 文件停写快照逐份 SHA256 校验通过**，包含 dsh_data、框架 data 根文件与 data/config，另备份部署配置/加密凭据和旧代码。没有打开活跃 SQLite。
- **02:59:20 安装两份变更文件，26/26 运行哈希匹配**。保留 main.py 中 DATA、MASTER_OPENID、KIMI_CLI、DL_DIR 及 Console MASTER，源码入口固定该功能提交；cmd_config.json、插件配置、runtime.json、console-credential.clixml 均保持原哈希，没有数据迁移。
- 使用现有 `D:\dsbot\start-bot.ps1 -RuntimeRoot D:\dsbot -WithConsole -TimeoutSeconds 60` 启动，Bot/Console 均报告 owned listener ready。认证 Console bot_running=true、管理心跳新鲜、两端口监听；认证首页 200、无认证历史 401、认证跨来源 403。
- 03:10 收尾再次 **26/26**，bot_running=true，心跳年龄 0.022 秒，6185/7850 监听。证据分别为 installation.json、activation.json、console-verification.json、final-health.json。服务保留本版运行，无后续热修。

本机 `corresponding-source.zip` 保留本版无秘密精确源码；提交尚未推送，固定远端源码入口仍需随用户后续推送安排核对，不把本机源码包当成远端已发布。

## 实测结果与剩余问题

指定账号四个输入：私聊两张为两图无字；同私聊普通文字请求仍有反馈和主答；群两张无额外文字但实际五图；群单张为一图无字。共八图三文、十一条 accepted，客户端逐张滚动核对，群用例前后私聊未变化。等待文字 P2 关闭，模型重复选图超量新增 P2，**整体暂不通过**，并非启动成功即可验收。

测试数据和客户端气泡保留，未操作管理开关、清理数据、安装依赖、推送、合并 main 或稳定晋级。RQ04 原退出原因未定，TTS/F09 等继续暂缓。详细工具时间线和独立 2 通过/1 失败探针见[验收记录](../reviews/2026-10-25-sticker-feedback-reacceptance.md)。

## 回退

先重新核对当前 `.launcher` worker 的完整身份并停止本实例、确认停写，校验本发布 before/ 备份后使用 `rollback-code.ps1` 恢复旧代码，再用既有隐藏启动核心启动。旧版为 `8301c98`，会恢复纯表情额外等待文字问题，不能把回退视为该缺陷修复。

回退只恢复代码和入口，不以快照覆盖新聊天、不删除媒体/归档/日志，不重放 unknown。身份或文件哈希不符时保留现场，不继续覆盖。
