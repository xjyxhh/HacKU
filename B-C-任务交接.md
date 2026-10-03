# Contribution Graph：B、C 任务交接

本文根据 `A-职责总结.md` 和 `Contribution Graph/` 中已完成的代码整理。目标是让 B 的验证操作改变真实数据，让 C 的 Dashboard 和 Graph 展示同一份最新数据。

## 已有基础与共同约定

- A 已提供项目、成员、任务、贡献的数据模型，JSON 本地保存，以及 `CORE`、`SUPPORT`、`REVIEW`、`COORDINATION` 四类贡献的评分规则。
- 新贡献由 `ContributionStore.submit_contribution(...)` 创建，初始状态为 `PENDING`。`PENDING` 和 `DISPUTED` 得分为 0；`VERIFIED` 和 `RESOLVED` 按当前最终值计分。
- `ContributionStore.contribution_data(contribution_id)` 提供单条贡献及证据、验证、争议记录，供 B 使用；`dashboard_data(project_id)` 提供项目、成员、任务、贡献及帮助关系，供 C 使用。
- 当前已有 FastAPI 服务：C 的只读页面调用 `GET /api/dashboard`，B 可通过贡献详情、证据、验证与争议等 HTTP 接口操作同一份 JSON 数据文件。接口及启动方式见 `Contribution Graph/README.md`。不要在前端重写评分公式。
- `Contribution Graph/data.json` 目前仅含 2 名成员、1 项任务和 1 条待验证贡献。完整的 4 人流程由 `demo_workflow.py` 生成；联调时应使用一份固定的 4 人演示数据文件，并约定其路径与重置方式。

## B：证据、同伴验证与争议处理

### 要完成的工作

1. **贡献待办与详情。** 列出需要处理的贡献，显示贡献者、任务、类型、说明、帮助对象、提议分值和当前状态。详情展示证据、历史验证记录及争议处理记录。现有 `contribution_data(...)` 可读取单条详情；若需要按项目筛选待办，可基于现有 `store.contributions` 增加查询接口。
2. **证据录入。** 让成员为贡献添加 `NOTE`、`URL`、`IMAGE` 或 `GITHUB_PR` 类型的证据引用，调用 `add_evidence(contribution_id, submitted_by, kind, reference)`。目前 `reference` 保存文本或链接，并没有文件上传功能；若界面需要上传图片，应另行实现上传与存储，再将引用写入记录。
3. **同伴确认与调整。** 提供 `CONFIRM` 和 `ADJUST` 操作，调用 `review_contribution(...)`。确认与调整必须由贡献者之外的项目成员执行，且只能处理 `PENDING` 贡献。调整时填写 `completion`、`support_value` 或 `quality`，并展示调整前后的得分；调整必须实际改变得分。
4. **提出并解决争议。** 提出争议时必须填写原因，调用 `review_contribution(..., "DISPUTE", note=...)`；解决时填写结论和必要的最终分值，调用 `resolve_dispute(...)`。界面应清楚提示 `DISPUTED` 暂停计分、`RESOLVED` 恢复按最终值计分。解决者不能是贡献者本人。
5. **处理操作结果和错误。** 每次操作后重新读取贡献详情和项目数据，显示最新状态；把服务端的校验错误反馈给用户，避免界面显示成功而数据未保存。

### B 的交付与验收

- 能从一条 `PENDING` 贡献进入详情、添加证据，并由其他成员确认或调整为 `VERIFIED`。
- 能对 `PENDING` 或 `VERIFIED` 贡献提出争议，看到 `DISPUTED` 状态，再由其他成员解决为 `RESOLVED`，保留原因和处理结论。
- 不能确认自己的贡献；不合法的状态流转和无效分值会被拒绝，原数据保持不变。
- 每次确认、争议和解决后，C 读取的数据能反映最新状态及得分。

## C：Dashboard 与 Contribution Graph

### 要完成的工作

1. **项目总览。** 从 `dashboard_data(project_id)` 读取数据，展示项目名称、成员、任务及任务预设价值。成员卡片展示 `totalScore`、`contributionShare` 和四类 `breakdown`。
2. **贡献明细。** 显示每条贡献的贡献者、任务、类型、说明、帮助对象、状态和当前 `score`。对 `PENDING`、`DISPUTED` 显示“暂不计分”，避免把 0 分误解为没有提交贡献。
3. **帮助关系图。** 使用 `relationships` 绘制“贡献者 → 被帮助成员”的关系，并标注任务、贡献类型、状态和得分。关系图也应保留待验证或争议中的关系，但要用状态区分；这些关系的当前得分为 0。没有 `helpedMemberId` 的贡献不会出现在该数组中，仍应出现在贡献明细里。
4. **与 B 的操作联动。** B 完成确认、调整、争议或解决后，重新获取 `dashboard_data(...)` 并刷新成员分数、占比、分类明细、贡献状态及关系图。具体采用手动刷新还是自动刷新，可按最终界面技术栈决定。
5. **空数据与数字展示。** 处理团队总分为 0、没有帮助关系、没有贡献等情况；百分比按接口给出的两位小数展示。分数与占比直接使用 A 的结果，不在 C 中再次计算。

### C 的交付与验收

- 4 名成员、4 项任务和 4 类贡献均可在总览或明细中找到。
- 能看到 David 帮助 Alice 完成 Deployment 的关系，并能从图上辨认任务、状态和当前得分。
- B 修改贡献状态或最终价值后，刷新页面可看到一致的分数、分类明细、占比和关系图。
- 待验证、争议中及空数据状态都有明确展示，不出现错误或误导性的百分比。

## 联调顺序

1. 确定固定演示数据文件、项目 ID `fintech`、调用方式及 B/C 共用的读写入口。
2. B 接通“查看贡献 → 添加证据 → 确认/调整 → 争议 → 解决”的操作链。
3. C 接通 `dashboard_data("fintech")`，完成总览、明细和帮助关系图。
4. 用 `demo_workflow.py` 的结果核对联动：全部待验证时四人均为 0；确认与调整后 Alice/Bob/Charlie/David 分别为 40/20/3/12；David 的 Support 被争议时为 4；最终价值改为 7 并解决后为 11。
5. 运行 `python3 -m unittest discover -s 'Contribution Graph' -p 'test_*.py'`，再进行一次真实界面操作演示。

## 参考代码

- `Contribution Graph/contribution_engine.py`：数据类型、状态及评分规则。
- `Contribution Graph/contribution_store.py`：B 的写入方法和 C 的读取数据。
- `Contribution Graph/demo_workflow.py`：完整四人流程及预期分数。
- `Contribution Graph/README.md`：命令行示例与接口说明。
