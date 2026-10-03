const english = {
  "跳转到主要内容": "Skip to main content", "正在加载项目…": "Loading project…",
  "例如 FinTech Demo…": "e.g. FinTech Demo…", "例如 fintech-demo…": "e.g. fintech-demo…", "例如 David…": "e.g. David…", "例如 david…": "e.g. david…",
  "项目看板": "Project Dashboard", "Token 工作台": "Token Workspace", "当前项目": "Current project", "切换项目": "Switch project", "设置": "Settings", "语言": "Language", "界面语言": "Interface language",
  "刷新数据": "Refresh", "页面导航": "Page navigation", "总览": "Overview", "录入": "Add records", "关系图": "Graph", "贡献明细": "Contributions", "贡献审核": "Contribution Review",
  "项目总览": "Project overview", "正在加载项目...": "Loading project...", "查看贡献得分、任务价值，以及成员之间的协作关系。": "Explore contribution scores, task values, and team relationships.", "正在读取数据": "Loading data",
  "项目摘要": "Project summary", "团队总分": "Team score", "已验证与已解决贡献": "Verified and resolved contributions", "项目成员": "Members", "参与贡献": "Contributors", "项目任务": "Tasks", "预设任务价值": "Preset task value", "贡献记录": "Contribution records", "等待数据": "Waiting for data",
  "成员贡献": "Member contributions", "选择成员，查看与他相关的贡献": "Select a member to see related contributions", "暂无成员。": "No members yet.", "任务价值": "Task values", "选择任务，筛选贡献明细": "Select a task to filter contributions", "暂无任务。": "No tasks yet.",
  "录入新贡献": "Add a contribution", "先建立项目和任务，再提交贡献；新记录会立即以“待验证”出现在明细和关系图。": "Create a project and task, then submit a contribution. New records appear as pending in the list and graph.",
  "1 · 创建项目": "1 · Create project", "项目名称": "Project name", "项目 ID": "Project ID", "创建并切换项目": "Create and switch", "2 · 添加成员": "2 · Add member", "成员姓名": "Member name", "成员 ID": "Member ID", "添加成员": "Add member",
  "3 · 添加任务": "3 · Add task", "任务名称": "Task name", "任务 ID": "Task ID", "预设价值": "Preset value", "任务说明": "Task description", "添加任务": "Add task",
  "4 · 提交贡献": "4 · Submit contribution", "贡献者": "Contributor", "关联任务": "Related task", "贡献类型": "Contribution type", "帮助的成员": "Helped member", "可选": "Optional", "完成度（0–1）": "Completion (0–1)", "申报支持价值": "Proposed support value", "贡献说明": "Description", "提交后得分为 0，待验证后由服务端按规则计算。": "The score stays at 0 until verification. The server calculates it.", "提交贡献": "Submit contribution",
  "例如 FinTech Demo": "e.g. FinTech Demo", "例如 fintech-demo": "e.g. fintech-demo", "例如 David": "e.g. David", "例如 david": "e.g. david", "例如 部署应用": "e.g. Deploy app", "例如 deployment": "e.g. deployment", "例如 帮助 Alice 排查部署问题": "e.g. Helped Alice debug deployment",
  "贡献关系图": "Contribution graph", "成员 → 贡献 → 任务；虚线指向受帮助成员。点击贡献查看详情。": "Member → contribution → task. Dashed lines point to helped members. Select a contribution for details.", "成员、贡献与任务关系图": "Member, contribution, and task graph", "贡献关系列表": "Contribution relationships", "当前筛选下没有贡献。": "No contributions match the current filters.",
  "分数和占比来自项目评分数据": "Scores and shares come from project scoring data", "贡献筛选与排序": "Contribution filters and sorting", "关联成员": "Related member", "全部成员": "All members", "任务": "Task", "全部任务": "All tasks", "类型": "Type", "全部类型": "All types", "状态": "Status", "全部状态": "All statuses", "排序": "Sort", "原始顺序": "Original order", "得分从高到低": "Highest score", "得分从低到高": "Lowest score", "按成员名称": "Member name", "清除筛选": "Clear filters", "贡献者与内容": "Contributor and description", "当前得分": "Current score", "没有符合当前筛选条件的贡献。可清除筛选查看全部记录。": "No contributions match these filters. Clear filters to see all records.",
  "贡献详情": "Contribution details", "关闭贡献详情": "Close contribution details", "数据来自项目服务": "Data from the project service",
  "待验证": "Pending", "已验证": "Verified", "争议中": "Disputed", "已解决": "Resolved", "核心": "Core", "支持": "Support", "审查": "Review", "协调": "Coordination",
  "分": "pts", "价值": "value", "条贡献": "contributions", "条记录": "records", "条暂不计分": "not scored", "暂不计分": "Not scored", "帮助": "Helped", "成员": "Member", "贡献": "Contribution", "选择贡献者": "Select contributor", "选择任务": "Select task", "无": "None", "质量系数": "Quality factor", "任务预设价值": "Preset task value", "完成度": "Completion", "类型 / 状态": "Type / status",
  "先创建一个项目": "Create a project first", "尚无项目": "No projects yet", "数据读取失败": "Data load failed", "保存成功，页面已更新。": "Saved. The page is up to date.", "受帮助成员不能与贡献者相同。": "The helped member must differ from the contributor.", "正在读取贡献详情...": "Loading contribution details...", "0 条贡献": "0 contributions", "0 条记录": "0 records", "筛选成员": "Filter member", "筛选任务": "Filter task", "查看贡献": "View contribution", "查看": "View", "的贡献": "contribution", "帮助成员": "Helped member", "证据": "Evidence", "处理说明": "Resolution note"
};
I18n.register(english);
let language = localStorage.getItem("contribution-language") === "en" ? "en" : "zh";
document.addEventListener("languagechange", (event) => {
  if (language === event.detail.language) return;
  language = event.detail.language;
  if (currentData) render(currentData);
});
const t = (value) => language === "en" ? (english[value] ?? value) : value;
const statusName = (kind) => t({ PENDING: "待验证", VERIFIED: "已验证", DISPUTED: "争议中", RESOLVED: "已解决" }[kind] ?? kind);
const typeName = (kind) => t({ CORE: "核心", SUPPORT: "支持", REVIEW: "审查", COORDINATION: "协调" }[kind] ?? kind);
const categories = ["CORE", "SUPPORT", "REVIEW", "COORDINATION"];
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value ?? 0);
const tokenAmount = (value) => String(value ?? "0");
let currentData = null;
let selectedId = null;
let projectId = localStorage.getItem("contribution-project") || "fintech";
function setLanguage(next) {
  language = next === "en" ? "en" : "zh";
  I18n.setLanguage(language);
  if (currentData) render(currentData);
  else if (!projectId) {
    $("project-name").textContent = t("先创建一个项目");
    $("updated").textContent = t("尚无项目");
  }
  if (!$('form-message').hidden && $('form-message').dataset.source) $('form-message').textContent = t($('form-message').dataset.source);
}

