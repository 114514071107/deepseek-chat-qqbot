# 8301c98 表情重复补修部署与 QQ 复验

日期：2026-10-25（Asia/Shanghai）。本地 dev 功能版本 `8301c9872764aaa5e84ca737b98e7208ea7ffbf1`。沿用当前验收任务“离线完成后部署启动并继续 QQ”的用户授权，没有推送远端或合并 main。

## 实际发布与核验

- 先审阅补修差异并重新运行原三项 3/3、专项 8/8、完整 Python 193/193（184.769 秒）、余额 2/2、Node 13/13、54 份 AST/JS/差异及两套 PowerShell 矩阵，均通过。完整结果见[复验记录](../reviews/2026-10-25-sticker-duplicate-reacceptance.md)。
- 旧运行版为 `4cdf194`，26/26 文件匹配前次发布清单，未发现 active user 请求。新清单同为 26 文件，其中只有 main.py 发生部署内容变化。源码包由 `git archive 8301c98` 精确生成，部署常量保留、源码秘密匹配和暂存语法校验通过。
- 受保护备份目录为 `D:\dsbot\deployment-backups\20261025-sticker-selection-release`，继承既有受保护发布目录的权限，仅当前账号和 SYSTEM。
- 停止前先同时核对 Bot/Console worker 的 PID、启动时间、可执行路径、nonce、RuntimeRoot 和 InternalWorker 命令身份，保存元数据后仅停止这两个 worker。它们自己的 KILL_ON_JOB_CLOSE Job 回收所属子进程，未按 Python/Node 名称停止其他应用。随后确认端口关闭及无本实例进程。
- 停写快照 **376 文件逐份 SHA256 校验通过**，包含 dsh_data、data 根文件（含当时存在的 DB/WAL/SHM）、data/config，另备份 deployment-config、原代码/入口。未打开活跃 SQLite。
- **02:18（Asia/Shanghai）安装 1 份变更文件，26/26 运行哈希匹配**。main.py 保留 DATA、MASTER_OPENID、KIMI_CLI、DL_DIR，源码入口固定本版功能提交；Console 保留 MASTER。cmd_config.json、插件配置、runtime.json 和加密凭据均与备份哈希相同，未做数据迁移。
- 使用既有新启动核心 `D:\dsbot\start-bot.ps1 -RuntimeRoot D:\dsbot -WithConsole -TimeoutSeconds 60` 启动，分别报告 owned listener ready。认证 Console bot_running=true、管理心跳新鲜、6185/7850 监听；随后指定账号 QQ 实收验证新版业务。启动 stderr 未匹配 Traceback/ERROR/CRITICAL。

发布目录包含 before/、data-snapshot/、staged/、release-manifest.json、source-commit.txt、installation.json、activation.json、console-verification.json、final-health.json 和 corresponding-source.zip，以及实际使用的 prepare/validate/install/stop-owned/rollback 脚本。源码提交尚未推送，固定远端入口需随用户后续推送安排核对；本机保留本版无秘密对应源码包。

## QQ 结果及当前状态

四个编号输入：私聊单张/两张、群单张/两张。图片数依次为 1/2/1/2，原重复追加关闭；群两张前仍发一条等待文字，新增 P2，整体验收暂不通过。七个 accepted 为六张图片和一条文字，客户端分别确认；测试私聊在群用例前后未变化。完整时间线与隔离复现见[验收记录](../reviews/2026-10-25-sticker-duplicate-reacceptance.md)。

服务保持 `8301c98` 运行，收尾运行 26/26 哈希与认证/心跳/两端口正常；未操作管理开关或清理测试数据。未新增依赖、远端推送、合并 main 或稳定晋级，TTS/F09 等仍暂缓，RQ04 原退出原因未定。

## 回退

先重新核实当前 `.launcher` 中 worker 的完整身份，再停止本实例两个 worker 并确认服务停写。按本发布清单校验 before/ 备份后使用 rollback-code.ps1 恢复旧代码，再通过既有隐藏启动核心启动。旧代码基线为 `4cdf194`，回退会恢复原重复入队缺陷，只作为排障措施。

回退仅恢复代码/入口，不以停写快照覆盖新聊天，不删除新媒体、归档或日志，不重放 unknown，不按进程名批量停止其他程序。若 worker 或文件身份不符，先停止回退操作并保留现场。
