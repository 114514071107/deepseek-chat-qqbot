# 独立评审 R01—R07 补修记录

日期：2026-10-26（Asia/Shanghai）。实施基线：本地 `dev` / `08bb3100698f8938af80c06c43ea4840a7bc088d`，开工干净；关联旧任务均为 idle。用户已指派源码实施、本地提交和本实例配套部署；未授权生产配置 ACL 应用、真实 QQ 发信、付费模型、依赖变更或远端写入。原评审、原探针、表情 A、人工 B 及页面续验历史结论保留。

## 当前状态

后续真实复验（17:14—17:30）已完成：见 [review-2 QQ 与生产控制台验收](2026-10-26-review2-live-acceptance.md)。本轮定向功能通过，R05 生产 ACL、R06 源码交付/素材授权及长期稳定性仍未结项。真实 QQ 与配置模型已调用；下文“未验收”保留为部署收尾当时的事实。

源码补修、本地功能提交及配套部署已完成；实际运行功能提交 `d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd`，前后端/插件版本 `20261026-review-2`。16:55 收尾核验 34/34 文件一致，Bot SDK QQ 连接 ready（1/1），Console 实际自重启成功、Bot 重复启动复用原实例。**已部署，待验收/试用**；R05 仅准备与合成验证，生产问题仍开放。真实 QQ、付费模型及长期稳定性未验收。下文保留各阶段原始状态，最终结论以本文末及[发布记录](../releases/2026-10-26-independent-fixes.md)为准。

## QQ 能力及证据边界

