# A responsibilities for data, Token ledger, and graph engine

This is the Token model design specification. Some sections describe the original MVP scope rather than all features now implemented. A owns the data and settlement foundation: model verifiable results, convert direct and commissioned production into mint/allocation events, and project the ledger into an explanatory graph. B supplies verification and dispute decisions; C presents balances, transactions, and value paths.

The model's primary result is Token Balance. Value is minted once, then distributed by agreement. The legacy score engine remains available as a compatible valuation workflow.

```text
Project / Member → Task + Mint Cap → Direct Production / Commission Contract
→ Evidence + Independent Verification → Mint / Split / Transfer / Freeze / Resolve
→ Append-only Ledger → Token Balance + Contribution Graph
```

## 1. Model

Separate value type from production mode:

- CORE: core deliverables.
- REVIEW: quality assurance, defect identification, or decision validation.
- COORDINATION: organization, integration, and cross-module progress.
- DIRECT: mint verified result value to its producer.
- COMMISSIONED: a principal uses existing or future Tokens to commission a contractor; verify result value once, then allocate by contract.

SUPPORT is a commissioned production relationship, not an additional independent mint category. Its output is verifiable CORE, REVIEW, or COORDINATION work.

```text
Balance_i = MintedTo_i + PaymentsReceived_i - PaymentsMade_i
```

The design presents balances as the primary contribution metric, rather than maintaining a second independent score/share system.

## 2. Settlement rules

Direct production: a member delivers a task, B verifies value V, and the treasury mints V to that member. Member balance and total supply increase by V.

Commission example: A commissions B at price P = 50; an independent verifier values the CORE result at V = 60. Mint 60 to A and transfer 50 to B in one atomic settlement. A retains 10 for initiating, organizing, and taking delivery responsibility/risk; B receives 50 for execution. Team supply grows by 60, never 110. Transfers and circular payments do not increase supply.

Future mint-and-split allows a principal without sufficient initial balance to sign a commission. Logically record MINT 60 → A and TRANSFER 50 A → B, but execute atomically so the principal cannot receive the mint and refuse payment.

```text
0 <= FinalPayment <= VerifiedMintValue
FinalPayment = min(ContractPrice, VerifiedMintValue)
Sum of member net balance increases = Actual mint value
```

If a price-50 result is verified at 40, payment is capped at 40. More complex fixed-price risk allocation is outside this MVP design.

## 3. Data scope

Store Project, Member, Treasury, and GovernancePolicy. The policy describes mint thresholds, disputes, and amount limits. The original MVP excludes complex authentication, invitations, cross-project assets, and public wallets; later manuals cover the implemented account extensions.

Tasks contain `taskId`, `name`, `description`, `valueType`, `mintCap`, `acceptanceCriteria`, and `status`. Total task mint must not exceed its cap. A cap is issuing capacity, not an automatically earned score; mint only after B verifies a result.

All value changes are append-only. Contribution events carry `eventId`, `projectId`, `taskId`, `valueType`, `productionMode`, `principal` (optional for DIRECT), `contractor`, `verifiedMintValue`, `contractPrice`, `evidenceHashes`, `approvals`, `status`, `transactionHash`, `createdAt`, and `settledAt`.

Design event types include TASK_CREATED, COMMISSION_OFFERED, COMMISSION_ACCEPTED, DELIVERY_SUBMITTED, VALUE_VERIFIED, MINT, TRANSFER, FREEZE, RELEASE, REFUND, SPLIT, and SETTLED.

## 4. Commission state machine

Contracts include principal, contractor, valueType, relatedTask, contractPrice, maximumMintValue, acceptanceCriteriaHash, evidenceHashes, approvers, and status.

```text
DRAFT → OFFERED → ACCEPTED → CREDIT_RESERVED → DELIVERED → VERIFIED
→ MINTED_AND_PAID → SETTLED

DELIVERED / VERIFIED → DISPUTED → FROZEN → RESOLVED
                                               ├ RELEASE
                                               ├ REFUND
                                               └ SPLIT
```

These are design-level states; consult the implementation and settlement manual for actual stored enums. A must rebuild balances and graph deterministically after B's legal verification or resolution decisions.

## 5. Ledger

Support cap-constrained MINT, project-local TRANSFER, atomic MINT_AND_SPLIT, FREEZE, RELEASE, REFUND, and SPLIT. Derive member balances and task minted/reserved/available budgets from events. Reject duplicate evidence minting and repeated contract settlement. Balances are derived facts, not freely editable fields.

