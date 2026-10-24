# d31827c 独立复验与真实 QQ 验收

日期：2026-10-25（Asia/Shanghai）。待验收分支 dev，功能提交 `d31827c4462126a9156e0f1801f861953a7bc901`，开工工作区干净。

**A 的原长消息顺序 P2 关闭，源码、离线和本轮四个真实 QQ 用例通过。B 源码/API/隔离浏览器通过，生产人工关联/解除因电脑工具强制停止未验完；整单尚未通过完整验收。**

## 规则、授权与源码审阅

按用户提醒重新阅读全文 `D:\dsbot\repair-workorders\AGENTS.md`，检查开发仓库及上级实际规则（未发现新增适用 AGENTS.md）。遵守源码审阅、离线复验、版本核对、Bot 启动就绪、真实 QQ 的顺序，沿用本验收任务已有部署/启动及指定测试账号、测试群和机器人私聊许可；未派生代理。

审阅 `5c8844c..d31827c`：gate 额外保留请求内完整 `count_text`，首次 inject 按真实到达顺序形成 `_dsh_sticker_inputs`；完整当前正文仅一次，同 message_id 副本排除，不按文字去重；预算从固定快照计算，未 inject 时保留当前正文兜底。未扩大模型/历史正文存储，既有入队、ReplyPlan、发送上限和失败/unknown 语义不变。B 相对 `5c8844c` 无实现差异。本轮未发现需要阻断的源码问题，没有修改产品实现或原断言。

## 实际离线复验

工作目录为开发仓库，Python 使用既有 `D:\dsbot\venv\Scripts\python.exe -B`。

