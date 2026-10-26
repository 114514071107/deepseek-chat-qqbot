# S01—S09 启动流程实施计划

> 使用 executing-plans 连续实施；每个修复先复现失败再验证，整单完成后独立只读复核。用户已明确要求实施，不另设计划批准步骤。

目标：已有实例不被重复Start误停；启动、管理租约、QQ连接和后台状态证据一致。依据：仓库外 WORKORDER-STARTUP-FIXES-2026-10-26.md 及原 startup-review.md。基线dev e4c9de7，开工干净；本轮不push/PR/main，不改生产ACL、身份、闹钟/TTS、配置或业务数据，不安装依赖。

## 任务、接口和验证

- [x] S08：`scripts/start-bot.ps1`区分created/reused；`tests/test_repair_startup_ownership.py`真实临时实例重复Start不就绪超时后原PID/ticks/监听保持，新建失败仍清理。先运行专项取失败，再实现与复验。
- [x] S09：`admin_bridge.py`、`task_runtime.py`和main管理任务接线，追踪请求上下文/取消/文件替换；合成复现单请求撤销与短暂Windows访问冲突，管理任务独立实例归属、记录退出原因、真正关闭撤销租约。保留at/stopped真实语义，不无界重启。
- [x] S03：版本化QQ SDK事件观察，绑定当前socket的READY/认证RESUMED；关闭/失败失效，未知SDK拒绝冒报。实际已安装SDK合成回放首次READY、RESUMED、拒绝、旧socket、多连接及结构变化，无网络。
- [x] S04：诊断Job成员、句柄继承及异常worker退出；最小修正C#托管并使Stop-Owned对已经退出的已核身份幂等。双Shell临时应用/worker异常退出、并发退出/重复stop及其他实例不变；不在生产注入崩溃。
- [x] S02/S07：统一动作前解释器预检和外部控制器选择/阶段观察，失效缓存重评估但不重试已开始动作。临时PATH包含损坏7、仅5、有效7、模块异常、控制器启动失败和权限拒绝；定位5.1拒绝访问对象，实际临时Console认证自重启与端口交接。
- [x] S01/S05：默认强核就绪，时钟/版本/心跳/可信QQ状态全部必需；按组件输出及整体partial/unknown，不覆盖Bot失败。兼容显式单组件。临时未加载/错版/缺心跳/未来时间/连接中/Console失败/冷启动/复用矩阵。
- [x] S06：卡片合并缓存渲染；隔离浏览器连续/手动刷新与切页只有1份，草稿/焦点/暂停/来源不变。
- [x] 回归/交付：原启动矩阵和Console生命周期必须本轮重跑；完整受影响Python/Node、浏览器、语法/差异/秘密扫描。记录首次失败和取舍，本地功能commit，再受限停写备份/配套部署/实际加载核验。后台/既定群私聊及覆盖原约5分钟失效窗口的有界观察按本轮有效授权执行；不让启动器自动发QQ。

## 当前证据与取舍

- 本轮默认工具pwsh缺基础Management/Utility模块已复现；使用显式现有系统5.1做调查，未改系统环境。
- 只读现场：原Bot24800/应用10768、Console52404/Node14384归属匹配，端口仍在；租约stopped=true/at无效，不再次Start。`local/startup-fixes/baseline.json`仅保存脱敏状态，读取live允许共享删除。
- 沿用当前dev；其他活跃任务在无关项目，本实例其他任务idle。目标路径及祖先未发现额外AGENTS；保留原R01—R07成果和评审当时失败事实。
- 前期日志/测试材料保留在忽略目录local/startup-fixes，生产参数/备份仅在受保护部署目录，不复制进Git。
