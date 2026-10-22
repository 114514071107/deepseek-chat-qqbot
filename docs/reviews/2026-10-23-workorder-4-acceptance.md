# 第四单验收复核：需补修两项 P2

日期：2026-10-23（Asia/Shanghai）。用户请求：验收已交付的 F10/F11/F12。

结论：**本轮暂不通过源码与离线验收**。原有回归全部通过，但新增验收探针实证两项 P2，需补修并复验。F09 继续暂缓；真实 QQ 效果、到达、费用、热重载及长期稳定性仍未验收。

## 评审版本与操作范围

- 开发仓库 `D:\DSH Workspace\deepseek-chat-qqbot`，分支 `dev`，HEAD `7de42465dd9a491d4e8d0df9604c88f55ab51eec`，评审对象为其上第四单未提交差异，包含四个新增模块及配套测试。
- 在更新本次评审文档之前，`git apply --reverse --check local/workorder-4-review.patch` 退出 0，确认交付补丁与当时工作区匹配。本次文档追加不在原交付补丁中。
- 阅读工作单、交付记录、计划、实际差异与本机 AstrBot 4.29.1 相关源码；按代码审查技能另做独立只读复核，并用隔离探针验证结论。
- 本轮没有修改功能源码、既有测试或生产文件。只新增验收记录、本地忽略的复现脚本并同步工作单状态；没有暂存、提交、推送、部署、重启、安装依赖、真实 QQ 发送或真实模型调用。

## P2-1：补图来源在等待期间被首条消息覆盖

位置：`plugin/astrbot_plugin_dsh_soul/main.py:3190–3195`，关联 `_scope:1252–1262`、`_source:1264–1265`、`_record_user_turn:3340`。

触发顺序：

1. 首条消息 `slow-first` 已通过 gate。
2. 同作用域补图 `slow-later` 进入 `_save_inbox_images`，其来源已登记，随后在实际图片读取等待处暂停。
3. 首条消息进入 inject；其 `_scope(event)` 将共享的 `self.scopes[uid]` 改回 `slow-first`。
4. 补图读取完成，gate 调用 `_record_user_turn`；它经 `_source(uid)` 读取共享快照，因此将补图也写成 `slow-first`。

实证：真实框架、真实图片组件及真实插件方法，固定小图片和临时数据，期望两条历史的消息 ID 为 `['slow-first', 'slow-later']`，实际为 `['slow-first', 'slow-first']`。图片仍进入模型，因此现有“图片内容块存在”断言通过；历史、归档及后续压缩/recall 的来源却指向错误消息，不满足 F12 的可核验来源要求。

复现（仓库根目录）：

```powershell
& 'D:\dsbot\venv\Scripts\python.exe' -B local/workorder-4-acceptance-provenance.py
```

退出 1，断言 `supplemental image archived under first message ID` 失败。探针在内存中扩展既有框架测试，将暂停点置于 `_save_inbox_images` 内部读取处；不改写原测试。不应把暂停放在调用该方法之前，否则装饰器再次绑定来源会掩盖竞态。

补修要求：历史记录使用该事件绑定的不可变来源；不要在跨 await 后取作用域的“最后消息”快照。回归同时断言滚动历史、归档、压缩及检索来源，并覆盖首条图慢于补充消息、补图慢于 inject 两种顺序。

## P2-2：发送媒体准备/上传绕过原请求截止

位置：`plugin/astrbot_plugin_dsh_soul/main.py:1353–1354`，关联 `_send:1303–1308` 和 `qq_delivery.py` 的准备、上传、消息发送路径。

`media_run` 调用 `Resources.run` 时没有传入本轮 budget；`_send` 只创建计时器，也不检查 budget 截止。QQDelivery 的生命周期检查不能代替时间预算检查。因此原请求的 `resources.deadline` 已过期时，仍可开始新的媒体准备、上传和消息发送；这些媒体阶段的计时也没有请求 ID。

独立离线探针使用 AST 提取的真实 `_send/_budget` 和真实 QQDelivery，配置 `deadline=.01`、`media_timeout=.2`，先等待 `.02` 秒使预算过期，再执行耗时 `.04` 秒的替身图片准备。结果仍执行上传及消息两次替身 POST，返回 accepted；媒体计时的 `request_id` 为空。全部为本地替身，无真实网络。

复现脚本：`local/workorder-4-acceptance-deadline.py`。补修要求：让发送媒体阶段共享原预算和剩余技术截止，在过期后拒绝发起新操作，并保留 F06 对已开始消息 POST 的 unknown/不重发语义。增加“进入发送前已过期”和“准备期间跨越截止”的回归，核对阶段记录关联原请求。

## 本轮重新运行的验证

| 验证 | 实际结果 |
| --- | --- |
| `python -B -m unittest discover -s tests -p 'test_repair_*.py'` | 140/140，50.055 秒，OK |
| 余额插件 `test_balance.py` | 2/2，OK |
| Node 两份 repair 测试 | 12/12，零失败 |
| 全部 plugin/tests Python AST | 42 个文件通过 |
| `console/server.js`、`console/state-bridge.js` 与页面内嵌脚本语法 | 通过（内嵌脚本 1 份） |
| `git diff --check` | 通过（文档落盘后再次检查） |
| 原交付补丁反向应用检查 | 文档追加前退出 0 |
| 来源竞态探针 | 退出 1，实证 P2-1 |
| 发送截止探针 | 已过期仍 accepted，实证 P2-2 |

测量脚本 `tests/workorder4_measure.py` 重新运行成功：固定替身负载的前台/后台峰值从 5/6 变为 2/1，总耗时 44.60 → 222.11ms；合成归档同步扫描心跳最大间隔 77.10–92.84ms，有界线程扫描 15.19–16.69ms。压缩内容仍为 8648 字符，JSON 9274 字符，摘要模型调用 1 → 0。结论与原记录一致：并发限制在饱和负载下增加排队，归档改善事件循环响应性；没有实际 token、账单或整体提速证据。

## 当前状态与接手步骤

本轮是验收评审，**没有代为修复上述源码问题**。保留作者交付和独立评审的历史结论，本记录为后续新发现。先补修两项 P2、将探针固化为回归，再复跑相关测试与全集并交付新差异供复验。按本单“不自动提交推送”保持现状；验收结论不授权生产操作或解除 F09 暂缓。

## 补修后复验（2026-10-23）

用户交付补修后，两项原验收探针均退出 0，专项 17/17、全集 Python 157/157、余额 2/2、Node 12/12 及语法/差异检查通过。两项 P2 均已关闭，第四单源码与离线验收通过。详见[补修复验记录](2026-10-23-workorder-4-p2-reacceptance.md)。本文件前文保留原验收时失败事实；未提交、推送或部署，真实 QQ 与长期稳定性仍未验收，F09 继续暂缓。
