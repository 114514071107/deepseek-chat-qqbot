# 真实 QQ 验收补修与一键启动

日期：2026-10-24（Asia/Shanghai）。状态：源码与离线验证交付，待独立评审及用户验收；不是生产部署或真实 QQ 验收结论。

基线：本地 `dev`，`ba22877`，开工工作区干净。读取工作单及真实验收记录，目标目录及父目录没有适用的额外 AGENTS.md。由当前对话顺序实施，不派生代理。不推送、合并 main、部署、重启生产、调用真实 QQ/模型、安装依赖或清理真实数据。

## 实施与验证顺序

- [x] RQ01：合成窗口复现更正丢失，修复预算选择与摘录连续性，断言模型输入及来源隔离。
- [x] RQ02/RQ03：可控时序复现迟到、重复和停止指令再注入；修复请求内反馈及历史状态，回归删除/发送交错。
- [x] RQ04/RQ07：只读调查已记录，退出原因未定；双解释器后台启动器以临时实例/替身验证。
- [x] RQ06：核对官方平台能力与可信引用边界；显式纯表情计划无文字发送及一次失败回退。
- [x] 完整 Python、余额、Node、语法与差异检查；更新 MODIFICATIONS 与交付文档。提交按文末流程固定评审版。

RQ05/TTS、F09 闹钟、自动清理、公开画像、真实并发/账单继续暂缓。离线通过不代表真实 QQ 验收通过。每阶段在本文追加失败证据、修复、测试、兼容和缺口。

## 已取得的失败证据与阶段结果

- RQ01：`test_repair_real_context.py` 修复前两项失败，直接在真实 inject 的最终 `req.contexts` 中检查 C04，以及连续压缩/滚动窗口。原实现把最近十二条排除出摘录池，又按预算裁掉其中的记录。修复后未容纳记录重入候选池，更正/撤销优先；按实际序列化内容计预算，长消息后半部的更正也可截取。v2 摘录拒绝沿用 v1 选择结果，按保留的可信原文重新生成；不迁移生产数据，不删除原档。预算无法保留全部更正时明确提示不能据旧值确定现行值。
- RQ02：三项生命周期回归中的“先发反馈与主答重复”和“反馈在主答之后完成”均在原实现失败。反馈改为请求内一次中性反馈，避免额外模型调用和未证实图片/工具结论；快速路径等候完成事件最多 0.8 秒，主回答不等待该拟人延迟。capture 关闭反馈，完成发送前收拢被取消的反馈任务；同请求已 accepted 的相同文字不重复发送。实际平台调用中的取消沿用 QQDelivery 的 unknown/accepted 语义，没有假装撤销平台请求。
- RQ03：原实现关闭后仅撤销任务，user 原文仍进入恢复后的 inject；新增回归先失败。新 user 行绑定 request_id/request_state，停止时标记 stopped，模型及框架投影排除该指令；已 accepted 的 assistant 保留。归档原话保留，追加无正文的请求状态审计。缺少字段的旧行继续作为历史，不猜测全部未配对 user 都已取消。未发送的生成片段不再作为下一轮接续指令注入。旧 finally 仍按请求及事件身份校验。
- RQ06：新回归先复现显式纯表情仍先发文字、任意 REFIDX 被放入平台载荷。增加工具 `only_sticker` 和独立协议行 `动作：仅表情 X`，成功只发图，明确媒体失败时一次文字回退，unknown 不补发。代码/引用中的动作字样仍受原文保护。
- 截至阶段检查：Context 相关 16 项通过；新增真实验收专项扩展到 11 项，通过。第一次完整修复集合 166 项中发现五个失败（其中两项为相同用例的不同状态）：空历史桶副作用、archive-only 的缓存保留约束，以及工具测试载入器未绑定新增辅助方法；已按实际约束修正，最终全集结果待追加。

## RQ04 只读调查

保留日志：Bot stdout 57,431 字节，最后可提取时间 09:25:26；stderr 96 字节，仅有 07:54:06 监听提示。Console stdout 49 字节、stderr 0 字节。四份日志均无 Traceback/ERROR/CRITICAL 或匹配到的关闭/信号记录。Application 1000/1001 事件在 2026-10-23 09:20—09:38（UTC+8）没有匹配记录。原日志未复制入 Git，未读取活跃 SQLite 或生产管理接口。

