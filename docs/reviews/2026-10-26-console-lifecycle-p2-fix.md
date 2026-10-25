# 2026-10-26 五项 P2 与默认 Bot/Console 启动补修

状态：实施中。当前 dev `54f1a531f1be3bd75ab574f9f92142974ec8701d`，开工保留已有验收 Markdown/证据，未修改或清理其他成果。读取最新 AGENTS/TASKS/DEVELOPMENT 及验收报告；最新规则授权自检、本地提交后配套部署并使 Bot/Console 生效，QQ 同任务许可保留。无代理、新依赖、push/main、数据清理或其他暂缓扩展。

## 计划和失败证据

- [x] 当前版本重现报告五项：`node local/20261026-acceptance-projection-probes.cjs` 三项全部失败；`python -B local/20261026-independent-late-identity.py` 首次身份仍 null；`node local/20261026-independent-status-draft.cjs` 真实定时/数据变化/请求中输入仍 321→30、退出1。日志另存 `local/20261026-p2-*-red.txt`，原验收证据保留。
- [x] 纳入常规回归，分别修提交前草稿保护、未知来源纯 Bot 归档、混合文件歧义人工引用、近期时间顺序、首次晚到可信身份。
- [x] 实测唯一 `scripts/start-bot.cmd` 默认启动 Bot+Console（7850），保持同核双 PowerShell、显式参数、认证、重复启动/失败退出与后台生命周期。用户所称 start_bot.cmd 的实际文件为此连字符入口，不增加第二份用户入口。
- [x] 源码自审、专项/完整离线/隔离浏览器、静态和敏感检查，本地功能提交固定本记录和相关验收材料。
- [ ] 停写备份、清单配套部署、启动生效核对；按有效 QQ 许可做必要指定目标验证，分开记录未实证分支。更新 TASKS/HANDOFF 和交付记录。

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

生产部署、实际cmd启动、新版本页面和指定QQ状态待完成后追加，离线通过不等于所有真实边界已实证。源码自检通过后本地功能提交，再配套部署，不拿旧 triage-1 验本轮。
