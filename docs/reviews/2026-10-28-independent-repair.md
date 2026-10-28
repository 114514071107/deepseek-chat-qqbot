# 独立评审缺陷实施记录

日期：2026-10-28，Asia/Shanghai。实施中；不替代原评审。

基线：本地 dev `73080c8550ffe5f31c9d41b4880e2bb10ba4895e`。开始时只有原评审三份 Markdown 和证据目录未跟踪，保留且不随本轮提交。未发现开发仓库及上级另有 AGENTS.md；遵守外部 repair-workorders 指派规则。运行版和部署清单另核。

| 顺序 | 问题、根因及接口 | 实施与验证位置 |
| --- | --- | --- |
| W01 | D01 适配器 self_id 占位差异；管理域以可信 app/instance 限定，只兼容已证实占位值，完整指纹不变 | user_directory.py、user-workbench.js；真实形态取码/认领/确认、拒绝矩阵 |
| W01 | D02 人工 union 早于可靠反证，pending 仍混读 | user-workbench.js classify；先合并后冲突历史/记忆/搜索/计数 |
| W03 | D04 gate 副作用前无原子准入 | main.py、小型有界模块；实际 gate 本地/模型/媒体路径计数 |
| W04 | D05 出站别名直接 append；D06 选择先变、正文后提交且失败不撤销 | people-sources.js；index.html；Node/浏览器乱序与失败 |
| W05 | I01 先区分执行前拒绝/夹具/生命周期，再接 D07 独立入口、D08 旧断言 | 临时实例双 Shell 输出与生命周期；浏览器原流程 |
| W02 | D03 精确权限方案与受限主体合成验证，生产 Apply 待批；I05 临时日志 | 独立 W02 记录；不修改共享文件 |

每项先记录失败、再最小修改和受影响回归；共享文件串行集成。最后完整回归、差异/敏感检查、本地提交、精确备份与配套部署及就绪核验。所有测试使用临时数据及既有依赖。真实 QQ/付费验收未获本任务许可；不 push、PR 或合 main；不迁移真实数据、连接活跃 SQLite 或执行生产 ACL Apply。

实际使用已安装 systematic-debugging、test-driven-development（含 writing-good-tests）、python-testing-patterns、security-best-practices、async-python-patterns、python-resource-management、frontend-design-review、playwright、verification-before-completion。新增安装 0。原生前端/Node http，没有套用 React/Express 规则。

## 本轮结论与证据

源码及离线补修已完成，构建 `20261028-repair-1`。本地提交和实际发布结果以文末及配套发布记录追加为准；不表示用户验收、长期稳定或 QQ 客户端验收通过。

| 项目 | 本轮结果 | 实现与证据 |
| --- | --- | --- |
| D01 | 已修：以可信 SDK app、平台、实例及受限 bot 管理域认领；仅两个已证实占位值可等价，未知真实 bot 仍隔离。完整来源指纹不变 | user_directory.py `management_bot/_domain`；Console同规则；身份 Python 11 项，包括真实群/C2C形态、过期/重放、抢先/异人确认、跨应用/实例/未知bot、并发认领、否认及首次称呼持久化。旧夹具改成真实占位形态后原4条确认路径失败，修后全过；Node覆盖重启/目录一致 |
| D02 | 已修：人工决定遇可靠反证时，将整个冲突组件按已核来源隔离；未知旧档不猜归任何一方。人工映射字节不变，冲突保留 | user-workbench.js `classify`；新回归先实际link再出现同应用两个不同user_openid，历史/记忆/搜索/分类计数不混；再新增群来源、改名、deny/unlink及刷新人物编号仍隔离。已确认影响是受保护管理视图混合，没有证明 QQ 模型泄漏 |
| D03 | 方案与合成验证完成，生产未Apply | [W02独立记录](2026-10-28-independent-repair-w02.md)。Inspect默认只读；Plan会写受保护备份，Apply/Restore保持单独批准。5项定向通过；D:\父根可替换整个实例的边界单列，不能只保护文件就宣称隔离 |
| D04 | 已修：完整来源+可信SDK app+消息ID，在managed gate任何等待/请求撤销前原子预留；gate本身也有防护 | event_admission.py、task_runtime.py、main.py；实际gate并发5次，修前扣费/发送各5，修后真实积分spent=1、发送1、历史2。媒体/模型/工具/发送替身边界、取消、新ID/不同群/应用/实例及容量保留期4项通过 |
| D05 | 已修：原来源桶优先，随后旧出站别名；只有完整来源及稳定record/attempt/platform message证据才折叠，先去重再取近期150条和分页 | people-sources.js；修前同出站2条，修后1条；冲突版本保留projection_conflicts并有页面审计入口；不同事件相同正文保留；170个同事件副本不挤走原用户消息。不改真实历史 |
| D06 | 已修：选择变更立即撤下旧人物正文；提交仍受epoch约束，失败页内alert/重试；同人物刷新失败可保留明确归属的旧快照 | index.html；A/B/C乱序、503、auto开关改变提示、键盘与320/390长称呼5项；删除迟到响应/草稿焦点/确认弹窗3项；人物目录浏览器8项。另修共享HTML缓存跳过重绘后残留“加载中”，缓存未失效时也清状态；切人清正文时使缓存失效 |
| D07 | 已修：开发/运行Console cmd/VBS转同实例认证、shell预检、controller/worker、归属与最终结果；VBS等待并传播退出码；缺凭据不报started | cmd/VBS、start-bot.ps1仅入口默认root参数接线，未重写内核。空格/中文临时根、不同cwd、双Shell真实Console启动/重复启动及全生命周期矩阵通过；缺凭据和cmd/VBS退出37通过。已正确转发的两份生产兼容Bot入口保留 |
| D08 | 已修：原浏览器从等待旧“待人工确认”改验当前“自动建档”，并检查manual=false、历史可读/派生管理禁用等原关键分支 | 原脚本初跑30秒超时保留，改后完整8项；README日期化旧结论。真实适配器夹具不再使用同self_id掩盖D01 |

