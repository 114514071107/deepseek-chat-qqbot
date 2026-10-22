# 本地开发与发布

本项目沿用上游的 AGPL-3.0 许可证。以下流程使用 Git 管理源码，使用 uv 管理独立运行环境。

## 两个目录

| 目录 | 用途 |
| --- | --- |
| `D:\DSH Workspace\deepseek-chat-qqbot` | Git 管理的开发源码、模板、测试和文档 |
| `D:\dsbot` | 当前运行实例、`venv`、真实配置和聊天数据 |

运行实例不加入 Git。修改源码后先验证，再将要部署的文件复制到对应运行目录，重载插件或重启。不要在机器人运行期间覆盖整份数据目录。

## Git 日常流程

在源码目录打开 PowerShell：

```powershell
Set-Location 'D:\DSH Workspace\deepseek-chat-qqbot'
git status
git switch -c feature/你的功能名

# 修改后先看差异，运行与改动相关的检查。
git diff
git add -- 具体文件路径
git diff --cached
git commit -m 'feat: 描述本次功能'
git log --oneline -5
```

初始 `main` 是源码导入基线；`work/local-development` 记录本地新增插件、启动脚本和发布准备。新功能可从当前开发分支另建分支。每个可验证的改动单独提交。

`upstream` 指向原作者仓库，用来查看和比较上游变化。本仓库采用注明来源的独立源码快照，没有继承上游 Git 历史，以免把图库带入发布历史；不要直接执行 `git pull upstream main`。如需同步上游，先取回变更，在新分支审阅并迁移相关源码，同时更新来源与修改说明。

## 检查

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

2026-10-22 工作单 2 发布使用标签 `workorder-2-20261022` 固定对应源码；QQ 输入
“帮助”“关于”“源码”或既有状态指令可获得免费源码入口。运行参数只保存在部署副本，
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
| `scripts\run-astrbot.cmd` | `D:\dsbot\run-astrbot.cmd` |

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
git push -u origin work/local-development
```

如果凭据误入任何提交，仅删除当前文件不能清除历史；应先撤销或轮换该凭据，再清理对应历史。
