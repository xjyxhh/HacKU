# A：Data & Score Engine 职责总结

## 职责概述

A 负责 Contribution Graph 的数据基础、贡献录入和分数计算，建立从项目、成员、任务、贡献到个人得分与团队贡献占比的完整数据链，并将计算结果提供给 B 和 C。

> 项目与成员 → 任务及价值 → 贡献记录 → 验证状态 → 得分与分类明细 → 团队贡献占比 → Dashboard / Graph

## 工作范围

### 1. 项目与成员

支持创建和保存项目及成员。MVP 示例项目为 **FinTech Contribution Graph**，成员为 Alice、Bob、Charlie、David。暂不实现复杂登录、权限或邀请流程。

### 2. 任务与预设价值

支持创建带有名称、描述和 `Task Value` 的任务。任务价值应在工作开始前设定，作为贡献评分的基础规则。

| 任务 | Task Value |
|---|---:|
| Recommendation Engine | 40 |
| Frontend Dashboard | 25 |
| Deployment | 20 |
| Demo Preparation | 15 |

### 3. 贡献记录与提交

每条 Contribution 至少记录：

- `contributor`：贡献者
- `task`：关联任务
- `type`：`CORE`、`SUPPORT`、`REVIEW` 或 `COORDINATION`
- `description`：贡献说明
- `helpedMember`：受帮助成员，可选；Support 尤其需要支持此字段
- `completion`：完成程度
- `supportValue`：额外支持分值
- `status`：`PENDING`、`VERIFIED`、`DISPUTED` 或 `RESOLVED`

用户提交贡献后，状态设为 `PENDING`。提交本身不产生最终得分；贡献需经 B 验证后再计分。

**示例：** David 为 Deployment 提交一条 Support 贡献，说明为“帮助排查部署问题”，帮助对象为 Alice，`supportValue` 为 8，初始状态为 `PENDING`。

### 4. 评分规则与状态处理

按贡献类型计分：

```text
CORE = TaskValue × Completion × Quality
SUPPORT / REVIEW / COORDINATION = SupportValue × Quality
```

其中 `Completion` 使用 0–1 的比例，`Quality` 为质量系数。例：CORE 任务价值 40、完成度 100%、质量系数 1.0，则得分为 40；SUPPORT 价值 8、质量系数 1.0，则得分为 8。`supportValue` 在 `PENDING` 时只是提议值，经过验证或争议解决后才作为最终值计分。

状态对计分的影响：

| 状态 | 计分规则 |
|---|---|
| `PENDING` | 暂不计入最终得分 |
| `VERIFIED` | 按评分规则计入 |
| `DISPUTED` | 暂停计入 |
| `RESOLVED` | 按解决后的最终结果计入 |

B 负责证据、同伴验证、确认、调整、争议和解决。A 需要保证 B 更新贡献状态或最终价值后，分数、明细和占比能够重新计算。

### 5. 汇总分数、明细与贡献占比

系统需要按成员汇总有效贡献，提供总分及四类贡献明细，并计算团队贡献占比：

```text
ContributionShareᵢ = Scoreᵢ ÷ TeamTotalScore × 100%
```

例如 Alice 得分 40、Bob 32、Charlie 21、David 17 时，团队总分为 110；Alice 的占比为 36.36%。

提供给 C 的成员数据应包含：

- `totalScore`
- `contributionShare`
- `breakdown`：Core、Support、Review、Coordination 分类得分

C 直接使用 A 计算出的结果，不重复实现评分或占比计算。

### 6. 跨成员关系数据

保留 `helpedMember`，使系统能够表达并展示“谁帮助了谁、帮助发生在哪项任务上”。例如：David → Support → Alice → Deployment。该关系是呈现被忽略贡献价值的重要数据。

### 7. B 与 C 的接口

**交给 B：** 可验证和更新的 Contribution 记录，包括状态、证据所需关联信息及最终调整结果。

**交给 C：**

1. 分数数据：成员总分、贡献分类明细、贡献占比。
2. 关系数据：贡献者、贡献类型、受帮助成员、关联任务。

B 完成验证或解决争议后，A 根据最新状态重算；C 使用更新后的结果刷新 Dashboard 和 Contribution Graph。

### 8. Demo 数据

准备一个含 4 位成员、4 项任务和多种贡献类型的完整演示数据集，覆盖四种状态：`PENDING`、`VERIFIED`、`DISPUTED`、`RESOLVED`。示例贡献包括 Alice 的 Core、Bob 的 Core、Charlie 的 Review、David 帮助 Alice 的 Support，以及 David 的 Coordination。

## 验收标准

- [ ] 能创建和保存 Project、Member。
- [ ] 能创建带预设 Task Value 的 Task。
- [ ] 能提交 Core、Support、Review、Coordination 四类贡献。
- [ ] Support 贡献可以记录 `helpedMember`。
- [ ] Contribution 支持 Pending、Verified、Disputed、Resolved 状态。
- [ ] Pending 和 Disputed 不计入最终得分；Verified 和 Resolved 按规则计分。
- [ ] 能自动计算成员总分、分类明细和 Contribution Share。
- [ ] B 更新验证/解决结果后，系统重算分数，C 可获取更新数据。
- [ ] 准备好可直接用于开发和演示的 4 人 Demo 数据。

## 明确不在 A 的范围

当前阶段不扩展到 AI、GitHub API、登录系统、复杂权限或动画。A 的交付重点是可靠的数据结构、贡献录入、状态驱动的评分计算，以及供 B、C 使用的数据接口。
