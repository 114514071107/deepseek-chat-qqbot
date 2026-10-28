# 2026-10-28 W02 / D03 权限方案及 I05 日志调查

状态：源码与临时目录验证完成；**生产 ACL 未 Apply，D03 本机隔离尚未验收**。I05 已证明 PowerShell 7 临时 worker 的显式输出路由和正常退出刷新；没有复现日志丢失。PowerShell 5.1 在脚本执行前被拒，保留环境阻断。

开发基线 `dev / 73080c8550ffe5f31c9d41b4880e2bb10ba4895e`。与主修复对话共享目录，仅修改本单脚本、专属测试与本文/专属证据；未纳入原评审文件、未提交、未 push、未 PR、未合并 main。最终本地提交和配套发布由主记录给出。没有改生产配置、凭据、聊天、身份、图库、数据库、执行策略或依赖。

本单按已有 systematic-debugging / test-driven-development 的失败复现方法、python-testing-patterns 的临时夹具和实际行为断言、security-best-practices 的最小授权边界，以及 python-resource-management 的句柄/子进程清理和 verification-before-completion 执行。已安装 skill 直接读取使用，安装数为 0；原生 Windows ACL 没有相应 Web 框架安全参考，不套 Express/React 规则。

## 当前证据和账号

开始检查时，本实例端口无服务，CIM 没有可核对归属于运行根的 Bot/Console，因此不能凭旧心跳声称已经确认服务账号。当前维护账号 SID 可读取，私有方案以当前维护 SID 和 SYSTEM 为授权主体；不在 Git 中记录其原值。正式 Apply 前必须结合新服务进程 OwnerSid 再核实，若不同须先重做目标 DACL。主发布记录应补实际服务账号与维护账号相同与否的布尔结果。

真实 DACL 元数据重新检查：

| 精确对象或对象集合 | 当前状态 | 提案变化 |
| --- | --- | --- |
| `D:\dsbot` | 从 `D:\` 继承 Users / Authenticated Users FullControl，含子项删除能力 | 根和本实例逐对象取消继承，维护主体和 SYSTEM FullControl；目录 OI/CI，覆盖新临时文件 |
| `data`、`data\cmd_config.json`、`data\plugins`、`data\plugins\astrbot_plugin_dsh_soul` 及其代码 | 同样继承广泛 FullControl | 只收紧 DACL，不读/写配置正文；覆盖原子替换父目录 |
| `dsh-console`、根启动器/CS/PS1/cmd、`.launcher`、`logs\launcher` 及日志文件 | 当前均可经实例父目录获得广泛访问；不能只改 `main.py` | 同版代码、控制记录和父目录一起保护 |
| `astrbot-run.log`、`astrbot-stderr.log`、`console-run.log`、`console-stderr.log` | 广泛继承权限 | 维护主体仍能创建、追加日志；其他标准主体无读写 |
| `deployment-backups` | 本轮额外核实仍有广泛继承权限 | 历史部署材料也纳入实例范围；不把它用作本轮私有 ACL 备份位置 |
| `dsh_data`、`deployment-config` | 原目录已保护，主体为维护账号和 SYSTEM | 保留正文、所有者、SACL；目标 DACL 仍限制同一维护/服务主体，实际差异逐对象见私有记录 |
| `D:\` 驱动器根 | Users / Authenticated Users 当前在根本身有 FullControl；仅保护 `D:\dsbot` 仍不能证明整个实例不可被父目录删除/更名替换 | **单独待批的上级边界**：宽组在驱动器根直接权限收紧为 ReadAndExecute；原对子目录的 FullControl 作为 InheritOnly 保留，维护主体在根保留 FullControl。此项会影响其他标准账号在 `D:\` 新建/删除根项，不能顺带执行 |

完整枚举结果来自本轮 Inspect，不是硬编码产品常量：当时实例共 46,376 个对象（含根），其中 35,508 个含 Everyone / Users / Authenticated Users Allow ACE；重解析点为 0。此计数是权限盘点，不是聊天/人物数，也不等于所有宽 ACE 都有相同有效权限。`venv`、历史备份等也在完整实例方案中，不能把范围伪称为只改一份配置。

因驱动器根的替换边界尚待具体批准，**不建议只 Apply 一个叶文件或旧脚本默认 data 范围后声称 D03 已修复**。本次没有修改 `D:\` 或本实例任何目标的权限。

## 原 DACL、目标差异与回退

私有元数据备份：`C:\Users\Rocket\.codex\local-backups\20261028-dsh-acl-review`。

- `acl-rollback.json`：本轮完整精确路径清单、每对象原 SDDL 和目标 Access/DACL SDDL、实例根与时间；不含业务正文。含真实 Windows SID 和运行文件名，只保留本机，不入 Git。
- `ancestor-dacl.json`：`D:\` 原 SDDL 和上述上级提案目标 DACL，状态为 proposal only；没有应用命令自动执行它。
- 备份目录已取消继承，仅维护主体和 SYSTEM FullControl，检查通过。创建/收紧的是新备份目录，不是生产对象。
- 备份生成后再核 `D:\dsbot`、data、主配置、插件父目录/main、Console、logs、.launcher、业务/凭据/备份/venv 根及四份旧日志，共 18 个指定对象，原 SDDL 均仍与备份一致。未用这 18 项冒充 46,376 项逐个现状不变证明。

先审阅脚本，确认 Plan 有写备份副作用后，才执行显式的本机元数据备份：

```powershell
pwsh.exe -NoProfile -NonInteractive -File scripts/protect-config-acl.ps1 `
  -RuntimeRoot D:\dsbot `
  -BackupDirectory C:\Users\Rocket\.codex\local-backups\20261028-dsh-acl-review `
  -Mode Plan -RelativeTargets '.'
```

