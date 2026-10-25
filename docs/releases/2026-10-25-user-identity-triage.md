# 2026-10-25 用户身份盘点补修上线与 B 续验

本轮功能 dev **0118181b52ef7031e8b92b2b4f90609680c5b678**，前置源码自审、Python 233/233、余额 2/2、Node 47/47、隔离浏览器 15+17+11 及静态/敏感检查通过后，于晚间按既有同任务明确部署/启动/QQ 授权执行。没有推送、合并 main、安装依赖、增加 QQ 权限或清理数据。

实现、失败证据、盘点脱敏表和生产逐项记录见[评审记录](../reviews/2026-10-25-user-identity-triage.md)。原 5651587 的未完成 B 和电脑工具强制停止历史保留，不改写为旧轮通过；A 原真实通过不重开。

## 备份与配套部署

保护目录 `D:\dsbot\deployment-backups\20261025-user-identity-triage-release` 继承上轮受限 ACL，保存：

- 对应源码 zip、source-commit、30 项清单及哈希、staged、before、部署前真实常量/配置备份。
- `data-snapshot` 399 份停止 Bot/Console 后的快照，逐份哈希核对。只复制保留，不迁移或替换历史。
- `prepare_release.py`、`validate_release.py`、`stop-owned.ps1`、`install-stopped.ps1`、`rollback-code.ps1`、运行激活/界面/映射及数据核查证据。身份、昵称、聊天、截图和映射均不入 Git。

执行停止时核对两个既有 worker 的 PID、创建 ticks、exe、nonce、根目录和 InternalWorker 命令，利用各自 Job 结束后代；确认 6185/7850 关闭后才安装。实际替换 7 项（1 新文件 `dsh-console/people-sources.js`），30/30 运行文件匹配；main.py 仅沿原部署规则保留四项常量并固定对应源码 commit，Console MASTER 保留原值。真实框架/运行配置和 DPAPI 凭据未改。

## 启动与本次误报

使用既有 `pwsh -NoProfile -File D:\dsbot\start-bot.ps1 -RuntimeRoot D:\dsbot -WithConsole -TimeoutSeconds 60`。22:34 新 Bot worker PID 104740，Console worker PID 95152；Bot 端口先就绪，入口随后报 Console worker disappeared。

未盲目重复启动或按进程名结束：只读核对发现 Console worker 仍为同 PID/ticks，观测 phase running，Node PID 107596 为其直接子进程，监听 7850。初始 Console.json 中 exe 为 null；后续 Get-Process.Path 为真实 pwsh 路径，Test-Worker 因路径不等返回 false，Stop-Owned 因而也未结束该实例。此次并没有证据证明 worker 实际退出。

受保护 `recover-console-state.ps1` 严格验证同 PID/ticks/nonce/component/root、真实 pwsh 路径及 Node 子进程/端口后，先备份原元数据，再仅原子修复 exe/ready。正常启动入口随后输出 Bot reuse / Console reuse，未产生新后代。启动器源码未在本任务修改；此证据只解释本次误报，**不能据此给历史 RQ04 或 PS7 临时 worker 退出定因**，历史原因仍未确定。

22:37:40 及 22:59:18 健康核对：API `20261025-triage-1`、Bot running、30/30 运行哈希、3 份框架/运行/凭据哈希一致；浏览器实际重载新版页面及模块。端口就绪单独不算 QQ 通过，之后指定账号的实际客户端回复才确认两场景可用。

## B 实际操作与收尾

先核上轮真实映射：与保护快照语义一致、无旧确认框；当前本机 URL 可读，自动刷新勾选且面板收起。新版生产列表为 **1 已确认用户、6 待确认来源、4 旧档、8 会话来源、5 纯资料键、11 展示入口**。旧 16 入口里的 5 项由 memory_key 算法证明为资料别名，已挂回来源，不把剩余入口等同真实人数。

只对原已核测试人物的一群一私聊做 UI 预览/明确确认：解除后 0 人工组、1 条否认，刷新不合回；明确否认后共 6 条键级决定，刷新仍分开；重新确认后原一组两来源恢复，临时否认全部清除。最终 v2 映射的成员关系与最初 v1 相同，未直接覆盖备份文件或影响他人。

工具最初不能读最小化 QQ，用户恢复后使用原窗口提供的 Raise；重新核对指定账号资料卡、指定群号和原机器人私聊。只发各一次本地“状态”，私聊 22:52、群 22:57 客户端实见回复且源码为 0118181；对应 accepted 保存、资料 first_seen_at 正常，无模型路径。工作台群 31→33 条、私聊 45→47 条，场景正确；具体群可筛选，操作来源仍为空。没有重复 A 表情 QQ 用例。

原 history_all/history_v2 前缀全保留，scope 键集合未变；names/friends/插件配置及框架/运行/凭据哈希一致。两条测试按既有入口分别扣 1 积分，恰好原两测试账本、总余额变化 -2、spent +2，其余字段与键集合不变，未赠送或重复计算。测试数据原样保留。

收尾无原生/页面确认框，面板均收起、草稿/临时资料卡和菜单已收起，自动刷新勾选。更新时间 **22:58:46→22:59:44** 实际变化，重绘已恢复；回状态页读在线状态后返回用户，操作目标为空。受保护 `ui-final-state.json`、截图及 `final-data-check.json` 可核查。

真实跨域自动确认与全局 QQ 昵称仍缺平台证据；现群仅有平台用户名/成员域，私聊 user_openid 无昵称，不伪造映射。多群、改名冲突等分支仅合成证明。新源码/离线与已核测试人物 B 流程通过，**不是全部生产分支或全部自然人数已识别通过**。

## 回退

先运行本保护目录的 `stop-owned.ps1` 验证归属并停止本实例，确认端口关闭；再执行 `rollback-code.ps1` 恢复 before 中已验证的原文件哈希，最后使用原启动入口配套启动 Bot/Console、重载页面并核对旧版本。新增未引用 helper 保留，不为回退删数据。

默认只回退代码，不整份恢复 dsh_data、配置、凭据、聊天或生产映射。v2 映射与既有 v1/2 读逻辑兼容，当前已恢复原关系；如需另行回退展示决定，先逐项核对当前 revision 和后来决定，只针对获准来源经管理 UI 处理，不能覆盖旧快照丢弃后续数据。所有保护备份保留。
