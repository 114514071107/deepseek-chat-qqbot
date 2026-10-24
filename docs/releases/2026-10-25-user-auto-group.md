# 用户自动归类与资料展示上线试用

日期：2026-10-25（Asia/Shanghai）。本地 dev 功能提交 `565158706dbab63ba74928a4624bc950eb0a6c02`，未推送或合并 main。按本轮实施后接续 B 验收指令及已核对的同任务部署/启动/QQ 授权，在新增实现源码和离线阶段通过、本地提交后发布。A 原验收结论保留，B 生产未完整通过，见[逐项记录与工具阻断](../reviews/2026-10-25-user-auto-group-review.md)。

受保护本机目录 `D:\dsbot\deployment-backups\20261025-user-auto-group-release` 包含 before/、staged/、data-snapshot/、release-manifest.json、source-commit.txt、corresponding-source.zip、安装/激活记录、原进程记录及准备/校验/停止/安装/回退脚本。沿用既有受限目录 ACL，备份及真实资料不进入源码 Git。

旧运行 28/28 匹配 d31827c，Bot/Console 进程身份先按 root、exe、创建时间及 nonce 核对，再停止已确认的两个托管 worker，确认端口/后代退出。停写后 **396 份数据及配置快照逐份哈希校验**。本次清单 29 项，新增插件 `user_profiles.py`，实际更新 6 份：插件 main.py/user_profiles.py，Console server.js/user-workbench.js/public/user-workbench.js/public/index.html。安装与激活 **29/29 哈希一致**，保留原部署常量与配置/凭据，不迁移历史或重写旧关联。

使用现有 `start-bot.ps1 -RuntimeRoot D:\dsbot -WithConsole -TimeoutSeconds 60`，Bot 新 worker 于 **06:51:21** 启动、Console 于 **06:51:33** 启动，精确身份匹配；06:52:51 激活读到 bot_running=true、API `20261025-auto-1`、4 份关键配置/凭据原哈希不变。实际刷新浏览器后新版用户页已加载。后续指定目标群/私聊的本地状态命令分别实际收到回复，来源/accepted 历史及管理观察可对应，未调用模型。

生产只观察到群平台用户名、私聊 user_openid 与昵称缺失，缺可信跨场景共现映射；不把合成自动分支当生产验证。既有人工组的群/私聊/具体群切换通过，解除停在确认框后电脑工具再次因网址判断限制强制停止。最后观察确认框未由助手 accept，可能仍残留；自动刷新勾选保持，但展开面板/确认等待会暂停重绘。此后没有继续 UI、写接口或其他电脑控制，也未做最后映射/业务文件哈希及健康复核。服务保留本版，不能据早先激活结果冒称结束时已全面复核。

代码回退须先重新确认当前托管进程身份并停止本实例，再校验 before/ 与 manifest.previous_sha256，使用本发布回退脚本恢复已存在文件，最后按既有入口启动核对。新增资料模块可保留，旧 main 不引用；**不以数据快照覆盖后续聊天、资料或映射，不删除新文件凑旧状态**。若映射已由新版人工操作写成 v2，旧版工作台不支持读取该版本，应保留映射并先安排兼容的控制台回退方案，不能直接拿旧快照覆盖人工决定。本轮未执行回退。