命令退出 0，只写私有备份；**未执行生产 Apply/Restore**。清单可能随后因部署、新日志或业务活动失效。获得具体批准后应在受控变更窗口刷新到一个新的备份目录，核服务 SID，审阅目录成员和原 DACL 无漂移，再按批准的完整范围实施；不能重复用旧 snapshot 强行绕过检查。

逐对象回退使用同一清单和 `-Mode Restore -RelativeTargets '.'`，先父后子恢复原 DACL 及继承，仅写 Access；不改变 owner、SACL、文件内容或恢复旧业务快照。先停止本次 ACL 操作并核已改变对象；若中途失败，保留记录，逐对象处理失败后继续回退。对象丢失、重解析或不属于清单时拒绝，不猜测其他路径。新产生的业务内容继续保留；回退不会删除新增文件。上级 `D:\` 如未来获准修改，须另按 `ancestor-dacl.json` 仅还原原 Access，不能用实例脚本指向驱动器根。

此回退已在临时实例逐对象比较 ACE 身份/类型/权限/继承/传播和保护标志，并确认原子写后的新正文仍保留。生产回退未试验；生产执行后还须实际服务读取、原子保存和新文件继承验证。

## 脚本改动与离线红绿证据

位置：`scripts/protect-config-acl.ps1:4` 默认模式改为真正只读 Inspect；`:25` 支持显式实例相对目标并枚举目录后代；`:32` 拒绝重解析路径；`:45` 限制备份不能覆盖目标或其祖先/子树；`:50` Inspect 不创建目录/记录也不 SetAccessControl；`:64` 逐对象只恢复 DACL；`:99` Apply 在首次写生产 DACL前拒绝目录成员或原 DACL 漂移。Plan 的写备份行为在脚本和提示中明确。默认目标仍是历史 data/cmd_config 范围；完整实例需显式 `-RelativeTargets '.'`，不暗中扩大默认 Apply 范围。

旧脚本把目录继承传播影响排除在精确回退记录之外，且计划模式会先创建并收紧备份目录。本轮保留显式 Plan 的旧调用兼容，提供无写 Inspect，并记录目录内所有受影响对象。原 SDDL 保持完整以兼容历史回退检查，实际 SetAccessControl 仍只写 Access，不要求 SeSecurityPrivilege。

`tests/test_repair_runtime_acl.py:18` 的受限令牌夹具先证明修前可读写，然后实际 Apply 后应拒绝。Python mode-0700 临时根会在祖先就拒绝受限令牌，早期夹具错误单独定位后改用已核路径的继承型合成临时根；没有把“从来不能访问”的 token 当作修复有效证据。

| 检查 | 本轮结果 / 退出码 | 证据 |
| --- | --- | --- |
| 将测试指向 `73080c8` 原脚本的临时副本 | 新增三项失败，exit 1：缺 Inspect / RelativeTargets；修前受限令牌的允许断言已通过 | `acl-red.txt` |
| 新增三项及原两项 ACL 回归 | 5 项通过，exit 0 | `acl-green.txt` |
| 真实 Windows restricted token | secret、code、Console、log 读/写由 `[0,0]` 变为拒绝 `[5,5]`；实例目录新增/删除子项也被拒绝 | 新增完整实例测试 |
| 当前服务主体（测试运行主体） | 正常读取；临时文件写入+原子替换成功；Restore 后正文仍为新值 | 同上 |
| 无写 Inspect | 无备份目录/记录，原 DACL 不变；对象数从合成目录动态枚举 | 新增 Inspect 测试 |
| 新对象使已审阅清单漂移 | Apply 在变更任何目标 DACL 前失败；根 DACL 不变 | 新增 drift 测试 |
| 源码差异空白检查 | exit 0 | 本单四份代码文件 `git diff --check` |

命令、退出码见 [commands.json](evidence/2026-10-28-independent-repair-w02/commands.json)，当前脱敏库存见 [acl-inventory.json](evidence/2026-10-28-independent-repair-w02/acl-inventory.json)。专项命令：

```powershell
D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p '*acl.py' -v
```

主全集期间曾捕捉到“保存为只有 D 部分的 SDDL、旧回归仍比较含 O/G 的 SDDL”不兼容；本单已恢复原 SDDL 的完整备份，未放宽旧断言，上述 5 项定向复核通过。不能把全集当时的失败输出删掉或改成当时通过。

## I05 worker 输出调查

重复入口：[tests/probe_worker_logs.py:16](../../tests/probe_worker_logs.py)。它在独立临时实例复制现有 Python 可执行文件作为合成 Bot，使用真实 `start-bot.ps1 -InternalWorker` 和真实 `DshLauncherProcess.Child`。输出只有合成标记，不连 QQ 或模型，不监听生产端口、不重启生产。Popen 持有确切 worker 进程句柄；结束关闭其 Job，只清理经绝对路径/前缀确认的临时目录。

命令 `D:\dsbot\venv\Scripts\python.exe -B tests/probe_worker_logs.py` 调查程序 exit 0；**不表示两种 Shell 均通过**。完整结果见 [worker-logs.txt](evidence/2026-10-28-independent-repair-w02/worker-logs.txt)：

- PowerShell 7：live 时 stdout 和 stderr 各自已有 flush 标记，stdout 的未 flush 标记在退出后出现。worker exit=7，nonce observation phase=exited / exit_code=7；进程退出，临时资源清理。证明句柄路由和退出刷新在该路径有效，应用缓冲可以解释“当前零字节”的一种情况，**不能据此推断生产零字节的唯一原因**。
- PowerShell 5.1：exit=1，原 stderr 为 AuthorizationManager / UnauthorizedAccess，尚未进入脚本，未创建 observation 或应用日志；没有把缺少日志的二次异常覆盖第一原因。环境拒绝不算 worker 路由测试通过，也不因而重写启动内核或修改系统策略。

I05 结论为“未复现输出丢失；7 的显式输出路径已证，5.1 环境阻断；生产旧日志零字节的具体原因仍不能确定”。没有改 CS/worker 内核。尚未验证客户端实际收发。

## 最少待决定事项

1. 是否批准完整实例私有 DACL 方案，及 `D:\` 根仅直接权限收紧的上级方案；具体对象和原/目标 SDDL 已在私有备份。若不批准上级变更，另选有受保护父目录的运行位置属于后续部署/数据路径变更，不能本轮偷偷迁移；保留本机替换风险。
2. Apply 前确认实际服务账号；若与维护账号不同，先更新 ServiceSids 和新清单并复核。审批后才进行生产 Apply、实际标准主体与服务账号验证。

本单不要求 QQ/付费调用来证明 ACL；原聊天和数据库没有读取内容或改写。没有把 D03 标为生产已修复，也没有把 I05 标为日志缺陷已修复。
