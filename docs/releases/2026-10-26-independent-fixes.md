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
