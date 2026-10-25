# 2026-10-26 控制台、启动入口、旧档及 Bot 消息归属补修

状态：四项源码与离线回归已完成，随本记录固定本地待评审版本；外部独立评审和用户验收待进行。开发 dev 基线 `0568dac49d14bfa4264f51b2fad53dba5f70a27f`，开工工作区干净；该基线已按用户随后明确指令推送，后续四项修改不顺延推送授权。[计划](../superpowers/plans/2026-10-26-console-lifecycle-repairs.md)。

原 `0118181` 的独立验收和 B 原阻断关闭结论保留，原测试数字仅为历史基线。当前工作单新增第 4 项消息生命周期与会话/任务归属，四项一并实施、离线验证并本地提交；不部署、重启、迁移真实数据或操作 QQ。

## 证据与执行账本

- 已核对工作单 AGENTS/TASKS/最新交接、开发 DEVELOPMENT 和实际 Git 状态；目标及上级无附加 AGENTS。已读取 debugging/TDD/verification、计划及浏览器技能。采用原 dev 顺序实施；不拆分并行修改共享工作树。
- 计划执行裁定：用户已明确直接实施并本地提交，不再就计划重复索取许可；在本文件持久记录每项失败、修复与验证，最终固定整体可评审提交。
- 当前源码线索（尚待失败回归）：用户页每次刷新先将整个 view 替换为短加载卡，随后详情再异步加载；原 innerHTML 拦截只保存瞬间 scrollY 和第一个 pre，短 DOM 已使浏览器钳制滚动。启动有三个面向用户的 cmd；核心外层 catch 将真实子退出一律转换为 1。旧档分类仅看 scope 表，不使用逐条 source；Bot 历史也读取可变 scope，群投影排除没有 user-request 的助手消息，且自消息没有入站保护。以上须以实际复现进一步确认，不提前写成修复结论。

### 修改前四项失败（实际执行）

- `node tests/console_refresh_browser.cjs`：本机隔离 Edge、真实 5 秒定时请求，页面中部 **7366→0px**，断言失败；证据 `local/refresh-regression/first-timer.{json,png}`、`local/20261026-refresh-red.txt`。未手调刷新函数或修改时钟。
- `python -B -m unittest discover -s tests -p test_repair_launcher.py -k child_exit_code -v`：真实 pwsh 7.6.5 与 Windows PowerShell 5.1.26100.9711 均报告替身子进程 exit code 23，但入口实际返回 **1**；两分支失败。最初探针未提供替身 Python DLL 所需 PATH，已纠正探针后才取得业务失败，未误作产品根因。
- `node --test console/tests/repair-legacy-scenes.test.js`：**0/3**，完整逐条 source 的旧私聊/群聊仍为 legacy；混合文件预期 2 场景、实际 0 或 1；同一 scope 表掩盖了其他记录来源。原始裸 sender 键由原 `4e77efb` 实现的 `get_sender_id()` 生成，历史 role/text/ts 没有场景，不能从末次 UMO 恢复。
- `python -B -m unittest discover -s tests -p test_repair_outbound_ownership.py -v`：**0/4**，发送完成后新入站覆盖来源、同回执重复保存、空后台 token 覆盖显式原任务请求、Bot 自消息可新建来源。原任务在本项目中是 Runtime 请求 token 与后台 job（非独立产品任务表）；会话是原 scope，人物是只读管理聚合。后端群历史额外要求 user request，因此真实主动群发送即使 accepted 也被排除。失败日志在 `local/20261026-{legacy,outbound,launcher}-red.txt`。

至此四项各自失败证据已取得，开始最小修复。

## 四项根因及最终规则

### 自动刷新阅读位置

触发链为 5 秒定时器 → refreshNow → 工作台 render → 短加载卡替换整个 view → 浏览器将超出新高度的 scrollY 钳到 0 → 异步重建详情。原拦截器只恢复单次赋值时的 scrollY 和第一个 pre；详情自身重建及相同外层 HTML 跳过重绘时都没有保护。另实测记忆 pre **900→0**，日志独立定时器直接执行 scrollTop=scrollHeight，**900→5042**，是两条独立触发链。

