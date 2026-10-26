# 2026-10-26 独立评审补修配套发布

实施与限制见 [评审记录](../reviews/2026-10-26-independent-fixes.md)。本轮版本 `20261026-review-1`；仅本地 dev，未推送/PR/main 合并。发布状态及功能 commit 在实际执行后追加。

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
