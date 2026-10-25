# 2026-10-26 五项 P2 与默认 Bot/Console 启动补修

状态：五项 P2 已补修并通过本轮自检；功能提交 `7e58cf02ae9f2a32d0d074eb47b5c01f72f54b3a` 已配套部署，指定群/私聊新版状态实收。待独立复验，生产浏览器页面核对受工具设置阻断，首次激活 worker 后续消失原因未定，不宣称整单或长期稳定验收通过。开工 dev `54f1a531f1be3bd75ab574f9f92142974ec8701d`，保留已有验收 Markdown/证据，未清理其他成果。读取最新 AGENTS/TASKS/DEVELOPMENT 及验收报告；最新规则授权自检、本地提交后配套部署并使 Bot/Console 生效，QQ 同任务许可保留。无代理、新依赖、push/main、数据清理或其他暂缓扩展。

## 计划和失败证据

- [x] 当前版本重现报告五项：`node local/20261026-acceptance-projection-probes.cjs` 三项全部失败；`python -B local/20261026-independent-late-identity.py` 首次身份仍 null；`node local/20261026-independent-status-draft.cjs` 真实定时/数据变化/请求中输入仍 321→30、退出1。日志另存 `local/20261026-p2-*-red.txt`，原验收证据保留。
- [x] 纳入常规回归，分别修提交前草稿保护、未知来源纯 Bot 归档、混合文件歧义人工引用、近期时间顺序、首次晚到可信身份。
- [x] 实测唯一 `scripts/start-bot.cmd` 默认启动 Bot+Console（7850），保持同核双 PowerShell、显式参数、认证、重复启动/失败退出与后台生命周期。用户所称 start_bot.cmd 的实际文件为此连字符入口，不增加第二份用户入口。
- [x] 源码自审、专项/完整离线/隔离浏览器、静态和敏感检查，本地功能提交固定本记录和相关验收材料。
- [x] 停写备份、清单配套部署、启动生效核对；按有效 QQ 许可完成指定群/私聊各一次状态实收，更新 TASKS/HANDOFF 和发布记录。生产页面加载及刷新收尾受工具设置限制，未勾为通过。

## 实施与验证

### 五项根因与修改

| P2 | 根因 | 本轮修改和实际验证 |
| --- | --- | --- |
| 状态请求中草稿 321→30 | 只在请求前检查编辑，vStatus 不在提交前复核 | `index.html::vStatus` 对成功/失败响应提交前重查焦点、未提交草稿及删除面板。成功保存仅在输入仍等于本次提交内容时重置 defaultValue，使保存后可继续自动更新；新输入不误作已保存。真实 5 秒定时、正常状态数据变化、请求期间开始输入、失焦未保存、成功保存恢复更新、请求失败全部浏览器覆盖；原独立探针现 before/after 均321且焦点保持 |
| 无 source 纯 Bot 档成为用户 | 只把 known 的纯 assistant 桶归出站，其余误归 legacy 人物 | `people-sources.js` 将无已核入站的纯 Bot 桶（含 source=null）单列；恢复查找跳过缺来源，不造人。API 可读，confirm 拒绝，页面明确“目标来源未获取”、没有人物确认按钮；认证与媒体保护继续沿用 |
| 部分未知混合档人工确认被缩窄 | 多桶时把原 uid 优先交给 unknown，绕过歧义索引 | 无可靠原 scope 且多桶时全部使用稳定派生 UID，原整文件 UID 只作混合索引，旧人工引用保持未解析，不映射到其中一部分。原映射字节不变，确认用户0/未解析引用1/混合索引1；页面列出索引及警告，需维护者逐来源重确认 |
| 旧出站恢复挤掉新入站 | 合并时旧记录追加尾部，先 slice 再按时间排序 | `user-workbench.js` 对合并后的全部记录按有限 ts、稳定 id、内容摘要排序选最近150，再原场景过滤/分页；不改原存储。last_at 扫描真实时间，不依赖尾部。150 条 ts1000..1149 入站与150条 ts0..149旧出站合并后仍150条新入站，最新1149，文件不变；独立出站读取同样按时间选最近 |
| 第一次完整身份晚到被丢弃 | 旧事件只处理冲突，否则返回，未补首次完整证明 | `user_profiles.py` 仅在已有应用匹配、未有 identity 且没有冲突时，用旧事件补 identity/原观察时间/消息；最新昵称、事件时间、message/source和first_seen不倒退。跨应用/冲突走原保守分支，人工决定文件不在观察路径读取或改写。时间300稀疏、200首次完整（不同消息）取得有效证明200，最新称呼/时间仍300 |

### cmd 行为与边界

