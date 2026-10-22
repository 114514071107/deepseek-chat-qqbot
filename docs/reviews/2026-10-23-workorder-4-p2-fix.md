# 第四单验收 P2 补修：补图来源与发送截止

日期：2026-10-23（Asia/Shanghai）。任务：修复[验收记录](2026-10-23-workorder-4-acceptance.md)中的两项已复现 P2。状态：源码补修及离线回归通过，待用户复验；保留原“暂不通过”的历史结论，不代用户关闭验收。

## 基线与实际操作

- 开发目录 `D:\DSH Workspace\deepseek-chat-qqbot`，分支 `dev`，HEAD 仍为 `7de42465dd9a491d4e8d0df9604c88f55ab51eec`。在已有第四单未提交差异上补修，没有回退、清理或覆盖前三单成果。
- 遵守用户第四单“不自动提交推送”的明确要求；未暂存、提交、推送、合入 main、部署或重启。共享 AGENTS 的常态提交规则不覆盖该单指令。
- 只修改开发源码、增加隔离回归及交付文档。未修改生产副本、真实配置/数据/依赖或 site-packages；未发送真实 QQ、调用真实或付费模型、启动 TTS/Kimi。F09、F13—F16 及其他暂缓政策未实施。
- 先运行两个原验收探针，均退出 1：来源实际为 `['slow-first','slow-first']`；已过期发送仍准备一次、POST 两次并返回 accepted。然后编写失败回归再修复；没有以原有 140 项通过替代缺陷验证。

## P2-1：历史显式绑定收到该条消息的事件来源

修改 `plugin/astrbot_plugin_dsh_soul/main.py`：`_record_user_turn(uid, text, images=None, files=None, *, scope)` 必须接收该事件绑定的不可变 `Scope`，并验证 `scope.key == uid`。gate 全部十处调用传入局部 `scope`，包含媒体、批次超额、控制/状态和安全拒答等入口。

历史条目的 `source` 直接取此 Scope，不在跨媒体 await 后读取 `self.scopes[uid]` 的最后事件快照。同一个条目及 id 仍写入滚动历史、当前群共享记录和归档；不更改会话键、权限、群/私聊隔离及媒体引用格式。

新增真实框架临时子进程回归，暂停点设于 `_save_inbox_images` 内部的真实图片读取边界，覆盖：

1. 补图读取尚未结束时，首条消息 inject 重新绑定来源。
2. 首条图片读取尚未结束时，补充消息先完成 gate。

两种顺序均断言滚动历史落盘、当前群历史落盘、归档、较早记录压缩的消息标识及真实 recall 输出分别对应首条和补图。图片读取及所有历史均使用固定测试图片、虚构身份与临时目录。

## P2-2：发送阶段共享原请求预算

修改 `main.py`、`qq_delivery.py` 和 `resource_budget.py`：

- `_send` 获取同一个原请求 Budget，交给 `QQDelivery.send(..., budget=budget)`；构造器中的媒体回调给 `Resources.run` 传入同一个请求的缓存 Budget。prepare/upload 的媒体计时与 send 计时均关联原 request_id，不能在发送时重新开始一轮预算。
- QQDelivery 用任务局部 ContextVar 绑定 Budget。等待凭据锁、解析/转换、媒体读取、上传及消息请求均检查原截止；媒体和消息等待使用剩余技术截止。默认纯文字不占媒体池，但仍检查截止。
- HTTP 认证等待完成后、创建真实 HTTP POST 前再次检查预算；认证耗尽预算时返回“未开始”的跳过结果，不调用消息接口。上传成功后仍须检查预算，不能凭上传成功发出过期消息。
- 消息阶段另外绑定任务局部的实际 dispatch 标记：认证等待被超时取消时未 dispatch，结果为 skipped 且不关闭回复凭据；真正调用 HTTP request 后才按 unknown 处理。对自定义传输器，进入其调用后保守视为在途；官方 request_once 能细分认证和 HTTP 边界。
- `Resources.thread` 在异步 worker 获得运行机会及实际线程调用 fn 前重新检查原预算和媒体阶段截止；调用端退出后撤销 active 标记。即使共享 executor 把线程排队到调用端已经超时，也不能再开始媒体读取。已开始的阻塞工作无法被 asyncio 强杀，其槽位继续保留至真正结束，不提前释放以接纳无限替代工作。
- 超时类别依据实际 timeout 上下文是否触发，避免 Windows 计时器可能稍早唤醒时将本轮 deadline 错分为普通 network/media 失败而触发回退。
- 新的 `category=deadline` 与 QQ 凭据过期 `category=expired` 分开。消息尚未开始时是 `skipped`；消息请求已交出且超时是 `unknown`，关闭本次被动凭据后不重试、不降级主动路径。写 pending 账本时跨过截止但尚未调用消息请求，也保持 `skipped`。
- 已取得带消息 id 的 accepted 结果不会因返回时越过截止被改写。媒体留存/历史持久化仍独立反映，不把预算的事后检查套在整个发送操作上。
- 真正的媒体错误且预算仍有效时保留原有限文字回退；deadline 不触发文字回退。回退如被调用仍通过相同 `_send`、预算、权限、生命周期、次数和路由检查。

`budget` 是可选参数，独立 QQDelivery 替身或原 F06 测试可以不提供；插件正式发送总是显式提供。没有修改 QQ API 字段、添加重试或制定主动无权限后的长期政策。

## 离线证据

