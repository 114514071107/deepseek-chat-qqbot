# S01—S09 启动流程补修

日期：2026-10-27，Asia/Shanghai。基线dev `e4c9de7ea3b56a3217ed133c055e90127a1a2048`，开工干净；运行功能仍d62fe25/review-2。依据仓库外startup-review及WORKORDER-STARTUP-FIXES-2026-10-26，原R01—R07成果和失败记录保持。本记录持续追加，尚未完成的项目不提前标通过。

## 授权与开工现场

用户明确交单实施、必要验证及配套部署，并把指定账号群聊/私聊实际回复列为成功标准。依AGENTS先源码/离线/本地提交，再停写备份和成套部署，核真实版本/连接后才做既定目标的最小QQ验收；启动脚本不得自动发测试消息。无push、PR、main合并、依赖安装、系统权限/生产ACL、身份归类、闹钟/TTS或数据迁移授权。

00:04只读确认原Bot worker24800/应用10768、Console worker52404/Node14384及ticks/exe/nonce/root、所属监听仍在；管理lease仍stopped=true且无有效at，不能证明当前QQ就绪。读取使用允许共享删除的文件句柄。没有重复Start或为取绿灯先重启。目标路径及祖先没有额外AGENTS；相同实例其他任务idle，活跃任务在无关项目。用户后来“继续任务”沿用本单。

默认工具pwsh7.6.5缺Management/Utility，文件存在但不能运行必要命令，初次只读命令即复现S02。工具shell参数未改变实际宿主，因此调查明确调用系统5.1或现有Python，未修系统环境。开发/测试材料在忽略的`local/startup-fixes`；真实参数/数据不入Git。

## 根因、有效失败与改动

| 项目 | 已取得的根因/有效失败 | 补修方向与当前证据 |
| --- | --- | --- |
| S08 | 已有实例与新建实例共用timeout catch，均Stop-Owned；真实临时worker在重复Start后消失 | createdThisAction仅清理本轮新建实例；原实例超时保留，再恢复ready复用同PID。`s08-red.log`→`s08-green.log`15.408秒通过 |
| S09 | 单次live原子替换异常脱出循环；管理循环若继承聊天key，会被该请求invalidate取消；finally只有stopped无原因 | 管理任务固定实例key/feature；文件IO最多4次有界重试，已执行命令不重放；退出记录reason/时间/pid，真关闭仍撤销原lease。三有效失败→专项通过，永久失败不无限重启；历史23:43具体触发仍缺证据 |
| S03 | botpy1.2.1 RESUMED不设置新socket.user，旧检测要求user导致connecting | 版本化AstrBot4.29.1客户端connector与socket实例观察；当前连接发Resume且SDK成功处理RESUMED才确认，关闭/失效/异常撤销；READY保留。实际安装SDK合成回放有效红→绿，无网络、不改site-packages |
| S04 | 探针IsProcessInJob(worker,ownedJob)=true而child=false，句柄不可继承(flags0)；Store7应用实际未进Job，非猜测Job关闭失效 | 原生CreateProcess挂起创建→明确Assign→Resume，执行前纳管；仅继承日志/输入必要句柄，Job句柄不外传。Store7有效红→绿，两种解释器异常worker退出实际专项通过；Stop预开固定身份句柄，消失幂等，拒绝/归属变化仍失败 |
| S02 | PATH首项不可用pwsh仍被选；chosen永久缓存 | 同一launcher-shell动作前做命令/模块/Add-Type能力预检，cmd与Console共用；按候选预检、未开始业务才择其他，业务退出37只运行一次，损坏首项有效红→绿；无长期chosen缓存 |
| S07 | WMI Create返回0，直接/经cmd的系统5.1连无文件的-Command常量都未执行；日志拒绝访问。Store别名7可运行；当前用户medium非管理员，exe ACL有Users读取执行，无权限改动 | 不假定已确定OS策略名；移除这条不可可靠观察的WMI启动链，入口在组件Job之前创建同脚本独立控制器，认证请求有ack/结果，仍执行同一身份/锁/停止/启动核心。5.1及7真实临时Console自重启已走到后续故障矩阵，全集结果继续记录 |
| S01 | 默认无强核验，临时只有监听也报成功；S08已先保护 | 默认核版本/有效新鲜心跳/可信QQ及认证前端，未来时间不放行；仅监听有效红→绿，新建失败安全清理 |
| S05 | 原始基线实际双组件输出Bot unknown后再将Console标Bot succeeded | 原基线复制到临时源码复现；按组件返回并输出All/results及partial；相同合成两组件绿21.362秒，单组件协议保留 |
| S06 | HTML setter跳过相同主体，但insertAdjacentHTML仍执行，浏览器1→5份 | 隐私卡并入同一缓存字符串；7项浏览器通过，重复刷新/切页1份、草稿/焦点保留，POST0 |

