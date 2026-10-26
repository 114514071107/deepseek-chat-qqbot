# startup-1 运行核对与 dev 发布

日期：2026-10-27（Asia/Shanghai）。用户明确要求“将目前的新功能上线运行，并推送远端 dev”。本轮范围是已完成源码/离线验证、群私聊定向实测及有界运行观察的 S01—S09 启动补修，按明确指令发布 dev 试用；长期稳定性和用户后续试用分别保留，不据此晋级 main。

## 版本与现场核对

开工 dev HEAD `f23c89207c3a5088169471d9967744eec2a51898`，工作区干净，领先 origin/dev `e4c9de7` 两个提交且没有分叉。产品功能提交 `001b64d98d240e9356fa9a2f250ae14b98c848ac`，构建 `20261027-startup-1`；后一提交仅修改测试失败收尾与交付记录，36 份运行产品源码没有变化。

03:49 新执行现场核验：36/36 发布文件与当前源码及部署 manifest 一致，独立控制器身份有效；Bot worker54692/应用7248，Console worker53740/Node10372，创建时间、可执行文件、运行根、nonce、当前服务主体及监听家族均匹配。6185/7850 正常，API、前端和插件均为 startup-1，实际返回首页字节哈希等同安装文件；心跳年龄0.082秒、stopped=false、QQ SDK ready1/1；无认证401、跨来源403。

该版本已在前一实施任务成套部署并完成必要重启，当前仍然生效。因此本轮保留现有运行进程，不重复覆盖或重启，不让纯文档提交触发重复部署。原部署、群私聊真实到达及375秒/19次观察见[配套部署记录](2026-10-27-startup-fixes.md)和[补修验收证据](../reviews/2026-10-27-startup-fixes.md)；这些是前一阶段事实，不描述为本轮再次发信或重跑全集。

8 项配置凭据基线、4 项原生产 ACL、149 份图库文件均未变化。没有新增闹钟文件，没有打开活跃 SQLite、清理或迁移真实数据、修改生产配置/权限、安装依赖、发起 QQ 测试消息或付费模型验收调用。

## 本轮新执行验证

- `python -X utf8 -B -m unittest discover -s tests -p test_repair_platform_resume.py`：7/7，5.806秒，通过；使用合成 SDK 事件，不连接真实 QQ。
- 同入口 `test_repair_admin_service.py`：5/5，3.723秒，通过；临时数据验证管理任务取消隔离、原子写入冲突及退出原因。
- `node --test console/tests/*.test.js`：64/64，通过。
- 产品源码相对功能提交无变化，源码及运行 manifest 36/36；`git diff --check`通过。
- 提交前，37份待推文件和42个待推历史blob对照10项本机已知敏感值，命中0；文档链接无缺失。结项文档另核。

本轮证据单独保存于受限本机目录 `D:\dsbot\deployment-backups\20261027-dev-publication`，没有覆盖原部署和实测证据。核验仅作读取和受限证据落盘，没有调用生产生命周期写接口。

## 推送与对应源码

本轮明确推送授权已核，普通 `git push origin HEAD:refs/heads/dev` 成功：远端dev由 `e4c9de7` 前进至 `1f46c70a55374c9233fe7ce59b2cfaecb0520d81`，包含功能001b64d、测试/验收收尾f23c892及本文。远端dev、本地HEAD和origin/dev一致，工作区干净。结项只追加文档并在同一授权范围再次普通推送，最终提交SHA由仓库外TASKS.md记录，避免在提交内递归记录自身hash。

以不提供认证信息的HTTPS请求下载[运行功能对应的完整源码ZIP](https://codeload.github.com/114514071107/deepseek-chat-qqbot/zip/001b64d98d240e9356fa9a2f250ae14b98c848ac)，返回200，CRC通过，236/236文件与本地对应Git archive逐项SHA256一致。下载包为2,888,410字节，SHA256 `b04a41786c901f1f612b9bb5465ba2c638bad910c2fb6994a847c3abbb2e5de1`，核验副本留在本轮受限证据目录；本次新功能对应源码已可免费远程获取。素材权利链没有因此关闭。

03:51推送后再核36/36、原运行进程、心跳0.102秒、QQ ready1/1、前后端/实际HTML和401/403均通过；随后只读管理状态报告bot_running=true、readiness=ready、status=succeeded。两次现场核验均未重启服务或发QQ消息。main远端仍为 `5641b0a1e01f76b55293fa427b319136f1f7b837`，没有upstream写入、强推、PR或新增长期分支。结果为**当前新功能在线运行，定向验证通过并已发布origin/dev**。

## 备份、回退与保留项

本轮没有重新部署，沿用受保护 `D:\dsbot\deployment-backups\20261027-startup-fixes`：36份发布manifest、previous-code、完整对应源码ZIP、434份停写数据快照（含DB/WAL/SHM）及`rollback-code.ps1`。具体回退步骤见[原发布记录](2026-10-27-startup-fixes.md)。恢复时先核本实例身份、家族和端口，按明确清单恢复旧代码，不用旧业务/配置快照覆盖新聊天；恢复review-2会重新带入已知启动限制。生产没有执行回退。

历史S09首次失效的具体触发、旧WMI拒绝执行的具体OS策略、R05生产配置权限、素材权利链、长期稳定性及既有暂缓项仍开放。本次属于dev功能试用发布，不是main稳定发布，不把既有定向实测扩大为全部功能或长期稳定验收。
