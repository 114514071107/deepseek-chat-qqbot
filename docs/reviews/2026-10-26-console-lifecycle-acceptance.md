# 2026-10-26 四项补修独立验收

结论：**本轮验收未通过，5 项 P2 待补修。** 现有完整回归通过，但补充故障探针发现自动刷新、旧档分类/人工引用/时间顺序、晚到身份凭据仍有未覆盖分支。没有产品源码补修；不能将本记录描述为四项全部通过。

## 范围与授权

- 固定审阅 `dev` 的 `54f1a531f1be3bd75ab574f9f92142974ec8701d`，基线 `0568dac49d14bfa4264f51b2fad53dba5f70a27f`；开始工作区干净、领先本机远端跟踪分支 1 提交。本轮未 fetch、push、创建 PR 或合并 main。
- 重读仓库外 `D:\dsbot\repair-workorders\AGENTS.md`、最新 TASKS/HANDOFF、DEVELOPMENT、本轮计划和交付记录；目标及上级未发现附加 AGENTS。按 requesting-code-review 技能进行独立只读交叉审阅，按 verification-before-completion/webapp-testing 实际复跑；新增失败使用 systematic-debugging 定位。
- 用户补充“可使用qq验收”；沿用工作单指定账号和会话，许可在本任务内有效。工作单要求先通过源码/离线、核对部署版本并重启就绪，才进入真实 QQ。本轮出现源码/离线阻断，故没有发送 QQ、部署、重启或移出旧入口。无需重复索取同范围 QQ 许可；后续部署仍需核对相应授权。
- 所有新夹具、HTTP 服务、发送器和进程均隔离；未导入生产插件实例、未访问活跃 SQLite、未修改真实聊天、人工决定、积分或配置。仅只读核对生产版本常量和启动文件是否存在。

## 独立复跑

工作目录为开发仓库，解释器为已有 `D:\dsbot\venv\Scripts\python.exe`；未安装依赖。

| 命令/检查 | 本轮实际结果 |
| --- | --- |
| `python -B -m unittest discover -s tests -p 'test_repair_*.py' -v` | **247/247，210.076 秒，退出 0**；输出实际包含 pwsh.exe、powershell.exe 两套矩阵 |
| `python -B -m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | **2/2，退出 0** |
| `node --test console/tests/repair-*.test.js` | **57/57，1376.8876ms，退出 0**，无失败/跳过 |
| 六组已交付浏览器脚本 | **15+8+3+17+11+15=69 项**，全部退出 0；真实已安装 Edge、真实 5 秒定时器、合成临时目录 |
| 全部版本化 Python / Console JS 和浏览器 CJS / HTML 内嵌脚本 | **64 / 21 / 1** 语法检查通过，Python 仅 AST；双 PowerShell 生命周期与退出码由上述矩阵覆盖 |
| `git diff --check` | 通过 |

浏览器命令依次为 `node tests/console_refresh_browser.cjs`、`identity_lifecycle_browser.cjs`、`refresh_races_browser.cjs`、`workbench_browser.cjs`、`user_auto_browser.cjs`、`identity_triage_browser.cjs`。`NODE_PATH` 指向既有 bundled Playwright；分别使用 `DSH_REFRESH_EVIDENCE`、`DSH_BROWSER_EVIDENCE`、`DSH_AUTO_BROWSER_EVIDENCE`、`DSH_TRIAGE_BROWSER_EVIDENCE` 将输出放到忽略的 `local/20261026-independent-*`，没有覆盖旧截图。实际查看本轮 390px 阅读截图和状态页故障截图；原脚本内的历史 date 字段不作为执行日期证据。

完整新日志为 `local/20261026-independent-python.txt`、`-node.txt` 及 `-<浏览器脚本名>.txt`；[浏览器清单](evidence/2026-10-26-lifecycle-acceptance/browser.json)、[六组退出码](evidence/2026-10-26-lifecycle-acceptance/browser-exits.json)、[静态结果](evidence/2026-10-26-lifecycle-acceptance/static.json) 为本轮脱敏副本。首次静态驱动在向 Node stdin 传中文时遇到宿主默认 GBK 编码错误，改为明确 UTF-8 后完成检查；该错误未归为产品缺陷。

## 待补修的 5 项 P2

### 1. 状态页在刷新等待期间输入的新草稿被覆盖

- 位置：`console/public/index.html:190–195` 的刷新前检查，以及 `vStatus` 的异步请求和 `:302` 起的 DOM 提交。
- 真实定时复现：打开状态页并启用自动刷新；合成历史增加一条，使本轮状态 HTML 变化；暂缓该次 `/api/status` 响应，在请求已经发出后输入 `#pt-daily=321`，再释放响应。实际值 **321 → 30**；焦点仍在输入框，输入内容已丢失。原有“无变化 HTML 不重绘”会掩盖此问题，故探针明确制造正常的新数据。
- 根因：`refreshNow` 只在请求前检查输入/草稿。Users 与 Memory 在提交前另行检查，Status 未检查；通用 ReadingState 只恢复焦点与位置，不恢复输入值。
- 要求：自动刷新在提交 DOM 前再次检查期间新增的编辑状态；保留未提交内容，并在用户完成编辑后继续刷新。新增“状态数据变化 + 请求中开始输入”的回归，不能只测已在请求前输入或数据完全无变化。
- 探针：`node local/20261026-independent-status-draft.cjs`。修正测试驱动先点击非输入区域解除 auto-ref 焦点后，真实定时失败**连续复现两次**、退出 1；未改产品代码。[数值证据](evidence/2026-10-26-lifecycle-acceptance/status-draft.json)、[故障截图](evidence/2026-10-26-lifecycle-acceptance/status-draft.png)。

