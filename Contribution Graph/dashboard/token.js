const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const number = (value) => typeof value === "string"
  ? value : new Intl.NumberFormat(I18n.language === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: 9 }).format(Number(value) || 0);
const kindName = { MINT: "Mint", TRANSFER: "Transfer", FREEZE: "Freeze", RELEASE: "Release", REFUND: "Refund", SPLIT: "Allocation" };
const statusName = { DRAFT: "Draft", OFFERED: "Offered", ACCEPTED: "Accepted", CREDIT_RESERVED: "Reserved", DELIVERED: "Delivered", VERIFIED: "Verified", DISPUTED: "Disputed", FROZEN: "Frozen", SETTLED: "Settled", RESOLVED: "Resolved" };
const nextStatus = { DRAFT: "OFFERED", OFFERED: "ACCEPTED", ACCEPTED: "CREDIT_RESERVED", DELIVERED: "VERIFIED", DISPUTED: "FROZEN" };
const state = { ledger: null, graph: null, contracts: [], tasks: [], budgets: {}, debts: [], projects: [], projectId: "", busy: false };
const focusedEventId = new URLSearchParams(location.search).get("event");
const tokenApi = (path) => `/api/projects/${encodeURIComponent(state.projectId)}/token/${String(path).replace(/^\/api\/token\/?/, "")}`;

