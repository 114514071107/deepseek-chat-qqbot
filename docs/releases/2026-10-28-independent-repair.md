# 独立评审补修配套发布

2026-10-28，dev，构建 `20261028-repair-1`。实现与离线证据见[修复记录](../reviews/2026-10-28-independent-repair.md)。发布执行后追加准确commit、清单、进程和就绪证据，未执行步骤不算完成。

依据当前AGENTS常态授权，本轮代码先本地提交、精确备份和暂存，再发布到本实例使版本生效。没有等待用户验收才部署，也不将部署等同验收。本轮没有QQ测试/付费模型许可，不执行远端push、PR或合并main。

开始时端口6185/7850无监听，磁盘旧心跳不是当前运行证据。旧identity-2清单37份运行文件/基线HEAD源码全部匹配。保留两个已正确转发的旧Bot兼容入口；只覆盖本轮明确的Console入口及配套代码。

受保护备份计划位置 `D:\dsbot\deployment-backups\20261028-user-directory\independent-repair`，从已保护父目录继承maintenance+SYSTEM，不改变现有生产ACL。上级deployment-backups本身较宽，不能直接把含真实参数的备份放在未保护的新兄弟目录。parent D:\的DELETE_CHILD风险仍在D03方案中，备份保护不代表整体宿主隔离通过。

发布清单从当前37文件原manifest逐项扩充必要模块/Console入口，实际数动态计算。插件新增event_admission.py与main/task_runtime配套，Console全部原前后端和新入口同版，root入口及参数保持配对。main的五项部署常量及server MASTER仅从已核运行副本内存提取，保留真实值，不入Git。配置、凭据、真实身份/聊天/记忆/图库不被模板覆盖，不迁移数据或安装包。

停同实例组件后，确认无已核本实例写入进程，再作业务/配置物理快照；DB/WAL/SHM按原字节一起复制并核前后哈希，不打开SQLite。只从staged安装文件，核source/staged/runtime哈希；启动后检查新进程/归属、版本、心跳与QQ连接及认证页面。后台活动可能正常更新业务回执，不回写旧快照。

回退只恢复previous-code及原入口，同实例停/启每次独立Shell；新增模块可留在磁盘但旧版不引用。不恢复旧聊天/身份/积分/DB快照覆盖运行期间新增材料。旧版会恢复D01/D02/D04/D05/D06/D07已知风险。精确回退脚本与实际manifest保存在同一备份目录。

## 实际执行与最终核对

功能本地提交 `daa013d1a1b2d27523e88c860b66d31903c8e165`，空白/流程记录追加提交 **`b971dab53e22daba57a31f07a48808cca40e7240`**，后者是配套暂存/源码ZIP的固定版本。收尾文档提交不改变产品代码，不重复部署。

2026-10-28 14:21（Asia/Shanghai），使用实际旧同实例启动器分别Stop Console/Bot，退出均0；开始时两服务已不在线，因此此次记录为启动，不伪称重启。两个端口确认无监听、精确AstrBot/Node/worker筛选未检出本实例写入者后，复制 **477 文件 / 58136536 字节**，逐文件复制前/后及整批末尾源/备份哈希一致。没有建立SQLite连接、未执行恢复实验；DB/WAL/SHM保留于物理快照，不宣称恢复验收通过。

实际清单 **40 份 / 13份变化**；所有source、staged与运行哈希均核对，main五项真实部署常量和Console MASTER保留。受保护6份配置/凭据/人工和自助身份文件仍匹配发布前哈希；旧Bot兼容转发cmd不改，运行Console旧直启VBS已被本次明确入口覆盖，deployment-config旧脚本保留供历史参考，不自动删除。

14:21:23 新Bot应用PID **41412**，14:21:39 新Console PID **23348**；两者OwnerSid均与维护主体相同（不记录SID原值），监听127.0.0.1:6185/7850分别属于这两个进程。实际插件/API/前端均 `20261028-repair-1`，Bot状态succeeded/readiness ready，QQ configured=1/ready=1；14:24:11复核心跳年龄0.12秒，非旧磁盘租约。认证页面字节与部署文件一致，未认证401、跨来源403仍有效。

实际Edge只读页面：7人物入口/7记忆选项来自本轮API动态计数，所有选项有非空称呼或缺失标记；用户页默认全部消息，页面JS错误0、生产写请求0。图库旧表情示意GET在独立检查浏览器中跳过，以免未经SQLite前置一致性证明间接连接图库库；没有据此验收图库。当前SDK ready不等于客户端收到，**尚未验证客户端实际收发**，没有发真实QQ测试消息或付费模型验收请求。

备份目录 **`D:\dsbot\deployment-backups\20261028-user-directory\independent-repair`**：release-manifest/release-version、previous-code、staged、停写数据及manifest、六文件前置哈希、source-b971dab…zip（CRC通过）、Stop/Start输出、process-ownership、live-verification、browser-live、final-summary及rollback-code.ps1。backup目录仅继承已保护父目录，无Users/AuthUsers Allow；D:\祖先替换风险另见D03，不以备份私有化宣称宿主边界完整。

当前状态：**已部署，待独立验收/用户试用；未push、未PR、未合并main**。生产ACL未Apply、业务数据未迁移/恢复/清理；旧资料与新增资料保留。回退仅按本目录同版清单恢复代码/入口，不把旧业务快照自动还原。详见[脱敏生效证据](../reviews/evidence/2026-10-28-independent-repair/deployment-summary.json)。

## 获准真实QQ专项后的状态补充

2026-10-28，用户明确许可后，复用本轮同版新启动证据，重新核40文件/实际进程/心跳/QQ ready；指定账号的群与私聊模型消息、身份帮助及跨场景认领确认/过期/重放已实际收发，详见[专项矩阵](../reviews/2026-10-28-repair-real-qq-acceptance.md)。不重复部署/重启。自助目录因正常验证命令新增两条来源并关联，旧称呼及原人工映射保持，其余5份配置/凭据/人工映射哈希不变；不恢复发布前目录快照。媒体实收/账单/长期稳定未验收，ACL窗口另行安排、不Apply，未push/PR/main。