来源复核：安装 AstrBot适配器群 `self_id` 可取mention ID，缺少时为 `qq_official`，C2C为 `unknown_selfid`；本次只兼容后两值，不把mention真实ID无证据折入。官方[唯一身份机制](https://github.com/tencent-connect/bot-docs/blob/main/docs/develop/api-v2/dev-prepare/unique-id.md)仍区分AppID的openid和跨群member_openid；不按裸ID、同名或客户端自报app推断同人。官方C2C页面本轮web读取失败，实际字段另核已安装adapter/user_profiles匹配合同，不用失败页面宣称额外能力。

## 入站准入的准确语义与兼容

每个插件实例的进程内准入表默认8192条，终态保留24小时；processing预留在gate运行期间不因过期被挤掉，gate退出后按完成/终止未知状态保留。表满拒绝新带ID事件，保留既有保护；不按正文/时间近似淘汰。无ID事件无法证明重复，按普通事件受理。失败、取消及投递unknown均不释放额度来隐式重发；新事件ID可以正常处理。managed等待前取消也保留预留。进程退出/插件重载会丢失该窗口，保留期过后可能再次受理，**没有跨重启exactly-once承诺**。gate_complete表示入口结束，不代表模型/客户端完成；实际请求仍受现有120秒等资源预算。没有新增磁盘格式、积分补扣/返还或历史清理。

管理目录仍读写既有v1自助格式/兼容v1-v2人工映射。原始source、模型scope、权限、积分键、QQ发送目标、删除具体对象和群共享记忆均未改。旧pending码域可能不再匹配，短期码应从原私聊重新发起；不迁移生产目录。来源未知旧档仍未知；memory_key跨未关联人物或未知旧档有歧义时仍抑制读取；仅Bot出站桶不新增人物。新可信来源自动建档，称呼缺失独立标记，平台用户名与本人称呼不混称全局QQ昵称。

## 调查项与旧记录

| 项目 | 当前证据与状态 |
| --- | --- |
| I01 | 当前原startup专项3项再次1失败1错误；补断言后不再用Bot.json缺失掩盖原始AuthorizationManager。最小矩阵证明PS5.1从开发路径无process override时执行前拒绝，临时字节相同副本进入产品逻辑；PS7可执行。已有入口的process Bypass路径也可进入，未新增策略放宽、没有Set-ExecutionPolicy。具体Windows策略根因未确定。真实双Shell临时实例Console全矩阵当前通过；原开发路径4条相关失败仍列环境受阻，不记通过。初跑pwsh生命周期stop得unknown，当前247.888秒完整定向复跑通过，未稳定复现故未改内核 |
| I02 | [本轮匿名台账](evidence/2026-10-28-independent-repair/legacy-inventory.json)：7入口/9可信来源/4旧档/5资料键/18原始键、0未解析映射；全部现存人物仍有人工组。台账编号仅本轮排序、不持久化人物ID。3平台称呼、1本人称呼、3缺可靠称呼；2入口仅有旧档，现有资料不能恢复自然人身份/原场景。原确认者/时间/理由仍缺，须本人或维护者提供依据。不据“入口数一致”判归属完成 |
| I03 | 当前proactive_loop每1800秒评估，异常60秒后继续；成功才增加count/lastAt，失败不扣成功额度，因而不能限制多次失败生成的累计费用。现有Resources约束每job（默认deadline120、model_timeout45、model_calls6、background1等），不是跨job每日失败预算。建议待选政策：每应用/实例/目标每日最多2次失败尝试，permission首次后冷却24小时；网络失败按30分钟/2小时/6小时退避；仅保护控制台提示，不经QQ转述他人信息。数值是提案，未写生产配置或启用功能政策；真实费用未调用/验收 |
| I04 | 活跃框架DB/WAL/SHM没有建立SQLite连接，不以mode=ro/immutable当证明。发布如取得所有本实例写入者已停止证据，才复制DB+WAL+SHM并逐文件核哈希；这只是停写物理快照，不冒充已验证可恢复历史。恢复试验、完整历史检查仍未实施 |
| I05 | [W02/I05记录](2026-10-28-independent-repair-w02.md)：PS7临时worker flush/live/退出buffer及exit7传播已证；5.1原开发路径执行前拒绝。没有复现日志路由丢失，不能将生产零字节判为已知丢日志；不改内核 |

数据链路：history_all/v2滚动→逐条source或可核回执→只读来源投影→统一人物归属→历史/记忆/搜索/筛选/计数。scopes提供可信场景，profiles保留平台观察，console_people保留人工决定/否认，user_directory保留本人资料/验证；三者不替代模型scope。memories按原key去重并校验歧义；session/memes/念头不猜分配到拆分旧档。两个JSONL档案只盘点行类型及source，未加入当前近期分页/搜索；回执accepted不是客户端收到。所有所读真实文件前后哈希一致；不连活跃SQLite、不重写真实目录或恢复旧业务快照。

A01全归档浏览需另立只读索引/全量分页工作单；A02全局统计口径需另明确归档、失败、用户事件和request_state定义；A03陈旧锁恢复需另设计可证进程归属和人工处理；A04缺失的确认者/时间/理由等审计来源完善另立新写入契约，不能补造历史。闹钟/TTS继续暂缓。

## 本轮验证与保留失败

工作目录为开发仓库；Python均为 `D:\dsbot\venv\Scripts\python.exe -B`，Node使用已有包，浏览器NODE_PATH由load_workspace_dependencies取得，已安装Edge无头运行，未装生产依赖。命令输出在 [evidence](evidence/2026-10-28-independent-repair/)。

| 实际命令/输出文件 | 结果 |
| --- | --- |
| `-m unittest discover -s tests -p test_repair_user_directory.py -v` / d01-before、d01-after | 真适配器形态修前4条确认路径取不到challenge；修后11项通过 exit0 |
| `node --test console/tests/repair-conflict-isolation.test.js` / d02-before | 修前不同openid仍相同person ID；修后完整冲突隔离链通过 |
| `-m unittest discover -s tests -p test_repair_event_admission.py -v` / d04-before、after | 修前5!=1；修后4项通过 exit0，包含实际积分函数 |
| `node --test console/tests/repair-outbound-dedup.test.js` / d05-before | 修前相同出站2条；修后稳定事件/分页/近期上限/冲突审计通过 |
| `node tests/memory_failure_browser.cjs` / d06-before、memory-final | 修前无页内alert超时；最终5检查通过 exit0。中间发现缓存问题后有对应新增断言，未放宽 |
| `node tests/identity_lifecycle_browser.cjs` / d08-before、identity-final | 原30秒超时保留；当前8检查通过 exit0 |
| `node tests/user_directory_browser.cjs`、`refresh_races_browser.cjs` | 各8/3检查通过 exit0；320/390截图已查看，无横向溢出 |
| `node --test console/tests/*.test.js` / node-final | 75项通过 exit0 |
| `-m unittest discover -s tests -p 'test_repair_*.py' -v` / python-all、python-all-exit | 首次完整297项，7失败/1错误/1既有skip，exit1，**不是整套通过** |
| 完整初跑失败拆分 | ACL完整SDDL兼容问题已由W02原2+新3专项修复通过；开关交错fixture误用同ID作两条不同消息，补真实不同ID后8项通过；Console pwsh stop unknown当前双Shell矩阵复跑通过；媒体executor队列1秒等待超时当前17项复跑通过但原时序原因未确定；其余4条PS5.1路径拒绝保持环境受阻 |
| `-m unittest discover -s tests -p test_repair_console_entry.py -v` | 修前虚报started/退出0；修后缺凭据、cmd/VBS退出37传播通过 exit0。首次新测试引号错误及清理二次错误另外保留，不混作产品红证据 |
| `-m unittest discover -s tests -p test_repair_console_lifecycle.py -v` / console-entry-matrix | 临时真实双Shell、独立cmd启动/重复启动、认证/退出/冲突/归属等完整矩阵通过 exit0，247.888秒 |
| `-m unittest discover -s tests -p test_repair_workorder4_p2.py -v`、`test_repair_interleavings.py` | 定向17项/8项通过 exit0 |
| `-m unittest discover -s plugin/astrbot_plugin_ds_balance -p test_balance.py` | 2项通过 exit0，未请求余额接口 |
| AST / node --check / inline block / git diff --check | 计数见static.json，检查无错；仅语法解析，无生产插件导入 |

原始失败日志只对Windows SID等本机身份做脱敏，不删除失败/跳过或改成历史已通过。没有重做全面评分，未将SDK ready当客户端收发。生产功能不使用合成实例/故障注入；代码审阅无生产凭据与身份原值。

## 当前源码定位

- D01：[plugin/astrbot_plugin_dsh_soul/user_directory.py:83](<D:/DSH Workspace/deepseek-chat-qqbot/plugin/astrbot_plugin_dsh_soul/user_directory.py:83>)
- D01 Console：[console/user-workbench.js:10](<D:/DSH Workspace/deepseek-chat-qqbot/console/user-workbench.js:10>)
- D02：[console/user-workbench.js:87](<D:/DSH Workspace/deepseek-chat-qqbot/console/user-workbench.js:87>)
- D03：[scripts/protect-config-acl.ps1:4](<D:/DSH Workspace/deepseek-chat-qqbot/scripts/protect-config-acl.ps1:4>)
- D04：[plugin/astrbot_plugin_dsh_soul/event_admission.py:14](<D:/DSH Workspace/deepseek-chat-qqbot/plugin/astrbot_plugin_dsh_soul/event_admission.py:14>)
- D04 managed：[plugin/astrbot_plugin_dsh_soul/task_runtime.py:176](<D:/DSH Workspace/deepseek-chat-qqbot/plugin/astrbot_plugin_dsh_soul/task_runtime.py:176>)
- D04 gate：[plugin/astrbot_plugin_dsh_soul/main.py:3146](<D:/DSH Workspace/deepseek-chat-qqbot/plugin/astrbot_plugin_dsh_soul/main.py:3146>)
- D05：[console/people-sources.js:70](<D:/DSH Workspace/deepseek-chat-qqbot/console/people-sources.js:70>)
- D06：[console/public/index.html:632](<D:/DSH Workspace/deepseek-chat-qqbot/console/public/index.html:632>)
- D06 epoch：[console/public/index.html:639](<D:/DSH Workspace/deepseek-chat-qqbot/console/public/index.html:639>)
- D07：[console/start-dsh-console.cmd:1](<D:/DSH Workspace/deepseek-chat-qqbot/console/start-dsh-console.cmd:1>)
- D08：[tests/identity_lifecycle_browser.cjs:20](<D:/DSH Workspace/deepseek-chat-qqbot/tests/identity_lifecycle_browser.cjs:20>)
- I03：[plugin/astrbot_plugin_dsh_soul/main.py:3730](<D:/DSH Workspace/deepseek-chat-qqbot/plugin/astrbot_plugin_dsh_soul/main.py:3730>)
- I05：[tests/probe_worker_logs.py:16](<D:/DSH Workspace/deepseek-chat-qqbot/tests/probe_worker_logs.py:16>)

本地功能提交 `daa013d1a1b2d27523e88c860b66d31903c8e165` 已固定范围。首次cached diff检查的日志尾空格/测试EOF空行失败未被外层Shell拦住，导致提交先发生；随后追加仅规范空白与此流程记录的提交，检查通过后才配套发布，不改写历史。该偏差不记为首次检查通过。