自动刷新现在先取得列表、开关和选中场景历史，在真正提交 DOM 的瞬间读取最新位置，以稳定消息/来源键及可存活的邻居保住可见内容；每个有独立滚动条的区域单独处理。短暂维持原高度，填完详情后恢复位置和必要焦点，避免浏览器在中间空 DOM 上钳制。手动场景/人物导航保持原有加载反馈和可切换控件，旧请求由 epoch/AbortController 作废，不机械恢复到前一目标。

刷新等待期间输入、展开编辑或打开确认均优先于更新；未提交文本即使失焦也受保护。请求失败只在保留的页面显示可重试状态，不销毁草稿或确认上下文。列表 revision、人物与场景状态也延迟到成功提交时才替换。记忆加载/删除/导航有独立递增版本，迟到旧响应不能恢复已删条目或旧删除下标；日志初次进入可定位末尾，后续刷新保留行锚点/位置。周期仍为 5000ms，数据正常更新，没有以关刷新或延长周期修复。

### 唯一 Bot cmd 与 PowerShell

唯一用户 Bot cmd：`D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.cmd`。删除仓库 `scripts/run-astrbot.cmd` 和 `scripts/start-astrbot-launcher.cmd`；它们原先只转交同一入口，属于重复入口。保留 `start-bot.ps1` 核心及 `launcher-process.cs` 内部生命周期辅助；保留 Console 的独立 cmd/vbs 和受保护生产 start-runtime.ps1。Console 调用、README、DEVELOPMENT、当前启动说明及项目交接已更新；历史评审/发布中旧名称仍为当时事实。

cmd 在执行前依次检查 PATH 的 pwsh、标准 PowerShell 7 安装位置，再使用系统 powershell.exe；不安装环境、不因业务失败改解释器重跑。修复核心将子退出码一律变成 1 的 catch，正常观察及尚未取得身份的提前退出均返回真实非零码；尚未就绪而正常退出、配置/冲突/超时/身份未知仍作为启动失败处理。身份读取须取得完整 exe，有限等待不放宽 nonce/root/PID/ticks/命令及监听进程族验证。已有 venv、运行根、Unicode/空格参数、锁、Job Object、退出观察和 Console 显式启用保留。

### 旧档场景与人物身份分别判断

| 历史证据类别 | 场景规则 / 是否可从现有历史恢复 | 人物规则与缺口 |
| --- | --- | --- |
| 每条完整 source | 按该条 platform/instance/bot/private/group/sender 分区，可恢复私聊或具体群 | 场景识别不等于跨来源同人；仍需身份域证明或人工决定 |
| source 缺失，但原 scope 与完整 v2 生成键一致 | 重算 p2/c2 哈希并逐项匹配后只读补场景来源；不会把 scope 中最新 message_id 写成旧消息触发号 | 仅凭前缀无效，p2 也用于资料/账本；不能据共享 memory_key 合并人 |
| assistant 缺 source，有同文件唯一 request_id 对应 user.source | 派生该条来源；原消息/字段不改，注明 source_projection 依据 | 仅恢复该原请求，不猜其他请求；accepted、unknown、无回执分开 |
| 具有相同 attempt/message_id、状态一致且 source/Target 自洽的冻结回执 | 只读恢复旧助手记录及原任务/job，精确匹配唯一已有来源；不伪造旧消息标识 | 无入站/既有来源时只列 Bot 出站旧档，不新造用户；冲突原字段保留 |
| 同文件混合 source / 部分缺失 | 每条分区，未知部分保留；稳定派生键；同键两份历史保留不同记录，仅对有同一稳定 id 且内容完全相同的跨文件副本去重；文件内无标识重复记录保留 | 文件人工关系不把全部记录强归一个场景；无法唯一解析的旧引用保留并提示核对 |
| 原 get_sender_id 裸键、role/text/ts 或最后 UMO | 原生成规则不足以区分私聊/群，不能从末次路由反推 | 缺逐条平台/实例/群/私聊证据，需原消息元数据；昵称、正文、时间不能补证 |
| 可信 QQ author 成对映射 / OneBot 已核帐号 | 原场景继续各自独立 | 应用/实例/平台/身份域一致才自动同人；相同字符串跨域不合并 |
| 稀疏后续观察、重复/晚到/冲突 | 不倒退已记录观察或改写场景 | 保留旧可靠 identity 及原观察时间，冲突双方留存，人工解除/否认不被旧证据合回 |

