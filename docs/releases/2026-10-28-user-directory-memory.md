# 用户与记忆入口配套发布

日期 2026-10-28，dev，功能构建 `20261028-identity-1`。本页持续追加实际结果，未执行事项不记为完成。实现与证据见[修复记录](../reviews/2026-10-28-user-directory-memory.md)。

沿用 startup-1 的 36 文件配套清单，新增插件 `user_directory.py` 共 37 份。保留运行副本 main 的五项部署常量与 Console MASTER；只部署明确代码，不覆盖真实配置、身份映射、历史、图库或虚拟环境。此前用户的七个人工人物入口保留，不导入合成测试资料。

受保护备份目录 `D:\dsbot\deployment-backups\20261028-user-directory`，仅当前账号与 SYSTEM 可访问。完成离线检查和本地提交后才暂存，保留 previous-code、staged、manifest、对应源码 ZIP，以及停写状态下的业务/配置快照（含需要保留的 DB/WAL/SHM，不打开 SQLite）。停止及启动只调用经核本实例启动器，不结束其他会话或未知进程。

代码回退：停同实例 Console/Bot，核对运行代码仍匹配本轮 manifest，恢复 previous-code，重新启动并核对旧版本/心跳/QQ/后台。新增未被旧代码引用的辅助模块和自助资料文件可保留；不回写旧业务快照覆盖新增聊天。后续运行数据恢复另行判断，不在代码回退内自动执行。旧版会重新带入此次已知目录问题。

本轮未获真实 QQ 测试发送许可，不以 SDK ready 代替客户端收到；未推送、未创建 PR、未合入 main。对应源码以本地功能 commit 的免费源码 ZIP 提供，公开 dev 可能落后，帮助入口保留向主人索取匹配源码的说明。

## 部署前验证

基线只读核对：实际运行 startup-1，36/36 原清单一致，4 配置哈希一致，Bot/Console 均就绪，QQ configured=1/ready=1；本轮没有沿用昨天的 PID。初始核验使用旧采集器更新了其 latest live-verification 输出，随后把这份当前结果另存本轮 before-live-verification；原始业务数据和配置未修改，后续证据均保存在本轮目录。

Node 71/71、身份 Python 9/9、人物浏览器 8/8、自动刷新竞争 3/3 通过。完整 Python 初跑的进程授权错误与对应双 Shell/所有权/worker/Console 复跑已如实列在修复记录；不抹去失败日志。备份目录保存原始及重跑日志、合成截图和独立任务内的发布/回退脚本。提交和安装结果在实际执行后追加。