- 腾讯官方 [botpy/message.py](https://raw.githubusercontent.com/tencent-connect/botpy/master/botpy/message.py) 的 `GroupMessage._User.member_openid` / `C2CMessage._User.user_openid` 分别属于群成员和单聊身份域；附件 `BaseMessage._Attachments` 仅见 content_type、filename、height、width、id、size、url。未发现可信逐附件自定义表情标识，不能把 MIME、GIF、尺寸、文件名、CDN、视觉判断或正文 `[表情]` 当作该标识。
- 本机 AstrBot 4.29.1 的 `qqofficial_platform_adapter.py` 只读核对：42 行起保存 raw_data/message_type/msg_elements；633 行起 `_append_attachments` 把图片附件统一转成 Image；717 行起 face 解析输出文字；846 / 884 行群/私聊分别取 member_openid / user_openid 和可能为空的 username。`message_type/msg_elements` 被保留不等于已证实存在可信表情语义，不能据其名字放行。
- 链路为原始回调 → 本机 PatchedGroup/C2CMessage 的 raw_data → 统一 Image → 插件逐组件判定。当前判定全部 unknown，自动采集拒绝；不修改 site-packages，不新增推测性的元数据契约。未来有可靠字段时必须版本化接入、按消息内每个附件匹配，另行验证才能恢复。
- 本机配置只提取开关：唯一启用 QQ official 接入，group_c2c=true、guild_direct_message=true、use_markdown=true。它们是本地接入设置，不能代替 QQ 后台授权清单。未访问应用后台、申请新权限或采集新真实事件；受支持昵称接口及当前应用实际覆盖权限尚缺证据。
- 当前不能直接取得可靠真实数字 QQ 号；所需覆盖群/私聊的全局 QQ 昵称尚缺证据。`username` 若存在只按原平台资料标明来源，频道 Member.nick、union_user_account、内部 uid / OpenID 均不当作真实 QQ 号。官方 [user.py](https://raw.githubusercontent.com/tencent-connect/botpy/master/botpy/user.py) 的频道成员结构不能套用到群/单聊接收事件。
- 腾讯事件文档页面本轮仍无法通过网页工具读取，不把读取失败当作平台永远不支持的证明。**新增自动身份归类暂缓，保留现有用户功能**、已确认关联、人工解除/否认和可信展示名；本轮未修改身份系统。

## 有效首次失败与修复

复制原探针到忽略目录 `local/independent-fixes`，原文件未改。07:02 复现 A 私聊合成图被 B 群普通用户通过合法工具选取并交给替身发送器；AccessDenied 后 `/api/bot` 仍成功；Console 同端口重启得到 EADDRINUSE 后旧服务也退出；新来源闹钟持久化并说创建成功但无投递路由。没有真实 QQ 上传、真实私人图片外泄或无关进程被终止的断言。

### R01：共享图库

- `gallery_policy.py` 统一类型拒绝和内容绑定可见性；自动采集 hook 逐组件拒绝 unknown，直接 `_harvest_one` 也在 IO/模型前拒绝。没有用合成标志伪称真实表情识别通过。
- 列表、查询、目录注入、随机选图、工具/动作选图、Console 共享统计/示例都使用同一只读共享规则。最终发送重新核验，并发送当时已核验的字节快照，避免后续重新打开变化的原文件。路径越界、损坏/缺记录或内容变化均拒绝。
- 明确共享依据为逐文件 SHA256 的主人批准记录（本轮没有生成生产批准），或版本化公开素材来源中的精确 Git blob 内容；不凭目录名、标签、缺来源或 license 字段推断。公开来源只证明已公开的相同内容，不替代逐项素材授权核查。
- 只读文件范围盘点而未打开图库 SQLite：collect-001 有 5 个图片文件；dafeiyu-001 有 49 个；official-001 有 89 个。最初核对 anka 当前树未匹配，继续追溯 `UPSTREAM.json` 固定的公开上游快照 `ffde14a`，排除其 collect 自动图库后，49+89 个原共享素材全部与公开内容逐字节哈希匹配；collect 5 个均未匹配。没有将私图哈希上传外部，只下载公开树哈希在本机比较。
- 版本化 `public-gallery-source.json` 保留上述公开来源指纹；旧未知采集图默认不共享，原文件/数据库不删除、不搬移、不批量重写。后续历史核查方案：仅在停写一致副本审阅逐文件来源，主人明确批准后才生成逐文件许可；回退为移除新增许可记录，原图库保持。
- 普通识图、原会话媒体留存及原作用域不变。类型即使未来可识别，照片也可能被用户加成表情，不能保证无隐私。

### R02 / R03：实例生命周期

- 移除 Console tasklist/taskkill 按全机名称管理路径及自行 spawn 同端口 Node 路径。`lifecycle.js` 只调用现有 `start-bot.ps1`；同一脚本提供 Component / Action / VerifyReady，实例锁继续串行化。
- 校验运行根、组件、exe、ticks、nonce、实际命令行、子进程族及端口归属。停止保持已核验进程句柄、等待整个已核家族与端口退出；拒绝/残留/超时不再报成功，不结束无归属监听者。启动核新进程及归属，Bot 校验含 pid/version 的新鲜心跳，Console 校验认证拒绝、API/前端版本及服务 PID。
- Console 自重启由 WMI 启动独立于旧 worker Job 的控制器，仍执行同一启动脚本：先停旧家族并确认端口释放，再启同版新服务。API 只报受理，操作记录在 `.launcher/operations`，可经认证 GET `/api/lifecycle?id=…` 查询；不声称受理即成功，不盲目重试。调度回包超时不覆盖已开始/完成控制器的实际记录。
- Shell 选择沿用 pwsh 优先、5.1 回退；选定后不因业务失败换 Shell 重试。当前宿主的直接 WMI→5.1 诊断返回 OS 拒绝访问，保留事实；正常控制器优先选已存在的 pwsh。双 Shell 的启动器/worker 路径都经过实际临时实例测试，不声称当前机器完全无 pwsh 时的 WMI 环境限制已解决。
- 页面把进行中/最终结果保存在 DOM 之外，显式显示状态；自动刷新、切页和返回不丢结果，等待期间新 DOM 按钮仍禁用。`unknown` 要求核查，不冒充成功。

### R05：生产权限仍待授权应用

- `scripts/protect-config-acl.ps1` 默认 Plan，原/目标 DACL、继承和回退写到受限本机目录；仅修改 DACL，不要求 SeSecurityPrivilege，不修改正文或轮换密钥。
- 目标包括 `D:\dsbot\data` 与 `data\cmd_config.json`：AstrBot 保存使用 mkstemp + os.replace，单改文件 ACL 会在下一次保存继承回宽权限。父目录继承变化可能影响未保护的现有子项，必须作为精确影响范围审阅，不能借本单自动应用。
- 26 份相关 cmd_config 文件/备份逐项读取有效 ACL，24 份没有 broad allow；当前配置和 `deployment-backups/20261021-033826/data/cmd_config.json` 仍有 Users / Authenticated Users FullControl。父目录宽不用于否定受保护子项。旧备份也列为额外待处理目标，不自动清理或修改。
- 合成目录中验证 Plan→Apply→正常账号读写/原子替换→真正 Windows restricted token 的读/写均返回 AccessDenied(5)→回退。不是用管理员自己的成功读取替代低权限测试。Windows 恢复 DACL 时会规范化 AI 自动继承标记，ACE 与 protected/unprotected 语义相同。
- 独立复核发现 BackupDirectory==data 可使 Plan 提前修改目标；新增合成失败回归后，现于任何建目录/ACL 写入前拒绝 data 本身、子目录及实例祖先，验证拒绝前后 ACL 原样。
- 生产仅生成了 Plan，未调用 Apply；当前配置方案在 `20261026-independent-fixes-acl-plan`，旧备份以其归档根为 RuntimeRoot 单独生成 `20261026-independent-fixes-acl-legacy-plan`。两个受限目录均含原/目标 ACL 和回退记录；文件及目录实际权限未收紧，R05 不关闭。当前 Bot 已退出，实际服务身份核验未取得；Console 当前身份一致；应用前仍需确认实际服务主体及父目录继承范围。

### R04：闹钟不可用

创建/列表/取消工具均不可作为可用能力，执行入口给出可解释拒绝；直接创建路径不写任务，后台检查不投递、不读改旧表。旧 `alarms.json` 保留；帮助、模型说明及 Console 一致标为政策暂缓。不开启 F09、不制定补发/清理/失败恢复策略。

### R06 / R07：说明与键盘

- README、隐私说明、帮助及 Console 明确本机保存和外部推理：必要消息、上下文、人设、记忆/摘要、图片与工具结果可能提交给配置模型；联网检索/QQ 收发也经过外部服务。主人认证后台可见范围和 QQ 朋友互相隔离分别说明。
- 列可用、权限禁止、平台缺失、政策暂缓；未知收图、外包、闹钟禁用且管理接口不让旧开关恢复，普通用户文件能力明确禁止。删除没有当前实测支持的费用/延迟承诺。
- 原 AGPL、原作者、UPSTREAM 和修改记录保留。未推送本地版本，帮助提示免费向主人索取匹配源码包；实际远程交付方式及素材权利链仍是缺口，不能当作许可证义务已验收。
- Checkbox 保持原生可聚焦、正确名称/状态、可见 focus-visible 和禁用样式；操作捕获 uid/key/value，异步后不将结果投到另一个来源。键盘真实浏览器测试固定一次 Space 对应一次正确目标请求。

## 验证与首次失败记录

全部使用合成数据、临时目录/端口、替身模型/发送器；AST 抽取避免生产插件注册/构造；框架导入仅在临时子进程。没有依赖安装或 QQ/付费调用。

- 原缺陷探针：复制复跑，原报告和原断言未修改；详情在本机 `local/independent-fixes/probe-*.json`。
- R01 新失败→通过；R04 首次夹具参数错误保留，修正接线后得到实际持久化入口失败，再补修通过。R07 Tab 不可达失败→通过。
- 生命周期首批诊断包括夹具 PSModulePath、FE 常量接线和外部控制器拒绝，均留原日志；最终双 Shell 实际测试覆盖正常自重启、认证/版本、新进程、陈旧 ticks、不误停另一个监听实例、重复启动、进程提前失败、AccessDenied / 无退出 / 旧端口保留故障注入。注入只修改临时启动器副本，不碰无关真实进程。
- 完整 Python 首跑 252 项：4 failure、2 error、1 skip，原因分别为新诊断文案、清理掩盖退出码、权限拒绝文案和新增夹具缺 json。根因补修后第二轮 252 项 / 294.205s：OK，1 skip；两 Shell 旧矩阵执行。
- 被跳过的原未知图自动采集额度用例保留完整旧断言，因新产品规则禁止该路径；新未知拒收/跨用户读取发送验证替代，不冒称已验证真实表情自动准入。
- 独立只读复核提出 ACL Plan 与生命周期结果两项 P2；各补失败回归并修复；补充调度回包竞态验证。新 Node 全集 62/62（1.196s）；余额 2/2；真实浏览器键盘7、生命周期跨刷新5、相关刷新10项通过。
- 最终完整集合、静态检查、提交和实际部署待下节追加。

## 原运行实例退出（单列，未定因）

07:02 只读核验原 Bot33776 / Console33164、原 lifecycle-2 正常。08:13 再核：Bot33776 已退出，观察文件为 07:06:28（北京时间）、code1；6185 无监听，Console33164 仍在，心跳已旧。本轮在此之前未发起生产启停或替换运行文件。没有据独立 R03 复现认定这次退出原因，也不把它写成新版已稳定。部署后须按当前实际状态启动 Bot。

## 最终追加

最终完整 Python：`D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_repair_*.py'` → 254 项，295.036 秒，253 通过 / 1 明示跳过；两 Shell 旧矩阵执行。Node `node --test console/tests/repair-*.test.js` → 63/63，1.659 秒；余额 `-m unittest discover -s plugin\astrbot_plugin_ds_balance -p test_balance.py` → 2/2。

实际 Console 故障矩阵另跑 1 个双 Shell 综合测试：101.721 秒，包含旧端口不释放、外来占用、新 Node 退出17、心跳/健康超时、最终失败持久化及恢复。补充非默认 Bot 端口传参失败→通过，真实 API 启停/复用链另以双 Shell 综合测试通过（110.652 秒），防止仅凭辅助函数通过。浏览器命令为 `node tests/review_keyboard_browser.cjs`、`review_lifecycle_browser.cjs`、`console_p2_browser.cjs`、`refresh_races_browser.cjs`，共 7+5+7+3 项，使用既有 Playwright 模块及 Edge，无 JS 故障。一次脚本默认输出覆盖了两张旧合成截图，已先保存本轮截图到忽略目录，再从原 Git 对象逐字节恢复旧证据；旧评审材料没有随本轮改写。

70 Python AST、26 JS/CJS 及 3 个 script 块语法检查通过；`git diff --check` 无输出。实际配置仅在本机内存提取 6 个敏感值，与本轮 33 份修改/新增文件逐项比对，命中 0；不输出值，不扫描上传外部服务。后续新增文档继续复核。

功能 commit 与部署结果在发布记录实际追加；真实 QQ、付费模型及长期稳定验收未覆盖。

### 实际部署阻断后的补修（08:32—08:45）

首个功能提交 `9ec4061` 已固定、34 文件暂存（13 变化）及源码 zip CRC 通过；尚未覆盖生产代码。08:32 受控停止如实超时：旧 Console worker33164 已退出，而原 Node10696 仍监听7850。进程创建于04:05:16、parent33164、可执行文件/本实例脚本/端口/当前账号一致；没有结束端口上的任意进程。

新增临时旧式 worker（不持有子进程 Job）复现相同残留现象。停止契约现处理仍有可信父进程时捕获的子进程身份；对已退出的旧 Console，必须核原 root/component/nonce/worker 观察记录、子进程出生时间上界、精确 Node 路径/本实例脚本/端口、当前账号，才允许停止。进程句柄先打开并复核 ticks/exe，避免 PID 复用重定向；记录保留在实例控制目录。未知或伪造 nonce 用例拒绝且原监听继续，真实合成原子进程可安全退出。没有声称已经查明旧 Job 为何未结束 Node，也没有将此解释为历史 Bot 退出原因。

新专项失败原始断言是“孤儿子进程无可核停止路径”；首两次同时遇到夹具清理错误，原日志保留。修复后真实专项通过（8.685秒），双 Shell 实际 API/故障/恢复重新通过（115.153秒）。补修后完整 Python 255 项 / 339.591秒：254 通过、1 明示跳过；两 Shell 旧矩阵仍执行。新增测试仅为合成有限生命周期进程，不触碰无关真实进程。后续追加本地提交后重新暂存，才能继续生产停止/备份/部署。

### QQ 就绪核验补充

实际源码核查发现 SDK 使用 bot_log=false，启动日志中的框架提示不能作为 QQ READY。新增 `admin_bridge.qq_connection_status` 是 AstrBot4.29.1/当前botpy 的只读版本化观察：当前受管 WebSocket 集合、连接仍打开、`_ready_handler` 赋值的 user/id 与 session_id 都具备才计 ready；不输出身份、session_id、token或原始数据。断开、空集合、缺字段、恢复连接缺原READY证据均不冒称 ready，既不改SDK也不调用平台/模型。启动器对配置的QQ未ready继续有界等待。

新增专项先因路径接线错误/缺函数失败，随后 synthetic READY 缺SDK必需version字段的夹具错误保留；补齐后3项通过（含真实已安装 botpy `_ready_handler`，没有网络/生产对象）。管理状态回归10项通过；双 Shell 实际 API/连接未ready不得成功的专项通过，124.743秒。后续完整回归和实际 Bot review-2 加载/QQ状态仍待追加。

16:42 用户接续后重新核对：dev仍3825aab，仅本轮待提交补充；无其他活跃编写任务，运行原34/34仍匹配，Bot48076/Console33008仍为已核身份，心跳新鲜。没有覆盖间隔正常业务数据。最新完整Python258项/347.638秒：257通过、1明示跳过；同版状态卡unknown显示另有失败→通过浏览器证据，Console前后端随补充统一递增review-2，不把未知显示为未运行。Node63/63、键盘7、生命周期跨刷新5、72 AST/26 JS-CJS/3 script块通过；最后同版双Shell生命周期复验结果随后追加。

同版review-2双Shell真实生命周期复验127.072秒通过，包含非默认端口经API复用/停止、连接尚未ready不得成功及Console正常/失败恢复；Node63项、未知状态卡/跨刷新5项、键盘7项均通过。72 Python AST、26 JS/CJS及3 script块通过，差异检查无输出。

## 最终部署与收尾核对（16:46—16:55）

功能提交依次为 `9ec4061`、`3825aab`、`d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd`，均仅本地 dev。review-2 已提交后才暂存/部署，完整源码 zip 已在受保护本机目录保存并核 CRC；未推送、PR、合并 main 或发布外部源码。文档收尾另作本地提交，不改变运行功能版本，不重复部署/重启。

收尾另核备份回退脚本：临时目录先有效复现两个备份脚本停止后切换旧启动器时的同名C#类型错误（已恢复代码但未启动，非真实回退）。两份受保护`rollback-code.ps1`现把每次受控调用放入独立Shell；pwsh及Windows PowerShell5.1合成回退各2/2通过，均精确两次停止/一次启动、恢复预期代码且业务文件字节未变。修改前脚本另存`rollback-code-before-fresh-shell.ps1`，首次编码/夹具未设置退出码错误与有效红/绿JSON均保留；**生产未执行回退，运行代码未改**。命令为现有Python运行受保护`test-rollback-offline.py`，只用临时合成实例，不计入258项产品回归。

16:46 受控停止本实例 Console/Bot、确认端口释放后，保存414份/35,323,876字节停写快照（含DB/WAL/SHM）；34份配套清单安装并核哈希，7份相对review-1变化。首次在同一操作者 PowerShell 进程内先后使用开发/运行两份 Add-Type 定义，发生类型重复错误；未报启动成功。在新Shell通过运行实例入口启动成功，16:47:27两个组件ready，未执行回退。该操作宿主错误与历史Bot未知退出单列。

16:49实际认证API自重启：初始 pending/ok=false，最终 succeeded，Node5776→33716，前后端review-2；随后Bot start最终succeeded且worker/ticks保持原值，没有重复实例。16:55只读复核：Bot worker34796/应用17556、Console worker49144/Node33716，运行根、exe、ticks、nonce、命令行和监听家族匹配；实际存活服务进程为当前账号，补齐此前R05 Plan生成时Bot已停的身份缺口。临时状态查询子进程在WMI枚举间退出曾导致一次只读核验失败；核验器改为仅在确认原身份已退出时略过其身份查询，活进程查询失败仍拒绝。最终无生产管理写请求。

插件新鲜心跳含review-2和应用pid，SDK观察为configured=1/ready=1/status=ready；16:55年龄0.094秒。它证明受管连接当前满足SDK READY/open契约，不证明客户端收到消息、发送权限或长期稳定。实际HTTP健康版本匹配，返回页面与运行index.html逐字节哈希一致；无认证401、跨来源403。本轮没有重做原A/B/页面验收，也没有发送QQ或发起付费验收调用。

四份配置/凭据对首次和补充部署前快照共8次比对均未变；两组ACL Plan的4个精确目标SDDL仍与原记录相同，生产未Apply。图库149份文件（含图片、索引/数据库等）与停写快照哈希一致，核验未打开活跃SQLite。生产`dsh_data/alarms.json`在补充快照和收尾均不存在，不能把空集合比对说成验证了真实旧闹钟；已有闹钟保留由合成旧数据字节不变回归证明。138份已公开共享图片可读、5份未知collect图片不可共享的结论来自首次停写一致副本及只读策略检查，不是线上发图验收。

本机受保护证据：`D:\dsbot\deployment-backups\20261026-independent-fixes-qq-ready\actual-lifecycle-v2.json`、`final-readonly-verification.json`、`release-manifest.json`、`stopped-data-manifest.json`和`rollback-code.ps1`。公开安全的汇总见[verification.json](evidence/2026-10-26-independent-fixes/verification.json)。受保护`final-readonly-verify.ps1`用于只读核验；实际停止分别经开发`start-bot.ps1 -RuntimeRoot D:\dsbot -Component Console -Action Stop`与`-Component Bot -Action Stop`，启动分别经运行`start-bot.ps1 -RuntimeRoot D:\dsbot -Component Bot -Action Start -VerifyReady`和`-Component Console -Action Start -VerifyReady`。无数据库迁移、图库删除或凭据正文修改。

| 项目 | 源码修复 | 离线验证 | 实际部署 | 本轮真实验收 |
| --- | --- | --- | --- | --- |
| R01 | 入口未知拒收；所有共享出口同一内容绑定策略 | 跨A/B列表/随机/直发/最终字节、混合附件及公开内容通过 | review-2已生效 | QQ图片/收发未测；不冒称表情自动识别通过 |
| R02 | 本实例受控生命周期、结果可查 | 双Shell真实临时进程及拒绝/超时/陈旧/复用通过 | 已生效；实际Bot复用成功 | 本机生命周期已核；QQ业务未测 |
| R03 | 外部同入口控制器先停后启、页面保留结果 | 端口竞争/外来占用/退出/恢复和跨刷新通过 | 已生效；实际Console自重启成功 | 本机重启已核；非长期稳定结论 |
| R04 | 全部闹钟工具及投递暂不可用 | 新请求不持久化、不假成功；合成旧字节保留 | 已生效 | QQ请求未测；F09暂缓 |
| R05 | Plan/Apply/Restore脚本及精确回退就绪 | restricted token读写拒绝、原子保存及恢复通过 | **仅Plan；生产ACL未应用** | **未关闭，待授权应用** |
| R06 | 隐私/外部推理/权限/能力说明一致 | 相关状态及文案回归通过 | 已生效 | 源码远程免费获取/素材权利链仍缺证据 |
| R07 | 原生聚焦、名称、焦点及异步目标固定 | 浏览器键盘7及刷新/竞态通过 | 对应前后端已生效 | 生产页面键盘人工验收未重做 |

### 实施取舍与剩余边界

- 沿用已核干净dev，不强制新工作树；用户明确指定当前仓库，误判占用可能覆盖他人工作，因此开工及接续均核状态/其他任务。
- 无可信逐附件表情标识时拒收全部未知；代价是自动采集暂不可用。公开精确内容哈希作为既有共享依据，误判来源会扩大可见性，因此不依赖目录/标签且最终发送重核；素材授权仍另列缺口。
- 闹钟整体不可用，保留原数据/代码而不制定F09；代价是目前没有提醒服务，帮助和工具必须明确拒绝。
- ACL必须覆盖原子替换所依赖的data目录，但继承影响尚需批准；保持生产原ACL意味着过宽权限风险仍存在，不能标已关闭。
- 实际部署后仅更新文档不重复重启；保留原失败、测试及受保护回退材料。用户要求留证优先于技能默认清理临时工作材料。按用户明确指令保留dev，无合并/推送菜单和额外授权请求。

独立只读复核的两项P2均已有失败→修复→通过证据，无另列待修minor。PowerShell5.1-only的WMI宿主限制、真实QQ身份/昵称与素材权利链、旧Bot code1退出根因、长期稳定性仍分别保留，不能互相代替结论。**新增自动身份归类暂缓，保留现有用户功能。**

最终文档核对：本轮36份修改文件与8个本机已知敏感值逐项比对，命中0；Markdown本地链接无缺失，verification.json计数/版本一致，功能提交后plugin/console/scripts无未提交源码差异，git diff --check无输出。扫描只在内存读取必要秘密，输出仅数量/布尔值；证据在忽略目录`local/independent-fixes/final-sensitive-doc-check.json`。扫描器首次Windows默认GBK解码错误修正为UTF-8后完成，未输出秘密。本地dev文档收尾提交后保留工作区，不push/PR/main合并。