async function request(path, body) {
  const response = await fetch(path, { cache: "no-store", ...(body === undefined ? {} : { method: "POST", headers: window.HacKUAuth?.headers({ "Content-Type": "application/json" }) ?? { "Content-Type": "application/json" }, body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail ?? data.error;
    const error = new Error(Array.isArray(detail) ? detail.map((item) => `${item.loc?.slice(1).join(".") || "Input"}: ${item.msg}`).join("; ") : detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}
function message(text, error = false) {
  $(error ? "error" : "notice").textContent = text;
  $(error ? "error" : "notice").hidden = false;
}
function actionError(error) {
  const detail = error.message.toLowerCase();
  const hint = error.status === 401 ? "会话已过期，请重新登录。" : error.status === 403 ? "当前身份无此项目或操作权限。" : error.status === 409 && (detail.includes("ledger") || detail.includes("initial")) ? "项目账本待初始化，请使用重试初始化。" : error.status === 409 && (detail.includes("balance") || detail.includes("insufficient")) ? "余额不足，请查看债务并在收到新 Token 后追偿。" : error.status === 409 ? "账本状态已变化，请刷新后重试。" : "";
  return `${hint}${hint ? " " : ""}${error.message}`;
}
function clearMessages() { $("error").hidden = true; $("notice").hidden = true; }
function setBusy(value) {
  state.busy = value;
  for (const button of document.querySelectorAll("button")) button.disabled = value;
  document.querySelector("main").setAttribute("aria-busy", String(value));
  if (!value) {
    if (state.ledger) renderFreezeOptions();
    window.HacKUAuth?.refresh()?.then(() => {
      const identity=window.HacKUAuth.identity;
      const admin=identity.siteAdmin || identity.projects?.some((project)=>project.id===state.projectId && project.admin);
      $("retry-ledger").disabled=!state.projectId || !admin;
    });
  }
}
const projectName = (id) => state.projects.find((project) => project.id === id)?.name || id;
const nodeName = (address) => state.graph?.nodes.find((node) => node.address.join("/") === address.join("/"))?.label || address.at(-1);
function renderGraph(graph) {
  const svg = $("token-graph");
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
  for (const edge of graph.edges) {
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
  const kindsByView = {
    value: new Set(["CONTRIBUTES_TO", "MINTED"]),
    flow: new Set(["MINTED", "TRANSFER", "SPLIT", "REFUND"]),
    collaboration: new Set(["COMMISSIONED", "EXECUTED", "CONTRIBUTES_TO", "TRANSFER", "SPLIT"]),
    trust: new Set(["APPROVED", "DISPUTED", "FROZEN", "RELEASED", "REFUND"]),
  };
  const view = $("graph-view").value;
  localStorage.setItem("contribution-graph-view", view);
  const viewEdges = graph.edges.filter((edge) => kindsByView[view].has(edge.kind));
  const activeAddresses = new Set(viewEdges.flatMap((edge) => [edge.source.join("/"), edge.destination.join("/")]));
  const viewGraph = { nodes: graph.nodes.filter((node) => activeAddresses.has(node.address.join("/"))), edges: viewEdges };
  const help = { value: "Shows which contribution evidence and verified value created ledger value.", flow: "Shows mint, transfer, split, and refund movements with exact amounts.", collaboration: "Shows commissions, execution, and shared transfers between project participants.", trust: "Shows recorded independent approvals, disputes, freezes, releases, and refunds." };
  $("graph-view-help").textContent = help[view];
  $("workspace").hidden = false;
  $("setup").hidden = true;
  $("project-name").textContent = `${projectName(ledger.projectId)} · ${ledger.projectId}`;
  $("total-supply").textContent = number(ledger.totalSupplyExact ?? ledger.totalSupply);
  $("member-count").textContent = ledger.memberIds.length;
  $("task-count").textContent = tokenTasks().length;
  $("event-count").textContent = ledger.events.length;
  $("treasury").textContent = `Treasury ${ledger.treasuryId}`;
  $("balance-list").innerHTML = ledger.memberIds.map((id) => `<div class="balance-row"><span>${safe(id)}</span><strong>${number(ledger.balancesExact?.[id] ?? ledger.balances[id])}</strong></div>`).join("");
  listEmpty("balance-list", ledger.memberIds.length, "No ledger members yet.");
  const openDebts = state.debts.filter((debt) => /[1-9]/.test(debt.remainingExact));
  $("debt-list").innerHTML = openDebts
    .map((debt) => `<article class="token-row"><div><strong>${safe(debt.debtorId)} · ${safe(debt.id)}</strong><small>Task ${safe(debt.taskId)} · Receivable ${safe(debt.amountExact)}</small><p>Still due: ${safe(debt.remainingExact)}</p></div><button type="button" data-collect="${safe(debt.id)}">Recover available balance</button></article>`).join("");
  listEmpty("debt-list", openDebts.length, "No outstanding recovery.");
  const taskEntries = tokenTasks().map((task) => [task.id, task.name]);
  $("task-list").innerHTML = taskEntries.map(([id, name]) => {
    const budget = budgets[id];
    const task = state.tasks.find((item) => item.id === id);
    return `<article class="token-row"><div><strong>${safe(name)}</strong><small>${safe(id)} · ${safe(task.valueType)}</small><p>Acceptance criteria: ${safe(task.acceptanceCriteria)}</p><form class="cap-form" data-id="${safe(id)}"><label>Adjust mint cap<input name="mint_cap" type="number" min="0" step="any" value="${safe(task.mintCap)}" required></label><button type="submit">Save cap</button></form></div><dl class="budget-values"><div><dt>Cap</dt><dd>${number(budget.mintCap)}</dd></div><div><dt>Minted</dt><dd>${number(budget.minted)}</dd></div><div><dt>Reserved</dt><dd>${number(budget.reserved)}</dd></div><div><dt>Available</dt><dd>${number(budget.available)}</dd></div></dl></article>`;
  }).join("");
  listEmpty("task-list", taskEntries.length, "No Token tasks yet. Add a task first.");
  selectOptions(".task-select", taskEntries);
  const members = ledger.memberIds.map((id) => [id, id]);
  selectOptions(".member-select", members);
  const signedInMember = window.HacKUAuth?.identity?.memberId;
  const principalSelect = $("contract-form").elements.principal_id;
  selectOptions("#contract-form [name=principal_id]", signedInMember && ledger.memberIds.includes(signedInMember) ? [[signedInMember, signedInMember]] : []);
  if (principalSelect && signedInMember) principalSelect.value = signedInMember;
    selectOptions("#destination-select", [...members, [ledger.treasuryId, `Treasury · ${ledger.treasuryId}`]]);
  $("contract-list").innerHTML = contracts.map((contract) => {
    const next = nextStatus[contract.status];
    const identity = window.HacKUAuth?.identity || {};
    const member = identity.memberId;
    const party = member === contract.principalId || member === contract.contractorId;
    const memberRole = identity.projects?.find((project) => project.id === ledger.projectId)?.role;
    const projectAdmin = identity.siteAdmin || memberRole === "OWNER";
    const canVerify = identity.siteAdmin || ["OWNER", "VERIFIER"].includes(memberRole);
    const canAdvance = next && ((next === "OFFERED" && member === contract.principalId)
      || (next === "ACCEPTED" && member === contract.contractorId)
      || (next === "CREDIT_RESERVED" && (member === contract.principalId || projectAdmin))
      || (next === "VERIFIED" && canVerify && !party));
    const approvers = contract.approverIds || [];
    const candidates = ledger.memberIds.filter((id) => id !== contract.principalId && id !== contract.contractorId);
    const canApprove = contract.status === "VERIFIED" && member && canVerify && !party && !approvers.includes(member);
    const canSettle = contract.status === "VERIFIED" && approvers.length > 0 && canVerify;
    const canDispute = contract.status === "SETTLED" && party;
    const canFreeze = contract.status === "DISPUTED" && contract.settled && canVerify;
    const canResolve = contract.status === "FROZEN" && canVerify && !party;
    const canDeliver = contract.status === "CREDIT_RESERVED" && member === contract.contractorId;
    const resolution = contract.resolution;
    const delivery = contract.deliveryEvidence || [];
    return `<article id="contract-${safe(contract.id)}" class="token-row contract-row"><div><strong>${safe(contract.id)}</strong><small>${safe(contract.principalId)} → ${safe(contract.contractorId)} · ${safe(contract.taskId)}</small><p>Price ${number(contract.contractPriceExact ?? contract.contractPrice)}; maximum mint ${number(contract.maximumMintValueExact ?? contract.maximumMintValue)}</p><p>Next: ${contract.status === "CREDIT_RESERVED" ? `contractor ${safe(contract.contractorId)} must submit delivery evidence` : contract.status === "DELIVERED" ? "an independent verifier must advance verification" : contract.status === "VERIFIED" && !approvers.length ? "an independent project member must approve" : "follow the available contract action"}</p>${delivery.length ? `<p>Delivery evidence: ${safe(delivery.map((item) => item.reference).join(" · "))}</p>` : ""}${contract.settled ? `<p>Minted ${number(contract.verifiedMintValueExact ?? contract.verifiedMintValue)}; payment ${number(contract.contractPriceExact ?? contract.contractPrice)}; independent approvers ${safe(approvers.join(", ") || "None")}; evidence ${safe(contract.evidenceHashes.join(", "))}</p>` : ""}${contract.dispute ? `<p>Dispute reason: ${safe(contract.dispute.reason)} · raised by ${safe(contract.dispute.raisedBy)}</p>` : ""}${resolution ? `<p>Resolution ${safe(resolution.outcome)}: refund ${number(resolution.refundAmount)}, contractor retains ${number(resolution.retainedAmount)}. ${safe(resolution.note)}</p>` : ""}</div><div class="contract-action"><span class="contract-status">${safe(statusName[contract.status] || contract.status)}</span>${canAdvance ? `<button type="button" data-contract="${safe(contract.id)}" data-next="${next}">Advance to ${safe(statusName[next])}</button>` : ""}${canApprove ? `<button type="button" data-approve="${safe(contract.id)}" data-principal="${safe(contract.principalId)}" data-contractor="${safe(contract.contractorId)}">Approve independently</button>` : ""}${canDispute ? `<button type="button" data-dispute="${safe(contract.id)}" data-principal="${safe(contract.principalId)}" data-contractor="${safe(contract.contractorId)}">Raise dispute</button>` : ""}${canFreeze ? `<button type="button" data-freeze-contract="${safe(contract.id)}">Freeze payment</button>` : ""}</div>${canDeliver ? `<form class="delivery-form" data-id="${safe(contract.id)}" data-contractor="${safe(contract.contractorId)}"><label>Delivery evidence<textarea name="evidence" rows="2" maxlength="4096" required placeholder="PR, document, or other evidence URL"></textarea></label><button type="submit">Submit delivery evidence</button></form>` : ""}${canSettle ? `<form class="settle-form" data-id="${safe(contract.id)}"><label>Verified mint value<input name="verified_mint_value" type="number" min="0.000000001" max="${safe(contract.maximumMintValue)}" step="any" required></label><p>Recorded approvers: ${safe(approvers.join(", "))}</p><label>Evidence IDs<textarea name="evidence_hashes" rows="2" required></textarea></label><button type="submit">Confirm settlement</button></form>` : ""}${canResolve ? `<form class="contract-resolve-form" data-id="${safe(contract.id)}"><label>Outcome<select name="outcome">${contract.settled ? '<option value="RELEASE">Full release</option><option value="REFUND">Full refund</option><option value="SPLIT">Partial split</option>' : '<option value="CANCELLED">Cancel unsettled contract</option>'}</select></label><label class="refund-amount-field">Refund amount<input name="refund_amount" type="number" min="0.000000001" step="any"></label><label>Resolution note<textarea name="note" required></textarea></label><button type="submit">Record resolution</button></form>` : ""}</article>`;
  }).join("");
  listEmpty("contract-list", contracts.length, "No commission contracts yet.");
  for (const form of document.querySelectorAll(".contract-resolve-form")) {
    const split = form.elements.outcome.value === "SPLIT";
    form.querySelector(".refund-amount-field").hidden = !split;
  }
  renderEvents();
  renderFreezeOptions();
  $("graph-summary").textContent = `${viewGraph.nodes.length} nodes · ${viewGraph.edges.length} relationships`;
  renderGraph(viewGraph);
  $("graph-nodes").innerHTML = viewGraph.nodes.map((node) => `<span><small>${safe(node.kind)}</small>${safe(node.label)}</span>`).join("");
  $("graph-list").innerHTML = viewGraph.edges.map((edge) => `<div class="graph-edge"><span>${safe(nodeName(edge.source))}</span><span class="graph-edge-kind">${safe(edge.kind)}${edge.amountExact == null ? "" : ` · ${safe(edge.amountExact)}`}</span><span>${safe(nodeName(edge.destination))}</span></div>`).join("");
  listEmpty("graph-list", viewGraph.edges.length, "No relationships in this view yet. Check another view or return after new project activity.");
  updateTimestamp();
}
function updateTimestamp() {
  $("updated").textContent = `Updated at ${new Intl.DateTimeFormat("en-US", { timeStyle: "medium" }).format(new Date())}`;
}
function renderEvents() {
  const events = (state.ledger?.events || []).filter((event) => $("event-filter").value === "ALL" || event.kind === $("event-filter").value).slice().reverse();
  $("event-list").innerHTML = events.map((event) => `<article class="token-row event-row ${event.id === focusedEventId ? "is-focused" : ""}" data-event-id="${safe(event.id)}"><div><strong>#${event.sequence} ${safe(kindName[event.kind] || event.kind)}</strong><small>${safe(event.id)} · ${safe(event.taskId || "No task")}</small><p>${["FREEZE", "RELEASE"].includes(event.kind) ? `Holder ${safe(event.sourceId)} · Tag ${safe(event.destinationId)}` : `${safe(event.sourceId || "Treasury")} → ${safe(event.destinationId || "No destination")}`}${event.contractId ? ` · Contract ${safe(event.contractId)}` : ""}</p><details><summary>Event details</summary><p>Evidence key: ${safe(event.evidenceKey || "None")}<br>Note: ${safe(event.note || "None")}</p></details></div><strong class="event-amount">${number(event.amountExact ?? event.amount)}</strong></article>`).join("");
  listEmpty("event-list", events.length, "No events match the current filter.");
  if (focusedEventId) requestAnimationFrame(() => document.querySelector(".event-row.is-focused")?.scrollIntoView({ block: "center" }));
}
function renderFreezeOptions() {
  const events = state.ledger?.events || [];
  const action = $("freeze-action").value;
  const entries = events.filter((event) => ["MINT", "TRANSFER"].includes(event.kind))
    .filter((event) => action === "freeze" ? !event.frozen : event.frozen)
    .map((event) => [String(event.sequence), `#${event.sequence} ${kindName[event.kind]} · ${event.id} · ${number(event.amount)}`]);
  selectOptions("#mint-event", entries);
  $("freeze-form").querySelector('button[type="submit"]').disabled = state.busy || !entries.length;
}
async function refresh() {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  try {
    state.projects = await request("/api/projects");
    const preferred=localStorage.getItem("contribution-project");
    const requestedProject = new URLSearchParams(location.search).get("project");
    state.projectId=state.projects.some((item)=>item.id===requestedProject)?requestedProject:(state.projects.some((item)=>item.id===preferred)?preferred:(state.projects[0]?.id || ""));
    selectOptions("#token-project-select", state.projects.map((project) => [project.id, project.name]));
    $("token-project-select").value=state.projectId;
    if(!state.projectId){state.ledger=null;$("workspace").hidden=true;$("setup").hidden=false;$("ledger-state-copy").textContent="No projects are available. Create a project in the Project Dashboard first.";$("retry-ledger").disabled=true;return;}
    localStorage.setItem("contribution-project",state.projectId);
    const status=await request(tokenApi("status"));
    if(status.state!=="READY"){
      state.ledger=null;$("workspace").hidden=true;$("setup").hidden=false;$("project-name").textContent=projectName(state.projectId);$("ledger-state-copy").textContent="The ledger is waiting for initialization. The project and member relationships are saved; you can retry.";$("retry-ledger").disabled=false;return;
    }
    const ledger=await request(tokenApi("ledger"));
    state.ledger = ledger;
    const optional = (path) => request(tokenApi(path)).catch((error) => { if (error.status===403) return []; throw error; });
    const [graph, contracts, tasks, debts] = await Promise.all([request(tokenApi("graph")), optional("contracts"), request(tokenApi("tasks")), optional("debts")]);
    state.graph = graph; state.contracts = contracts; state.tasks = tasks; state.debts = debts;
    state.budgets = Object.fromEntries(await Promise.all(tasks.map(async (task) => {
      const id = task.id;
      return [id, await request(tokenApi(`tasks/${encodeURIComponent(id)}/budget`))];
    })));
    render();
  } catch (error) { message(`Could not load data: ${actionError(error)}`, true); }
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
    message(label + (result?.skipped?.length ? `; skipped ${result.skipped.length}` : ""));
    try { localStorage.setItem("contribution-graph-update", String(Date.now())); } catch { /* Manual refresh works. */ }
  } catch (error) { message(saved ? `${label} saved, but refresh failed: ${actionError(error)}` : `Action failed: ${actionError(error)}`, true); }
  finally { setBusy(false); }
}
function values(form) { return Object.fromEntries(new FormData(form)); }
for (const [id, path] of [["add-task", "tasks"], ["mint-form", "mint"], ["transfer-form", "transfer"], ["contract-form", "contracts"]]) {
  $(id).addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = values(form);
    if ("evidence_hashes" in body) body.evidence_hashes = evidence(body.evidence_hashes);
    if (body.evidence_hashes?.length === 0) { message("Enter at least one evidence ID.", true); return; }
    if (id === "contract-form" && body.principal_id === body.contractor_id) { message("The principal and contractor must be different.", true); return; }
    if (id === "transfer-form" && body.source_id === body.destination_id) { message("The source and destination must be different.", true); return; }
    mutate(tokenApi(path), body, "Action saved.", form);
  });
}
$("task-list").addEventListener("submit", (event) => {
  if (!event.target.matches(".cap-form")) return;
  event.preventDefault();
  const form = event.target;
  mutate(tokenApi(`tasks/${encodeURIComponent(form.dataset.id)}/cap`),
    { mint_cap: form.elements.mint_cap.value }, "Task mint cap updated.");
});
$("debt-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-collect]");
  if (button) mutate(tokenApi(`debts/${encodeURIComponent(button.dataset.collect)}/collect`), {}, "Recovery processed.");
});
$("mint-form").elements.contribution_id.addEventListener("change", async (event) => {
  const id = event.target.value.trim();
  if (!id) return;
  try {
    const detail = await request(`/api/contributions/${encodeURIComponent(id)}`);
    const item = detail.contribution;
    if (!["VERIFIED", "RESOLVED"].includes(item.status)) throw new Error("This contribution has not been reviewed.");
    const form = $("mint-form");
    form.elements.event_id.value = detail.tokenMintEventId;
    form.elements.task_id.value = item.task_id;
    form.elements.recipient_id.value = item.contributor_id;
    form.elements.amount.value = detail.currentScoreExact;
    form.elements.evidence_hashes.value = `legacy:${id}`;
  } catch (error) { message(`Could not load contribution: ${error.message}`, true); }
});
$("retry-ledger").addEventListener("click", () => mutate(tokenApi("setup/retry"), {}, "Project ledger initialized."));
$("token-project-select").addEventListener("change", (event) => {
  state.projectId=event.target.value;
  localStorage.setItem("contribution-project",state.projectId);
  refresh();
});
$("sync-legacy").addEventListener("click", () => mutate(tokenApi("sync"), {}, "Project members and tasks synced."));
$("reconcile").addEventListener("click", () => mutate(tokenApi("reconcile"), {}, "Contributions checked and reconciled."));
$("contract-list").addEventListener("click", (event) => {
  const advance = event.target.closest("[data-next]");
  const settle = event.target.closest("[data-settle]");
  const approve = event.target.closest("[data-approve]");
  const dispute = event.target.closest("[data-dispute]");
  const freeze = event.target.closest("[data-freeze-contract]");
  if (advance) mutate(tokenApi(`contracts/${encodeURIComponent(advance.dataset.contract)}/advance`), { status: advance.dataset.next }, "Contract status updated.");
  if (approve) mutate(tokenApi(`contracts/${encodeURIComponent(approve.dataset.approve)}/approve`), { note: "Independently approved through the workspace" }, "Independent approval recorded.");
  if (dispute) {
    const reason = window.prompt("Enter the dispute reason");
    if (reason?.trim()) mutate(tokenApi(`contracts/${encodeURIComponent(dispute.dataset.dispute)}/dispute`), { reason: reason.trim() }, "Dispute recorded.");
  }
  if (freeze) mutate(tokenApi(`contracts/${encodeURIComponent(freeze.dataset.freezeContract)}/freeze`), { reason: "Frozen for dispute settlement" }, "Contract payment frozen.");
  if (settle) {
    const form = [...document.querySelectorAll(".settle-form")].find((item) => item.dataset.id === settle.dataset.settle);
    if (form) { form.hidden = !form.hidden; if (!form.hidden) form.querySelector("input").focus(); }
  }
});
$("contract-list").addEventListener("submit", (event) => {
  if (!event.target.matches(".settle-form")) return;
  event.preventDefault();
  const form = event.target;
  const body = values(form);
  body.evidence_hashes = evidence(body.evidence_hashes);
  if (!body.evidence_hashes.length) { message("Enter settlement evidence.", true); return; }
  mutate(tokenApi(`contracts/${encodeURIComponent(form.dataset.id)}/settle`), body, "Contract settled.");
});
$("contract-list").addEventListener("change", (event) => {
  if (event.target.matches('.contract-resolve-form [name="outcome"]')) {
    event.target.form.querySelector(".refund-amount-field").hidden = event.target.value !== "SPLIT";
  }
});
$("contract-list").addEventListener("submit", (event) => {
  if (event.target.matches(".delivery-form")) {
    event.preventDefault();
    const form = event.target;
    const refs = form.elements.evidence.value.split("\n").map((item) => item.trim()).filter(Boolean);
    if (!refs.length) { message("Add at least one delivery evidence reference.", true); return; }
    mutate(tokenApi(`contracts/${encodeURIComponent(form.dataset.id)}/deliver`), { evidence: refs }, "Delivery evidence recorded.");
    return;
  }
  if (!event.target.matches(".contract-resolve-form")) return;
  event.preventDefault();
  const form = event.target;
  const body = values(form);
  if (body.outcome !== "SPLIT") delete body.refund_amount;
  mutate(tokenApi(`contracts/${encodeURIComponent(form.dataset.id)}/resolve`), body, "Final dispute resolution recorded.");
});
$("event-filter").addEventListener("change", renderEvents);
const savedGraphView = localStorage.getItem("contribution-graph-view");
if (["value", "flow", "collaboration", "trust"].includes(savedGraphView)) $("graph-view").value = savedGraphView;
$("graph-view").addEventListener("change", () => { if (state.graph) render(); });
$("freeze-action").addEventListener("change", renderFreezeOptions);
$("freeze-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const sequence = Number(form.elements.sequence.value);
  const note = form.elements.note.value.trim();
  if (!sequence || !note) { message("Select a mint event and enter a reason or note.", true); return; }
  const mint = state.ledger.events.find((item) => item.sequence === sequence);
  const action = form.elements.action.value;
  const body = { sequences: [sequence], ...(action === "freeze" ? { reason: note } : { note, tag: mint.freezeTag }) };
  mutate(tokenApi(action), body, action === "freeze" ? "Mint frozen." : "Mint released.");
});
$("refresh").addEventListener("click", refresh);
window.addEventListener("storage", (event) => {
  if (event.key === "contribution-graph-update" || event.key === "contribution-project") refresh();
});
window.addEventListener("focus", refresh);
document.addEventListener("languagechange", () => { if (state.ledger) updateTimestamp(); });
refresh();
