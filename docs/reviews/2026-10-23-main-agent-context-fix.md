# 主 Agent Context 类型校验阻断补修

日期：2026-10-23（Asia/Shanghai）。目标：修复[启动问题交接](<D:/dsbot/repair-workorders/STARTUP-ISSUES-2026-10-23.md>)报告的 `AstrAgentContext.context` 不接受 `BudgetContext`，补足真实主 Agent 构造路径回归。

## 基线与范围

- 开发分支 `dev`，开工 HEAD `6f57320942d2e6754e5840f07ed826aabf06d676`，工作区干净。前三单与第四单已发布成果保留，未回退旧基线。
- 实际修改 `plugin/astrbot_plugin_dsh_soul/model_integration.py`；新增 `tests/test_repair_main_agent_context.py`，更新本记录、DEVELOPMENT、MODIFICATIONS 及共享交接状态。
- 本轮仅开发源码与离线验证。没有修改运行副本、真实配置/聊天/数据库/依赖或 site-packages，没有重启、部署、QQ 发送或真实/付费模型调用。测试使用临时 ASTRBOT_ROOT、cwd、TEMP/TMP 子进程和替身服务、模型、传输。
- 沿用本对话第四单“不自动提交推送”的明确约束；本轮未暂存、提交、推送或合入 main。HEAD 不变，差异供复验；既有第四单上线授权不自动顺延本次补修部署或推送。F09、TTS 部署及其他暂缓事项未实施。

## 根因与修改

真实 AstrBot 4.29.1 `build_main_agent` 会构造 Pydantic dataclass `AstrAgentContext(context=plugin_context, event=event)`，字段要求真正的 `Context` 实例。原适配器把普通 `BudgetContext` 代理直接传入；该代理即使能转发方法，也不满足实例校验。服务启动、QQ 连接正常不能证明这一聊天请求路径可用。

旧框架集成测试直接调用 `runner.reset`，另行测试图片描述，没有贯通 `build_main_agent → AstrAgentContext`。新增三个测试在修复前全部于真实构造点复现 `is_instance_of Context`，输出保存在忽略目录 `local/main-agent-context-red.txt`。

修复增加 `BudgetContext.bind_context()`：

- 浅复制调用方提供的真实 Context，保留其实际类和共享配置、会话、工具等服务引用，不重新构造服务或连接。
- 仅在该请求副本上绑定 `get_provider_by_id` 与 `get_using_provider_async` 两个预算入口，再把此真实 Context 副本传给 builder。BudgetContext 留作请求内提供商包装 helper，不再交给 Pydantic 作为 Context。
- 原共享 Context 与全局 Provider 不被替换或修改；并发 builder 各持有不同 Context 副本、提供商缓存和事件预算。
- 前置图片描述仍使用保留真实 Provider 类型的请求副本；runner.reset 继续解除重复包装并套同一原请求 Budget。图片描述与主生成合计受同一调用次数限制，输出/重试/权限守卫保留。

没有修改框架磁盘文件、关闭 Pydantic 校验、伪造 `__class__`、撤掉预算或扩大普通用户工具权限。

## 回归与验证

新增三个隔离测试均调用真正的 builder、真正的 Context 构造和 AstrAgentContext 校验，没有替换这些被测入口：

1. 普通文字从真实输入收集、模型选择、Agent 构造与 runner.step，贯通 capture、实际完成入口、替身 QQ accepted 回执、插件历史及框架历史保存；同一生成过程下实际工具执行器仍拒绝未授权宿主 Shell 工具。
2. 固定小图片先经框架图片描述，再完成主回复；描述调用占用原请求额度，主生成后第三次调用在到达替身物理查询前被拒绝。
3. 两个场景同时构造主 Agent，副本保留真实 Context 类型与服务引用，预算分别关联各自请求；一个请求额度用尽不消耗另一个请求的额度。原 Context 两个提供商查询仍返回原 Provider，没有被绑定到某个请求；框架配置来源未变为内部 `c2_`/`p2_` 键。

执行命令（开发仓库根）：