派生来源只供查看与人物管理关联；没有原已核管理来源的投影不能选择为开关、积分、删除或通知目标。人物聚合仍不被 Bot 权限、发送路由、积分、模型上下文读取。未移动原 scopes/history/账本/记忆；纯读取可重复且不写迁移文件。新派生人工引用仍走既有 revision/锁/v2 映射；旧读者不一定能理解它，回退时不得用旧映射覆盖新人工决定。

### Bot 消息、任务和会话

本项目的“人物”是管理展示聚合，“来源/会话”是原 Scope；实际执行任务是 Runtime 的 request token 与后台 JobBudget，不另造产品任务表。AstrBot 的框架 conversation 仍由原隔离 UMO 和原 cid 更新，未另建 Bot 用户会话。

已追踪普通计划/分段、语音/图片/附件、工具结果、管理员主动消息、主动问候及已有提醒/后台投递链。`_send` 在任何 await 之前冻结 Scope、真实 Target、适用 request、job、模式和运行世代，经 contextvars 传入投递回执；普通回复保留触发 message_id，主动发送不把旧被动凭据冒充触发。后台来源在排队/装饰器绑定时捕获，避免最后路由、跨群或跨私聊串线。原用户请求为空是有意义的信息，不能被后来任务补成“原任务”；attempt_id 只作投递关联号。没有原用户请求的主动消息明确显示这一事实，实际后台 job 存在才显示 job。

已接受历史保持 assistant，使用回执冻结的来源/关联；attempt_id 或同目标平台 message_id 重复不追加滚动、群或归档副本。回执更新不改变原请求归属。脱离原协程的晚到保存仍检查原运行世代，不能恢复已撤销历史；只允许补充已存在回执的持久化元数据，不能因此重建已删除回执层。进程重启不重放旧内存任务或自动重发；持久 JSON 仍能只读追踪来源/请求/job，旧世代回调不能在新实例写回。

平台 sender=self_id 或适配器 message_sent 在绑定新 Scope/观察身份之前拒绝，避免 Bot 被当 user、生成新来源或再次回复。群历史接受核验过真实目标的主动投递，不再一律因没有 user request 而隐藏；缺目标、角色或投递证明的旧助手记录不强行挂任务。只有 assistant、无入站/原 scope 的旧记录，先按完整相同来源寻找唯一已有会话；否则放入可读取的“仅 Bot 出站旧档”，不计确认用户、待确认来源或会话来源。unknown/failed 回执单列，accepted 只代表接口接受；历史保存和客户端收到仍分别核验。

## 复核补修与统计解释

一次只读新上下文复核（按 requesting-code-review 技能）指出 7 项 Important、无 Critical，并指出脱离协程的回执持久化元数据未更新。已在同轮补齐：成功人工决定后立即重绘、来源推导落入可读投影、记忆删除竞态、失败刷新保护、权威空 request、worker 提前退出码、仅助手旧档统计及晚到元数据。分别增加实际失败或故障注入回归后验证，不将最初复核意见写成最终无条件通过；外部独立评审和用户验收仍待进行。

中间全集曾因新增 source 参与 token 相等比较而停在反馈等待；只停止已核命令的本轮 unittest 进程，source 改为不参与权限/请求 token 相等性，原生命周期 5/5 恢复。另一次 244 项中 4 个语音回退子场景发现替身每次返回同一 accepted-text 平台 ID，与新增真实幂等规则冲突；替身改为每次发送不同 ID，专门重复回执测试仍要求相同平台 ID 只入库一次。浏览器还实际抓到独立 pre、日志强制到底、成功保存重绘和迟到记忆删除问题，均记录在 local 红/绿日志；未放宽原来源/权限/原消息断言。

原 workbench 合成夹具故意在 g1 文件混入一条带完整 OTHER-MEMBER source 的用户记录。现在它独立投影为待确认来源，相关测试统计由 5→6 个入口/来源，人工关联三来源后的入口由 3→4；原 g1 人物仍不能读到其他成员内容，新增来源不能作管理目标。这个增加来自逐条证据恢复，不是多算 Bot。仅助手样本反向证明 0 确认/0 待确认/0 会话来源，原消息可单独读取。实际生产本轮未盘点或改数据，不把历史 1/6/4/8 保持或变化当作正确性标准。

## 本轮实际验证

工作目录为开发仓库；Python 使用 `D:\dsbot\venv\Scripts\python.exe -B`，全部数据/发送/进程均为隔离替身。Node 使用既有 bundled Playwright（NODE_PATH 指向本机既有依赖）及已安装 Edge，不安装依赖、不接生产服务。

