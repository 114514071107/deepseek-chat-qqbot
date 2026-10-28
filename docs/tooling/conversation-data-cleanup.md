# 私聊与整群模式：旧数据清理与发布

适用构建 `20261029-conversations-1`。新实例完成原有基本接入即可聊天，不运行迁移，也不配置任何身份映射。此工具只用于已有实例的旧成员记忆/混合旧档，绝不在 Bot 启动时自动运行。

## 数据边界

| 对象 | 处理 |
| --- | --- |
| 有可信私聊来源、未与旧群成员键冲突的 p2 记忆 | 保留 |
| 整群 g2 的记忆、摘要、学习资料、念头 | 保留 |
| 仅群成员拥有的 p2/c2 独立记忆、旧个人摘要 | 原文件完整备份后移出业务路径 |
| 既有私聊又有群成员共用同一个 p2 的旧记忆 | 无法可靠拆分，完整备份隔离，不归给私聊或群 |
| 裸 ID、未知来源、共享旧记忆 | 完整备份隔离，禁止按昵称猜归属 |
| 人物映射、一次性身份目录、Union 灰度/观察文件 | 完整备份后退役 |
| history、groups、archive/JSONL、scopes、积分、媒体、凭据、SQLite | 不在清理动作内 |

每个动作记录相对路径、长度、SHA-256、处理原因；念头索引只移除退役键，整份旧索引仍备份。备份目录必须在业务数据根之外，并沿用本机已有保护。备份和隔离不进入目录、检索、上下文扫描；不要复制到 `dsh_data` 的 memories、profiles、memes 或 archive。

## 停写后精确执行

以下示例使用本实例已存在的受保护备份父目录。`cleanup-recovery` 必须是未使用的新恢复目录；不要复用旧 manifest。完整私有清单含来源键，仅留本机，禁止进 Git。

1. 先完成代码离线检查，取得本轮有效的 Bot/Console 发布停写窗口。核对当前实例和进程，使用已有启动器停止受影响组件；确认没有活跃写入。旧的单次重启授权不能重复使用。
2. 停写后重新生成 Plan（运行期间生成的 Plan 只供评审），核对每项原因及原聊天动作数为零。备份同版旧代码及必要配置；不要连接活跃 SQLite 来备份。

```powershell
Set-Location 'D:\DSH Workspace\deepseek-chat-qqbot'
$python = 'D:\dsbot\venv\Scripts\python.exe'
$dataRoot = 'D:\dsbot\dsh_data'
$reviewRoot = 'D:\dsbot\deployment-backups\20261028-user-directory\independent-repair\union-gray\conversation-change'
& $python -B scripts/conversation_cleanup.py --root $dataRoot --plan "$reviewRoot\reviewed-cleanup-plan.json"
# 审阅 JSON 中 actions；确认所有目标有可信来源或明确列为歧义隔离。
& $python -B scripts/conversation_cleanup.py --root $dataRoot --plan "$reviewRoot\reviewed-cleanup-plan.json" --backup "$reviewRoot\cleanup-recovery" --apply
```

Apply 在首次移除前完整复制所有待处理原文件，fsync 并核对哈希，写恢复 manifest 后才清理。路径越界、符号链接、文件/标记漂移、近期活跃心跳会拒绝。JSON 原子替换；中断保留已完成备份，不自动覆盖或继续用同一恢复目录。对剩余文件重新 Plan，使用另一新目录，逐项检查上次 manifest。

3. 再次 Plan 应无清理动作；原私聊及群聊天文件哈希应与停写前一致。不能把“计划 15 项”写成“已清理 15 项”。有同裸 ID 冲突但尚无旧文件时，工具仅建立可恢复的清理状态标记，允许以后独立私聊写新记忆。
4. 按本轮发布清单配套安装 Python 插件与 Console 前后端，删除清单中的三个退役模块；保留部署常量、真实配置和凭据。启动、检查新进程/构建/有效心跳/QQ 就绪，再按已授权范围实测。本轮未获新窗口时停在已验证交付，不修改运行实例。

## 恢复

停止实例写入，核对 backup manifest 的 root 和原文件哈希，然后：

```powershell
& $python -B scripts/conversation_cleanup.py --root $dataRoot --backup "$reviewRoot\cleanup-recovery" --restore
```

恢复先撤销“旧歧义键已清理”标记，再原子恢复原文件；中断时不会把已恢复的混合旧记忆当作可信私聊读取。若已有新业务文件或索引变化，拒绝自动覆盖；先保存新增数据，人工逐项处理。恢复到旧代码还需使用同版代码备份，不能仅还原页面。清理后新私聊记忆不会被重复清理，旧混合记忆也不会合入新私聊或群记忆。

## 2026-10-29 本机执行记录

本机用户已明确授权后执行15项，13份退役文件备份隔离、2念头索引过滤；再次Plan为0、重复Apply为0。首轮因停机后新鲜旧心跳拒绝，后续等待租约自然过期再执行，没有伪造stopped。使用新的受保护conversation-cleanup-publish-20261029目录，示例旧路径仅为历史；原聊天/归档/积分/媒体/SQLite未清理。恢复限制和结果见[实际执行记录](../releases/2026-10-29-conversation-cleanup-dev-publication.md)。
