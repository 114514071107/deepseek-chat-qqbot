# 本地开发与发布

## 2026-10-27：S01—S09启动流程补修

当前补修构建`20261027-startup-1`：重复Start不清理原实例，默认检查实际插件/心跳/QQ认证状态；解释器统一动作前预检，独立控制器从组件Job外执行同一入口；应用挂起创建并明确入Job；管理租约独立于聊天请求，有界处理Windows文件冲突并记录退出原因；RESUMED按当前连接确认，页面卡片缓存一致。原R01—R07边界保持。实际测试/独立复核、提交及生效状态见[本轮记录](docs/reviews/2026-10-27-startup-fixes.md)，未写明的部署/QQ结果不能沿用历史通过。

功能001b64d已配套部署36/36；本轮Python280（原跳过1）/Node64、专项及浏览器通过，测试收尾补强后双Shell启动矩阵再跑4/4通过。实际后台在线、指定群/私聊正确实收、聊天后375秒/19次有效心跳与QQ ready1/1通过，备份及回退见[发布记录](docs/releases/2026-10-27-startup-fixes.md)。仍是本地dev试用，未push/main晋级；历史S09首次触发和S07OS策略名未定，不宣称长期稳定。

## 2026-10-26：独立评审 R01—R07 补修

共享图库按可核来源与内容哈希读取，未知来图停止自动采集；Console 启停和自重启统一实例启动器及可查询最终状态；闹钟不可用且旧数据保留；隐私/能力说明和原生开关键盘支持同步修正。R05 仅脚本、Plan 与合成验证，生产权限未应用。实际功能提交d62fe25、前后端/插件 `20261026-review-2` 已部署34/34，QQ SDK只读连接ready1/1、Console实际自重启及Bot复用通过，仍待真实QQ/付费验收和试用；未知历史退出单列。本轮完整Python258项（257通过/1跳过）、Node63/63、余额2/2。根因、实际验证、平台缺口和取舍见[本轮记录](docs/reviews/2026-10-26-independent-fixes.md)，备份/回退见[发布记录](docs/releases/2026-10-26-independent-fixes.md)。

本项目沿用上游的 AGPL-3.0 许可证。以下流程使用 Git 管理源码，使用 uv 管理独立运行环境。

## 两个目录

| 目录 | 用途 |
| --- | --- |
| `D:\DSH Workspace\deepseek-chat-qqbot` | Git 管理的开发源码、模板、测试和文档 |
| `D:\dsbot` | 当前运行实例、`venv`、真实配置和聊天数据 |

运行实例不加入 Git。修改源码后先验证，再将要部署的文件复制到对应运行目录，重载插件或重启。不要在机器人运行期间覆盖整份数据目录。

## Git 日常流程

2026-10-26 五项 P2 补修见[失败回归及部署记录](docs/reviews/2026-10-26-console-lifecycle-p2-fix.md)。
前后端版本 `20261026-lifecycle-2`。`scripts/start-bot.cmd` 现在默认启动 Bot 和 7850 Console；
需已有 Node 与受保护 Console 凭据，缺失时明确失败。直接运行 PS1 仍可只启动 Bot，详见启动说明。

2026-10-26 四项补修见[复现、规则及交付记录](docs/reviews/2026-10-26-console-lifecycle-repairs.md)。
Console 前后端版本 `20261026-lifecycle-1`；新增 `public/reading-state.js` 必须与全部工作台文件配套发布。
历史来源按记录只读派生；派生视图不是管理目标。Bot 回执/历史增加可选 provenance，原存储版本和来源权限不变。
唯一用户 Bot cmd 为 `scripts/start-bot.cmd`，两个旧兼容 cmd 已从开发仓库删除；生产旧文件尚未移除。
对应生产清理、完整文件清单和回退限制见记录，不能仅复制 cmd 或仅重启 Bot 更新控制台。

