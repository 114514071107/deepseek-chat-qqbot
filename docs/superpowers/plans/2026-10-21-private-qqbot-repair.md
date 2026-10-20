# 自用 QQ 机器人修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans for inline execution, or subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 修复已确认的 13 项缺陷，让现有 AstrBot QQ 机器人适合自己和朋友稳定使用。

**Architecture:** 保留 AstrBot 插件和 Node.js 控制台。在现有模块上修正访问校验、任务生命周期、状态同步与发送结束路径；只为公共逻辑提取小型辅助模块。独立语音服务继续作为可选组件。

**Tech Stack:** AstrBot 4.29.1、Python 3.12、uv/venv、QQ 官方 Bot API、Node.js 原生 HTTP、可选 GPT-SoVITS。

**Spec:** `docs/superpowers/specs/2026-10-21-private-qqbot-repair.md`

## Global Constraints

- 继续使用 AstrBot 插件，不迁移 Agent 框架，不新增外部数据库或云服务。
- 保留 QQ 官方接入与当前人设玩法。
- 全部测试使用临时数据与模拟网络/发送端；不访问真实密钥和聊天记录。
- 不以模板覆盖 `D:\dsbot\data` 或现有 `dsh_data`。
- 每批先写失败测试，再实现、验证和提交。
- 未通过全部相关检查，不部署到本机运行副本；部署保留备份与回退路径。

## Review Focus

- 网络抓取在多次重定向、DNS 结果改变和响应过大时都不能越过访问边界；Task 1 覆盖这些输入。
- 禁用/重载发生在模型等待或延迟发送期间时，旧任务必须退出；Task 2 覆盖中途终止。
- 管理操作与新消息、闹钟同时发生时不能恢复旧数据或丢掉新操作；Task 2 覆盖交错执行。
- 纯图片、纯表情和语音失败不能留下无响应或污染下一轮；Task 3 覆盖无文字结果链。
- 重启或客户端断连后不能留下不可用服务或临时音频；Task 4 覆盖这些异常结束。

---

## Task 1: 访问边界（R01、R02、R12）

**Files:** `plugin/astrbot_plugin_dsh_soul/main.py`、新增同目录 `network_safety.py`、`console/server.js`；新增 `tests/test_network_boundaries.py`、`tests/test_gallery_permissions.py`、`console/tests/server.test.js`。

**Interfaces:**
- `network_safety.fetch_public_bytes(url: str, *, max_bytes: int, timeout: float) -> bytes`：只允许公网 HTTP(S)，每跳检查并绑定已校验的连接地址，最多 5 次重定向；限制读取量。
- 控制台保留现有 API 路径；为页面和 API 统一添加本机访问认证，写接口同时检查同源及 JSON 内容类型。浏览器登录后沿用当前页面操作。
- `retag_sticker/delete_sticker` 仅主人可调用，普通用户请求的工具集合中剔除这两项。

- [ ] 写失败测试：公网到内网重定向被拒、混合公网/私网 DNS 被拒、超限正文中止；无凭据请求不能读记录或改开关；跨源写请求被拒；普通用户不能改图库且主人仍可操作。
- [ ] 运行并确认失败：`python -m unittest discover -s tests -p test_network_boundaries.py`、图库对应测试、`node --test console/tests/server.test.js`。
- [ ] 实现上述访问校验，默认继续监听本机；认证凭据只保存在运行目录，不写入源码。
- [ ] 重跑本任务测试并检查 `node --check console/server.js`、`git diff --check`。
- [ ] 提交：`fix: protect network tools and local management access`。

## Task 2: 生命周期、状态与闹钟（R03、R04、R05、R10）

**Files:** `plugin/astrbot_plugin_dsh_soul/main.py`、`console/server.js`；如需共享状态辅助模块则放在核心插件目录；新增 `tests/test_plugin_lifecycle.py`、`tests/test_runtime_state.py`、`tests/test_alarm_delivery.py`。

