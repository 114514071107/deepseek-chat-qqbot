# 第四单 P2 补修复验：源码与离线验收通过

日期：2026-10-23（Asia/Shanghai）。用户请求：继续验收已补修的两项 P2。

结论：**两项原 P2 均关闭，第四单 F10/F11/F12 的源码与离线验收通过。** 在本次补修及相关回归范围内没有发现新的可实证 P1/P2 阻断。此结论不表示真实 QQ 效果、客户端到达、实际费用或长期稳定性已经验收。

## 版本和范围

- 开发仓库 `D:\DSH Workspace\deepseek-chat-qqbot`，分支 `dev`，HEAD `7de42465dd9a491d4e8d0df9604c88f55ab51eec`，仍为未提交差异。
- 复核[补修记录](2026-10-23-workorder-4-p2-fix.md)、相对原交付的三个功能源码文件增量、完整第四单补丁及正式回归。原“暂不通过”记录保留，以下为补修后的新结论。
- 更新本次验收文档之前，`local/workorder-4-p2-manifest.json` 的 **27 个文件 SHA256 及补丁 SHA256 全部匹配**，`git apply --reverse --check local/workorder-4-p2-review.patch` 退出 0。评审补丁 SHA256 为 `6357fa1ca3985148f5ee303ceb846b8c8666eeef10228ef5bb5df8dac3b5ef0a`。随后仅追加验收文档与工作单状态，不改写原快照或 manifest；原快照中的文档哈希不覆盖这些后续追加。
- 本轮只读检查功能源码和测试，运行隔离离线验证并更新文档；没有修改功能源码、正式测试、真实配置/数据、依赖或运行副本，没有暂存、提交、推送、部署、重启或真实 QQ/模型请求。F09 继续暂缓。

## 两项缺陷的关闭依据

### P2-1：补图来源绑定原事件，关闭

`_record_user_turn` 强制接收并验证原事件的不可变 Scope，gate 十处 user 历史入口均显式传入；历史来源不再取跨 await 后可被覆盖的最后消息快照。

原验收探针未经改写直接复跑，退出 0，实际消息 ID 为 `['slow-first', 'slow-later']`。正式回归覆盖“补图读取慢于首条 inject”和“首条图片读取慢于补充消息 gate”两个顺序，并检查落盘滚动历史、群历史、归档、较早记录压缩及真实 recall 输出的消息来源。上述回归均通过，关闭原 P2-1。

没有迁移或修补真实旧记录，也没有声称能够推断历史中已经写错的消息来源。

### P2-2：发送及媒体共享原截止，关闭

核对 `_send` 显式传入原 Budget、构造器媒体回调使用缓存中的同一 Budget、QQDelivery 的任务局部预算与实际 HTTP dispatch 标记，以及线程排队后的实际开工检查。原截止探针退出 0：**过期后媒体准备 0 次、替身 POST 0 次、accepted=False**。

专项覆盖发送前过期、凭据锁等待、媒体准备/读取/上传、认证后和 pending 账本写入后跨截止、executor 排队及实际线程开工。媒体阶段计时关联原 request_id。确认 deadline 不走文字回退，真正媒体失败在预算仍有效时保留既有有限回退路径。

独立只读复核另外运行五类场景，均退出 0：

1. 单媒体槽饱和后排队至过期：skipped/deadline，parse 0 次、HTTP 0 次，等待数归零且槽恢复。
2. 已开始同步 worker 被取消：原线程结束之前保留槽，零排队配置拒绝替代工作；原线程结束后新任务可执行。
3. 真实 `request_once` 的慢认证替身：skipped/deadline，HTTP 0 次，回复凭据不关闭。
4. 真实 `request_once` 已进入替身 HTTP 后超时：unknown/deadline，HTTP 1 次，关闭凭据且无重试。
5. 真实 `request_once` 已解析 accepted 时预算越界：accepted 保留，HTTP 1 次，不因事后过期改写为失败。

以上均使用固定样例、临时数据或替身传输，关闭原 P2-2 的源码与离线验收。

## 本轮重新运行的结果

命令从开发仓库根目录执行，Python 为 `D:\dsbot\venv\Scripts\python.exe -B`：

| 检查 | 实际结果 |
| --- | --- |
| `-m unittest discover -s tests -p test_repair_workorder4_p2.py` | 17/17，10.383 秒，OK |
| `local/workorder-4-acceptance-provenance.py` | 退出 0，原来源探针通过 |
| `local/workorder-4-acceptance-deadline.py` | 退出 0，原截止探针通过 |
| `-m unittest discover -s tests -p 'test_repair_*.py'` | 157/157，54.808 秒，OK |
| `-m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | 2/2，OK |
| `node --test console/tests/repair-security.test.js console/tests/repair-state.test.js` | 12/12，零失败 |
| 全部 plugin/tests Python AST | 43 个文件通过 |
| 两份控制台 JS 与页面内嵌脚本语法 | 通过，内嵌脚本 1 份 |
| `git diff --check` | 通过，记录落盘后再次核对 |
| 独立只读复核 | 专项另外复跑 17/17，10.729 秒；上述额外五类场景通过 |

全集包含前三单的来源隔离、工具权限、固定目标、取消、删除、发送和持久化回归。部分 asyncio 调试耗时提示没有导致测试失败，不据此推导生产延迟。此次未重新测量吞吐、压缩字符、token 或账单，相关解释沿用[第四单交付](2026-10-23-workorder-4.md)。

## 当前状态与后续边界

第四单已通过本次源码与离线验收；原两项 P2 关闭。未提交、未推送、未部署，未合入 main。按本单“不自动提交推送”保持现状，验收不自动触发发布。

真实 QQ 的识图质量、客户端到达、媒体/语音播放、应用权限、热重载、真实网络超时、费用和长期稳定性仍需后续授权实测。F09、其他暂缓政策及 F13—F16 未实施。
