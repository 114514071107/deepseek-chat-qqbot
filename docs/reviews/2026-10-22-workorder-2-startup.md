# 工作单 2：首条消息前的配置绑定补修

日期：2026-10-22（Asia/Shanghai）。实施方补修与离线验证完成，等待用户复验。未部署、重启、修改真实配置/数据/依赖或提交，未推进第三单。

## 根因与最小修改

复验确认的 P2 是安装时机错误：上一轮的路由守卫已经能识别未登记的内部键，但只在 `bind_scope()` 接收到消息时安装。插件构造完成、首条消息尚未到达时，真实框架管理服务仍使用未受保护的方法。旧回归先绑定消息，因而遗漏该窗口。

- `main.py`：导入公开的 `install_policy_adapters()`，在真实构造函数中 `super().__init__()` 之后、Runtime 与数据加载之前同步调用。
- `session_scope.py`：将已有安装函数公开命名，说明启动时序；消息入口仍使用同一个幂等安装函数。没有修改策略、添加网络服务或复制配置数据。
- `tests/test_repair_p2_acceptance.py`：新增独立进程的真实构造路径回归，没有调用 `bind_scope()`、`on_loaded()` 或手动安装守卫，始终确认来源映射为空。

本轮不改变已复验通过的撤销、分层缓存删除或问候路径。原会话/平台配置绑定继续可用，内部 `c2_…` / `p2_…` 绑定仍明确拒绝。已有无效绑定不会被自动删除或迁移；实际部署前若存在这类旧绑定，应在受保护管理面单独核对。

## 验证证据

新增用例在修复前失败：首次构造、重复构造、辅助模块重载三阶段，共 24 次真实 Dashboard 单条/整表内部键请求被接受，路由表被改变。修复后这些请求全部被拒绝，内存和持久化状态不变；原始会话及平台的合法修改仍成功。

在开发仓库使用已有解释器运行：

```powershell
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p test_repair_p2_acceptance.py -k constructor -v
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s tests -p 'test_repair_*.py'
& 'D:\dsbot\venv\Scripts\python.exe' -B -m unittest discover -s plugin\astrbot_plugin_ds_balance -p test_balance.py
node --test console/tests/repair-security.test.js console/tests/repair-state.test.js
node --check console/server.js
node --check console/state-bridge.js
node --check local/workorder-2-startup-check/frontend.js
git diff --check
```

实际结果：新增构造回归 **1 项通过**（包含上述 24 次请求）；完整修复回归 **78 项通过**、余额 **2 项通过**、Node **7 项通过**。Python AST **26 文件**、JS 语法及差异检查通过。独立只读复核重新运行构造回归通过，未发现本轮微小增量新增 P1/P2。

真实框架只在临时 ASTRBOT_ROOT/cwd/TEMP/TMP 子进程中导入。AST 载入开发源码的实际构造函数，使用真实 Star、Runtime、状态控制器和工具守卫；仅与路由无关的图库创建使用替身。没有真实事件、QQ 发送、模型调用或生产数据库读取。Node 旧偶发失败本轮仍未复现，原因仍未确认。

## 基线、差异与交接

分支仍为 `chore/backend-agent-skills`，HEAD 仍为 `339e61e723ff4cf8709aabe474d201deabda4484`；承接已有未提交成果，没有重置或覆盖其他工作。重新读取工作单约束及开发交接，适用目录未发现新增 AGENTS.md。本轮前的开发材料对照和 SHA256 在忽略目录 `local/workorder-2-startup-before`。本轮运行 main.py 与 server.js 只读哈希核对未变化。

[本轮独立增量](../../local/workorder-2-startup-check/startup-followup.patch)。部署时 main.py 和 session_scope.py 必须配套更新，不能只复制调用方；本轮未执行复制、加载或重启。仍需另行安排真实 QQ、实际插件热重载和生产迁移验收；辅助模块重载测试不能代替真实热重载。

其余权限、数据兼容、备份/回退及许可证要求沿用 [第二单交付](2026-10-22-workorder-2.md) 与 [上一轮 P2 记录](2026-10-22-workorder-2-p2.md)。本轮完成后停止，不执行第三单。