管理工作台的用户/待确认/旧档分区、可靠身份及资料别名规则和本轮回归见
[用户身份盘点记录](docs/reviews/2026-10-25-user-identity-triage.md)。配套发布 Console 时新增
`console/people-sources.js` 必须与 `user-workbench.js`、server 和 public 页面整套复制；只重启 Bot 不会更新 Node 或页面。
`console_people_v1.json` 是仅供管理展示的映射（兼容 v1，写 v2）；来源不明旧档关联人物后仍保留未知场景。
生产数据、映射、昵称及原始截图不得加入 Git，不因改展示而迁移原 scope/历史/账本。

在源码目录打开 PowerShell：

```powershell
Set-Location 'D:\DSH Workspace\deepseek-chat-qqbot'
git status
git switch dev
git pull --ff-only origin dev

# 修改后先看差异，运行与改动相关的检查。
git diff
git add -- 具体文件路径
git diff --cached
git commit -m 'feat: 描述本次功能'
git push origin dev
git log --oneline -5
```

自 2026-10-23 起，本地及远端仅保留两个长期分支：

- `dev`：日常开发及最新功能试用版本，后续开发默认在此进行；完成相应离线检查后，可按用户授权部署验证。
- `main`：实测稳定的发布版本，保持 GitHub 默认分支。只有在实际运行场景验证并经用户确认稳定后，才将对应改动从 `dev` 合入；离线测试通过不能代替实测。

本次按用户指令将截至 `0b7451a` 的最新版本合入 `main`，再从相同基线创建 `dev`，
清理已合并的旧分支。两分支初始化时内容相同；本次整理不新增真实 QQ、热重载或数据迁移验收证据，
已有验证缺口仍按各交付记录保留。历史版本标签保留，不因整理分支而移动。

稳定版本晋级时，先确认 `dev` 中待合入内容均已实测，再切到 `main` 合并并验证、推送。
若 `dev` 混有尚未稳定的功能，先整理待发布范围，不能把整个分支当成已验收。推送分支本身不代表已经部署。

`upstream` 指向原作者仓库，用来查看和比较上游变化。本仓库采用注明来源的独立源码快照，没有继承上游 Git 历史，以免把图库带入发布历史；不要直接执行 `git pull upstream main`。如需同步上游，先取回变更，在新分支审阅并迁移相关源码，同时更新来源与修改说明。

## 检查

2026-10-25 用户自动归类与资料来源见[本轮记录](docs/reviews/2026-10-25-user-auto-group-review.md)。
新版本前后端标识为 `20261025-auto-1`；插件新增 `user_profiles.py`，必须随 `main.py` 与 Console 配套发布。
`workbench_profiles_v1.json` 是本机受保护的管理资料观察，`console_people_v1.json` 兼容旧人工组，首次人工修改后写 v2 的组及否认记录；两者均是运行数据，禁止入 Git。
关联只改变管理展示。平台原始资料不足时显示“待人工确认”“昵称未获取”，不从昵称或正文猜测身份。人工解除会阻止同一旧证据重新关联。
专项命令：`node --test console/tests/repair-people-auto.test.js console/tests/repair-workbench.test.js`，Python `-m unittest discover -s tests -p test_repair_user_profiles.py -v`。
使用已有 Playwright 模块路径后运行 `node tests/user_auto_browser.cjs`，全部使用合成临时目录；原浏览器集合可设 `DSH_BROWSER_EVIDENCE` 到忽略的 local 目录以保留历史截图。

2026-10-25 请求内表情数量及管理工作台聚合见
[实施、身份关联规则、后台使用与测试](docs/reviews/2026-10-25-sticker-count-users-workbench.md)。
用户页人工关联只影响管理展示，原 scope、身份/权限、积分账本和发送目标继续独立；旧档不猜测合并。
Console 新增 `user-workbench.js` 与 `public/user-workbench.js`，须与 server.js、index.html 同版发布（`20261025-users-1`）；开发交付本身不授权部署。
除下列旧集合，运行 `node --test console/tests/repair-workbench.test.js`；浏览器脚本为 `tests/workbench_browser.cjs`，使用已有 Node Playwright 和已安装 Edge，详见记录，不自动安装依赖。

