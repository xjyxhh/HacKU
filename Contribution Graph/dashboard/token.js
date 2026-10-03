const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const number = (value) => typeof value === "string"
  ? value : new Intl.NumberFormat(I18n.language === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: 9 }).format(Number(value) || 0);
const kindName = { MINT: "铸币", TRANSFER: "转账", FREEZE: "冻结", RELEASE: "释放", REFUND: "退款", SPLIT: "分配" };
const statusName = { DRAFT: "草稿", OFFERED: "已发出", ACCEPTED: "已接受", CREDIT_RESERVED: "已预留", DELIVERED: "已交付", VERIFIED: "已验证", DISPUTED: "争议中", FROZEN: "已冻结", SETTLED: "已结算" };
const nextStatus = { DRAFT: "OFFERED", OFFERED: "ACCEPTED", ACCEPTED: "CREDIT_RESERVED", CREDIT_RESERVED: "DELIVERED", DELIVERED: "VERIFIED", DISPUTED: "FROZEN", FROZEN: "DELIVERED" };
const graphViews = {
  value: new Set(["CONTRIBUTES_TO", "CREATED_VALUE", "MINTED"]),
  flow: new Set(["MINTED", "PAID", "SPLIT", "REFUNDED"]),
  collaboration: new Set(["COMMISSIONED", "EXECUTED", "CONTRIBUTES_TO", "PAID", "SPLIT"]),
  trust: new Set(["APPROVED", "DISPUTED", "FROZEN", "RELEASED"]),
};
const state = { ledger: null, graph: null, contracts: [], tasks: [], budgets: {}, debts: [], projects: [], role: null, memberId: null, busy: false };
let focusedEventId = new URLSearchParams(location.search).get("event");

