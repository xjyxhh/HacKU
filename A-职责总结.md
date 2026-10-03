# A：Data、Token Ledger & Graph Engine 职责总结

## 1. 职责概述

A 负责 Contribution Value Network 的数据与结算地基：把项目成果建模为可验证的价值事件，把直接生产和委托生产转换为 Token 铸造与分配记录，并将账本投影为 SourceCred 式 Contribution Graph，供 B 完成验证、争议处理，供 C 展示余额、交易和价值路径。

A 不再实现传统贡献打分或 Contribution Share。系统的核心结果是成员的 **Token Balance**：每项价值只铸造一次，再依据事先签署的合约完成分配。

```text
Project / Member
      ↓
Task + Mint Cap
      ↓
Direct Production 或 Commission Contract
      ↓
Evidence + Independent Verification（B）
      ↓
Mint / Split / Transfer / Freeze / Resolve
      ↓
Append-only Ledger
      ↓
Token Balance + Contribution Graph（C）
```

核心原则：

> Value is minted once, then distributed by agreement.
>
> 价值只铸造一次，再通过协议完成分配。

---

## 2. 最终模型

### 2.1 价值类型与生产方式分离

系统不再把 `SUPPORT` 与 `CORE`、`REVIEW`、`COORDINATION` 并列为四种计分类型，而是分为两个维度：

**价值类型 `valueType`：**

- `CORE`：产生项目核心交付物；
- `REVIEW`：产生质量保障、缺陷识别或决策校验价值；
- `COORDINATION`：产生组织、联调、跨模块推进等价值。

**生产方式 `productionMode`：**

- `DIRECT`：成员直接完成成果，验证后向该成员铸币；
- `COMMISSIONED`：委托人使用已有或未来 Token 委托执行人完成成果，验证后先确认成果总价值，再按合约分配。

因此，`SUPPORT` 的最终定义是：

> Support 是一种委托生产关系。委托人使用已有或未来的 Contribution Token，委托执行人完成可验证的 CORE、REVIEW 或 COORDINATION 成果；成果价值只铸造一次，再按合约向双方分配。

### 2.2 Token Balance

成员余额统一表示其在项目价值生产和交换后保留的净贡献权益：

```text
Balanceᵢ = MintedToᵢ + PaymentsReceivedᵢ - PaymentsMadeᵢ
```

Dashboard 以余额作为主要贡献指标，不再维护另一套 Score 或 Contribution Share。

---

## 3. 核心结算规则

### 3.1 直接生产

成员自己完成并对成果负责：

```text
A completes Task
→ B verifies value V
→ Treasury mints V Token to A
```

余额变化：

```text
ΔA = V
Total Supply += V
```

### 3.2 委托生产（Support）

假设 A 委托 B 完成一项 CORE 工作，双方约定报酬 `P = 50`，成果经独立验收后的价值为 `V = 60`：

```text
A commissions B for 50 Token
→ B delivers the CORE result
→ B verifies the result at 60 Token
→ Treasury mints 60 Token to A
→ Contract transfers 50 Token from A to B
```

最终余额变化：

```text
ΔA = V - P = 10
ΔB = P     = 50
ΔA + ΔB    = V = 60
```

这意味着：

- B 获得 50 Token，代表实际执行价值；
- A 保留 10 Token，代表发起任务、组织资源、承担交付责任和风险所形成的剩余价值；
- 团队总供应量只增加 60，不会把 A 的 60 与 B 的 50 重复计算为 110；
- 成员互相转账不会增加总供应量，因此不能仅靠循环支付刷高总贡献。

### 3.3 Mint-and-Split

为了允许尚无足够余额的委托人签约，MVP 推荐使用未来铸币分账：

```text
Verified Mint Value: 60
Contract Price: 50

Atomic Settlement
├── 10 Token → A
└── 50 Token → B
```

账本逻辑上仍记录为：

```text
MINT 60 → A
TRANSFER 50: A → B
```

但智能合约应在同一次原子结算中完成，避免 A 获得铸币后拒绝向 B 支付。

### 3.4 会计守恒

对每项委托成果：

```text
0 ≤ FinalPayment ≤ VerifiedMintValue
```

并满足：

```text
所有成员净余额增量之和 = 该成果实际铸币量
```

MVP 默认规则：

```text
FinalPayment = min(ContractPrice, VerifiedMintValue)
```

若成果只验收为 40，而约定价格为 50，则支付封顶为 40；更复杂的固定价风险承担机制暂不进入 MVP。

---

## 4. A 的工作范围

### 4.1 Project、Member 与 Treasury

实现并保存：

- `Project`：项目基本信息；
- `Member`：成员身份及项目内地址；
- `Treasury`：项目铸币主体；
- `GovernancePolicy`：Mint 审批阈值、争议规则和金额上限。