2026-10-24 真实 QQ 验收补修及双解释器启动器见
[本轮补修记录](docs/reviews/2026-10-24-real-qq-repair.md)和[一键启动说明](docs/tooling/one-click-bot-startup.md)。
开发入口为 `scripts/start-bot.cmd`，默认只启动 Bot，管理控制台需 `-WithConsole`。
本轮交付不代表生产已安装或真实 QQ 验收通过；启动器测试只用临时实例。

2026-10-22 工作单 1 的访问认证、工具权限、离线验证及部署前配置说明见
[工作单 1 交付](docs/reviews/2026-10-22-workorder-1.md)。控制台新版必须由启动环境提供
`DSH_CONSOLE_TOKEN`，没有凭据会拒绝启动；主人特权须绑定 `DSH_OWNER_PLATFORM_ID`，
文本助理另需独立的 `DSH_ASSISTANT_ROOT`。本单尚未部署，不能直接用源码模板覆盖运行参数。

工作单 2（F01/F04/F05/F08）的作用域、固定目标、任务生命周期、运行态管理确认和六层删除见
[工作单 2 交付](docs/reviews/2026-10-22-workorder-2.md)。新会话使用 v2 来源键，旧档保留；
控制台写入需要新版插件在线确认，离线不会直接改文件。`admin_v2` 与插件、控制台应使用同一数据根，
保护该目录的本机账号权限。部署需要整套辅助模块及前后端同版，不能只复制 main.py 或 server.js。
第二单验收补修见 [P2 补修记录](docs/reviews/2026-10-22-workorder-2-p2.md)：框架配置档继续绑定原始会话或平台，
`c2_…` / `p2_…` 内部键不支持独立绑定配置档；新内部会话的拒绝不会放宽原会话限制。
[启动时机补修](docs/reviews/2026-10-22-workorder-2-startup.md) 将守卫安装提前到插件构造阶段，首条消息前即可保护配置入口；
main.py 和 session_scope.py 必须配套更新。

当前运行环境已安装所需 Python；源码工具检查不需要读取实际配置或 API Key：

```powershell
D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_repair_*.py'
D:\dsbot\venv\Scripts\python.exe -B -m unittest discover -s plugin\astrbot_plugin_ds_balance -p test_balance.py
node --test console/tests/repair-security.test.js console/tests/repair-state.test.js
node --check console\server.js
node --check console\state-bridge.js
git diff --check
```

已有余额插件测试只覆盖身份判断和金额文本显示；真实余额接口、QQ 指令路由和插件重载需在运行实例中另行验证。
纯语法检查使用 `ast.parse`，不要为检查语法导入生产插件或初始化实际实例；框架导入的副作用在修复测试中由临时子进程隔离。

## venv 与部署

第四单 F10/F11/F12 的攒批识图、请求资源预算、上下文原文压缩与测量见
[第四单开发交付](docs/reviews/2026-10-23-workorder-4.md)。[补修复验](docs/reviews/2026-10-23-workorder-4-p2-reacceptance.md)
已确认源码与离线验收通过、两项 P2 关闭；用户随后于 2026-10-23 明确授权上线新功能并推送远端 dev。
F09 闹钟继续暂缓。新增四个辅助模块须与 main.py 和发送/任务/权限模块配套，main 稳定分支不随本次更新。
可选 `dsh_soul_conf.json.resources` 的有限默认值、构造时读取语义、历史兼容及回退条件见交付记录；
不要把示例直接覆盖到真实配置。
第四单验收发现的补图来源竞态与发送截止绕过已补修，见
[P2 补修与复验依据](docs/reviews/2026-10-23-workorder-4-p2-fix.md)。原交付与初次验收历史保留；
实际发布、健康检查与回退见[第四单上线试用记录](docs/releases/2026-10-23-workorder-4.md)。
后续真实聊天发现的主 Agent Context 类型校验阻断见
[Context 补修](docs/reviews/2026-10-23-main-agent-context-fix.md)。[源码与离线验收](docs/reviews/2026-10-23-main-agent-context-acceptance.md)
已通过，用户于 2026-10-23 明确授权上线、推送远端并启动 bot；实际执行与回退记录于
[Context 补修上线记录](docs/releases/2026-10-23-main-agent-context.md)。启动或 QQ 会话连接正常不能代替真实聊天验收。

