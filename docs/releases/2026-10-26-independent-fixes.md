# 2026-10-26 独立评审补修配套发布

实施与限制见 [评审记录](../reviews/2026-10-26-independent-fixes.md)。当前实际版本 `20261026-review-2`，功能提交 `d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd`，34/34配套文件已核；状态为**已部署，待验收/试用**。仅本地 dev，未推送/PR/main 合并。下文保留首次review-1和后续补充过程，最终生效记录在末尾。

后续状态（2026-10-26）：[定向 QQ 与生产控制台验收](../reviews/2026-10-26-review2-live-acceptance.md)通过，用户指示后的[dev 推送与运行核验](2026-10-26-review2-dev-publication.md)已完成；对应运行功能源码已匿名下载并核对一致。上段和下文未验收/未推送为原部署任务当时状态。R05、素材权利链及长期稳定性仍开放，main 未晋级。

## 发布清单与备份方案

来源为本轮已提交开发源码；沿用上一版 29 文件清单，新增 build_info.py、gallery_policy.py、gallery_query.py、public-gallery-source.json 和 console/lifecycle.js，预计 34 文件配套发布。
main.py / server.js 只在受限暂存区保留原部署常量，源码包继续使用模板；不覆盖真实配置、身份、业务 JSON 或图库。

受限本机目录：`D:\dsbot\deployment-backups\20261026-independent-fixes-release`。保存精确 manifest、原代码、配套暂存版本、源码 zip、停写数据/配置快照、原文件哈希和可执行回退脚本；秘密不入 Git。
停止前后均核本实例归属，Bot 如仍已退出则记启动；Console 用同一启动器停止，确认 worker/后代/端口退出后才复制。框架数据库若停写备份，保留同批 DB/WAL/SHM，不打开 SQLite。

## 回退契约

1. 使用本轮启动脚本仅停止本实例 Console/Bot，验证归属、后代与端口退出；不按名称结束进程。
2. 核对回退 manifest 的原哈希，只恢复 previous-code 中的明确源码清单；新增文件保留为不被旧版引用的辅助文件，不删除图库或数据。
3. 不用旧业务/配置快照覆盖发布后的聊天、人工决定或账本；需要数据恢复须另行授权并验证一致性。
4. 旧代码需要不带新版本心跳校验启动，启动时仍核旧实例身份及端口；以认证/原版本/进程和心跳确认实际状态。R01 旧版会重新开放未知图库，回退有安全影响，应仅限必要诊断并明确报告。
5. 失败保留 manifest、控制器记录和日志，不盲目重试或结束端口的任意占用者。

R05 ACL Plan 单独在 `D:\dsbot\deployment-backups\20261026-independent-fixes-acl-plan`；旧备份另有 `20261026-independent-fixes-acl-legacy-plan`。本轮不执行 Apply、不把它计入代码发布的生产权限变更。

## 实际执行记录

尚未部署；待最终自检、本地提交及实际执行后追加。

08:32 首次真实停止返回超时：旧 worker 退出、原 Node 残留；没有复制生产代码或假报部署完成，回退未执行。经同一启动器补齐旧子进程归属及停止路径、合成回归与双 Shell 全集后，追加本地提交再继续。暂存脚本首次路径拼接错误在受限暂存区修复，未触及运行代码；原首次 source zip 和版本记录保留。

### 首次生效（实际已完成）

功能提交 `3825aab357a44783f02a87ef2130a8b381474805`。08:46:46 旧 Console 原子进程经同一受控入口停止，Bot 原已停；6185/7850 均无监听。414 份停写快照共35,248,033字节逐文件哈希一致，包含 DB/WAL/SHM，未打开生产 SQLite。仅在确认无图库 WAL 的停写备份上只读查询新共享策略，前后全部文件哈希不变，确认公开包89+49张可用、collect未知图不可见。

34/34 安装及哈希通过，13份变化。Bot worker48076/应用进程51132、Console worker34476/Node44656 新启动，08:47:24 通过版本/所属家族/心跳、认证及前后端核验。4份真实配置/凭据原哈希均未变；生产 ACL 未应用。

09:01 通过认证的本实例 Console 自重启接口再做一次实际交接：最初 pending 且 ok=false，随后可查询最终 succeeded；Node44656→43136，新 API/前端同为 `20261026-review-1`，Bot未重启。没有真实 QQ/模型验收调用。受控API原始状态/最终结果在受限目录 `actual-console-restart.json`。

