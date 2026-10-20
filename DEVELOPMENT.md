# 本地开发与发布

本项目沿用上游的 AGPL-3.0 许可证。以下流程使用 Git 管理源码，使用 uv 管理独立运行环境。

## 两个目录

| 目录 | 用途 |
| --- | --- |
| `D:\DSH Workspace\deepseek-chan-qqbot` | Git 管理的开发源码、模板、测试和文档 |
| `D:\dsbot` | 当前运行实例、`venv`、真实配置和聊天数据 |

运行实例不加入 Git。修改源码后先验证，再将要部署的文件复制到对应运行目录，重载插件或重启。不要在机器人运行期间覆盖整份数据目录。

## Git 日常流程

在源码目录打开 PowerShell：

```powershell
Set-Location 'D:\DSH Workspace\deepseek-chan-qqbot'
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

当前运行环境已安装所需 Python；源码工具检查不需要读取实际配置或 API Key：

```powershell
D:\dsbot\venv\Scripts\python.exe -m unittest discover -s plugin\astrbot_plugin_ds_balance -p test_balance.py
D:\dsbot\venv\Scripts\python.exe -m compileall -q plugin tts
node --check console\server.js
git diff --check
```

已有余额插件测试只覆盖身份判断和金额文本显示；真实余额接口、QQ 指令路由和插件重载需在运行实例中另行验证。

## venv 与部署

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
5. 在自己的 GitHub 账号创建目标仓库后，将该仓库设为 `origin` 并推送需要发布的分支。实际远端地址确定前，不填写虚构 URL，也不推送到 `upstream`。

如果凭据误入任何提交，仅删除当前文件不能清除历史；应先撤销或轮换该凭据，再清理对应历史。
