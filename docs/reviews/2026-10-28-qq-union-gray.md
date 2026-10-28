# QQ union 白名单灰度上线与 QQ 验收

日期：2026-10-28（Asia/Shanghai）。状态：实施与上线前验证中，尚未部署。

## 授权与范围
用户明确要求“尝试灰度上线并用QQ验收”，随后明确允许 Bot／Console 各一次受控重启。此前不停机约束被本次必要单次受控重启许可部分更新；不允许重复任意重启、生产故障注入、第三方查询、数据迁移、push／PR／main合并。

开发基线 dev HEAD 0b058d8854c525b6e10573154aa681485df7088b。保留原未提交评审、沙盒及候选交付。使用现有 requesting-code-review 独立复核、systematic-debugging、test-driven-development、verification-before-completion，QQ阶段读取 computer-use 全部必需指引；不安装生产依赖、不改系统安全策略或 ACL。

## 候选重新复核与补修
原候选的13命令在全新临时根复现，与记录一致。独立评审发现：
1. exact旧identity_origin不含bot，可绕过新增union域；合成同原sender、不同真实bot及union仍合成1人。
2. 部分union升级拆散旧平台author-pair关系，previous_identity在后续稀疏事件丢失。
3. 补修后新author-user反证仍可能被union覆盖或降级丢弃；缺SDK app可重新丢旧证明。
4. 灰度apply退出后若走原writer，会把旧union与原user命名空间差异当冲突污染。

均先建立有效失败回归，再修正：带域规范键、保留旧deny别名、旧可信pair参与兼容且检查反证、持久化旧证明；既有union行即使退出灰度仍用识别命名空间的writer维护证据，但管理投影不再自动应用union。

补修初次引出旧测试对未知bot别名的假设差异，改为名单外使用原profileFor及原writer，保留原行为；原测试不放宽。历史失败保留在本轮证据，不能倒改原候选报告。

## 灰度合同
- 新 union_rollout_v1.json，默认无策略关闭；策略只含精确来源fingerprint白名单、observe/apply、24小时以内到期与私有比较键。
- 指纹包括平台、实例、bot、private/group、具体群、原sender、可信SDK app。最多32来源；当前计划仅已核测试账号的原私聊及指定群两来源。
- observe仅记录64条以内事件级有效性、scope_key及带私有随机比较键的HMAC；不写union明文、正文、消息ID、OpenID或AppID。
- apply仅名单内更改union观察/管理聚合和停取码。名单外保留原绑定、称呼、管理profile合同。Console每次读策略；观察到应用切换无需第二次重启。
- 无真实有效同union证据绝不进入apply。策略过期／移除回旧管理投影；历史证明保留不回滚旧数据。
- 仍使用本项目原适配器；未安装整个第三方插件、未引入SQL生产存储。上下文／权限／积分／scope／Target保持。

## 上线前验证
新增Python21/21、新Node15/15；完整Node90/90，exit0。Python全集运行中，结果待追加。原候选13命令复验后，原probe和原SQL仍非零；名单外原绑定10项现在通过，未删除原断言。AST29、JS4语法及git diff --check通过。临时诊断SQLite仅合成。

全集收尾：Python320项／710.875秒，315通过、4失败、1跳过，exit1。四失败均为原有PowerShell 5.1路径的AuthorizationManager／UnauthorizedAccess，分别launcher双Shell、startup冷启动、startup双组件、worker job；脚本未进入正常创建／停止阶段。未修改启动内核、原测试或系统策略。原正式入口只读preflight选中PowerShell7.6.5、action_started=false，无失败；因此本轮仅通过该现有受支持入口执行获准发布，不宣称全集通过。启动脚本及其生产副本均未被本轮修改，环境拒绝仍留调查项。

QQ账号与指定群均已通过原生客户端资料核验，尚未发本轮测试消息。真实两群及对照账号缺少授权目标，不扩大到其他联系人；指定一群与私聊是本轮实测范围，其余以合成证据为限。

## 发布与回退计划
构建20261028-union-gray-1。仅通过回归的本地提交成套部署；保留真实main五常量和server MASTER。受保护目录 D:\dsbot\deployment-backups\20261028-user-directory\independent-repair\union-gray。
先备份同版代码与配置清单；一次停止两组件，停写快照DB/WAL/SHM原字节、不打开SQLite，安装并启动各一次；核源码/staged/运行哈希和新进程同版、心跳/QQ就绪。仅端口或PID不代表客户端收到。
优先运行observe，QQ身份帮助等本地指令生成有界样本；可靠字段失败就关闭策略，保留原业务。严重发布故障的代码回退需说明当前服务状态与单次重启额度，不能静默多次重启。业务资料、聊天、积分快照不恢复覆盖。

交付日志格式补充：首次本地提交保留了日志行尾空白，差异检查报告该格式问题；随后仅规范化证据日志行尾并追加提交，原失败内容和退出码保留，未改产品实现或测试预期。
