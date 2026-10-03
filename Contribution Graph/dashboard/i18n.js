// Translate interface copy after each render. Keep project data and user input intact.
const I18n = (() => {
  const copy = {
    "中文": "Chinese", "设置": "Settings", "语言": "Language", "界面语言": "Interface language",
    "我的工作区": "My Workspace", "公开 Demo": "Public Demo", "个人资料": "Profile", "创建账号": "Create Account",
    "创建账号 · Contribution Graph": "Create Account · Contribution Graph", "我的工作区 · Contribution Graph": "My Workspace · Contribution Graph", "个人资料 · Contribution Graph": "Profile · Contribution Graph", "公开 Demo · Contribution Graph": "Public Demo · Contribution Graph",
    "这里还没有项目。你可以创建项目，或等待项目 Owner 邀请。": "No projects yet. Create one or wait for an invitation from a project Owner.",
    "打开项目看板": "Open Project Dashboard", "成员与角色": "Members and Roles", "待办": "To-dos", "目前没有待办。": "No to-dos right now.",
    "接受委托": "Accept Commission", "提交交付证据": "Submit Delivery Evidence", "独立批准委托": "Approve Commission Independently", "审核贡献": "Review Contribution", "处理成员退出": "Review Member Exit",
    "Token 余额暂不可用：": "Token balance unavailable: ", "账本读取失败": "ledger could not be read", "账本待初始化": "ledger setup is pending", "可用 Token：": "Available Tokens: ", "冻结：": "Frozen: ", "成员 ": "Members ", " · 任务 ": " · Tasks ",
    "请先登录后查看个人工作区。": "Sign in to view your workspace.", "请先登录查看个人资料。": "Sign in to view your profile.",
    "邮箱尚未验证。当前环境未配置验证邮件服务；修改邮箱请联系管理员。": "Your email is unverified. Email verification is not configured; contact an administrator to change it.",
    "邮箱尚未验证；邮箱登录和邮箱邀请暂不可用。": "Your email is unverified. Email sign-in and email invitations are unavailable.",
    "邮箱尚未验证；请保存成员 ID，用它登录。": "Email is unverified. Save your member ID and use it to sign in.",
    "注册会创建一个空账号，不会自动加入现有项目。邮箱验证暂不可用时，可用生成的成员 ID 登录。": "Registration creates an empty account and does not add you to existing projects. Use your generated member ID while email verification is unavailable.",
    "此页面只展示固定示例数据，不代表真实成员余额。": "This page uses fixed sample data and does not represent real member balances.",
    "图视图": "Graph view", "价值创造": "Value creation", "Token 流转": "Token flow", "协作": "Collaboration", "验证与信任": "Verification and trust",
    "我的工作区": "My Workspace", "个人资料": "Profile", "公开 Demo": "Public Demo",
    "添加管理员": "Add administrator", "确认添加": "Add", "成员登录": "Member login", "成员 ID": "Member ID", "密码": "Password", "登录": "Log in", "退出": "Log out", "取消": "Cancel", "只读访问": "Read-only access", "管理员已添加。": "Administrator added.", "添加管理员失败，请重试。": "Could not add administrator. Please try again.",
    "输入": "Input",
    "跳转到主要内容": "Skip to main content", "项目看板": "Project Dashboard",
    "Contribution Graph | 项目看板": "Contribution Graph | Project Dashboard",
    "Contribution Graph · 贡献审核": "Contribution Graph · Contribution Review",
    "Contribution Graph | Token 工作台": "Contribution Graph | Token Workspace",
    "贡献审核": "Contribution Review", "Token 工作台": "Token Workspace",
    "当前项目": "Current Project", "切换审核项目": "Switch Review Project",
    "刷新数据": "Refresh Data", "刷新数据 ↗": "Refresh Data ↗", "关系图": "Graph",
    "正在读取项目": "Loading Project…", "正在读取项目…": "Loading Project…",
    "更新于": "Updated at", "全部": "All", "类型": "Type", "状态": "Status",
    "团队总分": "Team Score", "贡献记录": "Contributions",
    "已认定 Token": "Recognized Tokens", "Token 余额": "Token Balance",
    "Token 事件": "Token Events", "旧贡献分": "Previous Score",
    "当前冻结": "Currently Frozen", "已入账": "Recorded",
    "待补铸": "Awaiting Mint", "前往 Token 工作台处理": "Open Token Workspace",
    "补同步。": "to Reconcile.", "Token 待补铸。请到": "Token Mint Pending. Go to",
    "待验证": "Pending", "已验证": "Verified", "争议中": "Disputed", "已解决": "Resolved",
    "核心": "Core", "支持": "Support", "审查": "Review", "协调": "Coordination",
    "暂无证据。": "No Evidence Yet.", "暂无审核记录。": "No Reviews Yet.",
    "暂无争议记录。": "No Disputes Yet.", "暂不计分": "Not Scored",
    "贡献详情": "Contribution Details", "证据": "Evidence", "无": "None",

    // Review page
    "证据 / 同伴验证 / 争议处理": "Evidence / Peer Review / Disputes",
    "审核摘要": "Review Summary",
    "当前操作成员": "Acting Member", "身份由登录会话确定": "Identity comes from the signed-in session",
    "已验证和已解决的贡献": "Verified and Resolved Contributions",
    "确认或调整后开始计分": "Scores Count After Confirmation or Adjustment",
    "解决前暂停计分": "Scoring Paused Until Resolution",
    "贡献列表": "Contribution Queue", "暂无符合条件的贡献。": "No Matching Contributions.",
    "选择一条贡献查看详情。": "Select a Contribution to View Details.",
    "证据类型": "Evidence Type", "文字说明": "Written Note", "网页链接": "Web Link",
    "图片链接": "Image Link", "GitHub PR 链接": "GitHub PR Link",
    "说明或链接": "Description or Link", "填写工作记录或证据链接": "Add a Work Note or Evidence Link…",
    "例如工作记录或 https://example.com/…": "e.g. Work Note or https://example.com/…",
    "图片和 PR 保存为链接引用。": "Images and PRs Are Saved as Links.",
    "添加证据": "Add Evidence", "审核操作": "Review Actions",
    "完成比例（0–1）": "Completion (0–1)", "支持分值": "Support Value",
    "质量系数（0.9–1.1）": "Quality Factor (0.9–1.1)",
    "预览分数": "Preview Score", "修改分值后先预览，再提交。": "Preview the Score Before Submitting Changes.",
    "审核说明 / 争议原因 / 解决结论": "Review Note / Dispute Reason / Resolution",
    "提出争议或解决争议时必须填写": "Required for Disputes and Resolutions…",
    "确认贡献": "Confirm Contribution", "提交调整": "Submit Adjustment",
    "提出争议": "Raise Dispute", "解决争议": "Resolve Dispute",
    "审核记录": "Review History", "争议记录": "Dispute History",
    "Contribution Graph · 同伴审核": "Contribution Graph · Peer Review",
    "审核结果写入与看板共用的数据文件": "Review Results Are Saved to the Dashboard Data File",
    "关联任务": "Related Task", "贡献类型": "Contribution Type", "帮助对象": "Helped Member",
    "未指定": "Not Specified", "任务价值": "Task Value", "完成比例": "Completion",
    "质量系数": "Quality Factor", "提议 / 最终分值": "Proposed / Final Score",
    "当前计入团队": "Current Team Score", "未填写说明": "No Note Provided",
    "尚未解决": "Unresolved", "确认": "Confirm", "调整": "Adjust",
    "这条贡献暂不计分。提议分值表示通过验证或解决争议后可计入的分数。": "This Contribution Is Not Scored Yet. The Proposed Score Can Count After Verification or Resolution.",
    "当前分数已计入成员总分和团队贡献占比。": "The Current Score Counts Toward Member Totals and Team Share.",
    "争议已解决，可查看最终结果和处理记录。": "This Dispute Is Resolved. Review the Final Result and History.",
    "不能确认、调整或解决自己的贡献；可以添加证据或提出争议。": "You Cannot Confirm, Adjust, or Resolve Your Own Contribution. You Can Add Evidence or Raise a Dispute.",
    "直接确认现有提议分值；调整时先预览，分数必须实际变化。": "Confirm the Proposed Score, or Preview an Adjustment That Changes It.",
    "填写解决结论并预览最终分数，再提交解决结果。": "Enter a Resolution and Preview the Final Score Before Submitting.",
    "贡献已验证；如需重新核实，填写原因后提出争议。": "This Contribution Is Verified. Give a Reason to Raise a Dispute.",
    "尚无项目": "No Projects Yet", "请填写争议原因。": "Enter a Dispute Reason.",
    "请填写证据说明或链接。": "Enter an Evidence Note or Link.",
    "请填写解决结论。": "Enter a Resolution.",
    "分数未变化，可直接确认。": "The Score Is Unchanged; You Can Confirm It.",
    "预览尚未保存。": "The Preview Has Not Been Saved.",
    "关联 Token 已冻结。": "The Related Token Is Frozen.",

    // Token page
    "余额": "Balances", "任务预算": "Task Budgets", "委托合约": "Commission Contracts",
    "Token 页面导航": "Token Page Navigation", "Token 摘要": "Token Summary",
    "Token 账本关系图": "Token Ledger Relationship Graph",
    "账本事件": "Ledger Events", "启用 Token 账本": "Enable Token Ledger",
    "一个服务实例使用一份 Token 账本。选择已有项目迁移历史贡献，或创建空账本后手动添加 Token 任务。": "Each Service Uses One Token Ledger. Migrate an Existing Project or Create an Empty Ledger and Add Token Tasks.",
    "来源项目": "Source Project", "迁移历史贡献": "Migrate Past Contributions",
    "创建空账本": "Create an Empty Ledger", "项目 ID": "Project ID", "项目名称": "Project Name",
    "金库 ID": "Treasury ID", "成员 ID（每行一个）": "Member IDs (One per Line)",
    "已有已审核贡献的项目须先迁移；空账本建立后不能再迁移历史贡献。新成员和任务可在建立后同步。": "Migrate Reviewed Contributions Before Creating an Empty Ledger. You Can Sync New Members and Tasks Later.",
    "创建账本": "Create Ledger", "流通总量": "Total Supply", "当前有效 Token": "Active Tokens",
    "成员": "Members", "账本成员": "Ledger Members", "Token 任务": "Token Tasks",
    "铸币预算": "Mint Budget", "不可变历史": "Immutable History",
    "成员余额": "Member Balances",
    "余额会在铸币、转账、冻结和释放后更新。旧贡献审核成功但账本写入失败时，可补同步。": "Balances Update After Minting, Transfers, Freezes, and Releases. Reconcile Reviewed Contributions if a Ledger Write Failed.",
    "补同步已审核贡献": "Reconcile Reviewed Contributions", "待追偿余额": "Outstanding Recovery",
    "争议解决后降分，但成员已转出 Token 时产生。成员重新获得余额后可在这里继续追偿。": "If a Resolved Dispute Lowers a Score After Tokens Were Transferred, Recovery Remains Due Until the Member Has Balance Again.",
    "可用额度已扣除铸币和未结算合约预留。": "Available Budget Excludes Minted Tokens and Unsettled Contract Reserves.",
    "同步项目成员与任务": "Sync Members and Tasks", "添加 Token 任务": "Add Token Task",
    "任务 ID": "Task ID", "任务名称": "Task Name", "价值类型": "Value Type",
    "铸币上限": "Mint Cap", "验收标准": "Acceptance Criteria", "添加任务": "Add Task",
    "直接铸币与转账": "Direct Minting and Transfers",
    "旧贡献通常由审核自动铸币；漏铸请优先用“补同步”。手工铸币可填已审核贡献 ID 进行严格核对；留空表示独立 Token 工作。证据标识逐行填写。": "Reviewed Contributions Usually Mint Automatically. Use Reconcile for Missing Mints. For Manual Minting, enter a Reviewed Contribution ID for Validation, or leave it blank for Independent Token Work. Enter One Evidence ID per Line.",
    "直接铸币": "Direct Mint", "事件 ID": "Event ID", "接收成员": "Recipient",
    "数量": "Amount", "已审核贡献 ID（可选）": "Reviewed Contribution ID (Optional)",
    "证据标识": "Evidence IDs", "铸币": "Mint", "转账": "Transfer",
    "来源成员": "Source Member", "目标账户": "Destination Account",
    "合约依次经过发出、接受、预留、交付、验证，再由独立成员批准结算。争议冻结后可重新交付、验证和结算。": "Contracts Move Through Offer, Acceptance, Reserve, Delivery, and Verification. An Independent Member Approves Settlement. Frozen Disputes Can Return to Delivery.",
    "创建委托": "Create Commission", "合约 ID": "Contract ID",
    "委托成员": "Principal", "承接成员": "Contractor",
    "合约价格": "Contract Price", "最高铸币值": "Maximum Mint Value",
    "创建合约": "Create Contract",
    "贡献审核会自动冻结和释放关联事件，也可以在这里处理铸币或转账事件。": "Contribution Reviews Automatically Freeze and Release Related Events. You Can Also Manage Mint and Transfer Events Here.",
    "冻结": "Freeze", "释放": "Release", "冻结或释放事件": "Freeze or Release Event",
    "操作": "Action", "铸币或转账事件": "Mint or Transfer Event",
    "原因或说明": "Reason or Note", "提交操作": "Submit Action",
    "Token 关系图": "Token Relationship Graph",
    "显示项目、金库、成员、任务和合约之间的账本关系。": "Shows Ledger Relationships Among the Project, Treasury, Members, Tasks, and Contracts.",
    "Token 数据来自独立 SQLite 账本": "Token Data Comes From a Separate SQLite Ledger",
    "退款": "Refund", "分配": "Allocation", "草稿": "Draft",
    "已发出": "Offered", "已接受": "Accepted", "已预留": "Reserved",
    "已交付": "Delivered", "已冻结": "Frozen", "已结算": "Settled",
    "账本尚无成员。": "No Ledger Members Yet.", "没有待追偿余额。": "No Outstanding Recovery.",
    "追偿可用余额": "Recover Available Balance", "调整铸币上限": "Adjust Mint Cap",
    "保存上限": "Save Cap", "上限": "Cap", "已铸": "Minted",
    "预留": "Reserved", "可用": "Available",
    "暂无 Token 任务，请先添加任务。": "No Token Tasks Yet. Add a Task First.",
    "没有独立批准成员；请先在项目中添加第三位成员并同步。": "No Independent Approver Is Available. Add a Third Member to the Project and Sync.",
    "结算": "Settle", "验证铸币值": "Verified Mint Value",
    "独立批准成员": "Independent Approver", "确认结算": "Confirm Settlement",
    "暂无委托合约。": "No Commission Contracts Yet.",
    "还没有关系。创建合约或发生账本事件后会显示在这里。": "No Relationships Yet. They Will Appear After a Contract or Ledger Event.",
    "无任务": "No Task", "金库": "Treasury", "无目标": "No Destination",
    "事件详情": "Event Details", "无": "None", "当前筛选下没有事件。": "No Events Match This Filter.",
    "没有可迁移的旧项目。": "No Past Projects to Migrate.",
    "尚未启用 Token 账本": "Token Ledger Is Not Enabled",
    "请填写至少一个证据标识。": "Enter at Least One Evidence ID.",
    "委托成员与承接成员不能相同。": "The Principal and Contractor Must Be Different.",
    "来源和目标不能相同。": "The Source and Destination Must Be Different.",
    "此贡献尚未通过审核": "This Contribution Has Not Been Reviewed.",
    "请填写证据和独立批准成员。": "Enter Evidence and an Independent Approver.",
    "请选择铸币事件并填写原因或说明。": "Select a Mint Event and Enter a Reason or Note.",
    "操作已保存。": "Action Saved.", "任务铸币上限已更新。": "Task Mint Cap Updated.",
    "追偿已处理。": "Recovery Processed.", "账本已创建。": "Ledger Created.",
    "历史贡献已迁移。": "Past Contributions Migrated.",
    "项目成员与任务已同步。": "Project Members and Tasks Synced.",
    "已检查并补同步贡献。": "Contributions Checked and Reconciled.",
    "合约状态已更新。": "Contract Status Updated.", "合约已结算。": "Contract Settled.",
    "铸币已冻结。": "Mint Frozen.", "铸币已释放。": "Mint Released.",
    "任务铸币上限不足；请先提高上限，再补同步": "The Mint Cap Is Too Low. Increase It, Then Reconcile.",
    "证据标识已经用于铸币；请核对贡献与账本事件": "This Evidence ID Has Already Been Used for Minting. Check the Contribution and Ledger Event.",
    "持有人余额不足，无法冻结关联 Token": "The Holder Has Insufficient Balance to Freeze the Related Tokens.",
    "成员余额不足，无法完成 Token 处理": "The Member Has Insufficient Balance to Complete Token Processing.",
    "Token 账本读取失败；请检查数据库并重试": "Could Not Read the Token Ledger. Check the Database and Retry.",
    "Token 处理失败；请检查账本状态后补同步": "Token Processing Failed. Check the Ledger, Then Reconcile.",
    "Token 账本属于其他项目": "The Token Ledger Belongs to Another Project.",
    "此项目已有已审核贡献，请选择迁移历史贡献建立账本": "This Project Has Reviewed Contributions. Migrate Them to Create the Ledger.",
    "贡献 ID 与当前项目任务不匹配": "The Contribution ID Does Not Match a Task in This Project.",
    "只有已审核或已解决的贡献可以补铸": "Only Verified or Resolved Contributions Can Be Minted.",
    "事件 ID、接收成员、数量和证据标识必须与已审核贡献一致": "Event ID, Recipient, Amount, and Evidence ID Must Match the Reviewed Contribution.",
    "Token 账本不可用": "The Token Ledger Is Unavailable.",
    "任务铸币上限不足；请先在 Token 工作台提高上限": "The Mint Cap Is Too Low. Increase It in the Token Workspace.",
    "有效得分为 0，无法铸币": "The Effective Score Is Zero, So No Tokens Can Be Minted.",
    "委托合约已存在（此前已铸币或已结算）": "The Commission Contract Already Exists (Minted or Settled).",
    "直接铸币已存在（此前已铸币）": "The Direct Mint Already Exists.",
    "任务铸币上限不足；请在 Token 工作台提高上限后补同步": "The Mint Cap Is Too Low. Increase It in the Token Workspace, Then Reconcile.",
    "Token 账本写入失败；请稍后补同步": "Could Not Write to the Token Ledger. Reconcile Later.",
    "没有需要冻结的铸币记录": "No Mint Events Need Freezing.",
    "Token 账本未启用": "The Token Ledger Is Not Enabled."
  };

  const patterns = [
    [/^更新于 (.+)$/, (_, time) => `Updated at ${time}`],
    [/^当前 ([\d,.]+) 分$/, (_, score) => `Current: ${score} pts`],
    [/^([\d,.]+) 分$/, (_, score) => `${score} pts`],
    [/^原因：(.+)$/, (_, value) => `Reason: ${value}`],
    [/^结论：(.+)$/, (_, value) => `Resolution: ${value}`],
    [/^解决者：(.+)$/, (_, value) => `Resolved by: ${value}`],
    [/^金库 (.+)$/, (_, id) => `Treasury ${id}`],
    [/^金库 · (.+)$/, (_, id) => `Treasury · ${id}`],
    [/^任务 (.+) · 应收 (.+)$/, (_, id, amount) => `Task ${id} · Receivable ${amount}`],
    [/^尚待追偿 (.+)$/, (_, amount) => `Still Due: ${amount}`],
    [/^验收标准：(.*)$/, (_, value) => `Acceptance Criteria: ${value}`],
    [/^价格 (.+)，最高铸币 (.+)$/, (_, price, cap) => `Price ${price}; Maximum Mint ${cap}`],
    [/^实际铸币 (.+)；批准成员 (.+)；证据 (.+)$/, (_, minted, members, evidence) => `Minted ${minted}; Approvers ${members}; Evidence ${evidence}`],
    [/^推进到(.+)$/, (_, status) => `Advance to ${copy[status] || status}`],
    [/^([\d,]+) 个节点，([\d,]+) 条关系$/, (_, nodes, edges) => `${nodes} Nodes · ${edges} Relationships`],
    [/^持有人 (.+) · 标签 (.+)$/, (_, holder, tag) => `Holder ${holder} · Tag ${tag}`],
    [/^证据键：(.*)$/, (_, value) => `Evidence Key: ${value}`],
    [/^备注：(.*)$/, (_, value) => `Note: ${value}`],
    [/^预计迁移 (\d+) 条贡献；跳过 (\d+) 条。旧项目团队总分 (.+)。$/, (_, count, skipped, score) => `Expected: ${count} Contributions; ${skipped} Skipped. Previous Team Score: ${score}.`],
    [/^当前账本属于 (.+)；项目看板选中的是 (.+)。$/, (_, ledger, selected) => `This Ledger Belongs to ${ledger}; the Dashboard Has ${selected} Selected.`],
    [/^；跳过 (\d+) 条$/, (_, count) => `; ${count} Skipped`],
    [/^(.+)；跳过 (\d+) 条$/, (_, action, count) => `${translate(action)} ${count} Skipped.`],
    [/^旧贡献分 (.+)；待补铸 (\d+) 条$/, (_, score, count) => `Previous Score ${score}; ${count} Awaiting Mint`],
    [/^旧贡献分 (.+)$/, (_, score) => `Previous Score ${score}`],
    [/^([\d,.]+) 条暂不计分$/, (_, count) => `${count} Not Scored`],
    [/^Token 账本有 (\d+) 条已审核贡献待补铸、(\d+) 个成员或任务待同步。$/, (_, pending, missing) => `Token Ledger: ${pending} Reviewed Contributions Await Minting and ${missing} Members or Tasks Await Sync.`],
    [/^查看账本事件 #(\d+)$/, (_, sequence) => `View Ledger Event #${sequence}`],
    [/^Token：(.+) · $/, (_, status) => `Token: ${copy[status] || status} · `],
    [/^(铸币|委托合约) · #(\d+)$/, (_, kind, sequence) => `${copy[kind]} · #${sequence}`],
    [/^#(\d+) (铸币|转账|冻结|释放|退款|分配)(.*)$/, (_, sequence, kind, rest) => `#${sequence} ${copy[kind]}${rest}`],
    [/^(.+) · (铸币|转账|冻结|释放|退款|分配) · (.+)$/, (_, before, kind, after) => `${before} · ${copy[kind]} · ${after}`],
    [/^Token：(.+) ·$/, (_, status) => `Token: ${copy[status] || status} ·`],
    [/^Token 账本有 (\d+) 条已审核贡献待补铸、(\d+) 个成员或任务待同步。$/, (_, pending, missing) => `Token Ledger: ${pending} Reviewed Contributions Await Minting and ${missing} Members or Tasks Await Sync.`],
    [/^(无法读取迁移预览|成员读取失败|读取失败|操作失败|读取详情失败|预览失败)：(.+)$/, (_, kind, detail) => `${({ "无法读取迁移预览": "Could Not Load Migration Preview", "成员读取失败": "Could Not Load Members", "读取失败": "Could Not Load Data", "操作失败": "Action Failed", "读取详情失败": "Could Not Load Details", "预览失败": "Could Not Preview Score" })[kind]}: ${translate(detail)}`],
    [/^(.+)已保存，但刷新失败：(.+)$/, (_, action, detail) => `${translate(action)} Was Saved, but Refresh Failed: ${translate(detail)}`],
    [/^Token 处理未完成：(.+)。$/, (_, detail) => `Token Processing Is Incomplete: ${translate(detail)}.`],
    [/^已生成 ([\d,.]+) Token。$/, (_, amount) => `${amount} Tokens Created.`],
    [/^Token 已处理，仍有 (.+) 待追偿；请到 Token 工作台查看。$/, (_, amount) => `Token Processed; ${amount} Remains Due. Check the Token Workspace.`],
    [/^Token 已按最终分值 ([\d,.]+) 更新。$/, (_, score) => `Token Updated to the Final Score of ${score}.`],
    [/^提议 \/ 原最终分值 ([\d,.]+) → ([\d,.]+) 分；当前计入 ([\d,.]+) 分。(.+)$/, (_, oldScore, newScore, current, note) => `Proposed / Previous Final Score: ${oldScore} → ${newScore} pts; Currently Counted: ${current} pts. ${translate(note)}`],
    [/^(.+)：(.+)，数据已保存。团队总分 ([\d,.]+) 分。(.*)$/, (_, id, action, score, note) => `${id}: ${translate(action)} Saved. Team Score: ${score} pts. ${translate(note)}`],
    [/^操作已保存，但刷新失败：(.+)。请点击刷新数据。$/, (_, detail) => `Action Saved, but Refresh Failed: ${translate(detail)}. Select Refresh Data.`],
    [/^请求失败 \((\d+)\)$/, (_, status) => `Request Failed (${status})`],
    [/^输入：(.+)$/, (_, detail) => `Input: ${detail}`],
    [/^读取贡献失败：(.+)$/, (_, detail) => `Could Not Load Contribution: ${translate(detail)}`]
  ];
  // Always start a fresh page in English. A Chinese selection remains available
  // for the current page, but is intentionally not restored on the next entry.
  let language = "en";
  const textSources = new WeakMap();
  const attributeSources = new WeakMap();
  const titleSource = document.title;
  const attributes = ["placeholder", "aria-label", "title", "data-label"];
  const hasChinese = (value) => /[\u3400-\u9fff]/.test(value);
  function translate(value) {
    if (language !== "en" || !hasChinese(value)) return value;
    const match = /^(\s*)(.*?)(\s*)$/s.exec(value);
    const [, before, content, after] = match;
    if (Object.hasOwn(copy, content)) return before + copy[content] + after;
    for (const [pattern, replacement] of patterns) {
      if (pattern.test(content)) return before + content.replace(pattern, replacement) + after;
    }
    const keys = Object.keys(copy).filter((key) => key && content.includes(key)).sort((a, b) => b.length - a.length);
    const translated = keys.reduce((result, key) => result.split(key).join(copy[key]), content);
    return before + translated + after;
  }
  function ignored(node) {
    return node.parentElement?.closest('[translate="no"], [data-i18n-ignore], script, style');
  }
  function updateText(node) {
    if (ignored(node)) return;
    const current = node.nodeValue;
    let entry = textSources.get(node);
    if (!entry || current !== entry.rendered) entry = { source: current, rendered: current };
    const rendered = translate(entry.source);
    textSources.set(node, { source: entry.source, rendered });
    if (current !== rendered) node.nodeValue = rendered;
  }
  function updateAttribute(element, name) {
    if (element.closest('[translate="no"], [data-i18n-ignore]') || !element.hasAttribute(name)) return;
    let records = attributeSources.get(element);
    if (!records) { records = {}; attributeSources.set(element, records); }
    const current = element.getAttribute(name);
    let entry = records[name];
    if (!entry || current !== entry.rendered) entry = { source: current, rendered: current };
    const rendered = translate(entry.source);
    records[name] = { source: entry.source, rendered };
    if (current !== rendered) element.setAttribute(name, rendered);
  }
  function scan(root = document.body) {
    if (root.nodeType === Node.TEXT_NODE) { updateText(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) updateText(walker.currentNode);
    for (const element of [root, ...root.querySelectorAll("*")]) {
      for (const name of attributes) updateAttribute(element, name);
    }
  }
  function apply() {
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    document.title = translate(titleSource);
    const select = document.getElementById("language-select");
    if (select) select.value = language;
    scan();
  }
  function setLanguage(next) {
    language = next === "en" ? "en" : "zh";
    localStorage.setItem("contribution-language", language);
    apply();
    document.dispatchEvent(new CustomEvent("languagechange", { detail: { language } }));
  }
  document.getElementById("language-select")?.addEventListener("change", (event) => setLanguage(event.target.value));
  window.addEventListener("storage", (event) => {
    if (event.key !== "contribution-language" || !event.newValue) return;
    language = event.newValue === "en" ? "en" : "zh";
    apply();
    document.dispatchEvent(new CustomEvent("languagechange", { detail: { language } }));
  });
  new MutationObserver((changes) => {
    for (const change of changes) {
      if (change.type === "characterData") updateText(change.target);
      else if (change.type === "attributes") updateAttribute(change.target, change.attributeName);
      else for (const node of change.addedNodes) scan(node);
    }
  }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: attributes });
  apply();
  return {
    get language() { return language; },
    t: (value) => translate(value),
    register(entries) { Object.assign(copy, entries); apply(); },
    setLanguage,
    apply
  };
})();