| 命令/检查 | 本轮结果 |
| --- | --- |
| `-m unittest discover -s tests -p acceptance_sticker_count_order_20261025.py -v` | 原顺序探针 **3/3，0.596 秒**，长正文三改二四层均为 2 |
| `-m unittest discover -s tests -p test_repair_sticker_count_order.py -v` | 顺序集合 **9/9，2.059 秒**，包含原三项 |
| `-m unittest discover -s tests -p test_repair_sticker_count.py -v` | 数量专项 **12/12，2.097 秒**，含原重复轮次三项 |
| `-m unittest discover -s tests -p 'test_repair_*.py' -v` | **226/226，190.938 秒，退出 0**；实际输出 pwsh.exe/powershell.exe 两套启动器矩阵 |
| `-m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | **2/2** |
| `node --test console/tests/repair-security.test.js console/tests/repair-state.test.js console/tests/repair-workbench.test.js` | 首跑 **22/22，1319.6256ms**，无失败/跳过 |
| 既有 `local/count-users-reacceptance-browser.cjs` | 隔离 Edge **17 项通过，JS 异常 0**，不覆盖提交内合成截图 |
| 静态/差异 | **60 份 Python AST、7 个 JS/CJS、1 段页面脚本**语法通过；`git diff --check` 通过 |

完整 Python 日志为忽略目录 `local/count-order-reacceptance-2026-10-25-python.txt`。浏览器使用已有 bundled Playwright、现有 Edge 和临时合成根，不安装依赖。独立运行数量与顺序专项不额外计入 226 项。

## 运行准备与发布

运行文件仍 26/26 匹配旧 `1da1746`。旧 `.launcher` 记录中的两个 worker 均已退出，6185/7850 无监听，精确运行命令筛选未发现目标实例进程；因此本轮记为**启动新实例**，不伪称重启。旧退出原因本轮未调查，RQ04 不因此关闭。

按既有发布流程备份及配套安装 `d31827c`，包含 B 的两个新模块；**390 份停写快照逐份校验，28 个清单文件、7 份变更，安装后 28/28 哈希一致**。开发及暂存语法、秘密扫描通过；保留部署常量和原配置/凭据，无数据迁移。Bot worker 于 **05:46:03** 启动，Console 于 **05:46:13** 启动，精确进程身份匹配；插件 loaded hook、AstrBot started、QQ websocket 启动可见，后续真实入站/回复证明 QQ 链路可用。

收尾认证状态 bot_running=true，管理心跳年龄 **0.09 秒**，6185/7850 监听，28/28 运行哈希仍匹配。认证首页 200，无认证 people 401，认证跨来源 403，新 people API 正常。框架配置、插件 dsh_soul_conf、runtime.json 和加密凭据保持原哈希。备份、清单、对应源码包、activation/final-health/qq-results 及回退材料保存在受保护本机目录 `D:\dsbot\deployment-backups\20261025-sticker-count-order-release`；详见[发布及回退记录](../releases/2026-10-25-sticker-count-order.md)。

## A：真实 QQ 用例

从原生 QQ 资料卡重新核对指定测试账号、指定群及机器人私聊对象；仅操作该测试账号，群聊使用实际机器人提及。采用合成输入，不复制身份原值或正文到 Git 文档。等请求 finished 后逐屏滚动核对实际图片及其前后气泡，再关联 request、plan、历史和回执，不仅看接口成功。

| 用例 | 客户端实际显示 | 后台及来源 |
| --- | --- | --- |
| P01 私聊明确两张 | **2 图，0 额外文字/语音**；完整滚动确认请求至第一图无等待气泡 | finished，1 个 plan，2 条 accepted 历史及回执 |
| P02 下一普通私聊 | **1 条正常反馈 + 1 条主答，0 图**；不继承纯表情静默 | finished，1 个 plan，2 条 accepted 历史及回执 |
| G01 群聊完整长正文末尾更正 | 原生 QQ 输入 **2308 字**，开头三张、2000 字以后末尾改两张；**实际 2 图，0 额外文字/语音**，逐屏确认末尾更正和第一图/第二图 | finished，1 个 plan，2 条 accepted 历史及回执；持久历史仍按既有上限保留 2000 字 |
| G02 群聊单张对照 | **1 图，0 额外文字/语音**，请求与图片之间无等待气泡 | finished，1 个 plan，1 条 accepted 历史及回执 |

总计四个测试输入、**5 图 + 2 文、7 条 accepted**；四个请求均结束，同请求助手记录与入站来源完全一致。群测试前后私聊历史序列 SHA256 相同，未错投私聊。真实 failed/unknown 不主动制造，相关语义由离线回归覆盖；真实多群及实际管理写操作不因这些用例被视为通过。

## B：生产界面阶段及强制停止

真实 Console 已加载同版用户工作台，17 个来源保持 17 个独立入口，旧档明确未关联；默认私聊/群聊、来源说明及具体来源管理入口可见。根据本轮指定测试账号实际发起的两类消息，核对其群/私聊来源，再在页面选择仅用于展示的关联候选，没有依据昵称或相同标识猜测其他用户。

页面原自动刷新已临时取消以避免 DOM 索引失效。点击关联后确认框被观察为 confirm，但浏览器控制出现 CDP 超时；不重试提交。随后只读检查 **console_people_v1.json 尚不存在，原历史/scopes/friends/插件配置/积分/归档哈希均未变**，未形成真实关联。电脑工具在进一步检查弹窗时明确报告无法可靠确认当前浏览器网址，并强制结束本轮操作；随即停止所有 UI 输入，没有绕过限制或改走另一套电脑控制。此工具阻断不归因于产品功能失败。

**生产关联、关联后群/私聊与具体群切换、解除恢复仍未完成。** 不将 17 项合成浏览器通过写成生产全通过。最终映射文件仍不存在；控制台可能仍有待处理确认框，页面自动刷新未能恢复，接手须先只读检查弹窗/当前状态再继续，不能重复提交未知操作。未操作真实开关、积分、分层删除或发送管理目标。

## 收尾与下一步

服务保留本版运行；测试消息、媒体和回执保留，无测试数据清理。仅新增评审/发布记录及本机忽略的验收辅助材料，功能 HEAD 保持 `d31827c`；没有产品补修、本地新提交、推送、main 合并、依赖安装或权限变更。TASKS/HANDOFF 同步本状态，历史失败结论保留并以上述后续证据关闭 A/P2。

下一步在电脑控制可用且确认浏览器弹窗状态后，继续 B 的真实展示关联、场景/群切换、明确原来源、解除与恢复自动刷新；无需无变化重复 A 已通过的离线及 QQ 用例。整单仍待 B 剩余生产核验及用户验收，不自动晋级 main。TTS/F09 等暂缓不变。