function namesById(items) {
  return Object.fromEntries(items.map((item) => [item.id, item.name]));
}

function filterValue(name) {
  return $(`${name}-filter`).value;
}

function filteredContributions() {
  if (!currentData) return [];
  const members = namesById(currentData.members);
  const rows = currentData.contributions.filter((item) =>
    (filterValue("member") === "ALL" || item.contributorId === filterValue("member") || item.helpedMemberId === filterValue("member")) &&
    (filterValue("task") === "ALL" || item.taskId === filterValue("task")) &&
    (filterValue("type") === "ALL" || item.type === filterValue("type")) &&
    (filterValue("status") === "ALL" || item.status === filterValue("status"))
  );
  const sort = $("sort-order").value;
  if (sort === "score-desc") rows.sort((a, b) => b.score - a.score);
  if (sort === "score-asc") rows.sort((a, b) => a.score - b.score);
  if (sort === "member") rows.sort((a, b) => (members[a.contributorId] ?? a.contributorId).localeCompare(members[b.contributorId] ?? b.contributorId, "zh-CN"));
  return rows;
}

function fillSelect(id, items, emptyLabel, emptyValue = "ALL") {
  const select = $(id);
  const previous = select.value;
  select.replaceChildren(new Option(emptyLabel, emptyValue), ...items.map((item) => new Option(item.name, item.id)));
  select.value = items.some((item) => item.id === previous) ? previous : emptyValue;
}

function fillRequiredSelect(id, items, emptyLabel) {
  const select = $(id);
  const previous = select.value;
  select.replaceChildren(new Option(emptyLabel, ""), ...items.map((item) => new Option(item.name, item.id)));
  select.value = items.some((item) => item.id === previous) ? previous : "";
}

