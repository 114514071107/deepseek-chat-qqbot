# 已撤销的人物/Union产品合同测试

2026-10-29用户明确取消跨群/私聊人物聚合、认领和Union灰度。这些断言所要求的产品行为已撤销，保留源码及Git历史供审计，不纳入当前测试集合，不能将其移出当作修复旧缺陷。

替代行为测试：tests/test_repair_conversation_mode.py（实际上下文/框架/发言者与目录资料）、test_repair_conversation_cleanup.py（备份隔离/重复执行）、console/tests/conversation-mode.test.js（整群目录/搜索分页/记忆隔离/废弃接口）、tests/conversation_browser.cjs（原生前端交互）。

原目录中的投递来源/出站去重/旧档边界属于保留的安全合同，新会话测试必须继续覆盖；认证、状态桥、生命周期等原集合保持执行。历史脚本相对导入按当时路径，复跑旧版请使用对应Git快照，不能直接导入当前已删除Union实现。
