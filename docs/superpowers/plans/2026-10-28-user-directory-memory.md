# 用户与记忆统一入口实施计划

2026-10-28。用户已允许本人首次设置称呼、验证跨会话关联，之后自动归类。基线 dev / 22c8d4f。使用 writing-plans、systematic-debugging、test-driven-development 与 verification-before-completion；沿用现有界面组件。

## 需求及边界

- 用户页和记忆页均按人物展示；消息逐条保留私聊、具体群聊或来源未知标签。
- 新可信来源自动建档，不要求维护者确认；平台没有提供昵称时明确提示本人设置称呼，不能伪称获取了 QQ 昵称或 QQ 号。
- 跨域 OpenID、相同昵称不能直接合并。私聊生成一次性关联码，群聊认领，原私聊最终确认后建立管理展示关联；同群旁观者不能凭公开码直接完成关联。
- 保留人工关联、解除与否认。旧来源未知不补造场景。不迁移历史、不改变模型记忆、权限、积分或发送目标。
- 不调用第三方 OpenID 查询服务，不对外传送真实标识。

## 实施顺序

1. 写失败回归：自动建档、不同场景和同名用户隔离；本人称呼、跨域验证的来源/应用边界、过期、重放、冲突；人物记忆只读投影与场景筛选。
2. 增加有界原子写入的自助身份模块，与已有可信平台观察及本地命令入口集成；不进入模型、不扣模型积分，不记录验证码进聊天档案。
3. Console 读取自助证明并遵守人工否认；单来源自动建档，新增全部消息视图；记忆按相同人物目录读取，以来源明确展示既有材料。
4. 运行受影响和完整离线回归、合成浏览器验证、语法/差异检查；更新研究/实施记录和修改说明。
5. 本地提交后按既有规则备份配套代码与受影响数据，部署并重启 Bot/Console，核对哈希、实际版本、心跳和 QQ 连接。真实 QQ 测试发送另需本轮许可。更新交接记录，待用户验收，不推送远端。

## 研究依据

- Tencent 标识域说明：<https://github.com/tencent-connect/bot-docs/blob/645787a45937e5d9c4f0f61afefdffde0f38696e/docs/develop/api-v2/dev-prepare/unique-id.md>
- Tencent SDK 消息结构：<https://github.com/tencent-connect/botpy/blob/e25f3e84bad7217357d8200a9d12939b58285b84/botpy/message.py>
- LangBot 官方 QQ 适配只提供本地资料缓存：<https://github.com/langbot-app/LangBot/blob/6b57a1074ff4002a0153f667435c2418b617f0f3/src/langbot/pkg/platform/adapters/qqofficial/api_impl.py>
- qq-crack 的昵称查询依赖第三方 API，并非官方保证，本轮不采用：<https://github.com/koishi-shangxue-plugins/koishi-plugin-adapter-qq-crack/blob/78c6b55df2825593a86be76413e7758607f4cc8c/src/bot/index.ts>
