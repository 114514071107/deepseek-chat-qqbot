# 工作单 3：普通媒体关联与请求追踪补修

日期：2026-10-23（Asia/Shanghai）。状态：源码补修及离线验证完成，待用户复验。原[验收记录](2026-10-23-workorder-3-acceptance.md)保持不改，不把“暂不通过”改成已经验收。

分支 `dev`，HEAD 仍为 `5641b0a1e01f76b55293fa427b319136f1f7b837`。承接原未提交成果，不覆盖前两单与第三单其他修复；按本轮延续的要求未提交、推送、部署、重启或操作真实配置、数据、依赖。没有真实 QQ/TTS/Kimi/付费模型调用，未执行第四单。

## P2：已接受普通媒体的具体引用

根因是普通结果链和框架直接发送只将文字交给历史入口；没有将本次媒体关联至 accepted 条目。初始新增回归复现纯图片和文字加图片的 `images` 缺失。

- `QQDelivery` 在取得消息 id 后，调用插件 `_retain_sent_media` 从实际上传的 `file_data` 保存副本，再将安全引用放在 `DeliveryResult.media`。普通图片、录音、文件和视频均按媒体类型映射为 `images/voice/files`，不将原始绝对路径、URL、查询凭据或上传 base64 放入历史或账本。
- 新副本为 `media/sent/<会话键>/<attempt_id>.<安全后缀>`，用既有 `_write_media` 登记当前会话的媒体索引。所有普通媒体均保存实际上传快照；不会因源已登记就引用可变原文件。新增“发送 await 期间原文件被改写”用例确认回看仍为已上传内容。
- DATA 内源必须属于当前会话媒体索引或共享图库，否则留存明确失败；不把另一人的私有原路径写入当前历史。DATA 外生成文件使用已经提交的内容留存，不在接受后再次读取原文件或下载。远程文件/视频在上传前用既有公网安全入口取得至多 20MiB 的内容，上传和保存使用同一份内容，不在接受后重新抓取变化后的资源。
- 统一 `_record_assistant_turn` 默认继承 `result.media`，所以纯媒体、文字加媒体、工具发文件和框架 `event.send` 都在同一条 accepted 历史中携带引用。滚动磁盘、群历史和归档保存相同条目 id 与媒体字段；失败/未知不产生已发送媒体，媒体失败后纯文字回退的新回执也没有旧图片引用。
- 媒体保存失败单独写入 `persistence.media=failed`，不将已知 accepted 改成发送失败，也不重发。保存前请求被撤销时停止写入；取消结果仍携带已知 accepted 和消息 id，标记媒体保存 cancelled，不覆盖为 unknown。未得到消息回执的取消仍按原未知规则处理。
- 原语音动作继续用原 WAV 的 `voice` 字段回放，原表情动作继续用图库 `sticker` 字段展示；这两个专门入口保留既有展示语义。实际上传的转换后语音（可能为 SILK）或图片快照保存在结果账本/媒体索引，并通过 attempt_id 关联，不将 WAV 宣称为实际上传编码。浏览器不支持的语音编码仍可下载，真实编码播放另行验收。

控制台沿用现有图片/语音展示，增加附件与语音文件下载入口。新增快照的非图片/音频格式只在 `media/sent` 内按 `application/octet-stream` + `Content-Disposition: attachment` 下载；原有其他目录扩展名限制、鉴权、Host/Origin 和路径边界保持。没有将 HTML 等文件按活动网页执行。

F08 的**媒体层**增加 `media/sent`，显式选择该层后可删除当前来源的副本；其他来源的索引和文件保留。没有增加自动清理或自动迁移。

## P3：统一请求与投递追踪

- 在有效运行时上下文中，assistant 历史的 `request_id` 统一取 `token.request`，与投递账本一致；调用者遗漏参数不再写空字符串。
- `ReplyPlan.id` 单列为历史 `plan_id`，不再冒充运行时请求 id。语音、表情和气泡使用同一契约。
- 历史 `delivery.attempt_id` 指向具体投递账本条目。没有触发请求 id 的独立后台发送，以该次 attempt_id 作为非空追踪键，历史和账本一致；不伪造一条已不存在的用户触发请求。

只影响新记录；不扫描、改写或猜测修复旧记录。原缺少图片引用的历史不能凭昵称、最后记录或时间接近补关联。

## 验证

新增 `tests/test_repair_media_history.py` 共 **9 项**；真实框架隔离测试追加普通图片、混合图片、直接发送图片分支；控制台追加 **2 项**渲染/受保护下载回归。

先取得图片关联、空 request_id、源文件替换、媒体目录删除、取消覆盖 accepted、控制台附件读取/显示的实际失败，再修复。独立只读复核发现的源快照和取消回执两项已加入上述回归并补修；没有把复核意见当成用户整体通过。

本轮执行结果：

| 命令/检查 | 结果 |
| --- | --- |
| Python `-B -m unittest discover -s tests -p 'test_repair_*.py'` | **113/113**，0 失败 |
| 余额插件 `test_balance.py` | **2/2** |
| Node `--test console/tests/repair-security.test.js console/tests/repair-state.test.js` | **12/12**，0 失败 |
| 插件及测试 Python `ast.parse` | **33 文件** |
| server.js、state-bridge.js 与页面脚本 `node --check` | 通过 |
| `git diff --check` | 通过 |

测试只用临时目录、虚构身份、替身发送与媒体接口。真实 AstrBot 类只在临时 cwd/ASTRBOT_ROOT/TEMP/TMP 子进程内导入；没有构造生产插件实例或读取生产聊天。新增回归断言实际文件字节、历史字段、消息 id、请求/计划/attempt id、分层删除以及失败不补发，覆盖了原先只有组件发送断言的缺口。

离线输出：`local/workorder-3-media-final.txt`；最新完整差异和文件校验清单：`local/workorder-3-media-review.patch`、`local/workorder-3-media-manifest.json`。这些本地材料不自动提交或推送。

## 配套部署与回退说明（未执行）

没有新增环境变量或真实配置。后续获准部署时，应配套更新 main.py、qq_delivery.py、state_store.py、控制台 server.js 与 index.html，并保留此前全部安全和生命周期辅助模块。旧版本整套备份及一致性数据备份仍按[原交付](2026-10-23-workorder-3.md)执行；媒体目录备份包含新增 `media/sent`。

回退需恢复同版源码，保留新媒体、索引和账本，不把 unknown 重放或给旧历史猜测挂图。无需生产数据迁移。真实 QQ 收到、实际浏览器交互、平台媒体兼容、真实 TTS/编码、热重载及长期稳定性仍需另行实测；本轮仅修复验收指出的范围。