`scripts/start-bot.cmd` 的进程内默认值现在启用 Console，同一 `start-bot.ps1` 读取默认值，因此不用拼两次 `-WithConsole` 或端口参数。直接运行 PS1 仍默认只启 Bot，可显式 `-WithConsole`；cmd 默认 Bot+127.0.0.1:7850，显式 `-ConsolePort` 保留。pwsh PATH/标准安装优先、无 pwsh 回退系统5.1；不会因业务失败换解释器重跑，退出码不丢。

缺少 Node、server.js 或可解密有效凭据时 cmd 非零退出，不能把 Bot 已启动当双组件成功；修好依赖后重跑会严格核对并复用同实例已有组件。端口冲突不接管他人服务，后台仍为既有 Job/worker 管理。启动器源代码未放宽 PID/ticks/exe/nonce/root、命令行或监听进程族校验。用临时根与随机端口真实执行双 Shell：旧 cmd 在缺 Console 时错误退出0，新增断言两解释器均失败；补修后4项矩阵通过，实测默认 cmd 启动 Node、显式端口、认证、重复/并发、生命周期及37/23等真实退出码。

实际入口连字符为 `start-bot.cmd`，不是新建 `start_bot.cmd`；既有桌面链接指向开发入口，行为随同变化。两个生产旧兼容 cmd 先备份保留，本次不擅自删除其他启动文件或改快捷方式。使用说明已同步 README/DEVELOPMENT/[启动说明](../tooling/one-click-bot-startup.md)。

### 实际测试命令与结果