async function request(path, body) {
  let key = sessionStorage.getItem("tokenAdminKey") || "";
  const send = () => fetch(path, {
    cache: "no-store",
    headers: {
      ...(localStorage.getItem("contribution-project") ? { "X-Project-ID": localStorage.getItem("contribution-project") } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(key ? { "X-Token-Admin-Key": key } : {}),
    },
    ...(body === undefined ? {} : { method: "POST", body: JSON.stringify(body) }),
  });
  let response = await send();
  let payload = await response.clone().json();
  if (response.status === 403 && payload.detail === "invalid token admin key") {
    sessionStorage.removeItem("tokenAdminKey");
    key = prompt(I18n.t("请输入服务启动时配置的 TOKEN_ADMIN_KEY")) || "";
    if (key) {
      sessionStorage.setItem("tokenAdminKey", key);
      response = await send();
      payload = await response.clone().json();
      if (response.status === 403) sessionStorage.removeItem("tokenAdminKey");
    }
    function applyRoleVisibility() {
      for (const element of document.querySelectorAll("[data-roles]")) {
        element.hidden = !element.dataset.roles.split(",").includes(state.role);
      }
    }
  }
  const data = payload;
  if (!response.ok) {
    const detail = data.detail ?? data.error;
    throw new Error(Array.isArray(detail) ? detail.map((item) => `${item.loc?.slice(1).join(".") || "输入"}：${item.msg}`).join("；") : detail || `请求失败 (${response.status})`);
  }
  return data;
}
function message(text, error = false) {
  $(error ? "error" : "notice").textContent = text;
  $(error ? "error" : "notice").hidden = false;
}
function clearMessages() { $("error").hidden = true; $("notice").hidden = true; }
function setBusy(value) {
  state.busy = value;
  for (const button of document.querySelectorAll("button")) button.disabled = value;
  document.querySelector("main").setAttribute("aria-busy", String(value));
  if (!value) {
    $("migrate").disabled = !$("legacy-project").value;
    if (state.ledger) renderFreezeOptions();
  }
}
const projectName = (id) => state.projects.find((project) => project.id === id)?.name || id;
const nodeName = (address) => state.graph?.nodes.find((node) => node.address.join("/") === address.join("/"))?.label || address.at(-1);
function renderGraph() {
  const svg = $("token-graph");
  const graph = state.graph;
  const edges = graph.edges.filter((edge) => graphViews[$("graph-view").value]?.has(edge.kind));
  const kinds = ["PROJECT", "TREASURY", "MEMBER", "COMMISSION_CONTRACT", "TASK"];
  const columns = kinds.map((kind) => graph.nodes.filter((node) => node.kind === kind));
  const height = Math.max(220, ...columns.map((nodes) => nodes.length * 62 + 38));
  svg.setAttribute("viewBox", `0 0 980 ${height}`);
  svg.replaceChildren();
  const namespace = "http://www.w3.org/2000/svg";
  const create = (tag, attrs, value) => {
    const element = document.createElementNS(namespace, tag);
    for (const [key, item] of Object.entries(attrs)) element.setAttribute(key, String(item));
    if (value !== undefined) element.textContent = value;
    return element;
  };
  const positions = new Map();
  columns.forEach((nodes, column) => nodes.forEach((node, row) => {
    positions.set(node.address.join("/"), { x: 12 + column * 196, y: 20 + row * 62 });
  }));
  for (const edge of edges) {
    const source = positions.get(edge.source.join("/"));
    const destination = positions.get(edge.destination.join("/"));
    if (!source || !destination) continue;
    svg.append(create("line", { x1: source.x + 164, y1: source.y + 20, x2: destination.x, y2: destination.y + 20, class: "graph-line" }));
  }
  for (const node of graph.nodes) {
    const position = positions.get(node.address.join("/"));
    if (!position) continue;
    const group = create("g", { class: "graph-node" });
    group.append(create("rect", { x: position.x, y: position.y, width: 164, height: 42, rx: 8 }));
    group.append(create("text", { x: position.x + 10, y: position.y + 14, class: "graph-node-kind" }, node.kind));
    group.append(create("text", { x: position.x + 10, y: position.y + 32, class: "graph-node-label" }, node.label.length > 19 ? node.label.slice(0, 18) + "…" : node.label));
    group.append(create("title", {}, node.label));
    svg.append(group);
  }
}
function selectOptions(selector, entries) {
  for (const select of document.querySelectorAll(selector)) {
    const previous = select.value;
    select.replaceChildren(...entries.map(([value, label]) => new Option(label, value)));
    if (entries.some(([value]) => value === previous)) select.value = previous;
  }
}
function tokenTasks() { return state.tasks; }
function listEmpty(id, count, messageText) { $(id).hidden = count > 0; if (!count) $(id).innerHTML = `<p class="empty">${safe(messageText)}</p>`; }

function render() {
  const { ledger, graph, contracts, budgets } = state;
  applyRoleVisibility();
  $("workspace").hidden = false;
  $("setup").hidden = true;
  $("project-name").textContent = `${projectName(ledger.projectId)} · ${ledger.projectId}`;
  $("total-supply").textContent = number(ledger.totalSupplyExact ?? ledger.totalSupply);
  $("member-count").textContent = ledger.memberIds.length;
  $("task-count").textContent = tokenTasks().length;
  $("event-count").textContent = ledger.events.length;
  $("treasury").textContent = `金库 ${ledger.treasuryId}`;
  $("balance-list").innerHTML = ledger.memberIds.map((id) => {
    const available = Number(ledger.balancesExact?.[id] ?? ledger.balances[id]) || 0;
    const locked = (ledger.events || []).filter((event) => ["MINT", "TRANSFER", "SPLIT"].includes(event.kind)
      && event.destinationId === id && event.frozen).reduce((total, event) => total + Number(event.amountExact ?? event.amount), 0);
    const memberEvents = ledger.events.filter((event) => event.sourceId === id || event.destinationId === id);
    const lines = memberEvents.map((event) => {
      const amount = Number(event.amountExact ?? event.amount);
      const delta = event.kind === "FREEZE" ? (event.sourceId === id ? -amount : 0)
        : event.kind === "RELEASE" ? (event.sourceId === id ? amount : 0)
          : (event.destinationId === id ? amount : 0) - (event.sourceId === id ? amount : 0);
      if (!delta) return "";
      const sign = delta > 0 ? "+" : "−";
      return `<li><a href="#activity" data-focus-event="${safe(event.id)}">#${event.sequence} ${safe(kindName[event.kind] || event.kind)}</a> ${sign}${number(Math.abs(delta))} · ${safe(event.note || event.taskId)}</li>`;
    }).filter(Boolean);
    return `<details class="balance-row"><summary><span>${safe(id)}</span><strong>${number(available + locked)} Token</strong></summary><p>可用 ${number(available)} · 冻结 ${number(locked)} · 待铸 ${number(ledger.pendingMintsExact?.[id] || 0)}</p>${lines.length ? `<ul>${lines.join("")}</ul>` : "<p>暂无余额变动。</p>"}</details>`;
  }).join("");
  applyRoleVisibility();
  listEmpty("balance-list", ledger.memberIds.length, "账本尚无成员。");
  const openDebts = state.debts.filter((debt) => /[1-9]/.test(debt.remainingExact));
  $("debt-list").innerHTML = openDebts
    .map((debt) => `<article class="token-row"><div><strong>${safe(debt.debtorId)} · ${safe(debt.id)}</strong><small>任务 ${safe(debt.taskId)} · 应收 ${safe(debt.amountExact)}</small><p>尚待追偿 ${safe(debt.remainingExact)}</p></div><button type="button" data-collect="${safe(debt.id)}">追偿可用余额</button></article>`).join("");
  listEmpty("debt-list", openDebts.length, "没有待追偿余额。");
  const taskEntries = tokenTasks().map((task) => [task.id, task.name]);
  $("task-list").innerHTML = taskEntries.map(([id, name]) => {
    const budget = budgets[id];
    const task = state.tasks.find((item) => item.id === id);
    return `<article class="token-row"><div><strong>${safe(name)}</strong><small>${safe(id)} · ${safe(task.valueType)}</small><p>验收标准：${safe(task.acceptanceCriteria)}</p><form class="cap-form" data-id="${safe(id)}" data-roles="OWNER"><label>调整铸币上限<input name="mint_cap" type="number" min="0" step="any" value="${safe(task.mintCap)}" required></label><button type="submit">保存上限</button></form></div><dl class="budget-values"><div><dt>上限</dt><dd>${number(budget.mintCap)}</dd></div><div><dt>已铸</dt><dd>${number(budget.minted)}</dd></div><div><dt>预留</dt><dd>${number(budget.reserved)}</dd></div><div><dt>可用</dt><dd>${number(budget.available)}</dd></div></dl></article>`;
  }).join("");
  listEmpty("task-list", taskEntries.length, "暂无 Token 任务，请先添加任务。");
  selectOptions(".task-select", taskEntries);
  const members = ledger.memberIds.map((id) => [id, id]);
  selectOptions(".member-select", members);
  selectOptions("#destination-select", [...members, [ledger.treasuryId, `金库 · ${ledger.treasuryId}`]]);
  $("contract-list").innerHTML = contracts.map((contract) => {
    const next = nextStatus[contract.status];
    const approvers = ledger.memberIds.filter((id) => id !== contract.principalId && id !== contract.contractorId);
    const canSettle = contract.status === "VERIFIED" && approvers.length > 0
      && ["OWNER", "VERIFIER"].includes(state.role);
    const canDispute = (contract.status === "DELIVERED" || contract.status === "VERIFIED")
      && (["OWNER", "VERIFIER"].includes(state.role)
        || state.memberId === contract.principalId || state.memberId === contract.contractorId);
    const canAdvance = {
      OFFERED: state.memberId === contract.principalId,
      ACCEPTED: state.memberId === contract.contractorId,
      CREDIT_RESERVED: state.memberId === contract.principalId,
      VERIFIED: ["OWNER", "VERIFIER"].includes(state.role)
        && ![contract.principalId, contract.contractorId].includes(state.memberId),
      FROZEN: ["OWNER", "VERIFIER"].includes(state.role),
    }[next];
    const needsDelivery = (contract.status === "CREDIT_RESERVED" || contract.status === "FROZEN")
      && state.memberId === contract.contractorId;
    const showAdvance = next && next !== "DELIVERED" && canAdvance;
    return `<article class="token-row contract-row"><div><strong>${safe(contract.id)}</strong><small>${safe(contract.principalId)} → ${safe(contract.contractorId)} · ${safe(contract.taskId)}</small><p>价格 ${number(contract.contractPriceExact ?? contract.contractPrice)}，最高铸币 ${number(contract.maximumMintValueExact ?? contract.maximumMintValue)}</p>${contract.evidenceHashes?.length ? `<p>交付证据 ${safe(contract.evidenceHashes.join("、"))}</p>` : ""}${contract.status === "SETTLED" ? `<p>实际铸币 ${number(contract.verifiedMintValueExact ?? contract.verifiedMintValue)}；批准成员 ${safe(contract.approverIds.join("、"))}</p>` : ""}${contract.status === "VERIFIED" && !approvers.length ? "<p>没有独立批准成员；请先在项目中添加第三位成员并同步。</p>" : ""}</div><div class="contract-action"><span class="contract-status">${safe(statusName[contract.status] || contract.status)}</span>${showAdvance ? `<button type="button" data-contract="${safe(contract.id)}" data-next="${next}">推进到${safe(statusName[next])}</button>` : ""}${canDispute ? `<button type="button" data-contract="${safe(contract.id)}" data-next="DISPUTED">提出争议</button>` : ""}${canSettle ? `<button type="button" data-settle="${safe(contract.id)}">结算</button>` : ""}</div>${needsDelivery ? `<form class="delivery-form" data-id="${safe(contract.id)}"><label>交付证据（每行一个标识）<textarea name="evidence_hashes" rows="2" required></textarea></label><button type="submit">提交交付</button></form>` : ""}${canSettle ? `<form class="settle-form" data-id="${safe(contract.id)}"><label>验证铸币值<input name="verified_mint_value" type="number" min="0.000000001" max="${safe(contract.maximumMintValue)}" step="any" required></label><label>独立批准成员<select name="approver_ids" required>${approvers.map((id) => `<option value="${safe(id)}">${safe(id)}</option>`).join("")}</select></label><label>结算证据标识<textarea name="evidence_hashes" rows="2" required></textarea></label><button type="submit">确认结算</button></form>` : ""}</article>`;
  }).join("");
  listEmpty("contract-list", contracts.length, "暂无委托合约。");
  for (const form of document.querySelectorAll(".settle-form")) form.hidden = true;
  renderEvents();
  renderFreezeOptions();
  $("graph-summary").textContent = `${graph.nodes.length} 个节点，当前视图 ${edges.length} 条关系`;
  renderGraph();
  $("graph-nodes").innerHTML = graph.nodes.map((node) => `<span><small>${safe(node.kind)}</small>${safe(node.label)}</span>`).join("");
  const visibleEdges = graph.edges.filter((edge) => graphViews[$("graph-view").value]?.has(edge.kind));
  $("graph-list").innerHTML = visibleEdges.map((edge) => `<div class="graph-edge"><span>${safe(nodeName(edge.source))}</span><span class="graph-edge-kind">${safe(edge.kind)}${edge.amount == null ? "" : ` · ${number(edge.amount)}`}</span><span>${safe(nodeName(edge.destination))}</span></div>`).join("");
  listEmpty("graph-list", visibleEdges.length, "此视图暂时没有关系；发生贡献、结算或验证后会显示。");
  updateTimestamp();
}
function updateTimestamp() {
  $("updated").textContent = `更新于 ${new Intl.DateTimeFormat(I18n.language === "en" ? "en-US" : "zh-CN", { timeStyle: "medium" }).format(new Date())}`;
}
function renderEvents() {
  const events = (state.ledger?.events || []).filter((event) => event.id === focusedEventId || $("event-filter").value === "ALL" || event.kind === $("event-filter").value).slice().reverse();
  $("event-list").innerHTML = events.map((event) => `<article class="token-row event-row ${event.id === focusedEventId ? "is-focused" : ""}" data-event-id="${safe(event.id)}"><div><strong>#${event.sequence} ${safe(kindName[event.kind] || event.kind)}</strong><small>${safe(event.id)} · ${safe(event.taskId || "无任务")}</small><p>${["FREEZE", "RELEASE"].includes(event.kind) ? `持有人 ${safe(event.sourceId)} · 标签 ${safe(event.destinationId)}` : `${safe(event.sourceId || "金库")} → ${safe(event.destinationId || "无目标")}`}${event.contractId ? ` · 合约 ${safe(event.contractId)}` : ""}</p><details><summary>事件详情</summary><p>证据键：${safe(event.evidenceKey || "无")}<br>备注：${safe(event.note || "无")}</p></details></div><strong class="event-amount">${number(event.amountExact ?? event.amount)}</strong></article>`).join("");
  listEmpty("event-list", events.length, "当前筛选下没有事件。");
  if (focusedEventId) requestAnimationFrame(() => document.querySelector(".event-row.is-focused")?.scrollIntoView({ block: "center" }));
}
function renderFreezeOptions() {
  const events = state.ledger?.events || [];
  const action = $("freeze-action").value;
  const entries = events.filter((event) => ["MINT", "TRANSFER", "SPLIT"].includes(event.kind))
    .filter((event) => action === "freeze" ? !event.frozen : event.frozen)
    .map((event) => [String(event.sequence), `#${event.sequence} ${kindName[event.kind]} · ${event.id} · ${number(event.amount)}`]);
  selectOptions("#mint-event", entries);
  $("freeze-form").querySelector('button[type="submit"]').disabled = state.busy || !entries.length;
}
async function loadPreview() {
  const id = $("legacy-project").value;
  if (!id) { $("migration-preview").textContent = "没有可迁移的旧项目。"; return; }
  try {
    const view = await request(`/api/projects/${encodeURIComponent(id)}/token-view`);
    $("migration-preview").textContent = `预计迁移 ${view.events.filter((event) => event.kind === "MINT").length} 条贡献；跳过 ${view.skipped.length} 条。旧项目团队总分 ${number(view.oldTeamTotal)}。`;
  } catch (error) { $("migration-preview").textContent = `无法读取迁移预览：${error.message}`; }
  $("migrate").disabled = !id;
}
async function fillProjectDefaults(id) {
  const current = state.projects.find((project) => project.id === id);
  if (!current) return;
  const form = $("create-project");
  form.elements.id.value = current.id;
  form.elements.name.value = current.name;
  form.elements.treasury_id.value = `${current.id}-treasury`;
  try {
    const dashboard = await request(`/api/projects/${encodeURIComponent(id)}/dashboard`);
    if ($("legacy-project").value === id) form.elements.member_ids.value = dashboard.members.map((member) => member.id).join("\n");
  } catch (error) { message(`成员读取失败：${error.message}`, true); }
}
async function refresh() {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  try {
    state.projects = await request("/api/projects");
    selectOptions("#legacy-project", state.projects.map((project) => [project.id, project.name]));
    const selectedProject = localStorage.getItem("contribution-project");
    const projectId = state.projects.some((project) => project.id === selectedProject)
      ? selectedProject : (state.projects[0]?.id || "");
    if (projectId) localStorage.setItem("contribution-project", projectId);
    selectOptions("#token-project-select", state.projects.map((project) => [project.id, project.name]));
    $("token-project-select").value = projectId;
    if (!projectId) {
      $("workspace").hidden = true;
      $("setup").hidden = true;
      $("empty-workspace").hidden = false;
      $("project-name").textContent = "请先创建或加入项目";
      return;
    }
    $("empty-workspace").hidden = true;
    const members = await request(`/api/projects/${encodeURIComponent(projectId)}/members`);
    state.memberId = Auth.member?.memberId || null;
    state.role = members.find((member) => member.id === state.memberId)?.role || "OWNER";
    let ledger;
    try { ledger = await request("/api/token/ledger"); }
    catch (error) {
      if (!String(error.message).startsWith("unknown token ledger")
          && !String(error.message).startsWith("unknown token project")) throw error;
      state.ledger = null; $("workspace").hidden = true; $("setup").hidden = false;
      $("project-name").textContent = "尚未启用 Token 账本";
      const selected = localStorage.getItem("contribution-project");
      if (state.projects.some((project) => project.id === selected)) $("legacy-project").value = selected;
      await fillProjectDefaults($("legacy-project").value);
      await loadPreview();
      return;
    }
    state.ledger = ledger;
    const [graph, contracts, tasks, debts] = await Promise.all([request("/api/token/graph"), request("/api/token/contracts"), request("/api/token/tasks"), request("/api/token/debts")]);
    state.graph = graph; state.contracts = contracts; state.tasks = tasks; state.debts = debts;
    state.budgets = Object.fromEntries(await Promise.all(tasks.map(async (task) => {
      const id = task.id;
      return [id, await request(`/api/token/tasks/${encodeURIComponent(id)}/budget`)];
    })));
    render();
    const selected = localStorage.getItem("contribution-project");
    if (selected && selected !== ledger.projectId) message(`当前账本属于 ${ledger.projectId}；项目看板选中的是 ${selected}。`);
  } catch (error) { message(`读取失败：${error.message}`, true); }
  finally { setBusy(false); }
}
function evidence(value) { return value.split(/\n+/).map((part) => part.trim()).filter(Boolean); }
async function mutate(path, body, label, form) {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  let saved = false;
  try {
    const result = await request(path, body);
    saved = true;
    if (form) form.reset();
    setBusy(false);
    await refresh();
    message(label + (result?.skipped?.length ? `；跳过 ${result.skipped.length} 条` : ""));
    try { localStorage.setItem("contribution-graph-update", String(Date.now())); } catch { /* Manual refresh works. */ }
  } catch (error) { message(saved ? `${label}已保存，但刷新失败：${error.message}` : `操作失败：${error.message}`, true); }
  finally { setBusy(false); }
}
function values(form) { return Object.fromEntries(new FormData(form)); }
for (const [id, path] of [["add-task", "/api/token/tasks"], ["mint-form", "/api/token/mint"], ["transfer-form", "/api/token/transfer"], ["contract-form", "/api/token/contracts"]]) {
  $(id).addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = values(form);
    if ("evidence_hashes" in body) body.evidence_hashes = evidence(body.evidence_hashes);
    if (body.evidence_hashes?.length === 0) { message("请填写至少一个证据标识。", true); return; }
    if (id === "contract-form" && body.principal_id === body.contractor_id) { message("委托成员与承接成员不能相同。", true); return; }
    if (id === "transfer-form" && body.source_id === body.destination_id) { message("来源和目标不能相同。", true); return; }
    mutate(path, body, "操作已保存。", form);
  });
}
$("task-list").addEventListener("submit", (event) => {
  if (!event.target.matches(".cap-form")) return;
  event.preventDefault();
  const form = event.target;
  mutate(`/api/token/tasks/${encodeURIComponent(form.dataset.id)}/cap`,
    { mint_cap: form.elements.mint_cap.value }, "任务铸币上限已更新。");
});
$("debt-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-collect]");
  if (button) mutate(`/api/token/debts/${encodeURIComponent(button.dataset.collect)}/collect`, {}, "追偿已处理。");
});
$("mint-form").elements.contribution_id.addEventListener("change", async (event) => {
  const id = event.target.value.trim();
  if (!id) return;
  try {
    const detail = await request(`/api/contributions/${encodeURIComponent(id)}`);
    const item = detail.contribution;
    if (!["VERIFIED", "RESOLVED"].includes(item.status)) throw new Error("此贡献尚未通过审核");
    const form = $("mint-form");
    form.elements.event_id.value = detail.tokenMintEventId;
    form.elements.task_id.value = item.task_id;
    form.elements.recipient_id.value = item.contributor_id;
    form.elements.amount.value = detail.currentScoreExact;
    form.elements.evidence_hashes.value = `legacy:${id}`;
  } catch (error) { message(`读取贡献失败：${error.message}`, true); }
});
$("create-project").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = values(form);
  body.member_ids = evidence(body.member_ids);
  mutate("/api/token/project", body, "账本已创建。", form);
});
$("migrate").addEventListener("click", () => mutate(`/api/token/migrate?project_id=${encodeURIComponent($("legacy-project").value)}`, {}, "历史贡献已迁移。"));
$("sync-legacy").addEventListener("click", () => mutate("/api/token/sync", {}, "项目成员与任务已同步。"));
$("reconcile").addEventListener("click", () => mutate("/api/token/reconcile", {}, "已检查并补同步贡献。"));
$("legacy-project").addEventListener("change", async () => {
  await fillProjectDefaults($("legacy-project").value);
  await loadPreview();
});
$("token-project-select").addEventListener("change", (event) => {
  localStorage.setItem("contribution-project", event.target.value);
  refresh();
});
$("contract-list").addEventListener("click", (event) => {
  const advance = event.target.closest("[data-next]");
  const settle = event.target.closest("[data-settle]");
  if (advance) mutate(`/api/token/contracts/${encodeURIComponent(advance.dataset.contract)}/advance`, { status: advance.dataset.next }, "合约状态已更新。");
  if (settle) {
    const form = [...document.querySelectorAll(".settle-form")].find((item) => item.dataset.id === settle.dataset.settle);
    if (form) { form.hidden = !form.hidden; if (!form.hidden) form.querySelector("input").focus(); }
  }
});
$("contract-list").addEventListener("submit", (event) => {
  if (event.target.matches(".delivery-form")) {
    event.preventDefault();
    const form = event.target;
    const body = { status: "DELIVERED", evidence_hashes: evidence(form.elements.evidence_hashes.value) };
    if (!body.evidence_hashes.length) { message("请填写交付证据。", true); return; }
    mutate(`/api/token/contracts/${encodeURIComponent(form.dataset.id)}/advance`, body, "委托交付已提交。");
    return;
  }
  if (!event.target.matches(".settle-form")) return;
  event.preventDefault();
  const form = event.target;
  const body = values(form);
  body.evidence_hashes = evidence(body.evidence_hashes);
  body.approver_ids = [body.approver_ids];
  if (!body.evidence_hashes.length || !body.approver_ids[0]) { message("请填写证据和独立批准成员。", true); return; }
  mutate(`/api/token/contracts/${encodeURIComponent(form.dataset.id)}/settle`, body, "合约已结算。");
});
$("event-filter").addEventListener("change", renderEvents);
$("graph-view").addEventListener("change", () => { if (state.graph) refresh(); });
$("balance-list").addEventListener("click", (event) => {
  const link = event.target.closest("[data-focus-event]");
  if (!link) return;
  event.preventDefault();
  const eventId = link.dataset.focusEvent;
  $("event-filter").value = "ALL";
  history.pushState(null, "", `?event=${encodeURIComponent(eventId)}#activity`);
  focusedEventId = eventId;
  renderEvents();
});
$("freeze-action").addEventListener("change", renderFreezeOptions);
$("freeze-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const sequence = Number(form.elements.sequence.value);
  const note = form.elements.note.value.trim();
  if (!sequence || !note) { message("请选择铸币事件并填写原因或说明。", true); return; }
  const mint = state.ledger.events.find((item) => item.sequence === sequence);
  const action = form.elements.action.value;
  const body = { sequences: [sequence], ...(action === "freeze" ? { reason: note } : { note, tag: mint.freezeTag }) };
  mutate(`/api/token/${action}`, body, action === "freeze" ? "铸币已冻结。" : "铸币已释放。");
});
$("refresh").addEventListener("click", refresh);
window.addEventListener("storage", (event) => {
  if (event.key === "contribution-graph-update" || event.key === "contribution-project") refresh();
});
window.addEventListener("focus", refresh);
document.addEventListener("languagechange", () => { if (state.ledger) updateTimestamp(); });
Auth.ready.then((member) => { if (member) refresh(); });