原始失败、编码/夹具错误和有效产品失败分开：S03首次inert漏kwargs、S05首次prep模块路径及Python DLL路径错误均不是产品失败；随后有效RESUMED/误标失败留存。S04原生NUL输入在5.1的FileStream设备限制经实际日志定位，改用CreateFileW，不改用户/系统权限。旧故障注入用注释替换Kill会破坏新增try语法，改为等价空语句，拒绝/超时的原断言保留。

## 实施取舍

- Ruling: 沿用干净dev而不新建工作树——用户指定原仓库且无占用；误判占用的代价是覆盖他人工作，因此开工/接续核Git和任务状态。
- Ruling: WMI控制器替换为同入口的独立控制器——本机5.1在脚本前拒绝执行，不能靠延时或放权限修复；代价是增加一个受控后台进程，需核身份、锁、寿命及失败收尾。没有Windows服务/计划任务、无限重启或新启动入口。
- Ruling: QQ观察严格固定已装版本，未知契约返回unknown——不把旧session/开socket当认证；代价是升级SDK后需重新核查，不偷偷放宽条件。
- Ruling: 有界IO重试与退出原因替代无限自重启——暂时共享冲突可恢复，永久异常明确失效；代价是持续权限故障需维护者处理，不能承诺永不停止。

## 独立复核与本轮离线结果

独立只读复核提出6个重要问题，均先保留有效失败再补修：控制器未ack的请求过期后不得迟到执行；顺序重载保留当前已认证RESUMED证据；控制器每次动作重新评估解释器；应用提前退出0不能被当作ready；枚举子PID后重新核CIM创建时间/父关系并持有进程句柄，拒绝复用PID；新建实例首次状态落盘失败也须清理。本轮没有遗留未处理的复核项，没有以延长超时或弱化断言关闭问题。

最终完整Python命令（桌面同等PATH，专项另覆盖损坏首项）：`D:\dsbot\venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -p test_repair_*.py -v`，280项、728.828秒，OK，保留1项既有跳过。启动矩阵明确输出pwsh.exe及powershell.exe；实际Console生命周期203秒专项此前也通过。首次全集272项有3失败1错误，第二次279项仅测试观察器与原子替换的共享冲突错误，均保留日志并修正后才重跑，未沿用旧全绿。

Node `node --test console/tests/*.test.js` 64/64通过；余额专项2/2；浏览器卡片7、生命周期5、键盘7、状态7、刷新竞态3通过。语法检查80份Python AST、28份JS/CJS、3段内联脚本无错误，git diff --check通过。配套user-workbench.js版本同步后才通过真实浏览器模块检查。敏感值扫描及本地链接检查无命中/断链；原失败日志仍在忽略目录，脱敏汇总入库。

实际部署/回退、后台与群私聊/观察期结果在发布记录执行后追加。当前未部署未固定源码；历史S09的具体首次触发及本机WMI拒绝执行的OS策略名称尚不能确定，不把合成根因冒充原现场定论。
