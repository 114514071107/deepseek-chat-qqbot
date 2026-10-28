# 独立评审补修配套发布

2026-10-28，dev，构建 `20261028-repair-1`。实现与离线证据见[修复记录](../reviews/2026-10-28-independent-repair.md)。发布执行后追加准确commit、清单、进程和就绪证据，未执行步骤不算完成。

依据当前AGENTS常态授权，本轮代码先本地提交、精确备份和暂存，再发布到本实例使版本生效。没有等待用户验收才部署，也不将部署等同验收。本轮没有QQ测试/付费模型许可，不执行远端push、PR或合并main。

开始时端口6185/7850无监听，磁盘旧心跳不是当前运行证据。旧identity-2清单37份运行文件/基线HEAD源码全部匹配。保留两个已正确转发的旧Bot兼容入口；只覆盖本轮明确的Console入口及配套代码。

受保护备份计划位置 `D:\dsbot\deployment-backups\20261028-user-directory\independent-repair`，从已保护父目录继承maintenance+SYSTEM，不改变现有生产ACL。上级deployment-backups本身较宽，不能直接把含真实参数的备份放在未保护的新兄弟目录。parent D:\的DELETE_CHILD风险仍在D03方案中，备份保护不代表整体宿主隔离通过。

发布清单从当前37文件原manifest逐项扩充必要模块/Console入口，实际数动态计算。插件新增event_admission.py与main/task_runtime配套，Console全部原前后端和新入口同版，root入口及参数保持配对。main的五项部署常量及server MASTER仅从已核运行副本内存提取，保留真实值，不入Git。配置、凭据、真实身份/聊天/记忆/图库不被模板覆盖，不迁移数据或安装包。

停同实例组件后，确认无已核本实例写入进程，再作业务/配置物理快照；DB/WAL/SHM按原字节一起复制并核前后哈希，不打开SQLite。只从staged安装文件，核source/staged/runtime哈希；启动后检查新进程/归属、版本、心跳与QQ连接及认证页面。后台活动可能正常更新业务回执，不回写旧快照。

回退只恢复previous-code及原入口，同实例停/启每次独立Shell；新增模块可留在磁盘但旧版不引用。不恢复旧聊天/身份/积分/DB快照覆盖运行期间新增材料。旧版会恢复D01/D02/D04/D05/D06/D07已知风险。精确回退脚本与实际manifest保存在同一备份目录。