```powershell
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p test_repair_main_agent_context.py
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p 'test_repair_*.py'
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py
node --test console/tests/repair-security.test.js console/tests/repair-state.test.js
node --check console/server.js
node --check console/state-bridge.js
git diff --check
```

专项 RED：3/3 失败，均为真实 `AstrAgentContext.context` 类型校验，失败原因与交接一致。普通主生成、前置描述和回复均停在替身，没有真实网络调用。

| 本轮验证 | 实际结果 |
| --- | --- |
| 新增真实 builder 专项 | 3/3，12.794 秒，OK |
| Python 完整修复集合 | 160/160，70.391 秒，OK |
| 余额插件 | 2/2，OK |
| Node 离线回归 | 12/12，零失败 |
| plugin/tests Python AST | 44 个文件通过 |
| 控制台 JS / 页面内嵌 JS | 两份文件及一份内嵌脚本通过 |
| `git diff --check` | 通过，记录落盘后再次检查 |

原有 F01—F08、前置图片描述、攒批图片输入、17 项发送/来源补修回归均包含在全集中。完整输出保存在忽略目录 `local/main-agent-context-python.txt`，没有新费用或性能测量结论。asyncio 调试模式打印了部分测试任务超过 100ms 的耗时提示，没有失败。

本轮开发差异快照保存为 `local/main-agent-context-fix.patch`，五份交付文件及补丁哈希保存为 `local/main-agent-context-manifest.json`；反向应用检查通过。仓库外的 STARTUP-ISSUES/TASKS 只更新交接状态，不复制进源码根目录或加入补丁。

## 兼容、发布及当前状态

- 不新增配置、数据格式或历史迁移，不修改框架/插件权限、发送结果或旧数据。原助手历史来源语义和其他未纳入本次的第四单问题未扩展重构。
- 当前运行实例仍使用修复前文件，本轮没有核验或宣称真实聊天恢复。源码补修与离线通过必须同生产上线、真实 QQ 到达、费用及长期稳定性分别判断。
- 后续获准发布时，需先备份实际同版插件文件和部署参数，校验 `model_integration.py` 与已发布资源/任务模块配套，再按授权选择重载或重启；不能仅覆盖磁盘就宣称内存适配器已更新。运行源码获取入口须固定到届时实际发布版本。
- 回退恢复备份的同版模块并重新加载对应适配器；恢复旧模块会重新暴露本类型错误，应事先明确影响，不以恢复数据掩盖代码失败。不需要改写或恢复聊天数据、配置或依赖。

独立只读复核结论：本轮限定范围没有阻断，可交用户复验。已核对 Context 副本类型/服务引用、原查询路径、Provider 类型、runner 解除重复包装与原请求预算，以及真实 builder 测试和 RED/全集输出证据；未发现新增预算绕过、权限放宽或跨请求串用风险。复核没有修改文件、索引或 HEAD。未评价其他框架版本/自定义复制行为的 Context 子类，也没有扩展到第四单全部功能、真实 QQ、重载和长期稳定性。

当前：开发补修、离线验证及独立只读复核通过，待用户复验；未提交、推送或部署，dev HEAD 仍为 `6f57320942d2e6754e5840f07ed826aabf06d676`。原第四单验收/上线记录保留，本记录为其后续实测缺陷补充。

## 后续验收（2026-10-23）

用户要求验收后，重新运行真实 builder 专项 3/3、Python 全集 160/160、余额 2/2、Node 12/12，以及 44 份 Python AST、JS 和差异检查均通过；五份交付文件及补丁哈希匹配，补丁反向检查通过。修复前代码在隔离子进程的同一真实 builder 测试中再次复现原类型错误，当前代码通过。**本次 Context 类型补修的源码与离线验收通过**，详情见[Context 补修验收记录](2026-10-23-main-agent-context-acceptance.md)。本段为后续状态，前文“待复验”保留原交付历史。运行实例尚未应用补修，未提交、推送或部署，真实聊天恢复待上线验证。

本轮验收的独立只读审查也未发现明确 P1/P2，另行复跑新增专项 3/3（13.166 秒）及差异检查通过；没有修改文件、索引或 HEAD。其结论同样仅限当前框架版本及源码补丁，不包含真实 QQ 和生产恢复。
