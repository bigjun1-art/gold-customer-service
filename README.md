# 金牌客服 · Gold Customer Service

持续学习客服资料、起草回复、复盘服务质量，并从获授权的近期客服对话中提炼经验。朋友使用后可以回传去标识的改进反馈，由维护者审核后更新公共技能。

**当前版本：1.1.0。** 包内含23条通用方法，不包含原始培训文档、视频、客户对话、员工身份或任何公司的生效赔付规则。技能名不是认证，没有真实业务对照数据时不宣称服务水平提升。

## 安装

把以下这句话发给支持安装Skills的Codex：

> 请使用 skill-installer，从 https://github.com/bigjun1-art/gold-customer-service 安装金牌客服技能，仓库技能路径为根目录，名称为 gold-customer-service。已有同名技能时先检查本地知识与版本，保留备份后比较更新。

也可手动下载本仓库，将含SKILL.md的整个目录命名为`gold-customer-service`，放入所用客户端的技能目录。Codex默认目录为`~/.codex/skills/`；不要只复制入口文件。重新开启一个任务后确认客户端可发现该技能。其他客户端按其技能目录规范安装，本项目未对所有客户端作兼容承诺。

首次安装的终端示例（已有目录时停止，不覆盖）：

```sh
git clone https://github.com/bigjun1-art/gold-customer-service.git ~/.codex/skills/gold-customer-service
```

核心分析需要支持Skills的语言模型；本地辅助脚本需要Python 3。知识写入工具使用POSIX文件锁，适用于macOS/Linux；不需要客服平台账号、外部API密钥或另一套技能。模型负责理解与脱敏复核，脚本负责结构检查、反馈打包和版本可靠写入。

## 让朋友开始蒸馏

朋友提供自己获授权的对话导出和当前业务规则后，可直接发送：

> 使用金牌客服，蒸馏这批近期客服对话。先确认实际日期范围、业务范围和角色，保留顾客、客服、机器人及转接上下文。把同一工单和近重复分到同一组，再分离提炼案例与保留评估案例。提炼判断方法、动作、例外和升级条件；结果未知就标未知。完成本地候选和对照报告，优化本地适用范围，不准备或上传公共反馈。

需要给公共技能提建议时，另行发送：“从本地报告中提炼通用改进，生成去标识反馈草稿供我复核，先不上传。”

若朋友同时希望公开回传，可在完成内容复核后补充：“把这份已复核、无隐私的反馈提交到金牌客服的 GitHub Issue。”这一步会公开反馈正文，不会自动更新主技能。

少量对话也能提炼未验证候选。没有身份映射就做团队案例分析，不归因给具体员工；没有独立案例就不报告已验证。新增店铺规则仅写入本地范围，不混入公共通用方法。

## 反馈能力

流程：本地蒸馏 → 经验候选与反例 → 保留案例验证 → 去标识反馈包 → GitHub Issue或交给维护者 → 审核与PR → 新版本。

反馈包含版本、日期范围、案例覆盖、建议修改、支持证据摘要、反例和验证结果。脚本不读取原始对话、不联网、不上传、不自动合入；最终是否可以公开必须由实际内容复核和用户授权确定。隐私规则不能发现所有姓名、隐含身份或业务机密。

合成示例与命令：

```sh
python3 scripts/feedback_bundle.py validate assets/feedback-example.json
python3 scripts/feedback_bundle.py render assets/feedback-example.json
mkdir -p feedback-output
python3 scripts/feedback_bundle.py build assets/feedback-example.json --output feedback-output/demo
```

示例用于验证打包功能，不是真实客服效果证据。使用者应生成自己的反馈文件；授权字段不能直接照搬示例。具体流程见[反馈与审核](references/feedback.md)。

公开提交仅在用户明确授权后执行：

```sh
gh issue create --repo bigjun1-art/gold-customer-service --title '蒸馏反馈：场景及改进点' --body-file feedback-output/demo/feedback.md
```

实际提交应指向真实反馈包，**不要发布示例**。发布前按feedback_id查重；失败状态不明确时先回读已有Issue。无需GitHub也可把本地反馈包交给大军，再由维护者审核。

## 已有方法

- 需求澄清、价格异议、投诉处理。
- 物流异常、仅退款、退换货、错漏发及交接。
- 活动协同、排班口径、质检、培训和复盘。
- 商品知识、机器人回答、转人工与分流。
- 回复演练、风险话术和历史规则冲突。

[知识入口](knowledge/index.md)按场景加载，来源摘要用于追踪，不代表朋友能访问原件。平台政策、商品功效、退款期限和补偿额度都需核实当前业务依据。

## 开发与验证

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

测试保障本地写入、反馈结构、证据集合、隐私规则及打包可靠性，不证明脱敏绝对安全或客服效果已提升。更新请保留本地业务知识并进行语义比较；禁止直接用公共版本覆盖个人知识库。

## 来源与贡献

方法设计与定向源码审查见[设计依据](references/design-sources.md)及[源码核查](references/source-review.md)。独立实现的工具与文档按[MIT License](LICENSE)发布；上游项目、未分发原始培训资料及第三方商标仍受各自权利约束。
