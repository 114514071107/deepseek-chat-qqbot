# 会话模式验证证据

全部测试使用临时合成实例；构造实际框架请求及模型输入，不发送真实QQ或调用付费模型。完整集合保留失败输出；Windows用户目录/SID已脱敏。

- Python受影响集合：`tests/test_repair_{conversation_mode,conversation_cleanup,event_admission,context_window,session_scope,permissions,p2_acceptance,proxy_integration,state,lifecycle,interleavings,outbound_ownership,real_context,capture_identity,routing,main_agent_context,real_lifecycle,real_media,real_qq_acceptance,workorder4_integration,workorder4_p2}.py`，131通过（最后权限边界补修后）。
- 完整集合（最后权限边界补修前；补修后复验上述131项）：`python -B -m unittest discover -s tests -p 'test_repair_*.py' -v`，292项，287通过/4失败/1原有跳过。四处失败输出均为PS5.1 AuthorizationManager拒绝；本轮未改启动器。
- `node --test console/tests/*.test.js`：25通过；`NODE_PATH`使用已安装的Playwright依赖后执行 `node tests/conversation_browser.cjs`：12组通过。
- 最后文件流式备份调整后另复跑清理5项及实际模型输入/会话8项通过。余额插件2通过；语法与差异检查通过。
- `conversation-policy-red.txt`保留同群成员框架策略串用的失败；`review-*-red.txt`保留独立审阅修复前的真实失败。其他初次旧产品合同失败留在忽略的local，不冒充最终结果。
- `conversation-production-plan-summary.json`是只读真实数据Plan计数；15项尚未Apply。`conversation-runtime-readonly.json`只核当前旧版服务，无启停或写业务数据。
- `conversation-390.png`是已实看、使用合成来源和文本的390px页面。320px亦检查无横向溢出。

完整处理路径/哈希清单和部署计划仅存在受保护本机备份区，不随源码发布。新代码未部署；旧版在线状态不能作为新版真实QQ验收结论。