新增 `tests/test_repair_workorder4_p2.py`：17 项（15 项发送/线程预算边界、2 项真实框架来源竞态）。测试执行实际 `_send/_budget/_thread`、实际构造器媒体回调及 QQDelivery；传输全部替换。原验收脚本保留未改。

新增初版 8 项回归在补修前为 7 失败、1 通过（通过项保护已有 accepted 行为）；追加边界回归又实证了媒体读取等待和 pending 账本跨截止两条未保护路径。按 requesting-code-review 技能做独立只读复核时，还实证认证等待超时误记在途、异步/线程 executor 排队后过期仍新开工；分别补失败回归并修复，最终专项 17/17。

仓库根目录运行：

```powershell
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p test_repair_workorder4_p2.py
& 'D:\dsbot\venv\Scripts\python.exe' -B local/workorder-4-acceptance-provenance.py
& 'D:\dsbot\venv\Scripts\python.exe' -B local/workorder-4-acceptance-deadline.py
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p 'test_repair_*.py'
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py
node --test console/tests/repair-security.test.js console/tests/repair-state.test.js
node --check console/server.js
node --check console/state-bridge.js
git diff --check
```

| 本轮最终验证 | 实际结果 |
| --- | --- |
| 新增专项 | 17/17，OK |
| 原来源探针 | 退出 0，消息来源为 `['slow-first','slow-later']` |
| 原截止探针 | 退出 0，过期后准备 0 次、POST 0 次，非 accepted |
| Python 全部修复回归 | 157/157，53.921 秒，OK |
| 余额插件 | 2/2，OK |
| Node 离线回归 | 12/12，零失败 |
| plugin/tests Python AST | 43 个文件通过 |
| 两份控制台 JS 与页面内嵌脚本 | 通过，内嵌脚本 1 份 |
| 差异空白检查 | 通过，交付文档落盘后再次检查 |

Python 全集含 F01—F08 的实际权限、隔离、固定目标、取消、历史/媒体留存、回退与删除交错回归。asyncio 调试模式输出了部分测试任务超过 100ms 的耗时提示，没有测试失败；不据此宣称生产延迟改善。

原始离线输出保存在忽略目录 `local/workorder-4-p2-*`，含 RED、GREEN、原探针与 `python-final.txt`；不纳入源码发布。此前 `local/workorder-4-review.patch` 及其 manifest 保留为原交付快照。本次没有重新测量吞吐、压缩字符、token 或账单，原测量及边界仍按[第四单交付](2026-10-23-workorder-4.md)解释。

可复验快照为 `local/workorder-4-p2-review.patch`（相对当前 HEAD 的完整第四单差异，含原验收记录）、`local/workorder-4-p2-manifest.json`（27 个文件哈希及补丁哈希），以及 `local/workorder-4-p2-source-only.diff`（相对原第四单交付的三个功能源码文件增量）。补丁反向 `git apply --reverse --check` 退出 0；这些材料不代表本地已提交。

独立只读复核最终另外运行专项 **17/17，10.021 秒，OK**；慢认证探针得到 skipped/deadline、0 HTTP、凭据未关闭，executor 排队探针实际 worker 启动记录为空。另用四个替身探针核对：预算充足的媒体失败只有一次文字回退；预算过期、权限撤销或 Runtime 停止后不发回退 POST。复核结论为限定补修范围没有剩余阻断，可交用户复验；未代用户验收，没有修改源码/索引/HEAD或调用真实服务。

本轮没有扩展重构 `_record_assistant_turn` 的既有 source 语义；P2-1 针对入站事件原始来源，十处 user 历史入口全部使用显式 Scope。`_group_append` 从同一 Scope.key 对应缓存取群键时，消息 ID 变化不改变群归属。本轮不据此宣称整个项目所有旧来源语义已重新验收。

## 兼容、部署前要求与遗留

- 不迁移或修补已有历史；已经错误归属的旧记录不能靠最后消息猜回来源。若以后需要修复真实旧档，须单独依据可靠消息证据安排。
- 新记录 source 格式、框架实际发送投影、插件历史、归档和媒体删除层均保持兼容；只修正新接收消息的来源。内部 `_record_user_turn` 调用必须带 Scope；第三方若调用此私有方法需同步。
- QQDelivery 的 `budget`、`deadline` 结果类别需与 main.py 配套。发布时仍应使用完整同版第四单模块，不单独复制 main.py；不需要新增配置项或更改本轮预算默认值。
- 本次未生产操作。若后续获准发布，先备份同版运行代码、真实参数、插件/框架数据；SQLite 使用一致性备份保留 WAL/SHM。备份仅留受保护本机目录。回退恢复整套同版代码，不覆盖上线后新聊天，不重放 unknown，不恢复已删除数据；原第四单摘要兼容风险仍按其交付记录处理。
- 真实 QQ 到达、实际补图识别质量、媒体/语音播放、应用权限、框架热重载、真实网络超时和长期稳定性未验证。接口 accepted 只表示平台接受，不能称客户端收到。

下一步：用户按新源码和新增回归复验两项 P2，再决定后续发布。F09 继续暂缓。

## 后续复验结论（2026-10-23）

用户要求继续验收后，重新运行专项 17/17、Python 全集 157/157、余额 2/2、Node 12/12、两个原验收探针及语法/差异检查均通过；独立只读复核的额外五类发送/取消场景通过。两项 P2 关闭，第四单源码与离线验收通过。证据见[补修复验记录](2026-10-23-workorder-4-p2-reacceptance.md)。本段为后续状态，不改写前文交付时“待复验”的历史事实；未提交、推送、部署或真实 QQ/模型调用，F09 继续暂缓。
