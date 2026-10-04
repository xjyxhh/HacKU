
const language = "en";
const t = (value) => language === "en" ? value : value;
const statusName = (kind) => t({ PENDING: "Pending", VERIFIED: "Verified", DISPUTED: "Disputed", RESOLVED: "Resolved" }[kind] ?? kind);
const typeName = (kind) => t({ CORE: "Core", SUPPORT: "Support", REVIEW: "Review", COORDINATION: "Coordination" }[kind] ?? kind);
const categories = ["CORE", "SUPPORT", "REVIEW", "COORDINATION"];
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value ?? 0);
const tokenAmount = (value) => String(value ?? "0");
let currentData = null;
let lifecycleRenderGeneration = 0;
let selectedId = null;
let projectId = localStorage.getItem("contribution-project") || "fintech";
function setLanguage(next) {
  // English is the fixed interface language.
  I18n.apply();
  if (currentData) render(currentData);
  else if (!projectId) {
    $("project-name").textContent = t("Create a project first");
    $("updated").textContent = t("No projects yet");
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
    (filterValue("status") === "ALL" || (filterValue("status") === "WITHDRAWN" ? item.withdrawalState === "WITHDRAWN" : item.status === filterValue("status")))
  );
  const sort = $("sort-order").value;
  if (sort === "score-desc") rows.sort((a, b) => b.score - a.score);
  if (sort === "score-asc") rows.sort((a, b) => a.score - b.score);
  if (sort === "member") rows.sort((a, b) => (members[a.contributorId] ?? a.contributorId).localeCompare(members[b.contributorId] ?? b.contributorId, "en-US"));
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
  const identity=window.HacKUAuth?.identity||{};
  const canManageMembers = Boolean(identity.siteAdmin || identity.projects?.some((project) => project.id === projectId && project.admin));
  $("members").innerHTML = data.members.map((member) => `
    <div class="member-shell"><button class="member ${filterValue("member") === member.id ? "is-active" : ""}" type="button" data-member-id="${safe(member.id)}" aria-pressed="${filterValue("member") === member.id}">
      <span class="member-top"><span class="identity"><span class="avatar" aria-hidden="true">${safe(member.name.slice(0, 1))}</span><span class="member-name">${safe(member.name)}</span></span><span class="share">${recognition ? "Token balance" : `${Number(member.contributionShare).toFixed(2)}%`}</span></span>
      <span class="member-score">${recognition ? safe(tokenAmount(recognition.balancesExact?.[member.id])) : points(member.totalScore)} <small>${recognition ? "Token" : t("pts")}</small></span>
      <span class="breakdown">${recognition ? `<span>Previous score ${points(member.totalScore)}</span>` : categories.map((kind) => `<span>${typeName(kind)} <b>${points(member.breakdown[kind])}</b></span>`).join("")}</span>
      <span class="membership-state">${member.membershipState === "WITHDRAWN" ? "Exited this project" : member.membershipState === "EXIT_REQUESTED" ? "Exit pending" : "Project member"}</span>
    </button>${member.exitRequest ? `<div class="member-exit-request"><p>Exit reason: ${safe(member.exitRequest.reason)}</p><p>Related contributions ${member.exitRequest.contributionIds.length} records</p>${identity.memberId===member.id ? `<button type="button" data-cancel-exit="${safe(member.exitRequest.id)}" data-member="${safe(member.id)}">Cancel exit request</button>` : identity.projects?.some((project) => project.id === projectId) ? `<button type="button" data-exit-decision="APPROVE" data-request="${safe(member.exitRequest.id)}" data-member="${safe(member.id)}">Approve exit</button><button type="button" data-exit-decision="REJECT" data-request="${safe(member.exitRequest.id)}" data-member="${safe(member.id)}">Reject exit</button>` : ""}</div>` : ""}</div>`).join("");
  if (canManageMembers) {
    data.members.filter((member) => member.membershipState === "ACTIVE").forEach((member) => {
      const shell = $("members").querySelector('[data-member-id="' + CSS.escape(member.id) + '"]')?.parentElement;
      if (!shell) return;
      const actions = document.createElement("div");
      actions.className = "member-actions";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "member-remove";
      remove.dataset.removeMember = member.id;
      remove.textContent = t("Remove from this project");
      actions.append(remove);
      shell.append(actions);
    });
  }
}

