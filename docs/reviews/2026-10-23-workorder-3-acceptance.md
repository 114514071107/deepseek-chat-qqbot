# 工作单 3：F06/F07 评审验收记录

日期：2026-10-23（Asia/Shanghai）。用户要求：验收现有交付。本轮只读审阅待审源码、运行隔离离线验证并新增本记录；未补修源码，未提交、推送、部署、重启或执行第四单，未发送真实 QQ 消息、启动 TTS、调用付费模型或访问真实聊天数据。

结论：**离线回归通过，完整源码验收暂不通过；1 项 P2 需补修，另有 1 项 P3 追踪一致性问题。** 未发现可实证的 P0/P1。真实 QQ 到达及长期稳定性仍未验收。

## 评审版本

- 仓库：`D:\DSH Workspace\deepseek-chat-qqbot`。
- 分支：`dev`；HEAD：`5641b0a1e01f76b55293fa427b319136f1f7b837`。
- 本次审阅对象：当前未提交差异及新增源码、测试，与交付说明及完整补丁对照。用户本轮说明不提交，故未根据旧常态规则补做提交。
- 完整补丁列出 20 个文件。按文件名排序，依次对“UTF-8 文件名、NUL、当前文件字节、NUL”累计计算 SHA256：`e288b08c039daf2e2a254b75f703c5489be1c8b1182d08b17c75f515aee186ec`。本验收记录不计入该快照。

## 需要补修

### [P2] 普通媒体发送成功后没有关联具体历史条目

位置：`plugin/astrbot_plugin_dsh_soul/main.py:1603`、`:1616`；同类入口为 `plugin/astrbot_plugin_dsh_soul/reply_integration.py:29`。

`ReplyPlan.others` 中的图片、录音或文件可在当轮送达发送入口，但接受后的 `_record_assistant_turn` 仅得到 `[媒体]` 或气泡文字，没有传入媒体引用。直接 `event.send` 适配也只保存纯文本或 `[媒体]`。只有专门的表情、语音动作分支传入了 `media`。

补充隔离复现载入真实 `capture/_complete_reply/_record_assistant_turn` 方法：构造纯图片结果链，发送替身返回 `accepted` 及消息 id。得到滚动历史 `text='[媒体]'`，`images/files/voice/sticker` 均缺失；归档中也没有媒体字段。现有 `test_nontext_response_and_preserved_components_are_consumed_in_current_plan` 只断言发送组件，没有断言历史媒体关联，因此全量绿色不能覆盖此缺口。

影响：已经接受的图片在控制台历史中无法回看具体内容，归档与群历史也无法还原是哪份媒体；不满足 F07“媒体关联具体请求/历史条目”的完成标准。这是普通结果链媒体入口的缺口，不否定专门语音和表情动作已有的关联修复。

补修要求：在统一历史写入前提取并保存安全、可回看的实际媒体引用，与本次接受结果、请求和条目关联；不可写入其他用户私有路径或将后续媒体挂到 uid 最后一条记录。纯媒体、文字加媒体及框架直接发送都应覆盖。失败/未知不写入已发送媒体，媒体失败后文字回退成功只记录实际文字。补充滚动、群历史及归档的字段一致性回归。

## 其他发现

### [P3] 历史与投递账本的 request_id 不统一

位置：`plugin/astrbot_plugin_dsh_soul/main.py:3185`、`:3197`；对照 `:3156` 及 `:1616`。

普通 `_record_assistant_turn` 调用默认写入空 `request_id`；气泡和语音计划传入 `plan.id`；投递账本记录的则是 `token.request`。有效请求上下文中直接写入一条 accepted 历史的隔离复现，确认历史 `request_id=''`，同时运行时请求 id 非空。

影响是同一轮的抢答、文件、气泡和投递账本不能统一通过 `request_id` 关联，排查部分成功与并发请求时容易误判。平台消息 id 仍可用于部分关联，因此不单独作为本轮拒收原因。建议以运行时请求 id 为统一字段，将计划 id 单列为 `plan_id`，并使历史中的投递信息可关联 `attempt_id`；按最终契约补充断言和交付说明。

## 本轮重新执行的验证

| 检查 | 本轮结果 |
| --- | --- |
| `D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_repair_*.py'` | 104 项，OK，34.768 秒 |
| 同解释器运行余额插件 `test_balance.py` | 2 项，OK |
| `node --test console/tests/repair-security.test.js console/tests/repair-state.test.js` | 10 项通过，0 失败 |
| 插件与测试目录全部 Python 文件 `ast.parse` | 32 个通过 |
| `node --check console/server.js`、`console/state-bridge.js` | 通过 |
| 控制台 HTML 的内嵌脚本提取至临时目录后 `node --check` | 1 页通过 |
| `git diff --check` | 通过 |
| 补充纯图片接受后的历史/归档检查 | 复现上述 P2 |
| 补充有效请求上下文中的历史请求 id 检查 | 复现上述 P3 |

独立只读评审另外检查了全部 `_send` 调用者、真实 AstrBot 媒体解析与 botpy HTTP 实现，并以替身验证两个发送器共享同一 context 并发八次：实际提交序号 `[1,2,3,4,5]`，五次 accepted、三次 skipped。未发现需新增报告的问题。

## 已核对的关键行为及边界

凭据、目标、共享序号和次数约束、未知结果不盲目重发、鉴权 await 后权限检查、上传后撤销、语音文字有限回退、纯表情当轮消费、请求清理与部分成功保存均已有本轮离线证据。平台接受与客户端收到的语义区分明确，磁盘分层保存失败没有触发 QQ 重发。

暂不判断以下行为，原因是超出本次离线验收授权或交付已明确暂缓：真实 QQ 权限与客户端到达、实际 event_id 支持范围及频控、真实语音转换和 TTS 服务、实际插件热重载及完整重启、生产数据迁移、长期运行、闹钟专项和主动失败后的长期政策。未用这些缺口推导已经上线或稳定。

后续只需针对本单补修并重新送验；本结论不授权推送、部署、合入 main 或执行第四单。