| 命令 | 实际结果 |
| --- | --- |
| `-m unittest discover -s tests -p 'test_repair_*.py' -v` | **247/247，202.319 秒，退出 0**；`local/20261026-python-verified.txt` |
| `-m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | **2/2，退出 0** |
| `node --test console/tests/repair-*.test.js` | **57/57，1307.0172ms，失败/跳过 0** |
| 真实 pwsh 7.6.5 / Windows PowerShell 5.1.26100.9711 | 全集实际执行双矩阵；4 个 launcher 测试覆盖核心生命周期、子退出 23、提前退出身份故障、cmd 一次选择/含空格 Unicode 和 & 参数/退出 37、不换解释器重试。既有并发、重复、超时、错 PID/ticks、日志、Console 凭据及 Job 归属断言保留 |
| 新增 `console_refresh_browser.cjs` | **15 项，退出 0、JS 错误 0**；中部首轮 **7903→7903px**，两轮及其余场景逐项通过 |
| 新增 `identity_lifecycle_browser.cjs` / `refresh_races_browser.cjs` | **8 / 3 项，均退出 0**，含旧档、回执恢复、仅 Bot 旧档、成功人工保存即时重绘与迟到删除/失败确认竞态 |
| 原 `workbench_browser.cjs` / `user_auto_browser.cjs` / `identity_triage_browser.cjs` | **17 / 11 / 15 项，均退出 0、JS 错误 0**；旧错误清空断言改为同一人物刷新错误保留阅读，切换人物/场景仍清空旧内容；人工保存等待条件排除尚未提交前的搜索提示 |

六集合实际 **69 项**。各集合最新成功结果汇总于 `local/20261026-browser-verified-summary.json`，可评审副本为 `docs/reviews/evidence/2026-10-26-lifecycle/browser.json`（其中 workbench 针对新错误保留行为及保存等待条件单独补跑退出 0；较早失败集合退出码保留在 local/20261026-browser-exits.json），日志 `local/20261026-verified-*.txt`；所有证据都来自本轮真实定时器，没有手动调用 refreshNow 或修改时钟。原截图文件不覆盖，原集合通过环境变量输出到 local/20261026-*。定时脚本包含中部/底部至少两轮、无变化/新增/减少、请求中主动滚动、嵌套列表/详情、390px、焦点/草稿、筛选/场景、确认取消、主动群消息/任务和 unknown 回执。既有集合回归人工关联/取消/解除/否认/恢复、并发与 stale revision、目标清空、私群历史/记忆/积分/管理权限边界。

## 尚未取得的平台/生产证据

- 当前任务没有部署、重启、真实数据迁移、QQ 消息、付费模型或平台权限变更。旧验收生产结论照旧，本轮不是其重新验收。
- QQ 官方群/私聊需要实际平台 author 映射及应用/实例证据；合成可靠映射、多群/改名/晚到/冲突通过不等于生产已提供映射，更不等于取得全局 QQ 昵称。缺字段的旧裸键无法从文本或最后 UMO 补证。
- self_id/message_sent 自消息保护、真实主动投递、媒体/附件及延迟回调是源码与离线证据，实际 QQ 客户端回流变体、平台到达及恢复需获准后逐一实测。当前不声称真实 Bot 已不再出现任何孤立记录。
- F09 闹钟及 TTS 部署继续暂缓；未启用、改造或验收旧 `_fire_alarm` 直发分支。已有 `_send_reminder`、主动问候和 Runtime 后台任务属于本次检查范围，不能据此扩大成所有暂缓机制已获准或通过。OneBot 资料证据测试不表示增加了新的适配器发送能力。
- 仅出站或冲突旧档没有可靠原始目标/消息/任务时继续保留、说明缺口，不按文本/时间推断。UI/API 提供只读预览，未写持久历史迁移；若以后要修复真实历史，须先逐记录证明、预览差异、停写备份并校验哈希、按稳定消息/目标键幂等更新，冲突跳过，提供反向补丁和独立授权。不得用旧全量快照覆盖上线后新消息。

## 待授权生产同步、旧入口清理和回退

1. 先确认待部署本地 commit、原运行版本及精确 worker 身份，在受保护 deployment-backups 新目录备份本次源码、三份启动辅助、原两个旧 cmd、快捷方式/调用配置及停写数据；保存清单与 SHA256。停止/启动 Bot 与 Console 分别按对应授权执行，不能只热重载或按进程名称批量停止。
2. 插件成套同步本次五份变化：`main.py`、`qq_delivery.py`、`session_scope.py`、`task_runtime.py`、`user_profiles.py`；其余既有依赖模块一并核清单。Console 同步六份：`server.js`、`people-sources.js`、`user-workbench.js`、`public/index.html`、`public/user-workbench.js`、新增 `public/reading-state.js`。保留生产常量/凭据的既有部署替换，不能拿模板覆盖真实配置。
3. 将源码 `scripts/start-bot.cmd`、`scripts/start-bot.ps1`、`scripts/launcher-process.cs` 同目录安装到 `D:\dsbot`；Console server 的新调用指向 `D:\dsbot\start-bot.cmd -RuntimeRoot D:\dsbot`，含空格实例同样显式传根目录。更新桌面快捷方式及外部调用方。
4. 已只读核实生产仍有 `D:\dsbot\run-astrbot.cmd` 和 `D:\dsbot\start-astrbot-launcher.cmd`，本轮没有删除。确认新入口及全部调用方可用后，另获清理授权，把这两份旧文件移到受保护备份而非继续作为用户入口。保留 Console 独立 `D:\dsbot\dsh-console\start-dsh-console.cmd`、其 vbs，以及内部 `deployment-config/start-runtime.ps1`；不清理 venv 或真实数据。
5. 通过唯一 cmd 默认只启动 Bot；需要 Console 时用显式 `-WithConsole` 或既有独立入口。核对新 PID/ticks/exe/nonce、原进程退出、Job/监听归属、插件加载、心跳及 API/页面 `20261026-lifecycle-1` 同版，再进行管理及获准的群/私聊实测。启动器的 owned-listener ready 不能替代 QQ 或插件业务就绪。
6. 回退前只停止已核本实例 worker，成套恢复所备份旧源码/启动文件、旧调用方/快捷方式，再用旧入口启动核对。回退不恢复旧聊天/积分/资料全量数据；新增 provenance/identity 证据为兼容附加字段。若上线后新增了指向派生来源的人工决定，旧工作台可能无法解析：保留新映射、单独备份并标明未解析引用，优先前向修正；不得用部署前映射覆盖新决定。原始历史从未迁移，恢复旧读者即可撤销本轮只读派生视图。

## 收尾证据与交付状态

- 本轮 Python AST **64 份**、JS/CJS **21 份**及页面 **1 段**内嵌脚本语法检查通过；`git diff --check` 退出 0。双 PowerShell 实际执行矩阵同时覆盖语法和 C# 辅助编译。真实生产启动文件只核存在及安装关系，未执行或改写。
- 已实际查看本轮 390px 阅读与主动群消息截图；全部是脱敏合成夹具。评审证据目录 `docs/reviews/evidence/2026-10-26-lifecycle/` 保存 69 项清单、首轮滚动数值、静态结果及两张本轮截图，不覆盖原验收截图。测试/日志均为本轮，未把历史数量复制成当前结果。
- 原请求为空、晚到回执、历史缺 source、没有稳定消息 id 的重复文本分别测试。暂存审阅另发现全已知混合文件索引被误列纯资料，已补失败回归并分列 archive_indexes；不再让混合索引静默满足整文件人工确认。来源推导不补造触发消息号；跨文件只对稳定 id 与完全相同内容去重，无 id 的重复原记录保留，阅读锚点另按稳定 id/内容与出现次序派生，不能用作人物证据。
- 内部只读复核的 7 项 Important 及回执元数据问题已补修并以失败→通过和全集/浏览器回归验证；没有需要延期的 Minor。该结论不是用户独立验收，也不覆盖复核者未执行的真实 QQ、生产数据及运行环境分支。
- 最终敏感值与暂存审阅、本地提交 hash 由本机 TASKS/HANDOFF 的收尾记录确认；Git 版本为 dev 的本次提交，避免为把自身 hash 写入文档改写提交。上一轮已推送基线为 `0568dac49d14bfa4264f51b2fad53dba5f70a27f`，本轮新版本仅本地固定。
- 状态分开记录：代码/离线交付已完成；外部独立评审、用户验收待进行；本轮四项未推送、未创建 PR、未合并 main、未部署或重启、未迁移真实数据、未做真实 QQ/付费模型实测。生产后续按上方步骤及相应授权执行。