| 命令（仓库根，已有 Python/Node/Edge） | 结果 |
| --- | --- |
| `node --test console/tests/repair-legacy-scenes.test.js` | 新增三项先失败（7通过/3失败），原断言不放宽；最终在完整 Node 内通过 |
| `python -B -m unittest discover -s tests -p test_repair_user_profiles.py -k first_reliable_older_identity -v` | 先失败 identity=None，修复后完整资料专项10/10（0.101秒）；原顺序/冲突/权限原断言保持 |
| `python -B -m unittest discover -s tests -p test_repair_launcher.py -v` | 4/4，122.931秒，实际 pwsh.exe/powershell.exe；cmd 新默认先取得两分支失败证据 |
| `python -B -m unittest discover -s tests -p 'test_repair_*.py' -v` | **248/248，213.947秒，退出0**，输出双Shell矩阵；包括本轮profile、原生命周期/出站/表情等 |
| `python -B -m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | **2/2，退出0** |
| `node --test console/tests/repair-*.test.js` | **60/60，1364.7462ms，退出0**；认证、媒体、来源/聚合管理边界保持 |
| `node tests/console_p2_browser.cjs` | **7项**，真实定时/实际隔离 Edge，未改时钟；新状态草稿四分支、未知出站、混合索引、390px与零JS异常 |
| 原六浏览器脚本 `console_refresh_browser / identity_lifecycle_browser / refresh_races_browser / workbench_browser / user_auto_browser / identity_triage_browser.cjs` | **15+8+3+17+11+15=69项**，全部退出0，证据重定向到local本轮目录，原截图未覆盖。混合未知选择器按 original_uid+kind 找新的子来源，仍断言原内容与隔离 |
| 原独立验收三个驱动 `local/20261026-acceptance-projection-probes.cjs`、`independent-late-identity.py`、`independent-status-draft.cjs` | **三项投影+身份+状态共5项断言均满足**。驱动内固定基线head是原报告参考，本轮结果由当前工作区源码执行；未修改其业务断言 |
| `local/p2_static_review.py`、配置敏感/真实身份扫描、`git diff --check` | **64 Python AST /22 JS+CJS /1页面脚本通过**；本轮与未推送历史无真实配置秘密、来源ID或昵称命中。扫描工具不输出秘密 |

Python为 `D:\dsbot\venv\Scripts\python.exe -B`，Playwright使用已有 NODE_PATH，无依赖安装。结果日志 `local/20261026-p2-*`；[76项浏览器清单](evidence/2026-10-26-p2-fix/browser-all.json)、[状态数值](evidence/2026-10-26-p2-fix/status-draft.json)、[状态画面](evidence/2026-10-26-p2-fix/status-draft-preserved.png)、[窄屏出站与索引](evidence/2026-10-26-p2-fix/unknown-outbound-and-mixed-index.png)、[静态结果](evidence/2026-10-26-p2-fix/static.json)均合成数据。

初次浏览器运行查出缺 source UI 解引用、索引长 UID 窄屏溢出，均补修并重跑；一次精确文字选择器未包含消息meta，改为定位实际出站消息再断言完整内容，未放宽产品行为。完整旧回归无遗漏报告失败。先自审本轮差异：没有改Bot权限/账本/原scope/目标及人工决定规则，投影排序是副本，旧文件不迁移；状态草稿不通过长周期或关刷新修复。新API版本 **20261026-lifecycle-2** 三处一致。

## 本地提交、配套部署及实际运行

源码自审及上述自检后，已审阅并本地提交 **7e58cf02ae9f2a32d0d074eb47b5c01f72f54b3a**（33文件、686增/26删），原独立失败验收文档/合成证据随同保留。随后按最新 AGENTS 授权部署，不拿旧 triage-1 验本轮。完整清单、停进程经过及回退见[发布记录](../releases/2026-10-26-console-lifecycle-p2.md)。

保护目录 `D:\dsbot\deployment-backups\20261026-console-lifecycle-p2-release` 保存源码zip、清单/before/staged和 **399份停写快照**。03:38安装13份变化文件，**29/29**运行哈希一致；仅按原规则保留4项插件部署常量、Console MASTER，三份框架/运行/DPAPI配置哈希一致。没有迁移或覆盖真实业务数据，旧兼容cmd备份后保留。

实际执行 `D:\dsbot\start-bot.cmd -RuntimeRoot D:\dsbot -TimeoutSeconds 60`，**没有加 -WithConsole**，两组件就绪且重复调用复用。首次03:38激活使用工具PATH中的PS7.6.5，03:39有API/哈希/复用证据，但03:45收尾发现两个worker均已消失、端口关闭，观察仍running/exit_code=null、未检到对应应用崩溃事件；**退出原因没有证据定论**，不把此前就绪当持续运行通过。随后选择已安装用户PATH的PS7.6.7，通过同一cmd重新启动，未改持久PATH、产品代码、凭据或安全设置。当前 Bot worker **118704**、Console worker **99472**，03:47:58、03:49、03:53、03:54均就绪，重复cmd仍复用相同PID。该次恢复不能关闭历史RQ04/PS7，也不证明长期存活。

生产API为 **20261026-lifecycle-2**，首页及两个 `/assets/` 脚本认证GET均200，首页/工作台模块版本一致。匿名访问首页拒绝认证；这只证明服务内容，不能代替实际浏览器加载证据。

## 指定QQ与数据边界

用户恢复原生测试窗口后重新核对账号资料卡、指定群号及原机器人私聊。仅私聊03:49、群03:51各一次本地状态命令，**客户端实际显示7e58cf0源码链接**；未触发模型路径，不重跑无改动的A表情用例。原v2历史群 **44→46**、私聊 **49→51**，每处恰好一user/一assistant；两个请求各一accepted回执，history/source/冻结provenance/target及request_id逐项一致，无错场景回复。

停写快照与实测后核对：history_all/history_v2全部旧前缀保持；原scope键集合不变；映射、names、friends和插件配置字节不变；只有原两个测试账本各扣1/累计spent加1，总余额-2、spent+2，没有聚合赠送或额外字段变化。真实映射/聊天/昵称/截图仅保存在保护目录，不入Git。运行投影实际为 **3已确认用户、4待确认来源、4旧档（2未归属）、8会话来源、5资料键、17原键、9展示入口**；与本轮部署前保存结果一致，不用历史1/6数字覆盖当前状态，也不将9入口当9自然人。

## 生产页面阻断与剩余验收

本轮控制台工具绑定原本机URL时返回 **“Local browser use is disabled in Work settings”**，未取得页面对象。已请求用户开启本地浏览器访问，尚未取得恢复答复；没有改用原生Edge、另一浏览器技术或写接口绕过。本轮没有进行生产UI关联/解除、草稿保存或刷新设置写入；映射哈希不变。生产页面是否已实际加载新前端、现有弹窗/面板、自动刷新勾选及实际重绘，**本轮均未核实**，保留缺口。两个QQ窗口最初均最小化，用户恢复后QQ缺口已补齐，与浏览器设置阻断分开记录。

旧B指定人物流程已有真实通过历史保留，新五项P2有失败到修复自检及隔离浏览器证据，但没有对生产数据造旧档/乱序事件或写入草稿来制造通过。真实跨域自动同人及全局QQ昵称的平台依据缺口依旧。当前为**已部署待独立复验**；未push/合并main/新增依赖权限/清真实数据，A已关闭、RQ04/TTS/F09保持原状态。

## 2026-10-26 后续：生产页面缺口补齐

用户要求重点补验上次未完成内容后，同一Edge访问恢复，实际reload新版、生产草稿保持/恢复、场景隔离/具体群、预览取消及自动刷新收尾已核。后旧标签Debugger unattached，按支持步骤在同一Edge临时标签继续完成，未改设置/换控制技术或提交未知操作。生产页面缺口关闭，具体观察和限制见[本轮续验](2026-10-26-console-lifecycle-p2-page-reacceptance.md)。期间现场映射/消息变化保留，不用旧快照回写；最终统计3/2/4/8，不能覆盖上文各时点3/4/4/8历史。未做产品修改、部署/重启/QQ/真实配置关联写入或推送/main；退出原因未知及平台身份缺口仍保留。