工作单 3（F06/F07）的统一 QQ 发送结果、请求结束、语音/媒体回退、历史兼容及部署回退要求见
[工作单 3 交付](docs/reviews/2026-10-23-workorder-3.md)。新增 `qq_delivery.py`、`reply_completion.py`、
`reply_integration.py` 需与核心插件整套发布；`delivery_receipts_v2.json` 属归档层，不能当作客户端到达证明。
原交付仅开发及离线验证；[媒体补修复验](docs/reviews/2026-10-23-workorder-3-media-acceptance.md)
已确认 P2/P3 关闭。用户随后于 2026-10-23 明确授权上线试用并推送 dev，稳定晋级 main 仍须实测与另行指令。
本次实际发布、健康检查与回退见[第三单上线试用记录](docs/releases/2026-10-23-workorder-3.md)。
验收补修的普通媒体快照、请求 ID、控制台回看及配套发布文件见
[媒体关联补修](docs/reviews/2026-10-23-workorder-3-media-fix.md)；新增 `media/sent` 属显式媒体删除层。

2026-10-22 工作单 2 的历史版本标签 `workorder-2-20261022` 保留；第三单开发源码入口更新为 dev，
部署时将运行副本的入口固定到实际发布 commit。QQ 输入“帮助”“关于”“源码”或既有状态指令可获得免费源码入口。运行参数只保存在部署副本，
`admin_v2` 文件管理通道须限制当前运行账号及 SYSTEM 访问。完整发布记录见
[工作单 2 上线记录](docs/releases/2026-10-22-workorder-2.md)。

从空目录安装时可使用：

```powershell
uv venv D:\dsbot\venv --python 3.12
uv pip install --python D:\dsbot\venv\Scripts\python.exe astrbot==4.29.1
Set-Location D:\dsbot
.\venv\Scripts\astrbot.exe init
```

已有实例不要重复初始化，不要用模板覆盖真实 `data\cmd_config.json`。`venv` 存放程序与依赖，`data` 和 `dsh_data` 存放运行数据，不应放进虚拟环境。

| 源码 | 部署位置 |
| --- | --- |
| `plugin\astrbot_plugin_dsh_soul` | `D:\dsbot\data\plugins\astrbot_plugin_dsh_soul` |
| `plugin\astrbot_plugin_ds_balance` | `D:\dsbot\data\plugins\astrbot_plugin_ds_balance` |
| `console` | `D:\dsbot\dsh-console` |
| `scripts\start-bot.cmd`、`start-bot.ps1`、`launcher-process.cs` | `D:\dsbot` 根目录，同目录成套安装 |

插件与控制台源码中的 `YOUR_*` 是公开模板占位符，只在部署副本填写；不要把已填真实身份的副本直接复制回 Git 仓库。`data_template` 仅用于新实例初始化，包含出厂人设，不含运行时记忆或图库。

在 `D:\dsbot` 使用 `venv\Scripts\astrbot.exe run`，或双击运行目录里的启动脚本。已有进程运行时不要重复启动。

## 发布到 GitHub

1. 保留 `LICENSE`、原作者署名、`UPSTREAM.json` 和 `MODIFICATIONS.md`；补充每次实质修改的内容与日期。
2. 发布对应版本的可修改源码、运行与安装说明。修改版向网络用户提供服务时，应让这些用户能取得对应修改源码；发布后在机器人帮助或关于信息中给出源码仓库链接。
3. 图片、声音及模型不因代码采用 AGPL 就自动获得授权。本仓库不包含上游图库；自行加入的资产应记录来源、授权与许可证。
4. 检查本次提交及全部待发布历史，确认没有真实密钥、用户 ID、聊天记录、个人资料或运行环境。不要使用 `git add -f` 强制加入忽略内容。
5. 本衍生版的目标仓库为 `https://github.com/114514071107/deepseek-chat-qqbot`，将其设为 `origin`；`upstream` 保留原作者地址。只向 `origin` 推送自己要发布的分支。

```powershell
git push origin main
git push origin dev
```

如果凭据误入任何提交，仅删除当前文件不能清除历史；应先撤销或轮换该凭据，再清理对应历史。
