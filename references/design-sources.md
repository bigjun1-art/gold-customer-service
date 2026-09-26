# 设计依据与边界

本技能为独立编写的中文工作流程，不打包或运行下列项目的程序，不要求安装其平台依赖。链接供追溯与后续比较，使用技能时无需联网读取。

| 原项目 | 相关设计方向 | 本技能的适用调整 |
|---|---|---|
| [Composio macro-builder](https://github.com/composio-community/support-skills/blob/main/macro-builder/SKILL.md) | 重复工单转处理手册 | 支持本地资料，增加来源、范围和独立评估；无数据不估解决率 |
| [Composio chatbot-review](https://github.com/composio-community/support-skills/blob/main/chatbot-review/SKILL.md) | 对话失败、错误回答与知识缺口检查 | 区分事实未知和已证实错误，保留结果未知样本 |
| [Composio qa-response](https://github.com/composio-community/support-skills/blob/main/qa-response/SKILL.md) | 回复准确、完整、语气和表达检查 | 加入业务依据、重大错误判定及缺项评分 |
| [Anthropic kb-article](https://github.com/anthropics/knowledge-work-plugins/blob/main/customer-support/skills/kb-article/SKILL.md) | 已解决案例沉淀为知识 | 增加业务隔离、冲突、时效、增量更新和回读 |
| [Anthropic draft-response](https://github.com/anthropics/knowledge-work-plugins/blob/main/customer-support/skills/draft-response/SKILL.md) | 上下文与场景化回复 | 中文顾客文案与内部动作分离，不机械要求安抚开场 |
| [Distilly](https://github.com/titanwings/distilly) | 从材料抽取工作经验与判断方式 | 只提炼可观察工作能力，员工阶段显式启动，加入反例与保留案例验证 |
| [Customer Support Operator](https://github.com/adatarwa/operator-skills/blob/main/skills/customer-support/SKILL.md) | 工单规律、SOP、回复评审与正反例训练 | 并入质检和培训模块，不增加另一套评分 |
| [Harness 客服体系](https://github.com/revfactory/harness-100/tree/main/en/49-customer-support/.claude) | FAQ、回复、升级、指标与客户旅程联动 | 保留层级和一致性检查，去掉强制多智能体及外部示例额度、时限 |
| [Amplitude 反馈排序](https://github.com/amplitude/builder-skills/blob/main/analytics-skills/skills/support-feedback-prioritization/SKILL.md) | 汇总多渠道反馈、客户影响和重复问题 | 使用证据解释排序，不移植客户价值倍数，不自动发送或调度 |
| [Zendesk Skill](https://github.com/andmarios/zendesk-skill) | 完整工单、分页、指标、先存再查 | 抽象为平台无关数据读取与核验，不打包 CLI，不要求 Zendesk 账号 |
| [ChatDistill](https://github.com/zouh9426/chat-distill) | 有价值知识筛选、查重、合并与健康检查 | 原生保存技能知识，去掉 Obsidian 依赖，业务范围独立管理 |
| [MLflow 轨迹分析](https://github.com/mlflow/skills/blob/main/analyze-mlflow-trace/SKILL.md) | 从中间证据定位错误，区分成功状态与正确输出 | 只在有轨迹的 AI 客服诊断启用；没有轨迹不臆测根因 |

未单独叠加的候选：Distiller 的结构化提炼与质量检查已由资料模块覆盖；Freshdesk、Intercom 等平台操作的通用价值归入数据模块；广泛角色提示词合集不另行重复加载。具体连接器未安装、未实测，不能据此声称已具备线上操作能力。

能力边界：本技能提供资料管理、推理与客服工作流程；不进行模型参数微调，不自带生产客服系统，不自动采集账号数据，不保证成交、满意度或解决率提升。

固定提交、关键代码发现与测试边界见 [源码核查](source-review.md)。
