# 主 Agent Context 补修上线记录

日期：2026-10-23（Asia/Shanghai）。用户在[源码与离线验收](../reviews/2026-10-23-main-agent-context-acceptance.md)通过后明确要求“上线新功能，推送远端，然后启动 bot”。本次只发布已验收 Context 补修，main 保留 `5641b0a`，F09 与其他暂缓项不变。

## 发布与启动结果

- 功能源码提交：`34445bb04e86f152b6a4811f866ef90fadb1d5f7`，位于 dev。功能修改限 model_integration.py：请求内浅复制真实 Context，仅绑定预算提供商查询入口；原 Context、Provider 类型、服务引用和请求预算隔离保留，不改框架或 Pydantic。
- 本轮重新运行 Python **160/160**（包含三项真实 builder 构造专项）、余额 **2/2**、Node **12/12**，全部通过；44 份 Python AST、前后端及页面脚本语法、暂存差异检查、生产秘密匹配检查通过。交付快照中的功能源码与测试匹配，文档验收追加保留。
- 现有 21 份运行文件与第四单发布清单一致后，完成本地提交、暂存与部署常量保留。停止控制台，向核实过的机器人控制台发送 Ctrl+C，确认本实例进程退出后备份。
- 停写后完整复制 dsh_data、框架根文件及 data/config，包含当时存在的数据库/WAL/SHM；**332** 份快照文件逐份 SHA256 校验一致，没有连接活跃 SQLite。安装改变两份运行文件：model_integration.py 和固定源码入口的 main.py；其余文件保持原字节，完整清单 **21/21** 匹配发布暂存版。
- 将功能提交推送 origin/dev 后，使用既有 deployment-config/start-runtime.ps1 分别完整启动 Bot/Console；activation.json 记录推送先于启动。执行完整进程启动使新的内存适配器生效，没有只覆盖文件后沿用旧进程。
- 07:54（Asia/Shanghai）核实 127.0.0.1:6185 与 :7850 监听，核心和余额插件加载，QQ 日志显示会话建立，bot_running=true，管理租约新鲜；启动日志无 Traceback、ERROR、CRITICAL。
- 控制台已认证首页 200、无凭据历史读取 401、已认证跨站 API 403；现有控制台版本 `20261023-delivery-3` 沿用。框架 cmd_config.json 和插件 dsh_soul_conf.json 与停写快照哈希均相同；原平台绑定、加密凭据、数据目录 ACL、依赖和真实旧数据均保留。

运行副本源码入口固定到[实际功能提交](https://github.com/114514071107/deepseek-chat-qqbot/tree/34445bb04e86f152b6a4811f866ef90fadb1d5f7)，源码包对应同一提交。未向 upstream 推送、未改 main 或历史标签。

## 记录与回退

受保护本机目录：`D:\dsbot\deployment-backups\20261023-context-fix-release`，仅当前 Windows 运行账号与 SYSTEM 访问，不加入 Git。

- before/：原同版代码、部署环境、配置、启动器及 ACL；data-snapshot/：一致性数据快照。
- release-manifest.json、source-commit.txt、installation.json：原/暂存/运行哈希，功能源码版本和快照校验；activation.json、verification.json：启动顺序与健康检查。
- corresponding-source.zip：实际功能提交的无秘密源码；DEPLOYMENT.md 为本文本机副本。旧标准日志移动到 stopped-*，新日志继续使用运行根目录标准路径。
- 回退时先停止 Bot/Console，在 PowerShell 7 运行 rollback-code.ps1 按哈希恢复原代码，再使用现有启动器重新启动。新增代码不涉及配置、数据格式或依赖迁移，不能以代码回退为由覆盖新聊天或重放 unknown。
- 回退到原 model_integration.py 会重新引入 Context 类型阻断，只用于排障；不要将其描述为恢复聊天的解决方案。

## 实测边界与下一步

当前状态是：已验收补修已应用运行实例、源码已推送 dev、bot 已启动并连接 QQ。原“运行副本尚未更新”的验收说明是当时状态，后续以本记录为准。

本轮没有主动发起真实模型调用或发送 QQ 验收消息。隔离真实 builder 测试已覆盖原类型错误，但启动和连接检查不能代替真实客户端聊天到达。普通文字、图片描述、客户端到达、实际费用、热重载及长期稳定性仍需后续实测；不因本次发布自动晋级 main。实测结果应追加到本记录或对应验收文档。