function renderMembers(data) {
  $("members-empty").hidden = data.members.length > 0;
  const recognition = data.tokenRecognition;
  $("members").innerHTML = data.members.map((member) => `
    <button class="member ${filterValue("member") === member.id ? "is-active" : ""}" type="button" data-member-id="${safe(member.id)}" aria-pressed="${filterValue("member") === member.id}">
      <span class="member-top"><span class="identity"><span class="avatar" aria-hidden="true">${safe(member.name.slice(0, 1))}</span><span class="member-name">${safe(member.name)}</span></span><span class="share">${recognition ? "Token 余额" : `${Number(member.contributionShare).toFixed(2)}%`}</span></span>
      <span class="member-score">${recognition ? safe(tokenAmount(recognition.balancesExact?.[member.id])) : points(member.totalScore)} <small>${recognition ? "Token" : t("分")}</small></span>
      <span class="breakdown">${recognition ? `<span>旧贡献分 ${points(member.totalScore)}</span>` : categories.map((kind) => `<span>${typeName(kind)} <b>${points(member.breakdown[kind])}</b></span>`).join("")}</span>
    </button>`).join("");
}

function renderTasks(data) {
  $("tasks-empty").hidden = data.tasks.length > 0;
  $("tasks").innerHTML = data.tasks.map((task) => `
    <button class="task ${filterValue("task") === task.id ? "is-active" : ""}" type="button" data-task-id="${safe(task.id)}" aria-pressed="${filterValue("task") === task.id}">
      <span><span class="task-name">${safe(task.name)}</span><span class="task-id">${safe(task.id)}${task.description ? ` · ${safe(task.description)}` : ""}</span></span>
      <span class="task-value">${points(task.taskValue)} <small>${t("价值")}</small></span>
    </button>`).join("");
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function svgText(parent, x, y, content, className) {
  const label = svgElement("text", { x, y, class: className });
  label.textContent = content;
  parent.append(label);
}

function renderGraph(data, rows) {
  const members = namesById(data.members);
  const tasks = namesById(data.tasks);
  const svg = $("graph");
  svg.replaceChildren();
  $("relationship-count").textContent = `${rows.length} ${t("条贡献")}`;
  $("graph-empty").hidden = rows.length > 0;
  $("graph-content").hidden = rows.length === 0;
  if (!rows.length) return;

  const usedMembers = data.members.filter((member) => rows.some((row) => row.contributorId === member.id || row.helpedMemberId === member.id));
  const usedTasks = data.tasks.filter((task) => rows.some((row) => row.taskId === task.id));
  const height = Math.max(340, rows.length * 76 + 48, usedMembers.length * 82 + 48, usedTasks.length * 82 + 48);
  svg.setAttribute("viewBox", `0 0 820 ${height}`);
  svg.style.height = `${height}px`;
  svg.setAttribute("aria-label", language === "en" ? `Showing ${rows.length} member, contribution, and task relationships. Use Tab to select a contribution.` : `当前显示 ${rows.length} 条成员、贡献与任务关系。可用 Tab 键选择贡献。`);
  const memberY = Object.fromEntries(usedMembers.map((item, index) => [item.id, (index + 1) * height / (usedMembers.length + 1)]));
  const taskY = Object.fromEntries(usedTasks.map((item, index) => [item.id, (index + 1) * height / (usedTasks.length + 1)]));
  const defs = svgElement("defs");
  const arrow = svgElement("marker", { id: "graph-arrow", markerWidth: 8, markerHeight: 8, refX: 7, refY: 3.5, orient: "auto" });
  arrow.append(svgElement("path", { d: "M0 0 L7 3.5 L0 7 Z" }));
  defs.append(arrow);
  svg.append(defs);
  svgText(svg, 86, 27, t("成员"), "graph-column");
  svgText(svg, 392, 27, t("贡献"), "graph-column");
  svgText(svg, 710, 27, t("任务"), "graph-column");
  rows.forEach((row, index) => {
    const y = 56 + index * 76;
    const link = (d, extra = "") => svg.append(svgElement("path", { d, class: `graph-link ${extra}` }));
    link(`M 173 ${memberY[row.contributorId]} C 244 ${memberY[row.contributorId]}, 251 ${y}, 316 ${y}`);
    link(`M 492 ${y} C 568 ${y}, 562 ${taskY[row.taskId]}, 635 ${taskY[row.taskId]}`);
    if (row.helpedMemberId) link(`M 316 ${y + 9} C 247 ${y + 49}, 228 ${memberY[row.helpedMemberId] + 22}, 173 ${memberY[row.helpedMemberId] + 22}`, "help-link");
    const group = svgElement("g", { class: `graph-contribution ${selectedId === row.id ? "is-selected" : ""} ${row.status === "PENDING" || row.status === "DISPUTED" ? "is-unscored" : ""}`, role: "button", tabindex: "0", "data-contribution-id": row.id, "aria-label": `${t("查看贡献")} ${row.description}` });
    group.append(svgElement("rect", { x: 316, y: y - 22, width: 176, height: 44, rx: 11 }));
    svgText(group, 328, y - 3, `${typeName(row.type)} · ${row.id}`.slice(0, 22), "graph-label");
    svgText(group, 328, y + 13, `${statusName(row.status)} · ${row.description}`.slice(0, 17), "graph-subtitle");
    svg.append(group);
  });
  usedMembers.forEach((member) => {
    const y = memberY[member.id];
    const group = svgElement("g", { class: `graph-entity ${filterValue("member") === member.id ? "is-active" : ""}`, role: "button", tabindex: "0", "data-member-id": member.id, "aria-label": `${t("筛选成员")} ${member.name}` });
    group.append(svgElement("rect", { x: 30, y: y - 23, width: 143, height: 46, rx: 11 }));
    svgText(group, 42, y + 5, member.name.slice(0, 17), "graph-label");
    svg.append(group);
  });
  usedTasks.forEach((task) => {
    const y = taskY[task.id];
    const group = svgElement("g", { class: `graph-entity ${filterValue("task") === task.id ? "is-active" : ""}`, role: "button", tabindex: "0", "data-task-id": task.id, "aria-label": `${t("筛选任务")} ${task.name}` });
    group.append(svgElement("rect", { x: 635, y: y - 23, width: 155, height: 46, rx: 11 }));
    svgText(group, 647, y + 5, task.name.slice(0, 17), "graph-label");
    svg.append(group);
  });
  $("relationships").innerHTML = rows.map((row) => `
    <button class="relation ${selectedId === row.id ? "is-selected" : ""}" type="button" data-contribution-id="${safe(row.id)}" aria-pressed="${selectedId === row.id}">
      <span class="relation-names"><strong>${safe(members[row.contributorId] ?? row.contributorId)}</strong><span aria-hidden="true">→</span><strong>${safe(typeName(row.type))}</strong><span aria-hidden="true">→</span><strong>${safe(tasks[row.taskId] ?? row.taskId)}</strong></span>
      <span class="relation-meta">${safe(row.description)}${row.helpedMemberId ? ` · ${t("帮助")} ${safe(members[row.helpedMemberId] ?? row.helpedMemberId)}` : ""}</span>
      <span class="relation-foot"><span class="status ${row.status.toLowerCase()}">${safe(statusName(row.status))}</span><span>${row.status === "PENDING" || row.status === "DISPUTED" ? t("暂不计分") : `${points(row.score)} ${t("分")}`}</span></span>
    </button>`).join("");
}

function renderContributions(data, rows) {
  const members = namesById(data.members);
  const tasks = namesById(data.tasks);
  $("result-count").textContent = `${rows.length} / ${data.contributions.length} ${t("条记录")}`;
  $("contributions-empty").hidden = rows.length > 0;
  $("contributions").innerHTML = rows.map((item) => `
    <tr class="${selectedId === item.id ? "is-selected" : ""}" data-row-id="${safe(item.id)}">
      <td><button class="row-select" type="button" data-contribution-id="${safe(item.id)}" aria-label="${t("查看")} ${safe(members[item.contributorId] ?? item.contributorId)} ${t("的贡献")} ${safe(item.description)}"><strong>${safe(members[item.contributorId] ?? item.contributorId)}</strong><span>${safe(item.description)}</span>${item.helpedMemberId ? `<small>${t("帮助")} ${safe(members[item.helpedMemberId] ?? item.helpedMemberId)}</small>` : ""}</button></td>
      <td data-label="${t("任务")}">${safe(tasks[item.taskId] ?? item.taskId)}</td><td data-label="${t("类型")}"><span class="type">${safe(typeName(item.type))}</span></td>
      <td data-label="${t("状态")}"><span class="status ${item.status.toLowerCase()}">${safe(statusName(item.status))}</span></td>
      <td data-label="Token 事件">${item.tokenEventId ? `<a href="/token.html?event=${encodeURIComponent(item.tokenEventId)}#activity">${item.tokenEventId.includes(":commission:") ? "委托合约 · " : "铸币 · "}#${item.tokenEventSequence}</a>${item.tokenFrozen ? '<small class="token-state">当前冻结</small>' : ""}` : item.tokenPending ? '<span class="token-state">待补铸</span>' : '<span class="token-state">—</span>'}</td>
      <td data-label="旧贡献分" class="number">${item.status === "PENDING" || item.status === "DISPUTED" ? `<span class="no-score">${t("暂不计分")}</span>` : `<span class="score">${points(item.score)}</span>`}</td>
    </tr>`).join("");
}

async function loadDetail(id) {
  $("detail").hidden = false;
  $("detail-content").textContent = t("正在读取贡献详情...");
  try {
    const data = await request(`/api/contributions/${encodeURIComponent(id)}`);
    if (selectedId !== id) return;
    const record = currentData.contributions.find((item) => item.id === id);
    const contributor = currentData.members.find((item) => item.id === data.contribution.contributor_id);
    const helped = currentData.members.find((item) => item.id === data.contribution.helped_member_id);
    const item = data.contribution;
    $("detail-content").innerHTML = `
      <p class="detail-description">${safe(item.description)}</p>
      <div class="detail-grid"><div><span>${t("贡献者")}</span><strong>${safe(contributor?.name ?? item.contributor_id)}</strong></div><div><span>${t("任务")}</span><strong>${safe(data.task.name)}</strong></div><div><span>${t("类型 / 状态")}</span><strong>${safe(typeName(item.type))} / ${safe(statusName(item.status))}</strong></div><div><span>${t("当前得分")}</span><strong>${item.status === "PENDING" || item.status === "DISPUTED" ? t("暂不计分") : `${points(record?.score)} ${t("分")}`}</strong></div><div><span>${t("任务预设价值")}</span><strong>${safe(data.task.taskValue)}</strong></div><div><span>${t("完成度")}</span><strong>${safe(item.completion)}</strong></div><div><span>${t("质量系数")}</span><strong>${safe(item.quality)}</strong></div><div><span>${t("申报支持价值")}</span><strong>${safe(item.support_value)}</strong></div></div>
      ${helped ? `<p class="detail-extra">${t("帮助成员")}${language === "en" ? ": " : "："}${safe(helped.name)}</p>` : ""}
      ${data.evidence.length ? `<p class="detail-extra">${t("证据")}${language === "en" ? ": " : "："}${data.evidence.map((e) => safe(e.reference)).join(language === "en" ? "; " : "；")}</p>` : ""}
      ${item.resolution_note ? `<p class="detail-extra">${t("处理说明")}${language === "en" ? ": " : "："}${safe(item.resolution_note)}</p>` : ""}`;
    if (record?.tokenEventId) {
      const eventUrl = `/token.html?event=${encodeURIComponent(record.tokenEventId)}#activity`;
      $("detail-content").insertAdjacentHTML("beforeend", `<p class="detail-extra">Token：${record.tokenFrozen ? "当前冻结" : "已入账"} · <a href="${safe(eventUrl)}">查看账本事件 #${record.tokenEventSequence}</a></p>`);
    } else if (record?.tokenPending) {
      $("detail-content").insertAdjacentHTML("beforeend", '<p class="detail-extra">Token 待补铸。请到 <a href="/token.html#balances">Token 工作台</a> 补同步。</p>');
    }
  } catch (error) {
    if (selectedId === id) $("detail-content").textContent = language === "en" ? `Could not load details: ${error.message}` : `无法读取详情：${error.message}`;
  }
}