SDK配置 bot_log=false，现有启动日志不能证明 QQ READY；因此不把上述 Bot 端口/心跳等同 QQ 连接就绪。正在增加只读、仅计数的 SDK READY/open 状态观察；对应 Bot 构建将为 `20261026-review-2`，Console 前后端仍为 review-1。此后续补充将单独提交、备份并重启 Bot，不能先记作已生效。

### review-2 待发布补充

Bot只读QQ连接观察及未知状态卡修正后，前后端/插件统一使用 `20261026-review-2`。16:42 接续核对旧34/34及原进程仍匹配。后续受限目录为 `D:\dsbot\deployment-backups\20261026-independent-fixes-qq-ready`，保留此前已生效review-1作为回退基线，不覆盖首次发布备份或旧快照。等待同版自检与本地提交后，重新停写备份并配套部署，实际结果待追加。

### review-2 实际生效及收尾

本地提交`d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd`后，16:46:25/26受控停止Console/Bot，端口释放。受保护目录`D:\dsbot\deployment-backups\20261026-independent-fixes-qq-ready`保存414份/35,323,876字节停写快照、原代码、34份manifest/暂存源码、源码zip（CRC通过）、配置哈希及可执行回退。快照包括DB/WAL/SHM，备份及收尾未打开活跃SQLite。

34/34安装哈希通过，其中7份变化。首次在同一PowerShell操作宿主先后加载不同路径的同名C#类型，Add-Type重复导致启动失败；改用新Shell调用运行实例原入口后16:47:27就绪，无代码补写、无假成功、无回退。Bot worker34796/应用17556，插件review-2，QQ只读SDK观察ready（配置1/就绪1）；Console初始Node5776。

16:49实际Console自重启经认证API受理pending/ok=false→最终succeeded，Node5776→33716、worker49144，API/前端均review-2；随后Bot start复用原worker/ticks。原始脱敏操作记录为同目录`actual-lifecycle-v2.json`。16:55`final-readonly-verify.ps1`核验34/34、服务身份/家族/监听、HTML实际返回哈希、无认证401/跨来源403、心跳0.094秒及SDK ready1/1，结果为`final-readonly-verification.json`。只读核验中瞬时状态查询子进程退出导致的WMI失败单独保留为核验器竞态，确认原身份退出后再核通过；没有据此重启服务。

四份配置/凭据与两轮部署前记录共8项哈希均一致，两组ACL Plan四目标原SDDL不变；图库149份文件与停写快照哈希不变。实际alarms.json在该快照和收尾均不存在，旧数据保留由合成测试验证。没有真实数据迁移、图库清理、身份重写、依赖安装或生产ACL Apply。

回退入口为该目录`rollback-code.ps1`，只停止核实的本实例、核当前/原哈希并恢复previous-code，不恢复业务/配置快照。此补充目录退回review-1（已含R01边界），首次发布目录退回更早版本会重新带入R01风险；不要混用。此次未执行任何回退。需要回退时先审阅脚本及manifest，按同一受控入口恢复启动并重新核版本/心跳/认证；数据恢复另需授权。

收尾通过临时合成实例发现两份回退脚本在切换旧启动器时也会遇同宿主Add-Type冲突；原脚本已受限留存，现每次启动器调用均独立Shell。有效失败（停止两次、代码已恢复、启动失败）→修复后pwsh/Windows PowerShell5.1各两个备份脚本均通过，精确停止两次/启动一次、代码恢复及合成业务文件哈希不变。证据为受保护同目录`rollback-red-valid.json`、`rollback-green.json`、`rollback-green-ps51.json`及`test-rollback-offline.py`；未对生产执行回退，不改变34份发布文件。

本轮离线最终Python258项（257通过、1明示跳过）、Node63/63、余额2/2、双Shell真实临时生命周期127.072秒、浏览器键盘7/跨刷新5等通过。SDK ready不等于真实QQ投递或长期稳定，本轮未获QQ/付费验收许可、未发送测试消息；R05生产ACL待授权，源码实际远程免费交付及素材权利链仍缺口。文档收尾提交仅固化记录，不触发重复部署。
