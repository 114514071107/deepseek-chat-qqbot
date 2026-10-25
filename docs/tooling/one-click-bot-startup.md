# Windows 一键启动 Bot

2026-10-24。本轮仅交付开发源码与临时实例的离线证据，未安装到生产、未启动真实 Bot/Console。

2026-10-26 更新：开发仓库仅保留 `scripts/start-bot.cmd` 一个用户 Bot cmd；两个旧兼容入口已删除，Console 独立入口保留。本次没有更新生产，生产五个启动文件仍在，待另行部署时按[四项补修记录](../reviews/2026-10-26-console-lifecycle-repairs.md)同步和清理。下文安装步骤以本次更新为准，原日期的安装/验收事实保留。

## 入口与使用

双击 `start-bot.cmd`，默认实例为 `D:\dsbot`，**同时启动 Bot 和 127.0.0.1:7850 管理控制台**。开发入口为 `scripts/start-bot.cmd`，配套部署后运行根同名文件也有此行为。无需再加 `-WithConsole`，已运行的同实例组件通过严格归属核验后复用；缺 Node/凭据或端口冲突会明确失败，不把只启动了 Bot 当作全部成功。直接执行同一核心脚本：

```powershell
pwsh -NoProfile -File 'D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.ps1'
# 直接运行 PS1 默认只启 Bot，需要控制台时加开关：
pwsh -NoProfile -File 'D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.ps1' -WithConsole
# 自选实例；可从任意当前目录执行：
powershell.exe -NoProfile -File 'D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.ps1' -RuntimeRoot 'D:\实例 空格' -TimeoutSeconds 45
```

以上 PS1 方式保留维护者只启动 Bot 的能力；cmd 用进程内默认值启用 Console，不重复拼接参数，显式 `-ConsolePort` 和 `-WithConsole` 可正常传递。默认 7850，改端口不修改生产配置或认证。2026-10-26 本轮实际部署/启动与验证见[五项 P2 补修记录](../reviews/2026-10-26-console-lifecycle-p2-fix.md)，更早“尚未更新生产”的表述保留为当时历史。

`start-bot.cmd` 先查 PATH 中的 pwsh，再查标准安装位置 `%ProgramFiles%\PowerShell\7\pwsh.exe`，没有则调用系统 Windows PowerShell 5.1。没有硬编码 Codex 私有缓存路径。Explorer 与 Codex 的 PATH 可以不同；测试分别提供最小系统 PATH 和显式 pwsh PATH，实际走过 5.1 回退和 7 优先路径。

普通当前登录账号即可运行，不要求管理员。入口只对新解释器进程传 `-ExecutionPolicy Bypass`，不修改机器/用户策略；组织组策略仍然优先。如果组织禁止执行脚本或进程作业对象限制，返回失败，需维护者在合适的本机环境排查，不会提权或安装服务。`DSH_LAUNCHER_NO_PAUSE=1` 可让自动化失败时不等待按键；交互双击失败会保留提示。

| 参数 | 默认与行为 |
| --- | --- |
| RuntimeRoot | `D:\dsbot`，显式指定实例，不使用当前工作目录猜测 |
| WithConsole | cmd 默认 true；直接 PS1 默认 false。启用 Console 必须检查 Node、server.js 和 Console 凭据 |
| TimeoutSeconds | 30，允许 1—120 秒；锁等待和组件就绪分别有界，不无限重试 |
| BotPort | 6185，用于检查已配置 Bot 的监听，不修改 AstrBot 配置 |
| ConsolePort | 7850，同时作为 Console 的 `--port`、PORT 环境和监听核验端口 |

`InternalWorker/Component/WorkerId` 是隐藏 worker 的内部协议，不供双击入口传入。实际启动、配置、等待和退出码在 PowerShell 中实现。旧 `run-astrbot.cmd`、`start-astrbot-launcher.cmd` 不再作为仓库入口；维护者须在获准生产部署时更新快捷方式和调用方，再备份移出旧文件。本轮不会删除生产文件。

## 依赖与保护配置

不安装任何依赖。核心依赖实例的 `venv\Scripts\astrbot.exe`、现有框架/插件及 Windows 内置能力；PS1 以 UTF-8 BOM 保存，辅助 `launcher-process.cs` 由两个解释器各自的 Add-Type 编译。

已只读对照既有受保护 `deployment-config/start-runtime.ps1` 的 `-Mode Bot/Console` 契约。新核心自行执行相同原生命令和认证环境设置；不调用旧脚本中写死的生产路径，避免显式 RuntimeRoot 意外落到另一实例。

- Bot：UTF-8 读取所选实例的 `deployment-config/runtime.json`，要求非空、非占位的 `OwnerPlatformId`，设置 DSH_OWNER_PLATFORM_ID；可选 AssistantRoot 保留原值，未配置则清空该子进程环境项。设置 ASTRBOT_ROOT 和工作目录为所选实例，执行 `venv\Scripts\astrbot.exe run`。
- Console：要求 PATH 中的 node.exe、实例内 `dsh-console/server.js`，以及当前 Windows 账号可解密的 `deployment-config/console-credential.clixml`。只向子进程环境传 DSH_CONSOLE_TOKEN，令牌至少 32 字符且不含空白/冒号；HOST 固定 127.0.0.1。DSH_RUNTIME_ROOT 将 Console 的数据来源绑定到同一个实例；已有认证和跨来源保护保留。
- 两者沿用 UTF-8 Python 输出和实例 venv/bin PATH。配置及凭据不会进入 Git、命令行或新增观察元数据；缺失、损坏、解密失败会明确报错，不以空认证启动。