function renderInteractive() {
  if (!currentData) return;
  const rows = filteredContributions();
  if (selectedId && !rows.some((item) => item.id === selectedId)) {
    selectedId = null;
    $("detail").hidden = true;
  }
  renderMembers(currentData);
  renderTasks(currentData);
  renderGraph(currentData, rows);
  renderContributions(currentData, rows);
  $("clear-filters").disabled = ["member", "task", "type", "status"].every((name) => filterValue(name) === "ALL") && $("sort-order").value === "original";
}

function render(data) {
  currentData = data;
  fillSelect("member-filter", data.members, t("全部成员"));
  fillSelect("task-filter", data.tasks, t("全部任务"));
  fillRequiredSelect("contributor-input", data.members, t("选择贡献者"));
  fillRequiredSelect("task-input", data.tasks, t("选择任务"));
  fillSelect("helped-input", data.members, t("无"), "");
  $("project-name").textContent = data.project.name;
  $("team-score").textContent = data.tokenRecognition
    ? tokenAmount(data.tokenRecognition.totalSupplyExact)
    : points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("team-score").previousElementSibling.textContent = data.tokenRecognition ? "已认定 Token" : t("团队总分");
  $("team-score").nextElementSibling.textContent = data.tokenRecognition
    ? `旧贡献分 ${points(data.members.reduce((sum, member) => sum + member.totalScore, 0))}；待补铸 ${data.tokenRecognition.pendingContributions.length} 条`
    : t("已验证与已解决贡献");
  const health = $("token-health");
  const pending = data.tokenRecognition?.pendingContributions ?? [];
  const missing = (data.tokenRecognition?.missingMembers?.length ?? 0) +
    (data.tokenRecognition?.missingTasks?.length ?? 0);
  health.hidden = !pending.length && !missing;
  if (!health.hidden) health.innerHTML = `Token 账本有 ${pending.length} 条已审核贡献待补铸、${missing} 个成员或任务待同步。<a href="/token.html#balances">前往 Token 工作台处理</a>`;
  $("member-count").textContent = data.members.length;
  $("task-count").textContent = data.tasks.length;
  $("contribution-count").textContent = data.contributions.length;
  $("pending-count").textContent = `${data.contributions.filter((item) => item.status === "PENDING" || item.status === "DISPUTED").length} ${t("条暂不计分")}`;
  renderInteractive();
  if (selectedId) loadDetail(selectedId);
  $("updated").textContent = `${language === "en" ? "Updated at" : "更新于"} ${new Date().toLocaleTimeString(language === "en" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

async function request(url, options) {
  let key = sessionStorage.getItem("tokenAdminKey") || "";
  const send = () => fetch(url, { cache: "no-store", ...options,
    headers: { ...options?.headers, ...(key ? { "X-Token-Admin-Key": key } : {}) } });
  let response = await send();
  if (response.status === 403 && options?.method === "POST") {
    sessionStorage.removeItem("tokenAdminKey");
    key = prompt(I18n.t("请输入账本管理员密钥")) || "";
    if (key) { sessionStorage.setItem("tokenAdminKey", key); response = await send(); }
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail ?? data.error;
    throw new Error(typeof detail === "string" ? detail : language === "en" ? `Request failed (${response.status})` : `请求失败 (${response.status})`);
  }
  return data;
}

async function refresh() {
  $("refresh").disabled = true;
  $("error").hidden = true;
  try {
    const projects = await request("/api/projects");
    if (!projects.some((item) => item.id === projectId)) projectId = projects[0]?.id ?? "";
    $("project-select").replaceChildren(...projects.map((item) => new Option(item.name, item.id)));
    $("project-select").value = projectId;
    if (projectId) render(await request(`/api/projects/${encodeURIComponent(projectId)}/dashboard`));
    else {
      currentData = null;
      $("project-name").textContent = t("先创建一个项目");
      $("updated").textContent = t("尚无项目");
    }
    for (const id of ["member-form", "task-form", "contribution-form"]) {
      $(id).querySelector('button[type="submit"]').disabled = !projectId;
    }
  } catch (error) {
    $("error").textContent = language === "en" ? `Could not load project data: ${error.message}` : `无法读取项目数据：${error.message}`;
    $("error").hidden = false;
    $("updated").textContent = t("数据读取失败");
  } finally {
    $("refresh").disabled = false;
  }
}

function focusContribution(id, scroll = true) {
  selectedId = id;
  renderInteractive();
  loadDetail(id);
  if (scroll) {
    $("detail").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    $("close-detail").focus({ preventScroll: true });
  }
}

function setFilter(name, id) {
  const select = $(`${name}-filter`);
  select.value = select.value === id ? "ALL" : id;
  renderInteractive();
  $("contribution-panel").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

function updateContributionFields() {
  const core = $("type-input").value === "CORE";
  $("support-field").hidden = core;
  $("support-field").querySelector("input").disabled = core;
  $("completion-field").hidden = !core;
  $("completion-field").querySelector("input").disabled = !core;
}

async function submitForm(form, path, payload, success) {
  const button = form.querySelector('button[type="submit"]');
  const message = $("form-message");
  button.disabled = true;
  message.hidden = true;
  try {
    await request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (success) await success();
    message.dataset.source = "保存成功，页面已更新。";
    message.textContent = t(message.dataset.source);
    message.className = "form-message";
  } catch (error) {
    message.dataset.source = "";
    message.textContent = language === "en" ? `Could not save: ${error.message}` : `保存失败：${error.message}`;
    message.className = "form-message is-error";
  } finally {
    message.hidden = false;
    button.disabled = false;
  }
}

$("refresh").addEventListener("click", refresh);
$("language-select").addEventListener("change", (event) => setLanguage(event.target.value));
$("project-select").addEventListener("change", () => {
  projectId = $("project-select").value;
  localStorage.setItem("contribution-project", projectId);
  selectedId = null;
  $("detail").hidden = true;
  for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).value = "ALL";
  refresh();
});
for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).addEventListener("change", renderInteractive);
$("sort-order").addEventListener("change", renderInteractive);
$("clear-filters").addEventListener("click", () => {
  for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).value = "ALL";
  $("sort-order").value = "original";
  renderInteractive();
});
$("close-detail").addEventListener("click", () => { selectedId = null; $("detail").hidden = true; renderInteractive(); });
$("type-input").addEventListener("change", updateContributionFields);
$("contributor-input").addEventListener("change", () => {
  const helped = $("helped-input");
  if (helped.value === $("contributor-input").value) helped.value = "";
});
document.addEventListener("click", (event) => {
  const member = event.target.closest("[data-member-id]");
  const task = event.target.closest("[data-task-id]");
  const contribution = event.target.closest("[data-contribution-id]");
  if (member) setFilter("member", member.dataset.memberId);
  else if (task) setFilter("task", task.dataset.taskId);
  else if (contribution) focusContribution(contribution.dataset.contributionId);
});
$("graph").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const target = event.target.closest("[data-member-id], [data-task-id], [data-contribution-id]");
  if (!target) return;
  event.preventDefault();
  target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
});
$("project-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  submitForm(form, "/api/projects", payload, async () => {
    projectId = payload.id;
    localStorage.setItem("contribution-project", projectId);
    selectedId = null;
    await refresh();
    form.reset();
  });
});
$("member-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  submitForm(form, `/api/projects/${encodeURIComponent(projectId)}/members`, Object.fromEntries(new FormData(form)), async () => { await refresh(); form.reset(); });
});
$("task-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  submitForm(form, `/api/projects/${encodeURIComponent(projectId)}/tasks`, Object.fromEntries(new FormData(form)), async () => { await refresh(); form.reset(); });
});
$("contribution-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  if (payload.contributor_id === payload.helped_member_id) {
    $("form-message").dataset.source = "受帮助成员不能与贡献者相同。";
    $("form-message").textContent = t($("form-message").dataset.source);
    $("form-message").className = "form-message is-error";
    $("form-message").hidden = false;
    return;
  }
  payload.id = `c-${crypto.randomUUID()}`;
  payload.helped_member_id ||= null;
  payload.completion ||= "1";
  payload.support_value ||= "0";
  submitForm(form, `/api/projects/${encodeURIComponent(projectId)}/contributions`, payload, async () => {
    await refresh();
    if (!filteredContributions().some((item) => item.id === payload.id)) {
      for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).value = "ALL";
    }
    focusContribution(payload.id);
    form.querySelector('textarea[name="description"]').value = "";
  });
});
updateContributionFields();
setLanguage(language);
// B publishes a change after a successful write; other dashboard tabs reload the shared data.
window.addEventListener("storage", (event) => {
  if (event.key === "contribution-project") {
    projectId = event.newValue || "fintech";
    refresh();
  }
  if (event.key === "contribution-graph-update") refresh();
});
window.addEventListener("focus", refresh);
refresh();