function renderTasks(data) {
  $("tasks-empty").hidden = data.tasks.length > 0;
  $("tasks").innerHTML = data.tasks.map((task) => `
    <button class="task ${filterValue("task") === task.id ? "is-active" : ""}" type="button" data-task-id="${safe(task.id)}" aria-pressed="${filterValue("task") === task.id}">
      <span><span class="task-name">${safe(task.name)}</span><span class="task-id">${safe(task.id)}${task.description ? ` · ${safe(task.description)}` : ""}</span></span>
      <span class="task-value">${points(task.taskValue)} <small>${t("value")}</small></span>
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
  $("relationship-count").textContent = `${rows.length} ${t("contributions")}`;
  $("graph-empty").hidden = rows.length > 0;
  $("graph-content").hidden = rows.length === 0;
  if (!rows.length) return;

  const usedMembers = data.members.filter((member) => rows.some((row) => row.contributorId === member.id || row.helpedMemberId === member.id));
  const usedTasks = data.tasks.filter((task) => rows.some((row) => row.taskId === task.id));
  const height = Math.max(340, rows.length * 76 + 48, usedMembers.length * 82 + 48, usedTasks.length * 82 + 48);
  svg.setAttribute("viewBox", `0 0 820 ${height}`);
  svg.style.height = `${height}px`;
  svg.setAttribute("aria-label", language === "en" ? `Showing ${rows.length} member, contribution, and task relationships. Use Tab to select a contribution.` : `Showing ${rows.length} member, contribution, and task relationships. Use Tab to select a contribution.`);
  const memberY = Object.fromEntries(usedMembers.map((item, index) => [item.id, (index + 1) * height / (usedMembers.length + 1)]));
  const taskY = Object.fromEntries(usedTasks.map((item, index) => [item.id, (index + 1) * height / (usedTasks.length + 1)]));
  const defs = svgElement("defs");
  const arrow = svgElement("marker", { id: "graph-arrow", markerWidth: 8, markerHeight: 8, refX: 7, refY: 3.5, orient: "auto" });
  arrow.append(svgElement("path", { d: "M0 0 L7 3.5 L0 7 Z" }));
  defs.append(arrow);
  svg.append(defs);
  svgText(svg, 86, 27, t("Member"), "graph-column");
  svgText(svg, 392, 27, t("Contribution"), "graph-column");
  svgText(svg, 710, 27, t("Task"), "graph-column");
  rows.forEach((row, index) => {
    const y = 56 + index * 76;
    const link = (d, extra = "") => svg.append(svgElement("path", { d, class: `graph-link ${extra}` }));
    const historyClass=row.withdrawalState==="WITHDRAWN"?"is-withdrawn":"";
    link(`M 173 ${memberY[row.contributorId]} C 244 ${memberY[row.contributorId]}, 251 ${y}, 316 ${y}`,historyClass);
    link(`M 492 ${y} C 568 ${y}, 562 ${taskY[row.taskId]}, 635 ${taskY[row.taskId]}`,historyClass);
    if (row.helpedMemberId) link(`M 316 ${y + 9} C 247 ${y + 49}, 228 ${memberY[row.helpedMemberId] + 22}, 173 ${memberY[row.helpedMemberId] + 22}`, "help-link");
    const group = svgElement("g", { class: `graph-contribution ${selectedId === row.id ? "is-selected" : ""} ${row.status === "PENDING" || row.status === "DISPUTED" ? "is-unscored" : ""} ${historyClass}`, role: "button", tabindex: "0", "data-contribution-id": row.id, "aria-label": `${t("View contribution")} ${row.description}${historyClass?", Withdrawn":""}` });
    group.append(svgElement("rect", { x: 316, y: y - 22, width: 176, height: 44, rx: 11 }));
    svgText(group, 328, y - 3, `${typeName(row.type)} · ${row.id}`.slice(0, 22), "graph-label");
    svgText(group, 328, y + 13, `${row.withdrawalState === "WITHDRAWN" ? "Withdrawn" : statusName(row.status)} · ${row.description}`.slice(0, 17), "graph-subtitle");
    svg.append(group);
  });
  usedMembers.forEach((member) => {
    const y = memberY[member.id];
    const group = svgElement("g", { class: `graph-entity ${filterValue("member") === member.id ? "is-active" : ""}`, role: "button", tabindex: "0", "data-member-id": member.id, "aria-label": `${t("Filter member")} ${member.name}` });
    group.append(svgElement("rect", { x: 30, y: y - 23, width: 143, height: 46, rx: 11 }));
    svgText(group, 42, y + 5, member.name.slice(0, 17), "graph-label");
    svg.append(group);
  });
  usedTasks.forEach((task) => {
    const y = taskY[task.id];
    const group = svgElement("g", { class: `graph-entity ${filterValue("task") === task.id ? "is-active" : ""}`, role: "button", tabindex: "0", "data-task-id": task.id, "aria-label": `${t("Filter task")} ${task.name}` });
    group.append(svgElement("rect", { x: 635, y: y - 23, width: 155, height: 46, rx: 11 }));
    svgText(group, 647, y + 5, task.name.slice(0, 17), "graph-label");
    svg.append(group);
  });
  $("relationships").innerHTML = rows.map((row) => `
    <button class="relation ${selectedId === row.id ? "is-selected" : ""}" type="button" data-contribution-id="${safe(row.id)}" aria-pressed="${selectedId === row.id}">
      <span class="relation-names"><strong>${safe(members[row.contributorId] ?? row.contributorId)}</strong><span aria-hidden="true">→</span><strong>${safe(typeName(row.type))}</strong><span aria-hidden="true">→</span><strong>${safe(tasks[row.taskId] ?? row.taskId)}</strong></span>
      <span class="relation-meta">${safe(row.description)}${row.helpedMemberId ? ` · ${t("Helped")} ${safe(members[row.helpedMemberId] ?? row.helpedMemberId)}` : ""}</span>
      <span class="relation-foot"><span class="status ${row.withdrawalState === "WITHDRAWN" ? "withdrawn" : row.status.toLowerCase()}">${row.withdrawalState === "WITHDRAWN" ? "Withdrawn" : safe(statusName(row.status))}</span><span>${row.status === "PENDING" || row.status === "DISPUTED" ? t("Not scored") : `${points(row.score)} ${t("pts")}`}</span></span>
    </button>`).join("");
}

function renderContributions(data, rows) {
  const members = namesById(data.members);
  const tasks = namesById(data.tasks);
  $("result-count").textContent = `${rows.length} / ${data.contributions.length} ${t("records")}`;
  $("contributions-empty").hidden = rows.length > 0;
  $("contributions").innerHTML = rows.map((item) => `
    <tr class="${selectedId === item.id ? "is-selected" : ""}" data-row-id="${safe(item.id)}">
      <td><button class="row-select" type="button" data-contribution-id="${safe(item.id)}" aria-label="${t("View")} ${safe(members[item.contributorId] ?? item.contributorId)} ${t("contribution")} ${safe(item.description)}"><strong>${safe(members[item.contributorId] ?? item.contributorId)}</strong><span>${safe(item.description)}</span>${item.helpedMemberId ? `<small>${t("Helped")} ${safe(members[item.helpedMemberId] ?? item.helpedMemberId)}</small>` : ""}</button></td>
      <td data-label="${t("Task")}">${safe(tasks[item.taskId] ?? item.taskId)}</td><td data-label="${t("Type")}"><span class="type">${safe(typeName(item.type))}</span></td>
      <td data-label="${t("Status")}"><span class="status ${item.withdrawalState === "WITHDRAWN" ? "withdrawn" : item.status.toLowerCase()}">${item.withdrawalState === "WITHDRAWN" ? "Withdrawn" : safe(statusName(item.status))}</span></td>
      <td data-label="Token Events">${item.tokenEventId ? `<a href="/token.html?event=${encodeURIComponent(item.tokenEventId)}#activity">${item.tokenEventId.includes(":commission:") ? "Commission Contracts · " : "Mint · "}#${item.tokenEventSequence}</a>${item.tokenFrozen ? '<small class="token-state">Currently frozen</small>' : ""}` : item.tokenPending ? '<span class="token-state">Awaiting Mint</span>' : '<span class="token-state">—</span>'}</td>
      <td data-label="Previous score" class="number">${item.status === "PENDING" || item.status === "DISPUTED" ? `<span class="no-score">${t("Not scored")}</span>` : `<span class="score">${points(item.score)}</span>`}</td>
    </tr>`).join("");
}

async function loadDetail(id) {
  $("detail").hidden = false;
  $("detail-content").textContent = t("Loading contribution details...");
  try {
    const data = await request(`/api/contributions/${encodeURIComponent(id)}`);
    if (selectedId !== id) return;
    const record = currentData.contributions.find((item) => item.id === id);
    const contributor = currentData.members.find((item) => item.id === data.contribution.contributor_id);
    const helped = currentData.members.find((item) => item.id === data.contribution.helped_member_id);
    const item = data.contribution;
    $("detail-content").innerHTML = `
      <p class="detail-description">${safe(item.description)}</p>
      <div class="detail-grid"><div><span>${t("Contributor")}</span><strong>${safe(contributor?.name ?? item.contributor_id)}</strong></div><div><span>${t("Task")}</span><strong>${safe(data.task.name)}</strong></div><div><span>${t("Type / status")}</span><strong>${safe(typeName(item.type))} / ${item.withdrawal ? "Withdrawn" : safe(statusName(item.status))}</strong></div><div><span>Original / effective score</span><strong>${safe(data.originalScoreExact)} / ${safe(data.currentScoreExact)}</strong></div><div><span>${t("Preset task value")}</span><strong>${safe(data.task.taskValue)}</strong></div><div><span>${t("Completion")}</span><strong>${safe(item.completion)}</strong></div><div><span>${t("Quality factor")}</span><strong>${safe(item.quality)}</strong></div><div><span>${t("Proposed support value")}</span><strong>${safe(item.support_value)}</strong></div></div>
      ${helped ? `<p class="detail-extra">${t("Helped member")}${language === "en" ? ": " : ": "}${safe(helped.name)}</p>` : ""}
      ${data.evidence.length ? `<p class="detail-extra">${t("Evidence")}${language === "en" ? ": " : ": "}${data.evidence.map((e) => safe(e.reference)).join(language === "en" ? "; " : "; ")}</p>` : ""}
      ${item.resolution_note ? `<p class="detail-extra">${t("Resolution note")}${language === "en" ? ": " : ": "}${safe(item.resolution_note)}</p>` : ""}`;
    if(item.withdrawal){
      const recovery=record?.tokenRecovery;
      $("detail-content").insertAdjacentHTML("beforeend",`<section class="withdrawal-history"><h3>Withdrawal history</h3><p>Applicant ${safe(item.withdrawal.applicantId)}, Reason: ${safe(item.withdrawal.reason)}</p><p>Reviewer ${safe(item.withdrawal.reviewerId||"Pending")}, Note: ${safe(item.withdrawal.decisionNote||"None")}</p><p>The effective score is 0; review history and evidence are retained.</p>${recovery?`<p>Tokens recovered: ${safe(recovery.recoveredExact)}, Outstanding recovery: ${safe(recovery.debtExact)}, Accounting state: ${safe(recovery.state)}.${safe(recovery.detail)}</p>`:"<p>Token accounting status is shown in the ledger view.</p>"}</section>`);
    }
    const identity = window.HacKUAuth?.identity;
    if (record?.latestUnwindRequest && record.withdrawalState !== "WITHDRAWN") {
      const last=record.latestUnwindRequest;
      $("detail-content").insertAdjacentHTML("beforeend",`<p class="detail-extra">Withdrawal request: ${last.state === "PENDING" ? "Pending" : last.state === "REJECT" ? "Rejected" : safe(last.state)} · Applicant ${safe(last.applicantId)} · Reason ${safe(last.reason)}${last.reviewerId ? ` · Reviewer ${safe(last.reviewerId)}` : ""}${last.decisionNote ? ` · Note ${safe(last.decisionNote)}` : ""}</p>`);
    }
    if (identity?.authenticated && identity.memberId === item.contributor_id && record?.withdrawalState !== "WITHDRAWN" && !record?.unwindRequest) {
      $("detail-content").insertAdjacentHTML("beforeend", `<form class="unwind-form" id="request-unwind"><label>Withdrawal reason<input name="reason" required maxlength="500"></label><button type="submit">Request withdrawal</button></form>`);
      $("request-unwind").addEventListener("submit", async (event) => {
        event.preventDefault();
        const reason = new FormData(event.currentTarget).get("reason");
        try { await request(`/api/contributions/${encodeURIComponent(id)}/unwind-requests`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason})}); await refresh(); loadDetail(id); }
        catch (error) { lifecycleMessage(error.message,true); }
      });
    }
    if (identity?.projects?.some((project) => project.id === projectId) && record?.unwindRequest && identity.memberId !== record.unwindRequest.applicantId) {
      $("detail-content").insertAdjacentHTML("beforeend", `<form class="unwind-form" id="decide-unwind"><label>Decision note<input name="note" maxlength="500"></label><button type="submit" name="decision" value="APPROVE">Approve withdrawal</button><button type="submit" name="decision" value="REJECT">Reject</button></form>`);
      $("decide-unwind").addEventListener("submit", async (event) => {
        event.preventDefault();
        const decision=event.submitter.value;
        const note=new FormData(event.currentTarget).get("note");
        if (decision === "REJECT" && !String(note).trim()) { lifecycleMessage("Enter a rejection reason.",true); return; }
        try { await request(`/api/contributions/${encodeURIComponent(id)}/unwind-requests/${encodeURIComponent(record.unwindRequest.id)}/decision`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,note})}); await refresh(); loadDetail(id); }
        catch (error) { lifecycleMessage(error.message,true); }
      });
    }
    if (record?.withdrawalState === "WITHDRAWN") $("detail-content").insertAdjacentHTML("beforeend", '<p class="detail-extra">Withdrawn, History is retained</p>');
    if (record?.tokenEventId) {
      const eventUrl = `/token.html?event=${encodeURIComponent(record.tokenEventId)}#activity`;
      $("detail-content").insertAdjacentHTML("beforeend", `<p class="detail-extra">Token: ${record.tokenFrozen ? "Currently frozen" : "Recorded"} · <a href="${safe(eventUrl)}">View ledger event #${record.tokenEventSequence}</a></p>`);
    } else if (record?.tokenPending) {
      $("detail-content").insertAdjacentHTML("beforeend", '<p class="detail-extra">Token mint pending. Open the <a href="/token.html#balances">Token Workspace</a> to Reconcile.</p>');
    }
  } catch (error) {
    if (selectedId === id) $("detail-content").textContent = language === "en" ? `Could not load details: ${error.message}` : `Could not load details: ${error.message}`;
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
  fillSelect("member-filter", data.members, t("All members"));
  fillSelect("task-filter", data.tasks, t("All tasks"));
  fillRequiredSelect("contributor-input", data.members, t("Select contributor"));
  const identity = window.HacKUAuth?.identity;
  if (identity?.authenticated) {
    const self = data.members.find((member) => member.id === identity.memberId);
    $("contributor-input").replaceChildren(...(self ? [new Option(self.name, self.id)] : []));
  }
  $("contributor-input").disabled = true;
  fillRequiredSelect("task-input", data.tasks, t("Select task"));
  fillSelect("helped-input", data.members, t("None"), "");
  $("project-name").textContent = data.project.name;
  const ownProject = window.HacKUAuth?.identity?.projects?.find((item) => item.id === data.project.id);
  $("invite-panel").hidden = !(ownProject?.admin || window.HacKUAuth?.identity?.siteAdmin);
  $("team-score").textContent = data.tokenRecognition
    ? tokenAmount(data.tokenRecognition.totalSupplyExact)
    : points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("team-score").previousElementSibling.textContent = data.tokenRecognition ? "Recognized Tokens" : t("Team score");
  $("team-score").nextElementSibling.textContent = data.tokenRecognition
    ? `Previous score ${points(data.members.reduce((sum, member) => sum + member.totalScore, 0))}; Awaiting Mint ${data.tokenRecognition.pendingContributions.length} records`
    : t("Verified and resolved contributions");
  const health = $("token-health");
  const pending = data.tokenRecognition?.pendingContributions ?? [];
  const missing = (data.tokenRecognition?.missingMembers?.length ?? 0) +
    (data.tokenRecognition?.missingTasks?.length ?? 0);
  health.hidden = !pending.length && !missing;
  if (!health.hidden) health.innerHTML = `Token ledger: ${pending.length} reviewed contributions await minting; ${missing} members or tasks await sync.<a href="/token.html#balances">Open Token Workspace</a>`;
  $("member-count").textContent = data.members.length;
  $("task-count").textContent = data.tasks.length;
  $("contribution-count").textContent = data.contributions.length;
  $("pending-count").textContent = `${data.contributions.filter((item) => item.status === "PENDING" || item.status === "DISPUTED").length} ${t("not scored")}`;
  renderInteractive();
  if (selectedId) loadDetail(selectedId);
  $("updated").textContent = `${language === "en" ? "Updated at" : "Updated at"} ${new Date().toLocaleTimeString(language === "en" ? "en-US" : "en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

$("invite-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  const memberId = new FormData(event.currentTarget).get("member_id");
  try {
    const result = await request(`/api/projects/${encodeURIComponent(projectId)}/invites`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({member_id:memberId}) });
    const expires = new Date(result.expiresAt * 1000).toLocaleString(language === "en" ? "en-US" : "en-US");
    $("invite-result").innerHTML = `<p>${language === "en" ? "One-use invitation; shown only now. Expires" : "One-use invitation; shown only now. Expires"}: ${safe(expires)}</p><input aria-label="Invitation link" readonly value="${safe(result.inviteUrl)}"><button type="button" data-copy-invite>${language === "en" ? "Copy link" : "Copy link"}</button><span data-copy-result role="status"></span>`;
    $("invite-result").hidden = false;
  } catch (error) { $("invite-result").textContent = error.message; $("invite-result").hidden = false; }
  finally { button.disabled = false; }
});
$("invite-result").addEventListener("click", async (event) => {
  if (!event.target.matches("[data-copy-invite]")) return;
  const input = $("invite-result").querySelector("input");
  try { await navigator.clipboard.writeText(input.value); $("invite-result").querySelector("[data-copy-result]").textContent = language === "en" ? "Copied." : "Copied."; }
  catch { input.focus(); input.select(); $("invite-result").querySelector("[data-copy-result]").textContent = language === "en" ? "Copy failed. Select and copy the link manually." : "Copy failed. Select and copy the link manually."; }
});

async function request(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options,
    headers: window.HacKUAuth?.headers(options?.headers) ?? options?.headers });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail ?? data.error;
    throw new Error(typeof detail === "string" ? detail : language === "en" ? `Request failed (${response.status})` : `Request failed (${response.status})`);
  }
  return data;
}

async function refresh() {
  $("refresh").disabled = true;
  $("error").hidden = true;
  try {
    const projects = await request("/api/projects");
    const requestedProject = new URLSearchParams(location.search).get("project");
    if (requestedProject && projects.some((item) => item.id === requestedProject)) projectId = requestedProject;
    if (!projects.some((item) => item.id === projectId)) projectId = projects[0]?.id ?? "";
    localStorage.setItem("contribution-project", projectId);
    $("project-select").replaceChildren(...projects.map((item) => new Option(item.name, item.id)));
    $("project-select").value = projectId;
    if (projectId) render(await request(`/api/projects/${encodeURIComponent(projectId)}/dashboard`));
    else {
      currentData = null;
      $("project-name").textContent = t("Create a project first");
      $("updated").textContent = t("No projects yet");
      for (const id of ["members","tasks","relationships","contributions","detail-content"]) $(id).replaceChildren();
      for (const id of ["team-score","member-count","task-count","contribution-count"]) $(id).textContent = "0";
      $("detail").hidden = true;
      $("token-health").hidden = true;
    }
    for (const id of ["member-form", "task-form", "contribution-form"]) {
      $(id).querySelector('button[type="submit"]').disabled = !projectId;
    }
    updateLifecycleActions();
    await renderLifecyclePanel();
  } catch (error) {
    $("error").textContent = language === "en" ? `Could not load project data: ${error.message}` : `Could not load project data: ${error.message}`;
    $("error").hidden = false;
    $("updated").textContent = t("Data load failed");
  } finally {
    $("refresh").disabled = false;
  }
}

function updateLifecycleActions() {
  const actions = document.querySelector(".top-actions");
  const identity = window.HacKUAuth?.identity;
  if (!actions || !identity?.authenticated || !projectId) return;
  document.getElementById("lifecycle-panel").hidden = false;
}
window.addEventListener("hacku:identity", () => { updateLifecycleActions(); renderLifecyclePanel(); });

async function renderLifecyclePanel() {
  const generation = ++lifecycleRenderGeneration;
  const identity = window.HacKUAuth?.identity;
  const panel = $("lifecycle-panel");
  panel.hidden = !identity?.authenticated;
  if (panel.hidden) return;
  const content = $("lifecycle-content");
  const active = identity.projects?.some((project) => project.id === projectId);
  const admin = identity.siteAdmin || identity.projects?.some((project) => project.id === projectId && project.admin);
  let exitPreview = null, archivePreview = null, outbox = [], archived = [];
  try {
    if (projectId && active) exitPreview = await request(`/api/projects/${encodeURIComponent(projectId)}/members/me/exit-preview`);
    if (projectId && admin) outbox = await request(`/api/projects/${encodeURIComponent(projectId)}/unwind-outbox`);
    if (projectId && identity.siteAdmin) archivePreview = await request(`/api/projects/${encodeURIComponent(projectId)}/archive-preview`);
    if (identity.siteAdmin) {
      archived = await request("/api/admin/projects?state=archived");
      archived = await Promise.all(archived.map(async (item) => ({...item, detail: await request(`/api/admin/projects/${encodeURIComponent(item.id)}`)})));
    }
  } catch (error) { lifecycleMessage(error.message, true); }
  if (generation !== lifecycleRenderGeneration) return;
  const pending = outbox.filter((item) => item.state === "PENDING");
  content.innerHTML = `
    ${exitPreview ? `<div class="lifecycle-card"><h3>Exit preview</h3><p>My effective contributions ${exitPreview.contributions.filter((item) => Number(item.score) > 0).length} records · Available balance ${safe(exitPreview.balance)} Token · Frozen ${safe(exitPreview.frozen)} · Existing debts ${exitPreview.debts.length} entries</p><p>Currently to recover ${safe(exitPreview.recognizedToRecoverExact)} Token · Estimated shortfall ${safe(exitPreview.estimatedShortfallExact)} Token; Actual amounts depend on ledger reconciliation after approval.</p><p>Contribution list: ${exitPreview.contributions.map((item) => `${safe(item.id)}(${safe(item.score)} pts)`).join(", ") || "None"}</p>${exitPreview.blockers.length ? `<p class="lifecycle-blockers">Resolve before approval: ${exitPreview.blockers.map(safe).join("; ")}</p>` : ""}${!exitPreview.pendingRequest ? `<form data-lifecycle="exit"><label>Exit reason<input name="reason" required></label><button type="submit">Submit exit request</button></form>` : `<p class="lifecycle-state">Request submitted; waiting for another active member to approve.</p>`}</div>` : ""}
    ${admin && projectId ? `<div class="lifecycle-card"><h3>Withdrawal accounting</h3><p>${pending.length ? `${pending.length} recordsAwaiting sync; Complete recovery or accounting before archiving.` : "No withdrawal accounting is awaiting sync."}</p>${pending.map((item) => `<p class="lifecycle-blockers">${safe(item.id)}: ${safe(item.detail || "Pending")}</p>`).join("")}<button type="button" data-lifecycle-retry ${pending.length ? "" : "disabled"}>Retry accounting reconciliation</button></div>` : ""}
    ${archivePreview ? `<div class="lifecycle-card"><h3>Archive preview</h3><p>Project ${safe(archivePreview.projectName)}(${safe(archivePreview.projectId)}) · Data version ${archivePreview.version} · Members ${archivePreview.counts.members} · Contribution ${archivePreview.counts.contributions} · Ledger Events ${archivePreview.tokenLedger.eventCount}</p><p>Balances: ${Object.entries(archivePreview.tokenLedger.balances).map(([member, amount]) => `${safe(member)} ${safe(amount)}`).join(", ") || "None"}</p><p>Debts ${archivePreview.tokenLedger.debts.length} entries · Pending withdrawals ${archivePreview.counts.pendingWithdrawals} · Pending exits ${archivePreview.counts.pendingExits} · Pending reconciliation ${archivePreview.counts.pendingOutbox} · Unsettled contracts ${archivePreview.tokenLedger.unsettledContracts.length}</p><p class="lifecycle-state">Archives can be restored; all member, contribution, audit, and ledger records are retained.</p><form data-lifecycle="archive" data-version="${archivePreview.version}"><label>Enter project ID to confirm<input name="project_id" required autocomplete="off"></label><label>Archive reason<input name="reason" required></label><button type="submit" ${archivePreview.counts.pendingOutbox ? "disabled" : ""}>Archive project</button></form></div>` : ""}
    ${identity.siteAdmin ? `<div class="lifecycle-card"><h3>Archived projects</h3>${archived.length ? archived.map((item) => { const snapshot=item.detail.archiveSnapshots.at(-1)?.payload; return `<details><summary>${safe(item.name)} · ${safe(item.id)} · Version ${item.version}</summary><p>Historical contributions ${item.detail.dashboard.contributions.length} records · Ledger Events ${snapshot?.tokenLedger?.eventCount ?? 0} records</p><p>Debts at archive: ${snapshot?.tokenLedger?.debts?.length ? snapshot.tokenLedger.debts.map((debt) => `${safe(debt.debtorId)} owes ${safe(debt.remainingExact)}`).join("; ") : "None"}</p><p>Balances at archive: ${snapshot?.tokenLedger?.balances ? Object.entries(snapshot.tokenLedger.balances).map(([member, amount]) => `${safe(member)} ${safe(amount)}`).join(", ") : "None"}</p><form data-lifecycle="restore" data-project="${safe(item.id)}"><label>Restoration reason<input name="reason" required></label><button type="submit">Restore project</button></form></details>`; }).join("") : "<p>No archived projects yet.</p>"}</div>` : ""}`;
}

function lifecycleMessage(message, error = false) {
  const element = $("lifecycle-message");
  element.hidden = false;
  element.className = `form-message${error ? " is-error" : ""}`;
  element.textContent = message;
}

$("lifecycle-content").addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-lifecycle]");
  if (!form) return;
  event.preventDefault();
  if (form.dataset.submitting) return;
  form.dataset.submitting = "true";
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  form.setAttribute("aria-busy", "true");
  const operation = form.dataset.lifecycle;
  const values = Object.fromEntries(new FormData(form));
  const id = operation === "restore" ? form.dataset.project : projectId;
  if (operation === "archive" && values.project_id !== id) { lifecycleMessage("Project ID does not match.", true); button.disabled = false; form.removeAttribute("data-submitting"); form.setAttribute("aria-busy", "false"); return; }
  const endpoint = operation === "exit" ? `/api/projects/${encodeURIComponent(id)}/members/me/exit-requests` : `/api/projects/${encodeURIComponent(id)}/${operation}`;
  if (operation === "archive") values.version = Number(form.dataset.version);
  try {
    await request(endpoint, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(values)});
    lifecycleMessage(operation === "exit" ? "Exit request submitted." : operation === "archive" ? "Project archived." : "Project restored.");
    await window.HacKUAuth?.refresh();
    await refresh();
    await renderLifecyclePanel();
  } catch (error) {
    const detail = error.message.toLowerCase();
    lifecycleMessage(detail.includes("version") ? "Project data changed. Reload the archive preview before submitting." : detail.includes("outbox") || detail.includes("reconcil") ? "Accounting is still pending. Retry withdrawal reconciliation, then refresh the preview." : error.message, true);
  } finally { button.disabled = false; form.removeAttribute("data-submitting"); form.setAttribute("aria-busy", "false"); }
});
$("lifecycle-content").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-lifecycle-retry]");
  if (!button || button.disabled) return;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const result = await request(`/api/projects/${encodeURIComponent(projectId)}/unwind-outbox/reconcile`, {method:"POST",body:"{}"});
    lifecycleMessage(result.some((item) => item.state === "PENDING") ? "Accounting still awaits sync. Check the reported reason." : "Accounting reconciliation complete.");
    await refresh();
  } catch (error) { lifecycleMessage(error.message, true); }
  finally { button.disabled = false; button.setAttribute("aria-busy", "false"); }
});

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
    message.dataset.source = "Saved. The page is up to date.";
    message.textContent = t(message.dataset.source);
    message.className = "form-message";
  } catch (error) {
    message.dataset.source = "";
    message.textContent = language === "en" ? `Could not save: ${error.message}` : `Could not save: ${error.message}`;
    message.className = "form-message is-error";
  } finally {
    message.hidden = false;
    button.disabled = false;
  }
}

$("refresh").addEventListener("click", refresh);
$("language-select")?.addEventListener("change", (event) => setLanguage(event.target.value));
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
  const removeMember = event.target.closest("[data-remove-member]");
  if (removeMember) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm(language === "en" ? `Remove ${removeMember.dataset.removeMember} from this project? The account and history remain. Members with contributions must use the exit request.` : `Remove ${removeMember.dataset.removeMember} from this project? The account and history remain. Members with contributions must use an exit request.`)) return;
    const path = "/api/projects/" + encodeURIComponent(projectId) + "/members/" + encodeURIComponent(removeMember.dataset.removeMember);
    request(path, { method: "DELETE", body: "{}" })
      .then(async () => { window.alert(t("Member removed from this project.")); await refresh(); })
      .catch((error) => window.alert(`${error.message}\n${language === "en" ? "For contribution history, use the exit request in Project lifecycle." : "For contribution history, use the exit request in Project lifecycle."}`));
    return;
  }
  const exitDecision=event.target.closest("[data-exit-decision]");
  const cancelExit=event.target.closest("[data-cancel-exit]");
  if(exitDecision){
    event.preventDefault(); event.stopPropagation();
    const decision=exitDecision.dataset.exitDecision;
    const promptText=decision==="APPROVE"?"Approval withdraws the listed effective contributions and settles project Tokens. Approve?":"Enter a rejection reason";
    if(decision==="APPROVE"&&!window.confirm(promptText))return;
    const note=decision==="APPROVE"?"":window.prompt(promptText);
    if(decision==="REJECT"&&!note?.trim())return;
    request(`/api/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(exitDecision.dataset.member)}/exit-requests/${encodeURIComponent(exitDecision.dataset.request)}/decision`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,note})}).then(async(result)=>{window.alert(result.accountingState==="COMPLETE"?"Member exited; accounting completed.":"Member exited; accounting awaits sync. A site administrator can retry.");await refresh();}).catch((error)=>window.alert(error.message));
    return;
  }
  if(cancelExit){
    event.preventDefault(); event.stopPropagation();
    request(`/api/projects/${encodeURIComponent(projectId)}/members/me/exit-requests/${encodeURIComponent(cancelExit.dataset.request)}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}).then(refresh).catch((error)=>window.alert(error.message));
    return;
  }
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
  // Disabled controls are omitted from FormData. The contributor is the signed-in member.
  payload.contributor_id = window.HacKUAuth?.identity?.memberId || "";
  if (!payload.contributor_id) {
    $("form-message").textContent = language === "en" ? "Log in before submitting a contribution." : "Log in before submitting a contribution.";
    $("form-message").className = "form-message is-error";
    $("form-message").hidden = false;
    return;
  }
  if (payload.contributor_id === payload.helped_member_id) {
    $("form-message").dataset.source = "The helped member must differ from the contributor.";
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
window.addEventListener("focus", async () => { await window.HacKUAuth?.refresh(); await refresh(); });
refresh();