生产框架/插件/Console 中既有部署参数仍须按原发布流程保留。指定另一 RuntimeRoot 不会替维护者填充这些源码中的部署常量；新实例需先正确配置。新启动器不会初始化数据、迁移聊天或执行部署。

## 防重复、就绪和生命周期

同实例使用 `.launcher/start.lock` 文件排他锁，串行处理并发双击。只有 worker PID、启动时间、可执行路径、随机 worker 身份和实例根目录都匹配，且监听端口属于该 worker 的真实后代，才报告 reuse。后代的创建时间也要晚于其父进程，避免把 PID 复用留下的旧子进程当成本次服务。

失效 PID 不会阻止新启动；PID 被复用、端口被外部程序占用，或原来的未纳管 Bot 正在运行时，会返回冲突，不按进程名结束 Python/Node，也不把端口存在当作本实例成功。

输出区分 created（worker 已创建）和 ready（已核验所属监听）。ready 是本机监听就绪，**不证明插件加载、QQ 连接或真实消息已通过**。Bot/Console 分别报告；Console 失败时，已经 ready 的 Bot 保留，整体返回非零。

worker 由 Windows 隐藏后台启动，应用由 worker 监管。每个 worker 建立独立 Job Object，worker 异常退出或启动超时清理时，只结束自身拥有的子进程。关闭启动入口不结束 worker；没有无限重启、Windows 服务、计划任务或开机自启。本轮测试也检查 worker 不在测试终端的父 Job 进程列表中，不能只凭 detached 参数推断独立性。注销、系统关机和组织策略仍可终止进程，不能承诺跨登录会话存活。

## 日志与退出观察

每次启动使用新随机编号，保留历史文件，不自动轮转或删除：

- `<RuntimeRoot>\logs\launcher\Bot-<id>-stdout.log`、stderr.log；Console 同理。日志会及时刷新，可边运行边读取。应用自身输出可能含运行内容，应按原实例数据的隐私边界保管。
- `<RuntimeRoot>\.launcher\Bot.json`、Console.json：当前 worker 身份和端口；不能手工伪造/复用其他进程 PID。
- `<RuntimeRoot>\.launcher\<id>.json`：必要的 UTC 时间、组件、PID、阶段及退出码。正常/非零退出记录 exited；启动监管失败记录 worker-failed。被强杀或关机时可能无法写入终态，必须保留“原因/退出码未知”，不能把上一条 running 当成仍在运行。

已观察到的子进程业务错误保留准确退出码（例如 23），包括 worker 提前退出而尚未取得身份的路径；缺配置、冲突、超时或不能确定的失败返回 1 并给出日志位置。只在执行前选择一次解释器，业务错误不会触发另换解释器重试。unknown 退出不自动重启。不要将旧生产根目录 `astrbot-run.log` 的历史内容当作这套启动器的新日志。

## 后续获准安装与回退

本轮未执行安装。获准后，将下列文件成套放到运行根目录（也可保留在同一个维护工具目录，显式指定 RuntimeRoot）：

| 源文件 | 运行目录建议 |
| --- | --- |
| scripts/start-bot.cmd | start-bot.cmd |
| scripts/start-bot.ps1 | start-bot.ps1 |
| scripts/launcher-process.cs | launcher-process.cs，与 PS1 同目录 |
| 生产原 run-astrbot.cmd、start-astrbot-launcher.cmd | 获准后备份移出运行根目录；不再安装兼容入口 |

Console 的 DSH_RUNTIME_ROOT 支持需与此次 server.js 配套发布；插件修复也须配套整套模块，按[补修记录](../reviews/2026-10-24-real-qq-repair.md)及既有发布流程保留部署常量。不要复制配置模板覆盖真实 runtime.json/凭据，也不要把受保护启动脚本及配置复制回 Git。

首次接管时，如果已有旧方式启动的服务，入口会提示端口冲突。由维护者另行安排确认、停止旧实例再切换；本轮不会自动接管或停止它。回退时先确认确切 worker 身份并按获准维护流程停止该 worker/子进程，恢复同套旧源码和入口；保留日志和新数据，不覆盖聊天、记忆、媒体或备份。旧受保护启动方式保留作回退参考。

## 离线证据

命令：`D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_repair_launcher.py`。

测试使用临时中文/空格路径、复制到临时目录的 Python 可执行文件作为 astrbot.exe、合成 run 文件、随机本机端口及有限生命周期 Node 替身；没有导入生产插件或启动真实 Bot。覆盖 PS1 默认 Bot 无 Node、cmd 默认双组件及缺 Console 失败、临时 DPAPI 凭据、并发冷启动、重复启动、失效 PID、启动时间不符、端口冲突、非零退出、超时清理、UTF-8 中文配置与日志、真实 cmd 入口的两种解释器选择及父 Job 独立性。解释器版本与最终结果见补修记录；不能据此宣称真实 QQ 已验收。
