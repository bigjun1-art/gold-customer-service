# 金牌客服：源码核查与融合依据

日期：2026-09-26

## 核查层次

初稿主要基于实际 SKILL.md、部分配套参考文件和模拟案例，未先完整审查配套程序。后续补做了与资料提炼、知识更新、客服复盘直接相关的定向源码审查、部分原项目测试及合成数据边界复现。这不等于九个项目的全仓审计，也不等于客服平台联网联调。

## 固定版本与阅读范围

| 项目与提交 | 本次检查范围 | 结论与融合方式 |
|---|---|---|
| [Composio 83382c4](https://github.com/composio-community/support-skills/tree/83382c4b055fc4e5b055044adb5bfb7585484c9a) | macro-builder、chatbot-review、qa-response、安装脚本、仓库文件树 | 相关模块为提示词；吸收手册与质检结构，不将其取样指令当全量数据管道 |
| [Anthropic da38ec1](https://github.com/anthropics/knowledge-work-plugins/tree/da38ec1ee89d41e5380e652a97382695003396e7/customer-support) | kb-article、draft-response、客服插件配置与文件树 | 吸收知识文章、复查、内外文案分层；分页、事实校验和评估集隔离仍需另行落实 |
| [Distilly b830d3d](https://github.com/titanwings/distilly/tree/b830d3dcbde006370f141155795b89021e3a947b) | 工作分析、合并、纠正提示词；消息解析、写入、版本备份与回退关键函数；对应测试 | 吸收经验结构与版本思路；员工精确绑定、保留双方上下文，更新前检查同节其他规则 |
| [ChatDistill 170bfd7](https://github.com/zouh9426/chat-distill/tree/170bfd70f6c64cde4248636b65adde894c2fea87) | knowledge_note.py 的路径、锁、原子写入、检索与重复候选逻辑；测试文件 | 吸收可靠写入与查重候选思路；金牌客服独立实现本地知识写入工具，不依赖 Obsidian |
| [Operator ff8afd3](https://github.com/adatarwa/operator-skills/tree/ff8afd3de8cddaef7dc4cf20b17fa51da5b6f308/skills/customer-support) | 客服入口与完整提示词库 | 提供工作方法与模板；融合正反例训练、SOP与工单规律分析 |
| [Harness 8e8d35c](https://github.com/revfactory/harness-100/tree/8e8d35c6a19166614d1af1df85512266d51121ae/en/49-customer-support/.claude) | 客服、升级与指标定义；审核者指令；角色与文件树 | 融合 FAQ、手册、升级和指标的一致性检查，不移植示例额度、时限和强制五人执行流程 |
| [Amplitude 51838c2](https://github.com/amplitude/builder-skills/blob/51838c2d85560466d1bbc174ea0e645bb9c44ea9/analytics-skills/skills/support-feedback-prioritization/SKILL.md) | 反馈优先级完整提示词与所在目录 | 融合反馈分类和影响排序，不将客户价值倍数当通用评分模型 |
| [Zendesk b7f4f64](https://github.com/andmarios/zendesk-skill/tree/b7f4f648ba9dd76b9f66c140baa48fafaf378cbd) | 工单搜索、详情和指标关键函数；存储/查询文件结构；指标测试探针 | 融合快照分析和时间口径；未安装其CLI或执行真实账号请求 |
| [MLflow 0766761](https://github.com/mlflow/skills/tree/0766761276a7dd378d88ac8aa7ca742c92b830fe/analyze-mlflow-trace) | trace分析入口与关联结构参考 | 融合检索、工具和生成错误的证据定位；未运行 MLflow 服务 |

## 关键代码发现

### 1. 只筛员工消息会破坏客服对话上下文

Distilly 的 [feishu_parser.py 第74–80行](https://github.com/titanwings/distilly/blob/b830d3dcbde006370f141155795b89021e3a947b/tools/feishu_parser.py#L74-L80) 用目标名字的包含关系筛选发送人，并过滤部分非文本内容。

合成数据复现：输入“顾客、小李、小李助理”三条消息，以“小李”为目标时，结果是“小李、小李助理”；顾客问题被过滤，相似名字被混入。

金牌客服采用精确身份映射，保留双方轮次和转接上下文，非文本缺失保留标记。尚未提供员工导出格式，因此没有宣称已实现所有平台的通用解析器。

### 2. 同标题更新会替换整节

Distilly 的 [merge_markdown_patch 第317–349行](https://github.com/titanwings/distilly/blob/b830d3dcbde006370f141155795b89021e3a947b/tools/skill_writer.py#L317-L349) 按二级标题替换章节。合成输入中，同一标题下的A/B两项会被只含C的新章节替代。这是其设计行为，不能把它描述为自动保留所有旧知识的语义增量合并。

金牌客服要求准备完整新正文并核对未变规则；用旧版本哈希拒绝过期覆盖，保留旧正文。

### 3. 锁与原子写入有实际实现，语义判断仍依赖模型

ChatDistill 的 [locked_paths / atomic_write_text](https://github.com/zouh9426/chat-distill/blob/170bfd70f6c64cde4248636b65adde894c2fea87/skills/chat-distill/scripts/knowledge_note.py#L353-L424) 确有文件锁和原子替换。其重复检测也明确只给候选提示，不能证明两项知识在业务上等价。

金牌客服新增独立的 knowledge_store.py，支持单文件版本核对、锁、原子替换、备份与回读；语义合并与来源核实仍由技能流程负责，多文件更新不宣称事务原子性。

### 4. 0 与缺失值需要分开处理

Zendesk 指标脚本 [第423–438行](https://github.com/andmarios/zendesk-skill/blob/b7f4f648ba9dd76b9f66c140baa48fafaf378cbd/src/zendesk_skill/scripts/analyze_support_metrics.py#L423-L438) 使用真假判断回退时间值。对该原函数做合成输入复现：工作时间0、自然时间600分钟、普通优先级，输出均值600分钟。

金牌客服明确有效0不回退为自然时间，也不能仅凭“不是顾客本人”就判定人工客服响应。

### 5. “工单详情”名称不能证明评论全量

Zendesk [get_ticket_details 第198–205行](https://github.com/andmarios/zendesk-skill/blob/b7f4f648ba9dd76b9f66c140baa48fafaf378cbd/src/zendesk_skill/operations.py#L198-L205) 在该层只发起一次评论请求并组合返回；Composio 相关提示词也仅要求近期50或50–100条。金牌客服将工单列表分页和工单内消息分页分别列为核查项，尚无真实平台全量读取实测。

## 测试记录

- Distilly：4项选定原测试通过，覆盖路径限制、更新归档、同标题替换、备份与回退。
- ChatDistill：test_knowledge_note.py 的17项原测试通过；使用临时资料，不访问用户真实知识库。
- 金牌客服：knowledge_store.py 的6项本地测试通过，覆盖只读、备份与回读、过期更新、路径和符号链接、替换失败、并发更新。
- 合成探针：复现目标名字包含匹配、同标题整节替换、0分钟回退三个行为。
- 模拟业务：资料冲突、范围未绑定、证据不足质检、员工蒸馏启动与单样本状态；发现范围误用与过度评分后已修订指令与输出。

此记录对应1.0.0的定向源码审查。后续已加入历史培训资料的通用方法；尚未完成真实员工对话效果验证、平台账号联调、生产机器人部署和全部上游测试。测试数字只属于上述固定版本，不代表1.1.0新增反馈工具的测试结果。