MVP 暂不实现复杂登录、邀请、跨项目资产或公开钱包经济。

### 4.2 Task 与 Mint Cap

每项任务创建时设置：

- `taskId`
- `name`
- `description`
- `valueType`
- `mintCap`
- `acceptanceCriteria`
- `status`

核心约束：

```text
Task Total Minted ≤ Task Mint Cap
```

`Mint Cap` 是可发行上限，不是自动获得的分数。只有成果经 B 验证后才能实际铸币。

### 4.3 Contribution Event

所有价值变化均以追加式事件记录，不直接覆盖历史。

事件至少包括：

- `eventId`
- `projectId`
- `taskId`
- `valueType`
- `productionMode`
- `principal`：委托人；DIRECT 时可为空
- `contractor`：执行人
- `verifiedMintValue`
- `contractPrice`
- `evidenceHashes`
- `approvals`
- `status`
- `transactionHash`
- `createdAt` / `settledAt`

主要事件类型：

```text
TASK_CREATED
COMMISSION_OFFERED
COMMISSION_ACCEPTED
DELIVERY_SUBMITTED
VALUE_VERIFIED
MINT
TRANSFER
FREEZE
RELEASE
REFUND
SPLIT
SETTLED
```

### 4.4 Commission Contract

A 需要实现委托合约数据结构和状态机。

核心字段：

```text
principal
contractor
valueType
relatedTask
contractPrice
maximumMintValue
acceptanceCriteriaHash
evidenceHashes
approvers
status
```

状态流：

```text
DRAFT
→ OFFERED
→ ACCEPTED
→ CREDIT_RESERVED
→ DELIVERED
→ VERIFIED
→ MINTED_AND_PAID
→ SETTLED
```

争议分支：

```text
DELIVERED / VERIFIED
→ DISPUTED
→ FROZEN
→ RESOLVED
   ├── RELEASE
   ├── REFUND
   └── SPLIT
```

A 负责确保 B 更新验证或解决结果后，账本、余额与 Graph 可以确定性重建。

### 4.5 Token Ledger

A 维护追加式 Ledger，至少支持：

- 受 Mint Cap 约束的 `MINT`；
- 项目内 `TRANSFER`；
- `MINT_AND_SPLIT` 原子结算；
- `FREEZE`、`RELEASE`、`REFUND`、`SPLIT`；
- 按成员计算余额；
- 按任务统计已铸、预留和剩余额度；
- 防止同一成果或 Evidence 重复铸币；
- 防止重复结算同一合约。

余额是 Ledger 事件的派生结果，不应作为可随意修改的独立字段。

### 4.6 SourceCred 式 Contribution Graph

SourceCred 在本项目中不是计分器或铸币器，而是关系建模与分析参考：

> 区块链记录价值，智能合约分配价值，Token Balance 表示价值，SourceCred 式 Graph 解释价值。

Graph 节点：

```text
PROJECT
TREASURY
MEMBER
TASK
ARTIFACT
CONTRIBUTION_EVENT
COMMISSION_CONTRACT
EVIDENCE
DISPUTE
SETTLEMENT
```

Graph 边：

```text
COMMISSIONED
EXECUTED
CONTRIBUTES_TO
REVIEWED
COORDINATED
SUPPORTED_BY
VERIFIED
MINTED
PAID
DISPUTED
RESOLVED_AS
```

以 A 委托 B 完成 60 Token CORE、支付 50 Token 为例：

```text
Treasury ──MINTED 60──→ A
A ──COMMISSIONED──→ B
B ──EXECUTED──→ Core Task
A ──PAID 50──→ B
Verifier ──VERIFIED──→ Core Task
```

Graph 只解释已发生的价值事实，不使用 PageRank/CredRank 自动决定 Mint 数量。

### 4.7 稳定地址与幂等导入

参考 SourceCred，为节点和边提供分层地址：

```text
["cvn", projectId, "member", memberId]
["cvn", projectId, "task", taskId]
["cvn", projectId, "event", eventId]
["cvn", projectId, "contract", contractId]
["cvn", projectId, "evidence", evidenceHash]
["cvn", projectId, "settlement", transactionHash]
```

要求：

- 同一账本事件重复导入时结果幂等；
- Graph 可从 Ledger 完整重建；
- Graph 事实与分析权重分离；
- GitHub、合约和手工 Evidence 等数据源未来可生成子图再合并。

---

## 5. A 与 B、C 的边界

### 5.1 与 B：Verification & Dispute

A 向 B 提供：

- Task、Mint Cap 与验收标准；
- Contribution Event 和 Commission Contract；
- Evidence 关联位；
- 可验证、冻结和解决的状态接口。

B 负责：

