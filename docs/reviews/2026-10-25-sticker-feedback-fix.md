# 2026-10-25 纯表情等待文字 P2 补修

状态：源码补修与离线验证完成，本记录随 dev 追加提交固定，待独立复验及用户验收。本补修未部署、重启生产或进行真实 QQ 复验。

后续验收（2026-10-25）：`1da1746` 已按同任务授权完成独立离线复验、部署及真实 QQ。等待文字约束与普通反馈对照通过；群明确两张实际五图，新增数量 P2，整体暂不通过。详见[后续验收及独立失败探针](2026-10-25-sticker-feedback-reacceptance.md)和[发布/回退](../releases/2026-10-25-sticker-feedback.md)。本记录下方“未部署/待复验”保留为实施交付时事实。

承接[数量通过、等待文字失败的复核](2026-10-25-sticker-duplicate-reacceptance.md)。两张图片实际到达、数量通过；本轮修复独立等待反馈“稍等，我整理一下”，不重新把问题归因于数量。分支 dev，基线 `8301c9872764aaa5e84ca737b98e7208ea7ffbf1`，原有复验/部署文档和独立探针予以保留。

## 失败证据与计划

- 本轮原独立探针重新运行：3 项，1 通过/2 失败，2.727 秒，退出 1；工具已声明、工具未声明前两条路径均有多余 text。日志为 `local/sticker-feedback-fix-2026-10-25-acceptance-red.txt`。
- 根因：`_react_and_send()` 只检查请求身份、反馈完成状态，不检查仅表情；工具/最终计划中的限制不能追溯撤销此前 accepted 的文字。
- 按 systematic-debugging、test-driven-development、verification-before-completion 顺序实施：补回归 → 发送前统一检查请求限制 → 复验。明确用户要求在模型/工具之前约束反馈；工具确认后关闭待发反馈，并在 await 后重查；普通反馈继续保留。只读取本请求来源，不把搜索词、历史或代码/引用里的动作当作指令。
- 覆盖纯表情/普通请求、快速/工具/繁忙反馈、工具晚确认、字面内容保护、媒体 accepted/failed/unknown、并行/后续请求、攒批约束。主回答不等待额外决策，不全局关闭反馈。

## 验证与交付

`main.py` 新增 `_feedback_suppressed()`，只检查当前事件的显式 `_dsh_sticker_only`、本请求已记住的静默反馈标志、入站正文/入站条目及同作用域攒批缓冲。`last_text` 可能是搜索词或 URL，不作为用户意图；不读取归档、历史或其他会话。inject 消费攒批时先保留静默标志，避免补充要求随缓冲被消费后丢失。

`_react_and_send()` 在开始前、原有 0.8 秒快速等候之后及 `_make_react()` 返回后检查该约束。不会为判断意图增加模型调用、延长等候或阻塞主回答。`send_sticker(..., only_sticker=True)` 立即关闭并取消待发反馈；已有生命周期的 accepted/unknown 处理保留，不声称能撤销已经被平台接受的文字。

`chat_style.py` 的字面边界迭代器新增可选引号遮蔽模式（原动作/格式调用仍使用原默认行为），仅对引号外请求正文识别“只发/只要/仅/纯表情”或发表情并明确“不要文字”的有限表达。代码围栏、缩进、引用块、行内代码及引号内容不提供意图；普通引号里的情绪名被遮蔽后，外部“只要一张…表情”仍可识别。否定的“不要只发表情，请用文字解释”不被识别为静默。此检测只抑制可选的进度文字，不执行用户动作行、不设定图片张数、不改写主回答计划，也不宣称覆盖任意自然语言表达。标志只在本请求有效，后续请求重建，普通对话仍有进度反馈。

原独立 `acceptance_sticker_feedback_20261025.py` 断言未改，由新增 `test_repair_sticker_feedback.py` 导入其测试类纳入正式发现；新增九项测试方法。专项共 **12 项**，含多种请求表达 × quick/fetch/search/busy、引用/代码/否定对照、工具晚确认、等待期间才设标志、发送前重查、取消清理、攒批消费前后、跨场景并行/后续请求，以及媒体 accepted/failed/unknown。媒体成功只两图，明确失败仍按原规则最多一次文字回退，unknown 不补发；“不要文字”没有被扩成忽略真实媒体失败的全局政策。

| 检查 | 本轮实际结果 |
| --- | --- |
| 原三项 `unittest discover -s tests -p acceptance_sticker_feedback_20261025.py -v` | 修复前 1 通过/2 失败（2.727 秒）；修复后 **3/3，1.107 秒，OK** |
| 新专项 `unittest discover -s tests -p test_repair_sticker_feedback.py -v` | 初始 10 项修复前有 30 个失败结果（含子场景），无环境错误；最终增加边界后 **12/12，5.265 秒，OK** |
| 完整 `unittest discover -s tests -p 'test_repair_*.py' -v` | **205/205，185.426 秒，OK**（原 193 + 本轮 12 项） |
| 余额插件 unittest | **2/2，OK** |
| Node security/state | 首轮 **12/13**，确认响应测试在 100ms 内未返回 true；单独复跑该项 **1/1**；Python 全集结束后原命令重跑为 **13/13，0 失败/跳过**。未修改 Node 源码或测试；现象符合短时限时序波动，但本轮未证明根因，保留首轮失败记录 |
| 静态语法 | plugin/tests 共 **56 份 Python AST**；server.js、state-bridge.js、页面 1 段内嵌 JS 通过 |
| 双 PowerShell、差异和临时替身 | 全集实际输出 pwsh.exe/powershell.exe 两套 `launcher matrix exercised`；`git diff --check` 通过，临时启动器替身残留 0 |

日志为 Git 忽略的 `local/sticker-feedback-fix-2026-10-25-*.txt`，包括 acceptance-red、regression-red、acceptance-green、regression-green、python、balance、node、node-targeted、node-rerun、static。测试源码是持久化可复跑证据，只用临时目录/合成事件/发送器，不依赖真实聊天或调用付费模型。

## 评审状态、兼容与下一步

由当前对话自查源码和回归，不派生代理，待独立复验及用户验收。全部检查已完成，按工作单追加本地 dev 提交，不改写 `8301c98`；commit hash 由交付消息和仓库外 TASKS/HANDOFF 记录，本记录随该提交固定。main 保持 `5641b0a`，本地 origin/dev 引用保持 `ba22877`，本轮未联网刷新或写入。原验收、发布文档中的当时状态保留，新增文档和探针随补修提交保存。

生产按用户已报告的 `8301c98` 运行；本轮不执行其健康检查、部署、重启或真实模型调用，不清理既有测试数据，未推送或合并 main。改动不改变配置、持久化格式、依赖及数据，不做迁移；后续若获准发布需配套 main.py/chat_style.py 并核对同版依赖，先备份再按既有发布流程部署。代码回退基线 `8301c98`，保留新数据、媒体和日志，不重放 unknown，不用旧聊天快照覆盖新消息。TTS/F09 等暂缓项和 RQ04 原因未定状态保持不变。

下一步：针对追加提交做源码/离线复验，再按用户对相应阶段的安排发布并重跑群 G02，分别核对两张图片和前后无等待文字。**数量此前已真实通过，本轮离线通过不代表 QQ 无文字已复验通过。**
