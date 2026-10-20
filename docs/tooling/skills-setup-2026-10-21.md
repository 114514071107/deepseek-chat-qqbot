# 后端与 Agent 开发技能配置

核查日期：2026-10-21。目标是维护现有 AstrBot 插件、QQ 接口及 Node.js 控制台，不改变项目技术栈。

## 安装范围与来源

新增 15 个 Codex 用户级技能，安装到 `~/.codex/skills/`。它们指导开发助手工作，不是 AstrBot 插件，也不是机器人运行依赖。已有测试驱动、系统排错、代码审查、Git 工作树与完成前验证等技能继续保留。

星数来自当日 GitHub API；这里是**整个来源仓库的星数**，不代表每个技能的独立评分。筛选同时考虑维护情况、内容与当前项目的相关性、辅助文件是否齐全，以及是否重复。

| 来源 | GitHub 星数 | 本次新增 | 主要用途 |
| --- | ---: | ---: | --- |
| [wshobson/agents](https://github.com/wshobson/agents) | 41,243 | 12 | Python 异步、资源管理、测试、日志、配置、uv、Node.js 后端、鉴权、API 与模型评测 |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | 284,807 | 1 | 大模型调用费用控制 |
| [anthropics/skills](https://github.com/anthropics/skills) | 182,475 | 1 | MCP 工具服务开发 |
| [openai/skills](https://github.com/openai/skills) | 28,189 | 1 | 安全威胁建模 |

辅助筛选参考 [Skills 排行榜](https://www.skills.sh/) 与单技能页面；安装以原始 GitHub 源码为准。没有安装整个技能合集、全局 hooks、远程安装脚本或新的服务框架。

## 技能清单

| 技能 | 在本项目中的用途 |
| --- | --- |
| `async-python-patterns` | 处理异步任务、取消、超时与并发，避免消息处理被阻塞 |
| `python-resource-management` | 管理 HTTP 会话、文件、临时目录与插件卸载时的资源清理 |
| `python-testing-patterns` | 为 QQ 事件、模型接口、定时任务编写隔离测试 |
| `python-resilience` | 对模型与网络故障设置有界重试、退避与超时 |
| `python-observability` | 设计日志与诊断信息，定位重复回复、任务失败等问题 |
| `uv-package-manager` | 管理 uv、虚拟环境与依赖 |
| `python-configuration` | 分离配置、环境变量和校验逻辑 |
| `nodejs-backend-patterns` | 维护现有 Node.js 控制台服务 |
| `auth-implementation-patterns` | 梳理管理员、群成员与接口访问权限 |
| `api-design-principles` | 改进控制台接口的输入、错误与响应约定 |
| `llm-evaluation` | 用固定样例评估回复、工具调用、延迟与成本 |
| `prompt-engineering-patterns` | 调整人设与工具提示，并通过样例验证效果 |
| `cost-aware-llm-pipeline` | 规划调用预算、缓存与重试上限 |
| `mcp-builder` | 将来需要独立 MCP 工具时使用；当前机器人不因此改用 MCP |
| `security-threat-model` | 明确安全审查任务时分析信任边界与攻击路径 |

前 12 项来自 `wshobson/agents`，后三项依次来自 ECC、Anthropic 与 OpenAI。示例中的模型名称、价格和第三方 API 必须在实际开发时核对，不能直接当作当前 DeepSeek 的配置。

## 安装与核验

使用 Codex 自带的 `skill-installer`，以 `--method download` 从固定 Git 提交安装。完整路径、提交哈希和文件 Git blob 哈希记录在 [skills.lock.json](skills.lock.json)。示例：

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" --repo wshobson/agents --ref 0874a27b17a22e2b7c2e2bcd725768e0803cad06 --path plugins/python-development/skills/async-python-patterns --method download
```

安装后完成以下检查：

- 15 份 `SKILL.md` 的 YAML 元数据、名称和本地引用可读取。
- 54 个上游文件与固定提交的 Git blob 哈希一致。
- 4 个 Python 辅助文件通过语法解析；未执行下载的辅助程序，未安装其示例依赖。
- 对不自带许可证的 13 个技能目录，额外保留对应上游仓库的 MIT 许可证为 `LICENSE.upstream`；另外两个技能保留自身的 `LICENSE.txt`。

这些是安装完整性与基本结构检查，不等于已经验证所有示例能直接用于本项目。技能从下一轮对话起可按任务选用，安装本身不会修复机器人已有缺陷。

## 取舍

- 已安装的 Superpowers 工作流不重复下载或覆盖。
- 暂不采用以 Celery、Redis 为核心的后台任务技能，当前单机自用场景优先使用已有进程与异步任务。
- 没有安装依赖整套仓库脚本才能工作的评测框架，选择可独立读取的模型评测技能。
- 没有将 LangChain、DeepAgents 等框架加入运行依赖；Agent 开发技能与框架迁移是不同事项。

这里只提交来源和版本记录，第三方技能正文留在本机 Codex 技能目录。原项目的许可证、署名及发布规则仍按根目录文档执行。