结论仍为**原因未定**。没有证据把图片、业务异常、宿主结束或外部停止中的任一种确认为根因；两个进程同时消失使宿主生命周期值得核验，但只是调查方向。新启动器将记录组件、UTC 时间、worker PID、阶段和退出码；正常/非零退出有观察文件，强制终止 worker 无法保证写出最后一条，后续只能标记进程消失，不能推断退出码。没有无限自动重启、自启项或服务安装。

## RQ06 平台能力依据

2026-10-24 读取腾讯官方 [bot-docs 发送消息文档](https://github.com/tencent-connect/bot-docs/blob/main/docs/develop/api-v2/server-inter/message/send-receive/send.md)：QQ 单聊和群聊均将 `message_reference` 标为暂未支持。频道接口是另一种场景，不能将其能力套用到本插件 v2 users/groups。

因此当前兼容方案是来源明确的文本摘录；不发送未经支持、来源未核验的原生引用参数。账本标记 `persistence.reference=unsupported`，不把普通发送 accepted 当作卡片成功。普通群回复及默认目标提及不改。未增加撤回猜测，检索无结果、缺标识与撤回保持不同语义；没有修改 QQ 后台权限。

## RQ07 启动器结果

入口 `scripts/start-bot.cmd`，同一核心 `scripts/start-bot.ps1`，Windows 进程/日志辅助 `scripts/launcher-process.cs`。旧两个 Bot cmd 入口转交新入口。使用、成套安装、配置、日志和回退详见[一键启动说明](../tooling/one-click-bot-startup.md)。默认 Bot 不要求 Node，Console 需显式 `-WithConsole`。

只读核对既有受保护启动器：Bot 使用 OwnerPlatformId/AssistantRoot 和 venv CLI 的 run，Console 使用当前账号 CLIXML 凭据、Node、127.0.0.1/7850。原脚本写死生产路径，新核心按明确 RuntimeRoot 实施同一环境与参数契约，不执行旧脚本的硬编码路径。Console 增加 DSH_RUNTIME_ROOT，并先用阻止外部磁盘读取的 Node 回归取得 500→200 证据；认证与跨来源保护保留。

实测版本：PowerShell **7.6.5**、Windows PowerShell **5.1.26100.9711**。同一脚本实际执行两套矩阵：中文/空格路径、任意 cwd、缺依赖/配置、默认 Bot 无 Node、并发冷启动只有一个 worker、重复复用、失效 PID、启动时间不符、外部端口冲突、启动超时、退出码 23、UTF-8 中文配置和运行中日志、临时 DPAPI 凭据及可选 Node 替身的独立结果。cmd 入口也在最小系统 PATH 与显式 pwsh PATH 中执行，覆盖 5.1 回退和 7 优先，不以语法检查代替运行。

当前测试账号没有管理员角色（IsInRole Administrator=false），没有提权或变更执行策略/ACL。测试宿主在带 KILL_ON_JOB_CLOSE 的 Windows Job 中；读取该 Job 的进程列表，确认两种解释器启动的 worker 均不在父 Job 中，且入口退出后所属监听仍可连通。worker 自己的 Job 在停止时清理其子进程。最终只读扫描没有本轮替身进程残留；没有结束真实 Bot/Console、AI 或整个登录会话来冒险验证。

开发中另实证并修正了运行中日志未及时刷新、退出观察替换/读取竞争，以及 PowerShell 向 .NET File.Replace 传 null 被绑定为空路径的问题。JSON 使用原子替换与允许替换的快照读取，null 由小型 C# 辅助传递。5.1 的合成凭据初始夹具还遭遇继承 PS7 模块路径导致 Security 模块自动加载失败；改为直接构造临时 SecureString，先核对可解密长度，再执行实际 Console 启动，未读取真实凭据。

## 收尾自查与补修

没有按工作单禁止的方式派生代理。本段为当前对话自查及失败回归记录，**独立评审与用户验收仍待进行**，不能称作独立验收通过。

自查补修三项，每项先取得失败再转绿：

1. 极小预算下，最早的更正不应压过较新的更正：`test_newest_correction_wins_excerpt_priority_when_neither_raw_row_fits`，调整更正组内优先级为从新到旧。
2. 总开关不能先撤销当前控制 epoch，再尝试保存其他请求的 stopped 状态：`test_global_shutdown_closes_active_history_before_revoking_control_context`，在无 await 的同步阶段先保存停止状态，再统一撤销。
3. 无文字、明确纯表情的计划不能先发独立 At/Reply 组件，也要保留媒体失败回退：`test_textless_explicit_sticker_plan_does_not_send_target_mention_as_extra_bubble`，统一计划规范化；普通图文和代码原文保护不变。

## 最终执行的验证

工作目录为开发仓库根目录。Python **3.12.15**，Node **22.20.0**，现有 AstrBot **4.29.1**；没有安装或升级依赖。

| 命令或检查 | 本轮实际结果 |
| --- | --- |
| `D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_repair_real_*.py'` | 14/14，2.604 秒，OK |
| `D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_repair_*.py'` | **175/175，175.733 秒，OK**；包含双解释器矩阵和既有真实 Context 构造回归 |
| `D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s plugin\astrbot_plugin_ds_balance -p test_balance.py` | **2/2，OK** |
| `node --test console/tests/repair-security.test.js console/tests/repair-state.test.js` | **13/13，0 失败** |
| plugin/tests Python AST | 48 文件通过，无生产插件初始化 |
| `node --check console/server.js`、`console/state-bridge.js`、页面内嵌脚本 | 通过 |
| PowerShell/C# | 两个真实解释器均解析、编译并执行同一核心；PS1 保留 UTF-8 BOM |
| `git diff --check`、暂存差异核对 | 通过后固定本地评审版 |

日志保存在被 Git 忽略的 `local/real-qq-final-python.txt`、`local/real-qq-final-node.txt`、`local/real-qq-targeted-final.txt`；它们是离线测试输出，不是 QQ 客户端验收证据。asyncio 调试耗时提示不属于测试失败，也不能推算真实响应延迟或账单。

## 逐项状态、旧数据与后续复验

| 项目 | 交付状态 |
| --- | --- |
| RQ01 | 源码已修、离线输入与边界回归通过；真实 C01—C07 待复验 |
| RQ02 | 源码已修、请求内反馈与时序回归通过；真实 T01/P05/G07 待复验 |
| RQ03 | 源码已修、停止状态/输入/accepted 历史与交错回归通过；真实 P14→关闭→恢复→P15 待复验 |
| RQ04 | 调查完成本轮可取得部分，**原因未定，未关闭**；新增后续退出观测 |
| RQ05 | **TTS 部署继续暂缓**；既有合成/媒体失败一次文字回退包含在全集，未验证真实语音可用 |
| RQ06 | 显式纯表情计划已修并离线通过；原生 QQ 引用为文档能力缺口，文本兼容；自然语言意图是否正确选择新标记仍待 QQ 复验 |
| RQ07 | 一键启动源码及双解释器离线矩阵通过；未安装、未真实启动生产 |

旧无请求状态字段的 user 行继续保留，不猜测取消；旧 assistant 仍需 accepted 才进入新输入。v1 摘录不继续固定旧选择，原文仍在时重新生成 v2；已滚出原文且只剩 v1 的内容不能凭空恢复，应在授权范围内 recall 核验。原始归档、长期记忆、媒体和备份不因本轮压缩自动删除或迁移。代码回退保留新状态字段和审计事件；旧代码不认识 stopped，可能重新注入该历史，回退后不应立即恢复回复而不复核上下文。

后续如获准部署，插件须配套 main/context_window/reply_completion/qq_delivery/state_store，保留既有其他辅助模块；Console server.js 和启动器需同版，不能只复制入口。按既有 releases 流程保留部署常量与一致性备份。本轮未操作生产代码、配置或运行数据，未重启/部署、推送或合并 main。

部署后按用户另行安排：复测压缩前后的一次/多次更正与取消；T01 同文、P05 工具拒绝、G07 补图中的反馈时序；生成/媒体/首气泡阶段关闭再恢复并发独立新题；纯表情成功和一次失败回退；当前来源文本引用不额外提及历史发言者；核验启动器关闭入口后仍在线并收集真实退出观察。TTS、闹钟、自动清理、公开画像、真正并发/账单继续暂缓。

评审固定流程：本轮源码、测试和本文一并在本地 dev 提交；准确 hash 由最终回复及仓库外 TASKS.md 记录，亦可用 `git log -1` 核对。提交不表示独立评审、用户验收、远端推送、部署或稳定晋级。main 保持 `5641b0a1e01f76b55293fa427b319136f1f7b837`。