- 验证成果是否存在；
- 确认最终 `verifiedMintValue`；
- 审核 Evidence；
- 发起及解决争议；
- 给出 Release、Refund 或 Split 结果。

A 不替 B 判断价值，但必须安全执行 B 的合法结论。

### 5.2 与 C：Dashboard & Graph UI

A 向 C 提供：

1. 成员 `tokenBalance`；
2. 余额变化明细：Mint、Payment、Freeze、Refund、Split；
3. 任务预算：Mint Cap、Minted、Reserved、Available；
4. 合约及状态；
5. Graph 节点、边、金额、时间和状态；
6. 可解释价值路径，例如“谁委托、谁执行、谁验收、铸造多少、如何分配”。

C 不重复计算余额，也不使用 Graph 算法重新生成一套贡献分数。

---

## 6. 风控与不变量

A 必须实现或保留以下约束：

- 普通 Transfer 不得增加 Total Supply；
- 只有验证后的价值事件可以 Mint；
- 委托双方不能单独完成独立验收；
- 单项任务累计 Mint 不得超过 Mint Cap；
- 同一成果和 Evidence 不得重复 Mint；
- 同一 Commission Contract 不得重复结算；
- `MINT_AND_SPLIT` 必须原子执行；
- `PENDING`、`DISPUTED`、`FROZEN` 事件不得进入可用余额；
- `RESOLVED` 按最终 Settlement 入账；
- 每项结算满足 Token 守恒；
- 循环委托和互相验收应输出风险标记，但不由 Graph 自动定罪。

新机制防止通过简单互相转账刷高总 Token，但虚假任务仍可能导致非法铸币。因此真正的发行安全来自：

```text
Mint Cap + Evidence + Independent Verification + Unique Settlement
```

---

## 7. Demo 数据与主流程

准备 Alice、Bob、Charlie、David 四人数据，至少覆盖：

1. Alice 直接完成 CORE，验证后获得 Mint；
2. Alice 委托 Bob 完成 CORE：价值 60、价格 50，结算后 Alice +10、Bob +50；
3. Charlie 完成 REVIEW 并独立铸币；
4. David 完成 COORDINATION 并获得直接或委托分账；
5. 一笔委托进入 `DISPUTED/FROZEN`；
6. 争议最终按 `SPLIT` 解决；
7. Ledger、余额和 Graph 随结算同步更新。

主 Demo：

```text
Create Task with Mint Cap
→ A commissions B for 50
→ B delivers CORE
→ Evidence attached
→ Independent verification values it at 60
→ Atomic mint-and-split
→ A balance +10 / B balance +50
→ Ledger and Graph update
→ Dispute another contract
→ Freeze and split settlement
```

---

## 8. 验收标准

- [ ] 能创建和保存 Project、Member、Treasury。
- [ ] 能创建带 `Mint Cap` 和验收标准的 Task。
- [ ] 支持 `CORE`、`REVIEW`、`COORDINATION` 三种价值类型。
- [ ] 支持 `DIRECT` 和 `COMMISSIONED` 两种生产方式。
- [ ] 能创建 A→B 的 Commission Contract 并约定价格。
- [ ] 能记录 Evidence、审批和最终 `verifiedMintValue`。
- [ ] 直接生产验证后能向生产者 Mint。
- [ ] 委托生产能执行原子 `MINT_AND_SPLIT`。
- [ ] 60 Token 成果、50 Token 合约能得到 A +10、B +50。
- [ ] 普通互相 Transfer 不改变 Total Supply。
- [ ] Task 累计 Mint 不超过 Mint Cap。
- [ ] 同一成果、Evidence 或合约不能重复铸币/结算。
- [ ] 支持 Pending、Verified、Disputed、Frozen、Resolved、Settled 状态。
- [ ] 支持 Release、Refund、Split 三种争议结算。
- [ ] Token Balance 可从 Ledger 确定性重建。
- [ ] Graph 可从 Ledger 投影并展示委托、执行、验证、铸币和支付关系。
- [ ] B 更新验证/争议结果后，余额和 Graph 自动更新。
- [ ] C 可直接获取余额、账本、任务预算和 Graph 数据。
- [ ] 准备完整的 4 人 Demo 数据。

---

## 9. 明确不在 A 的范围

MVP 阶段不实现：

- CredRank/PageRank 自动定价或铸币；
- 第二套 Contribution Score 或 Contribution Share；
- 公开交易、现金兑换、跨项目 Token；
- DAO、NFT、主网部署；
- AI 自动判断贡献价值；
- 复杂登录、权限或 GitHub API 深度集成；
- 仅为视觉效果服务的复杂动画。

A 的最终交付重点是：

> 一套满足“价值只铸造一次、按协议分配、余额可重建、关系可解释”的数据、账本、结算和 Graph Engine。
