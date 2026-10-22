# 主 Agent Context 补修验收

日期：2026-10-23（Asia/Shanghai）。用户请求：验收真实 Context 请求副本补修。

结论：**本次 Context 类型补修的源码与离线验收通过。** 真实 `build_main_agent → AstrAgentContext → runner.step` 路径已通过隔离验证，原类型错误关闭。当前运行副本尚未应用补修，不能将此结论描述为真实聊天已经恢复。

## 评审版本与操作范围

- 开发仓库 `D:\DSH Workspace\deepseek-chat-qqbot`，分支 `dev`，HEAD `6f57320942d2e6754e5840f07ed826aabf06d676`。评审该 HEAD 之上的未提交补修；功能改动限于 `model_integration.py` 的 Context 复制及 builder 传参，新测试为 `tests/test_repair_main_agent_context.py`。
- 查阅[补修记录](2026-10-23-main-agent-context-fix.md)、启动问题交接、实际差异及本机 AstrBot 4.29.1 的 Context、AstrAgentContext 和 builder 源码。
- 追加本记录前，`local/main-agent-context-manifest.json` 的五份文件 SHA256 和补丁 SHA256 均匹配；`git apply --reverse --check local/main-agent-context-fix.patch` 退出 0。补丁 SHA256 为 `e3627ec1035cc8b86159aef04fe586887fbf6b6ead84cd0a268ebbd6745469a9`。验收后文档追加不改写该交付快照。
- 本轮没有修改功能源码、正式测试、索引或 HEAD；只做只读检查、隔离离线验证并补充验收记录和交接状态。没有提交、推送、合入 main、部署、重启、真实 QQ/模型请求、真实数据修改或依赖操作。F09、TTS 部署和其他暂缓项保留。

## 缺陷关闭依据

修复为真实 Context 做请求内浅复制，仅将两个提供商查询入口绑定到该请求的 BudgetContext helper；传给 builder 和 Pydantic 字段的值保留真实 Context 类型。原 Context 的实例方法没有被覆盖，配置、会话、平台及提供商等服务保持原引用，不重新构造连接。

三个新增测试实际调用框架 builder 和 AstrAgentContext，没有替换被测构造点：

1. 文字请求完成真实 runner.step、capture、回复完成入口、替身 QQ accepted 回执，以及插件/框架历史保存；真实工具执行器继续拒绝未授权宿主 Shell。
2. 前置图片描述与主生成共享同一原请求预算，额度用尽后的调用在物理查询替身之前被拒，重试限制保留。
3. 两个场景并发构造时分别持有真实 Context 副本及原请求预算，额度不串用；原 Context 的提供商查询仍返回原 Provider，配置来源没有变为内部会话键。

另外在全新临时 ASTRBOT_ROOT/cwd/TEMP/TMP 进程中，将 `git show HEAD:plugin/astrbot_plugin_dsh_soul/model_integration.py` 的修复前代码仅加载到该子进程的内存模块，运行同一个真实文字 builder 测试。子进程退出 1，在 AstrAgentContext 处复现 `Input should be an instance of Context [type=is_instance_of]`。同测试在当前源码通过，确认该回归覆盖原实测类型错误，未编辑工作区或运行副本来切换版本。

独立只读审查核对了本次 11 行功能增量与真实框架路径，未发现明确 P1/P2；另行复跑新增专项 3/3（13.166 秒）、差异检查通过。确认 Provider 类型、原事件预算、runner.reset 解包和工具权限守卫保留，未见新增跨请求串用或预算绕过。结论限当前 AstrBot 4.29.1 与本次补丁，不外推其他框架版本或自定义 Context 复制行为。

## 本轮重新运行的结果

命令在开发仓库根目录执行，Python 使用 `D:\dsbot\venv\Scripts\python.exe -B`：

| 检查 | 实际结果 |
| --- | --- |
| `-m unittest discover -s tests -p test_repair_main_agent_context.py` | 3/3，13.175 秒，OK |
| `-m unittest discover -s tests -p 'test_repair_*.py'` | 160/160，71.355 秒，OK |
| `-m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | 2/2，OK |
| `node --test console/tests/repair-security.test.js console/tests/repair-state.test.js` | 12/12，零失败 |
| plugin/tests Python AST | 44 份通过 |
| `node --check console/server.js`、`console/state-bridge.js`、页面内嵌脚本 | 两份 JS 文件及一份内嵌脚本通过 |
| 交付 manifest、补丁 SHA256、补丁反向应用检查 | 追加本记录前全部通过 |
| `git diff --check` | 通过，验收文档落盘后再次核对 |

全集包括既有 F01—F08、第四单图片/预算/来源及发送截止回归；没有扩展本次结论为项目所有功能或其他框架版本均已验证。asyncio 的个别测试耗时提示没有测试失败，也不用于推导生产性能。

## 当前状态与下一步

Context 类型错误在本次源码和离线验证范围内关闭。未提交、未推送、未部署；运行实例尚未更新，真实聊天恢复、客户端到达、费用、热重载及长期稳定性待后续授权上线与实测。上线时须使内存适配器实际加载新版本，不能仅覆盖磁盘文件便宣称生效；配套与回退要求沿用补修记录。
