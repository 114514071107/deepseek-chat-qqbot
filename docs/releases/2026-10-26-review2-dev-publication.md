# review-2 运行核对与 dev 发布

日期：2026-10-26（Asia/Shanghai）。用户明确要求“将目前的新功能上线运行，并推送远端 dev”。本轮发布范围是已经部署并完成定向验收的当前 dev 功能，不涉及 main 稳定晋级。

## 版本与运行结果

运行功能提交为 `d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd`，插件、Console API 和前端均为 `20261026-review-2`。开工本地 dev HEAD 为 `d2dc069`，领先 origin/dev（`0568dac`）8 个提交；未提交的两份文件属于本版本的验收记录与回链，本轮审阅后一并纳入交付。

该功能已在前一部署任务安装，本轮重新核实 34/34 发布文件的源码、功能提交、运行副本哈希全部匹配；需要发布的产品文件没有遗漏，功能提交之后没有新增产品代码。因此本轮保留已经生效的部署与现有进程，不重复覆盖、停机或重启。文档提交不改变运行功能版本。

22:48 的现场核验通过：Bot worker 50572 / 应用 17740，Console worker 49068 / Node 6896；运行根、创建时间、可执行文件、nonce、实例进程家族、服务主体及监听归属全部匹配。6185 与 7850 正常，实际 HTML 哈希匹配、API/页面版本一致；Bot 新鲜心跳及 QQ SDK ready 1/1。无认证请求为 401、跨来源请求为 403。

8 项配置凭据哈希、4 项原生产 ACL、149 份图库文件与发布基线一致。本轮没有修改配置、应用 ACL、安装依赖、迁移/清理真实数据、打开活跃 SQLite、发送 QQ 测试消息或发起付费模型验收调用。

## 本轮验证

- `python -B -m unittest discover -s tests -p test_repair_platform_ready.py`：3/3，通过。
- 同入口 `test_repair_gallery_privacy.py`：2/2；`test_repair_alarm_unavailable.py`：1/1，通过。
- `node --test console/tests/repair-*.test.js`：63/63，通过。
- `git diff --check`、待发布文件与部署清单核对通过；90 份待交付文件、141 个待推送历史 blob 与 10 项本机敏感值逐项比对，命中 0，文档链接无缺失。

以上是本轮新执行的检查。完整回归与指定账号的真实 QQ/生产控制台验收依据保留在[补修记录](../reviews/2026-10-26-independent-fixes.md)和[定向验收](../reviews/2026-10-26-review2-live-acceptance.md)，没有把旧全集描述为本轮重跑。

## 远端交付状态

本轮普通 `git push origin HEAD:refs/heads/dev` 成功，origin/dev 从 `0568dac` 前进至 `80777990ca0a0a63ad964b989a8a691cc963b647`，包含前述 8 项已固定成果及本次验收/发布记录。远端 dev、本地 HEAD、origin/dev 一致；无分叉。后续纯文档结项提交同属本次授权范围，最终远端 SHA 记录在仓库外 TASKS.md。

实际以**不提供认证信息**的 HTTPS 请求下载运行功能提交的[完整源码 ZIP](https://codeload.github.com/114514071107/deepseek-chat-qqbot/zip/d62fe254a6c1d3ae53233f31bb0391ad8bcaf9bd)，返回 200，CRC 通过；219/219 份源码与本地对应 Git archive 逐文件 SHA256 完全一致。归档为 2,833,122 字节，SHA256 `bea02af524d0c60b4c49ca7b19f8a8ce2c4811e751a92a69db5fe135c28a2945`，核验副本保存在本轮受限证据目录。这补齐 R06“运行版本对应源码尚未远程可获取”的具体缺口，不等于素材权利链或全部许可证要求已验收。

推送后 22:52 再次现场核验通过：34/34、原进程与服务身份、QQ ready 1/1、前后端、认证及保留配置均不变。main 远端仍为 `5641b0a1e01f76b55293fa427b319136f1f7b837`，没有 PR、强推、历史改写或 upstream 写入。本次状态为**当前功能已部署运行、定向验收通过、已推送 origin/dev**，整体开放项保持下节范围。

## 备份、回退与保留事项

原部署备份和回退仍使用 `D:\dsbot\deployment-backups\20261026-independent-fixes-qq-ready`，有 34 文件 manifest、原代码及包含 DB/WAL/SHM 的停写快照；具体步骤见[原部署记录](2026-10-26-independent-fixes.md)。回退前审阅 `rollback-code.ps1`，按同一实例入口停止并核实归属，只恢复明确代码清单；不使用旧业务快照覆盖新增聊天，不混用更早会恢复图库风险的回退版本。本轮未执行回退。

本轮只读证据单独保存在受限本机 `D:\dsbot\deployment-backups\20261026-dev-publication`，原部署和验收证据未覆盖。核验脚本准备时一次输出路径替换失败，未生成核验器、未接触产品代码；修正后重新运行成功。

R05 真实配置 ACL 尚未应用，素材权利链、长期运行稳定性及其他暂缓项继续开放。本次为 dev 试用交付，不能据此宣称全部安全问题关闭或晋级 main。运行功能版本对应源码的匿名远程下载已按上节独立核实。
