# S01—S09 启动流程配套发布

日期：2026-10-27（Asia/Shanghai）。本地dev，实施基线e4c9de7；本轮源码构建`20261027-startup-1`。状态持续追加，实际执行前不标已部署；[修复与验证记录](../reviews/2026-10-27-startup-fixes.md)保留原失败和取舍。无push/PR/main合并或生产ACL/数据迁移授权。

## 清单、备份和回退

沿用原34份配套清单，新增`launcher-shell.ps1`和插件`qq_readiness.py`，合计36份。部署暂存只保留原main部署常量与Console MASTER配置，不用公开模板覆盖。运行源码未推送时，帮助如实提供向主人免费索取匹配源码包的方式，公开dev仅作可能落后的参考，不宣称未发布commit已可远程取得。

受保护本机目录`D:\dsbot\deployment-backups\20261027-startup-fixes`仅当前账号及SYSTEM权限，保留manifest、previous-code、staged、完整无秘密源码ZIP、配置哈希、停写数据快照（含DB/WAL/SHM）及`rollback-code.ps1`。仅创建这份新备份的受限ACL，未收紧生产配置ACL。

自检通过并本地提交后才执行暂存；仅停止已核本实例Console/Bot及独立控制器，确认家族/端口退出后备份、逐文件安装和核哈希，再从运行入口启动同版双组件。实际命令、时间、进程、版本/心跳/QQ认证及前后端结果在执行后追加。生产SQLite不打开、不迁移，不删除图库或覆盖业务JSON。

回退用受保护`rollback-code.ps1`，每次启动器调用独立Shell，只恢复明确清单的原代码；新辅助模块可保留为不被旧代码引用的文件，不恢复旧业务/配置快照。退回原review-2会重新带入已知S01—S09启动限制，R01共享边界仍保留；回退后必须重新核实际版本/心跳/QQ/后台，不能直接记稳定。任何数据恢复或ACL应用另需授权。

## 实际结果

功能提交 `001b64d98d240e9356fa9a2f250ae14b98c848ac`，dev；280项Python/64项Node及专项、浏览器通过后固定。36份清单中13变化，源码ZIP CRC通过。03:16复查原worker/应用身份、两个监听及stopped心跳仍与开工相同，未被其他任务占用。

03:16—03:17，以新核心在独立系统5.1进程执行Console Stop、Bot Stop，均succeeded/not_running；原24800/10768/52404/14384全部退出、6185/7850监听消失。停写快照434份、37,599,482字节，逐份复制前/后哈希一致、保留DB/WAL/SHM，未打开SQLite。之后安装36/36，配置和业务文件没有用模板覆盖。

从`C:\Windows`执行实际`D:\dsbot\start-bot.cmd`，能力预检选择7.6.5（其子环境PSModulePath正常化后预检可用，与此前工具宿主缺模块不同），03:17:49 Bot、03:17:52 Console取得ready，最终All succeeded。部署没有修改系统模块、PATH或安装依赖。损坏候选及5.1回退另由隔离专项实测。

实际认证Console API自重启：受理pending/ok=false，操作ID `229bd4033ed3ffa3c1833ac1c3c0dd84`最终succeeded，Node47408→48548，Bot7248保持；03:23默认cmd重复启动复用两个实例，均强核ready。运行Bot worker54692、应用7248；Console worker31484、应用48548；独立控制器14268，均核PID/ticks/exe/root/nonce、监听归属及当前非管理员主体。03:27再次36/36、8配置快照、4原ACL、149图库文件哈希不变；闹钟文件没有新增，生产ACL未应用。

实际后台Edge浏览器通过Basic认证访问当前运行页：显示“在线”，初次加4次刷新后“能力与隐私”仅1份，pageerror0、生产写入0。API/前端均startup-1，认证首页字节哈希等同安装文件；无认证401、跨来源403仍有效。

03:21私聊S9P01、03:23群聊S9G01：在原生QQ核实指定测试账号、群号及带官方机器人标记的实际资料卡后，各发送一条最小普通模型合成题；客户端均实际显示正确回复。每项历史user/assistant各1、request finished、accepted回执1，冻结来源/请求一致，服务收到至accepted分别7.311/10.781秒，未精确测量客户端延迟。没有调用管理工具、发图片、操作其他群或主人号；测试自然新增历史/用量未清理，发送由测试客户端完成，启动器没有测试消息逻辑。

聊天后完成375.032秒连续观察（19次，含每次强核API耗时），全部stopped=false、QQ ready1/1、Bot和Console进程不变，心跳最大年龄0.131秒；最终仍36/36且认证/页面/版本通过。覆盖原约5分钟失效窗口，运行从03:17至03:30持续有效。历史S09首次退出的具体触发及WMI拒绝执行的OS策略名仍未取得证据；已修复可重现机制并增加有界故障与退出原因，这段有界观察不等于长期稳定。

## 实际命令与复跑入口

以下命令均在独立进程调用，避免同Shell Add-Type旧类型复用：

```powershell
& 'D:\dsbot\venv\Scripts\python.exe' -X utf8 -B -m unittest discover -s tests -p 'test_repair_*.py' -v
node --test console/tests/*.test.js
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -NonInteractive -File 'D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.ps1' -RuntimeRoot 'D:\dsbot' -Component Console -Action Stop -TimeoutSeconds 30
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -NonInteractive -File 'D:\DSH Workspace\deepseek-chat-qqbot\scripts\start-bot.ps1' -RuntimeRoot 'D:\dsbot' -Component Bot -Action Stop -TimeoutSeconds 30
& 'D:\dsbot\venv\Scripts\python.exe' -X utf8 'D:\dsbot\deployment-backups\20261027-startup-fixes\prepare_release.py'
& 'D:\dsbot\venv\Scripts\python.exe' -X utf8 'D:\dsbot\deployment-backups\20261027-startup-fixes\stopped_snapshot.py'
& 'D:\dsbot\start-bot.cmd'
& 'D:\dsbot\venv\Scripts\python.exe' -X utf8 'D:\dsbot\deployment-backups\20261027-startup-fixes\verify_live.py' --restart-console
& 'D:\dsbot\venv\Scripts\python.exe' -X utf8 'D:\dsbot\deployment-backups\20261027-startup-fixes\verify_live.py' --observe
```

上表列复跑入口，不是盲目再次执行整组部署的指令；prepare_release只允许干净本地提交，真实文件复制由清单路径及前后SHA校验保护。受保护目录另有collect_qq.py（只导出两条合成用例的布尔结果/计数）、live-browser.cjs、final-readonly-verify.ps1及原始结果。仓库忽略目录保存启动完整失败/通过日志和rollback-verification.json。回退脚本已在36份合成清单验证恢复旧代码、新辅助文件不被引用、独立Shell启停，以及运行文件被他人改动时拒绝覆盖；未在生产执行回退。

当前仅本地dev，未push/PR/main晋级；提供匹配功能提交的受保护免费源码ZIP，公开dev仍可能落后。本轮离线与定向实测通过后仍需用户试用验收，不宣称无人看管长期稳定，原R05生产ACL/素材权利链等历史开放项没有被本单关闭。

03:32收尾只读复核仍36/36、8配置/4原ACL/149图库不变、心跳0.127秒及QQ ready1/1；原实例新进程保持。没有遗留以本轮临时dsh根启动的fixture进程，收尾审计没有结束任何进程。固定功能之后只补测试失败路径收尾与文档，启动矩阵4/4、232.947秒再通过，生产产品文件无需重复安装或重启。