**Interfaces:**
- `_spawn_task(coro) -> asyncio.Task` 统一记录插件后台任务；`terminate()` 取消并等待全部任务结束，包括循环、延迟发送和外包任务。
- 用户历史、念头、休眠与黑名单由运行插件统一应用管理变更；控制台不能在插件继续使用旧内存时声称操作已生效。
- 清历史明确覆盖该用户的滚动历史和归档；不暗中删除长期记忆，界面标明清理范围。
- 闹钟按 ID 原子更新，不跨网络 await 保存旧列表；超过本轮发送限额的到期项排队，不依赖严格相等的分钟判断。

- [ ] 写失败测试：禁用后无发送、重载旧实例不回写；清记录/删念头不被另一用户的更新恢复，解除休眠立即生效；发送期间新增与取消闹钟均保留；四个同分钟闹钟分批全部送达。
- [ ] 分别运行生命周期、状态和闹钟测试，确认旧实现失败。
- [ ] 实现任务管理及单一状态变更路径，保持现有数据格式可读，不清空已有用户数据。
- [ ] 重跑本任务与 Task 1 的接口测试，检查普通聊天和控制台操作兼容。
- [ ] 提交：`fix: synchronize runtime state and preserve scheduled reminders`。

## Task 3: 回复路径（R06、R07、R08、R09）

**Files:** `plugin/astrbot_plugin_dsh_soul/main.py`；新增 `tests/test_message_delivery.py`。

**Interfaces:**
- 使用可靠的请求结束路径清理生成状态；图片、文字、语音均调用同一结束逻辑，不依赖文字发送回调。
- TTS 生成或发送失败回退原文字；历史只记录已成功发送的内容。
- 攒批缓冲同时携带文本和媒体，补发图片进入主请求的 `image_urls`，不只留下历史占位。
- 纯表情回复在本轮直接产生有效发送，不残留到下一轮。

- [ ] 写失败测试：语音成功后 90 秒内下一条正常回复仍发出；TTS 失败有文字回退；先问后补图的主请求包含图片；纯表情当轮送达且下一轮无遗留图。
- [ ] 运行 `python -m unittest discover -s tests -p test_message_delivery.py`，确认旧路径失败。
- [ ] 修改发送与结束路径；沿用 Task 2 的任务登记，不重新引入未管理任务。
- [ ] 重跑本任务、生命周期及状态测试，检查两条气泡间被新消息打断仍有效。
- [ ] 提交：`fix: deliver voice image and sticker replies reliably`。

## Task 4: 控制台重启、TTS 清理与本机验收（R11、R13）

**Files:** `console/server.js`、`tts/tts_server.py`、`MODIFICATIONS.md`、`DEVELOPMENT.md`；新增 `tests/test_tts_cleanup.py`，扩充 `console/tests/server.test.js`。

**Interfaces:**
- 重启先释放旧监听端口，再启动新实例；Task 1 的本地认证配置在重启后继续生效。
- WAV/MP3 输出绑定响应结束清理回调，失败与断连也清理临时文件；不删除用户参考音频或模型。
- 所有修复逐项回填审查清单，并记录仍需用户实际 QQ 验证的项目。

- [ ] 写失败测试：随机端口自重启后服务可达且保留认证；WAV/MP3 响应发送完成、失败及断连后临时输出被清理。
- [ ] 运行对应 Node/Python 测试，确认旧实现失败。
- [ ] 实现修复并补充变更与本地认证的使用说明。
- [ ] 运行全部 Python/Node 测试、Python 编译、JS 语法与 Git 差异检查；独立复核整批修改。
- [ ] 提交：`fix: restart console safely and clean temporary speech output`。
- [ ] 为 `D:\dsbot` 的相关代码建立备份，保留真实部署参数，更新插件与控制台代码；只重启本实例，检查插件加载、QQ 连接及两个管理界面，记录回退步骤。

## 实施方式建议

建议由当前会话直接逐批实现，最后做一次独立代码复核。核心问题多处共享同一个插件文件，顺序实施便于控制改动和减少冲突。若用户选择分工实施，则按文件边界拆任务并执行逐批复核。