## 6. Explanatory graph

SourceCred is a relationship-modeling reference, not an automatic pricing or minting engine. The design principle is: the ledger records value, settlement distributes it, balances represent it, and the graph explains it.

Nodes: PROJECT, TREASURY, MEMBER, TASK, ARTIFACT, CONTRIBUTION_EVENT, COMMISSION_CONTRACT, EVIDENCE, DISPUTE, SETTLEMENT.

Edges: COMMISSIONED, EXECUTED, CONTRIBUTES_TO, REVIEWED, COORDINATED, SUPPORTED_BY, VERIFIED, MINTED, PAID, DISPUTED, RESOLVED_AS.

For the 60/50 example: Treasury MINTED 60 to A; A COMMISSIONED B; B EXECUTED the core task; A PAID 50 to B; an independent verifier VERIFIED the task. The graph explains events and never uses PageRank/CredRank to decide mint amounts.

Stable addresses follow `["cvn", projectId, kind, objectId]`, using member, task, event, contract, evidence, and settlement kinds. Evidence uses its hash; settlement can use its transaction hash. Repeated imports must be idempotent. Rebuild the graph from the ledger, separate facts from analytical weights, and allow future GitHub, contract, and manual-evidence subgraphs to merge.

## 7. Boundaries with B and C

A gives B task caps/criteria, events/contracts, evidence links, and state operations for verification, freezing, and resolution. B checks result existence, evidence, final verifiedMintValue, and RELEASE/REFUND/SPLIT decisions. A executes legal conclusions without independently deciding value.

A gives C member tokenBalance, Mint/Payment/Freeze/Refund/Split details, task budgets, contracts/statuses, and graph nodes/edges with amounts, times, and states. Explain who commissioned, executed, verified, minted, and received value. C must not recalculate balances or generate another score through graph algorithms.

## 8. Invariants and risks

- Transfers never increase total supply; mint only verified value.
- Commission parties cannot independently approve their own result.
- Cumulative task mint stays within cap.
- No duplicate result/evidence mint or contract settlement.
- Mint-and-split is atomic.
- Pending, disputed, and frozen value cannot become available balance; resolution follows final settlement.
- Every settlement conserves Tokens.
- Circular commissioning and mutual approval may produce risk flags; the graph does not automatically establish guilt.

Simple transfers cannot inflate supply, but fake tasks can still cause illegitimate issuance. Issuance safety requires Mint Cap + Evidence + Independent Verification + Unique Settlement.

## 9. Demo and acceptance

Use Alice, Bob, Charlie, and David. Cover Alice's direct CORE mint; Alice commissioning Bob for value 60/price 50 (Alice +10, Bob +50); Charlie's direct REVIEW; David's COORDINATION by direct or commissioned production; a DISPUTED/FROZEN commission; a final SPLIT; and synchronized ledger/balance/graph updates.

The main demo creates a capped task, offers a commission at 50, delivers CORE work and evidence, independently values it at 60, atomically mints/splits, and then demonstrates freezing and splitting another disputed contract.

- [ ] Persist projects, members, and treasury; create capped tasks with criteria.
- [ ] Support CORE/REVIEW/COORDINATION and DIRECT/COMMISSIONED.
- [ ] Record negotiated commissions, evidence, approvals, and final valuation.
- [ ] Mint direct value and atomically settle commissioned value.
- [ ] Verify the 60/50 example and supply-preserving transfers.
- [ ] Enforce caps, unique minting, and unique settlement.
- [ ] Represent Pending, Verified, Disputed, Frozen, Resolved, and Settled states.
- [ ] Support RELEASE, REFUND, and SPLIT.
- [ ] Rebuild balances/graph deterministically and update them after B decisions.
- [ ] Expose balances, events, budgets, and graph to C; prepare four-member demo data.

## 10. Outside the original A MVP

Automatic CredRank/PageRank pricing or minting, an independent second contribution score/share, public trading/cash conversion/cross-project Tokens, DAO/NFT/mainnet, AI valuation, complex authentication/permissions/deep GitHub integration, and decorative animation were excluded from the original design. The deliverable is a data, ledger, settlement, and graph engine where value is minted once, allocated by agreement, and explainable through rebuildable balances and relationships.