### 2. 缺来源的纯 Bot 旧档仍可新增已确认用户

- 位置：`console/people-sources.js:41–43`。
- 夹具仅有一条 `role=assistant` 旧记录，无 source、入站或 scopes。实际成为 legacy 人物入口：**total=1、outbound_archives=0**；经现有普通确认操作后，**confirmed_users=1**。
- 根因：纯 assistant 分桶只有 `known` 时才进入仅 Bot 出站旧档。缺来源的旧 Bot 发言继续进入可确认人物集合，违背“不能凭 Bot 发言增加用户统计”。
- 要求：未知来源的纯出站也应单列、可读并说明来源缺口；不能进入人物确认统计，UI/API 同时支持缺 source 的出站展示。

### 3. 混合旧档的整文件人工引用被静默缩窄

- 位置：`console/people-sources.js:37`、`:57`。
- 夹具 `mixed` 含一条完整 group source 的用户记录和一条无 source 用户记录，已有 v2 人工决定 `groups:[["mixed"]]`。实际把原 uid 交给 unknown 桶，原确认只作用于未知部分；已知部分另成 pending，返回 **confirmed_users=1、unresolved_mapping_references=0、archive_indexes=0**。
- 根因：存在 unknown 桶时优先保留原 uid，从而跳过仅在 `preferred===null` 时生成的歧义文件索引。已有“全部场景均已知”的混合索引回归没有覆盖“部分未知”的情况。
- 要求：没有可靠原 scope、整文件已分成多个来源时，旧整文件决定保持原始含义并作为待核引用；不能自动改成某个子集的人工确认。保留原决定，提示逐来源重确认，不将整文件无条件合人。

### 4. 旧出站别名恢复后挤掉较新历史

