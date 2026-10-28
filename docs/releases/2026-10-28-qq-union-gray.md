# QQ union 白名单观察版发布

2026-10-28，dev，构建20261028-union-gray-1；固定发布提交867b733bb1a4c301101649b37eada6e84ef1949b，功能5465aeb。用户明确允许Bot／Console各一次受控重启并用指定QQ验收。

44文件成套发布，10变更／新增；477文件停写物理快照含DB/WAL/SHM，不打开SQLite。发布流程38.22秒，新Bot27228／Node23096，版本、44运行哈希、心跳、QQ ready1/1及401/403核对通过。五份原配置／凭据／人工及本人身份文件未变。

上线先observe，只指定测试账号私聊＋一群；实际QQ各一条身份帮助均客户端收到、后台各一条accepted。两条可信事件union_openid字段存在但为空，因此从未开启apply，未自动改变真实人物归属或停用绑定。收尾将策略置为过期，原业务保持，未二次重启；尚不能认定免绑定功能可用于本应用。

受保护备份与源码包：D:\dsbot\deployment-backups\20261028-user-directory\independent-repair\union-gray。保存prepare/perform发布脚本、manifest、previous-code、staged、停写快照、固定源码ZIP、安装/生效/QQ摘要，以及disable-canary.ps1。该脚本只关闭策略，无需重启；全量代码回退应另定维护窗口，保留新增业务资料，不回写旧快照。

首次停止调用在参数绑定阶段被拒，服务未停；修正本机发布调用后才执行一次成功周期，原失败日志保留。Python全集320项有4项PowerShell5.1 AuthorizationManager失败、1跳过，未宣称全绿；新增Python21、全Node90通过。无push／PR／main、依赖/ACL/QQ权限变更、付费模型/媒体或真实数据迁移。

详情与证据：[本轮实施和真实取证](../reviews/2026-10-28-qq-union-gray.md)。后续仅文档提交不再部署或重启。
