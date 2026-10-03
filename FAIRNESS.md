# 公平规则与适用边界

## 撤回与退出

撤回必须由贡献者提出，并由另一位活跃项目成员决定。已批准撤回的有效分数为零，但原记录及审核历史不会删除。成员退出只影响单个项目，不删除全局账号；尚未追回的 Token 记为具名债务，不能从第三方余额强制扣除。退出前会阻止未解决争议、未结算合约、冻结 Token 和唯一管理员退出。项目归档可恢复，不能当作物理删除。Token 工作台按当前项目读取独立账本；生产备份与恢复仍需在部署环境演练。

Withdrawal must be requested by the contributor and decided by another active project member. An approved withdrawal has zero effective score, while its record and review history remain. Exit applies to one project and does not delete the global account. Unrecovered Tokens remain named debt; third-party balances cannot be forcibly debited. Unresolved disputes, unsettled contracts, frozen Tokens, and a sole administrator block exit. Archival is reversible. The Token workbench reads an independent ledger for the selected project. Production backup and restoration still need a deployment rehearsal.

## 贡献如何进入账本

成员提交贡献和证据后，由另一位项目成员独立审核。只有已核验的贡献价值可以铸币，同一贡献证据只能入账一次，且每个任务的累计铸币不得超过管理员设置的上限。审核者不能核验自己的贡献。发生争议时，相关分值和可识别的 Token 付款会暂停处理，结论由有权限且非争议当事人的管理员作出。

## 委托如何结算

委托预留任务铸币额度，但预留本身不会扣除委托人的 Token。交付并经独立成员批准后，系统按验证价值铸币，再按合约价格付款。争议终局可以释放付款给承接人、全额退还委托人，或按明确金额拆分。退款和拆分只处理已冻结的原付款，不再次铸币，也不会恢复已用任务额度。未结算合约取消只释放预留额度，不会生成金额退款。

## 谁受益，谁承担成本

贡献者可因可核验的工作取得 Token；委托人可以把任务交由承接人完成，并保留任务价值与付款价格之间的差额；承接人取得协商好的付款。独立审核和争议处理保护贡献者、委托人及承接人免受单方确认，但会增加等待时间，也要求成员投入审核与说明争议的时间。管理员需要维护任务上限、证据与账本。

## 规则的失效边界

- 只有两名成员的项目无法做到由第三名成员独立批准彼此的委托。系统应阻止结算，团队需要增加独立审核成员。
- 如果承接人已转出付款，系统可能无法冻结足额余额。此时结案会被拒绝并显示欠额；本版不会自动冲销其他成员余额。
- 余额冻结只覆盖账本中可识别的关联付款，不代表链外资产或已离开账本的价值可以追回。
- 贡献价值单位由任务上限、审核判断与团队实践共同决定，可能随时间漂移；Token 数量不能自动代表市场价格、工作时长或公平工资。
- 争议暂停的是系统可控制的分值和余额，不消除成员之间的信任、沟通与治理问题。