- 位置：`console/people-sources.js:62`；`console/user-workbench.js:145`、`:183`。
- 夹具：已有来源 150 条较新入站，时间 1000..1149；唯一同完整来源的旧出站别名含 150 条合法 proactive assistant，时间 0..149。恢复后，近期列表为 **0 条较新入站 / 150 条旧出站**，`last_at=149`，实际最新应为 1149。
- 根因：恢复的别名记录直接追加尾部，而近期截取发生在排序之前；last_at 也只看最后 150 条。原存储没有丢失，但用户无法在“近期”中看到真正最新记录，人物排序同时错误。
- 要求：多来源/别名合并后按真实时间和稳定规则选择近期记录，再分页；last_at 不依赖追加顺序。补旧出站早于已有入站的回归。

第 2–4 项可一起重跑 `node local/20261026-acceptance-projection-probes.cjs`，三项预期断言均失败，主验收者已独立重跑确认退出 1；原始文件仅在系统临时目录写入并清理。[三项实际结果](evidence/2026-10-26-lifecycle-acceptance/projection.json)。

### 5. 第一次完整可信身份凭据晚到时仍被丢弃

- 位置：`plugin/astrbot_plugin_dsh_soul/user_profiles.py:144–152`。
- 同一应用/同一群来源，先收到时间 300 的稀疏 author 事件（app 已知，缺 user_openid），再收到时间 200、不同消息 ID 的完整可信 author pair。实际保留最新称呼与时间，但 **identity 仍为 null**，没有吸收首次可靠映射。
- 根因：旧事件分支只保存冲突变化，否则直接返回；当前还没有 identity 时也没有补入可靠旧证明的分支。已有“先完整、后稀疏”和“晚到冲突”回归通过，不能覆盖这个反向到达顺序。
- 要求：在不倒退最新称呼/事件和不覆盖人工决定的条件下，接受首次完整可靠凭据，保留其原观察时间和消息；跨应用/冲突继续保守处理。
- 探针：`D:\dsbot\venv\Scripts\python.exe -B local/20261026-independent-late-identity.py`，退出 1。[实际结果](evidence/2026-10-26-lifecycle-acceptance/late-identity.json)。这是真实时间排序分支的遗漏，未宣称当前 QQ 已提供这份跨场景映射。

## 非阻断观察与未覆盖项

- 独立审阅额外模拟“旧回执在同 key 新 epoch 的 work_context 中重入”，可以重建已清空回执（`main.py:3440–3447`）。正常 QQDelivery audit 为同步调用并继承原 token，accepted 历史保存另有原 epoch 检查；没有证明常规入口会以新 token 重入旧结果。因此只保留契约边界观察，不计入上述 5 项 P2，也不宣称生产删除已被绕过。原始合成探针/说明在忽略的 `local/review-delivery-20261026/`。
- 发送前冻结来源与 Target、assistant 角色、空原请求、媒体/分段相关回归、原历史内幂等及自消息入口保护已有源码和离线证据；该结论不等于平台实际收到或所有适配器回流均已验证。
- 真实 QQ author 跨场景映射、全局 QQ 昵称、平台自消息变体、真实主动/媒体投递与客户端显示仍无本轮证据。F09/TTS 暂缓状态不变；不扩大本轮授权。

## 生产状态、收尾与后续

只读核对生产 Console 文件仍为 **20261025-triage-1**；`D:\dsbot` 中三个旧有 Bot cmd 仍存在。本轮没有成套同步、调用方更新、入口移出、服务启停、真实数据迁移、QQ 消息或模型调用。不能将旧生产版本测试算到 `54f1a53`。

5 项 P2 应补源码、失败回归并追加本地 commit，然后重做受影响独立复验；通过后才按部署授权和交付中的备份/回退步骤成套同步。既有 QQ 许可保留，准备就绪后接续指定目标实测。回退与入口清理方案仍见原交付记录，当前没有生产变更可回退。

本轮只新增验收文档与脱敏证据，并在原交付文档追加回链，同步仓库外 TASKS/HANDOFF。产品源码、测试实现、index、HEAD 未改；没有新本地提交、远端推送或 main 合并。文档留为可评审修改，不把工作区仍称为干净。
