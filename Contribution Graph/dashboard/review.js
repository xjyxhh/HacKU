const statusNames = { PENDING: "Pending", VERIFIED: "Verified", DISPUTED: "Disputed", RESOLVED: "Resolved" };
const typeNames = { CORE: "Core", SUPPORT: "Support", REVIEW: "Review", COORDINATION: "Coordination" };
const decisionNames = { CONFIRM: "Confirm", ADJUST: "Adjust", DISPUTE: "Raise dispute" };
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat(I18n.language === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: 2 }).format(value ?? 0);
const state = { dashboard: null, detail: null, selectedId: null, busy: false, preview: null };

async function request(path, body) {
  const response = await fetch(path, {
    cache: "no-store",
    ...(body === undefined ? {} : { method: "POST", headers: window.HacKUAuth?.headers({ "Content-Type": "application/json" }) ?? { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) {
    // FastAPI's schema errors contain an array; business errors contain a string.
    const detail = data.detail ?? data.error;
    const message = Array.isArray(detail)
      ? detail.map((item) => `${item.loc?.slice(1).join(".") || "Input"}: ${item.msg}`).join("; ")
      : detail || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

function showError(message) { $("error").textContent = message; $("error").hidden = false; }
function actionError(error) {
  const hint = error.status === 401 ? "会话已过期，请重新登录。" : error.status === 403 ? "当前身份无此项目或操作权限，请检查登录身份与项目。" : error.status === 409 ? "记录已变化，请刷新数据后重试。" : "";
  return `${hint}${hint ? " " : ""}${error.message}`;
}
function clearMessages() { $("error").hidden = true; $("success").hidden = true; }
function memberName(id) { return state.dashboard?.members.find((member) => member.id === id)?.name ?? id; }
function taskName(id) { return state.dashboard?.tasks.find((task) => task.id === id)?.name ?? id; }
function visibleContributions() {
  return (state.dashboard?.contributions ?? []).filter((item) => $("status-filter").value === "ALL" || ($("status-filter").value === "WITHDRAWN" ? item.withdrawalState === "WITHDRAWN" : item.status === $("status-filter").value && item.withdrawalState !== "WITHDRAWN"));
}

function renderProject() {
  const data = state.dashboard;
  const previousActor = $("actor").value;
  const signedIn = window.HacKUAuth?.identity;
  const availableActors = signedIn?.authenticated ? data.members.filter((member) => member.id === signedIn.memberId) : [];
  $("actor").innerHTML = availableActors.map((member) => `<option value="${safe(member.id)}">${safe(member.name)}</option>`).join("");
  if (availableActors.some((member) => member.id === previousActor)) $("actor").value = previousActor;
  $("actor").disabled = true;
  $("project-name").textContent = data.project.name;
  $("team-score").textContent = points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("pending-count").textContent = data.contributions.filter((item) => item.status === "PENDING").length;
  $("disputed-count").textContent = data.contributions.filter((item) => item.status === "DISPUTED").length;
  $("contribution-count").textContent = data.contributions.length;
  updateTimestamp();
  renderList();
}
function updateTimestamp() {
  $("updated").textContent = `Updated at ${new Intl.DateTimeFormat("en-US", { timeStyle: "medium" }).format(new Date())}`;
}

function renderList() {
  const rows = visibleContributions();
  $("queue-empty").hidden = rows.length > 0;
  $("contribution-list").innerHTML = rows.map((item) => `
    <button class="queue-item" type="button" data-id="${safe(item.id)}" aria-pressed="${item.id === state.selectedId}" ${state.busy ? "disabled" : ""}>
      <span class="queue-top"><strong>${safe(memberName(item.contributorId))} · ${safe(item.id)}</strong><span class="status ${item.withdrawalState === "WITHDRAWN" ? "withdrawn" : item.status.toLowerCase()}">${item.withdrawalState === "WITHDRAWN" ? "已撤回" : statusNames[item.status]}</span></span>
      <span class="type">${typeNames[item.type]}</span><div class="task-name">${safe(taskName(item.taskId))}</div><div class="queue-description">${safe(item.description)}</div>
      <div class="queue-score">${item.withdrawalState === "WITHDRAWN" ? `有效分 0 · 原审核 ${statusNames[item.status]}` : item.status === "PENDING" || item.status === "DISPUTED" ? "Not scored" : `Current: ${points(item.score)} pts`}</div>
    </button>`).join("");
}

function evidenceReference(item) {
  if (item.kind !== "NOTE") {
    try {
      const url = new URL(item.reference);
      if (url.protocol === "https:" || url.protocol === "http:") {
        return `<a href="${safe(url.href)}" target="_blank" rel="noopener noreferrer">${safe(item.reference)}</a>`;
      }
    } catch { /* Plain text is still a valid stored reference. */ }
  }
  return safe(item.reference);
}

function renderDetail() {
  const data = state.detail;
  $("detail-content").hidden = !data;
  $("detail-empty").hidden = !!data;
  if (!data) { updateControls(); return; }
  const item = data.contribution;
  $("contribution-id").textContent = `${memberName(item.contributor_id)} · ${item.id}`;
  $("contribution-status").textContent = data.withdrawal ? "已撤回" : statusNames[item.status];
  $("contribution-status").className = `status ${data.withdrawal ? "withdrawn" : item.status.toLowerCase()}`;
  $("description").textContent = item.description;
  const meta = [
    ["Related task", data.task.name], ["Contribution type", typeNames[item.type]],
    ["Helped member", item.helped_member_id ? memberName(item.helped_member_id) : "Not specified"],
    ["原审核状态", statusNames[item.status]], ["原分数 / 有效分", `${points(data.originalScore)} / ${points(data.currentScore)}`],
    ["Task value", `${points(data.task.taskValue)} pts`], ["Completion", item.completion],
    ["Support value", `${points(item.support_value)} pts`], ["Quality factor", item.quality],
    ["Proposed / final score", `${points(data.proposedScore)} pts`], ["Current team score", `${points(data.currentScore)} pts`],
  ];
  $("contribution-meta").innerHTML = meta.map(([label, value]) => `<dt>${safe(label)}</dt><dd>${safe(value)}</dd>`).join("");
  $("score-explanation").textContent = data.withdrawal ? `已撤回，有效分 0。申请人 ${data.withdrawal.applicantId}；审批人 ${data.withdrawal.reviewerId || "待处理"}；原因：${data.withdrawal.reason}；决定：${data.withdrawal.decisionNote || "无"}。证据与原审核历史保留。`
    : item.status === "PENDING" || item.status === "DISPUTED"
    ? "This contribution is not scored yet. The proposed score can count after verification or dispute resolution."
    : "The current score counts toward member totals and the team share.";
  $("evidence-list").innerHTML = data.evidence.length ? data.evidence.map((evidence) => `<li><span class="record-meta">${safe(memberName(evidence.submitted_by))} · ${safe(evidence.kind)}</span>${evidenceReference(evidence)}</li>`).join("") : '<li class="empty">No evidence yet.</li>';
  $("verification-list").innerHTML = data.verifications.length ? data.verifications.map((review) => `<li><span class="record-meta">${safe(memberName(review.reviewer_id))} · ${decisionNames[review.decision]}</span>${safe(review.note || "No note provided")}</li>`).join("") : '<li class="empty">No review history yet.</li>';
  $("dispute-list").innerHTML = data.disputes.length ? data.disputes.map((dispute) => `<li><span class="record-meta">${safe(memberName(dispute.raised_by))} · ${dispute.resolution === null ? "Unresolved" : "Resolved"}</span>Reason: ${safe(dispute.reason)}${dispute.resolution === null ? "" : `<br>Resolution: ${safe(dispute.resolution)}<br>Resolved by: ${safe(memberName(dispute.resolved_by))}`}</li>`).join("") : '<li class="empty">No dispute history yet.</li>';
  $("completion").value = item.completion;
  $("support-value").value = item.support_value;
  $("quality").value = item.quality;
  $("completion-label").hidden = item.type !== "CORE";
  $("support-label").hidden = item.type === "CORE";
  $("review-note").value = "";
  $("evidence-reference").value = "";
  invalidatePreview();
}

function scoreChanges() {
  if (!state.detail) return {};
  const item = state.detail.contribution;
  const fields = item.type === "CORE" ? [["completion", "completion"], ["quality", "quality"]] : [["support_value", "support-value"], ["quality", "quality"]];
  return Object.fromEntries(fields.filter(([key, id]) => $(id).value.trim() === "" || Number($(id).value) !== Number(item[key])).map(([key, id]) => [key, $(id).value]));
}

function updateControls() {
  const item = state.detail?.contribution;
  const hasActor = !!$("actor").value;
  const self = item?.contributor_id === $("actor").value;
  const pending = item?.status === "PENDING";
  const disputed = item?.status === "DISPUTED";
  const editable = !!item && hasActor && !self && (pending || disputed);
  const locked = state.busy || !item || !hasActor || !!state.detail?.withdrawal;
  $("refresh").disabled = state.busy;
  $("actor").disabled = true;
  $("status-filter").disabled = state.busy || !state.dashboard;
  for (const button of document.querySelectorAll(".queue-item")) button.disabled = state.busy;
  $("evidence-kind").disabled = locked;
  $("evidence-reference").disabled = locked;
  $("add-evidence").disabled = locked;
  $("review-note").disabled = locked || item.status === "RESOLVED";
  $("completion").disabled = state.busy || !editable || item.type !== "CORE";
  $("support-value").disabled = state.busy || !editable || item.type === "CORE";
  $("quality").disabled = state.busy || !editable;
  $("preview").disabled = state.busy || !editable;
  $("confirm").disabled = locked || self || !pending || Object.keys(scoreChanges()).length > 0;
  $("adjust").disabled = locked || self || !pending || !state.preview?.scoreChanged;
  $("dispute").disabled = locked || !(pending || item?.status === "VERIFIED");
  $("resolve").disabled = locked || self || !disputed || !state.preview;
  $("action-hint").textContent = !item ? "" : state.detail?.withdrawal ? "已撤回：仅保留历史，不能再次审核或计分。" : item.status === "RESOLVED" ? "This dispute is resolved. Review the final result and history."
    : self ? "You cannot confirm, adjust, or resolve your own contribution. You can add evidence or raise a dispute."
    : pending ? "Confirm the proposed score directly, or preview an adjustment that changes it."
    : disputed ? "Enter a resolution and preview the final score before submitting."
    : "This contribution is verified. Enter a reason to raise a dispute if needed.";
}

function setBusy(value) {
  state.busy = value;
  document.querySelector(".detail-panel").setAttribute("aria-busy", String(value));
  updateControls();
}

function invalidatePreview() {
  state.preview = null;
  $("preview-result").textContent = "Preview the score before submitting changes.";
  updateControls();
}

async function reloadData() {
  state.detail = null;
  renderDetail();
  const projects = await request("/api/projects");
  const preferred = localStorage.getItem("contribution-project") || "fintech";
  const requestedProject = new URLSearchParams(location.search).get("project");
  const projectId = projects.some((project) => project.id === requestedProject) ? requestedProject
    : projects.some((project) => project.id === preferred) ? preferred : projects[0]?.id;
  $("review-project").replaceChildren(...projects.map((project) => new Option(project.name, project.id)));
  if (!projectId) {
    state.dashboard = null;
    $("project-name").innerHTML = '暂无项目。请由站点管理员先在<a href="/">项目看板</a>创建项目。';
    $("contribution-list").replaceChildren();
    $("queue-empty").hidden = false;
    return;
  }
  $("review-project").value = projectId;
  localStorage.setItem("contribution-project", projectId);
  state.dashboard = await request(`/api/projects/${encodeURIComponent(projectId)}/dashboard`);
  const rows = visibleContributions();
  const requestedContribution = new URLSearchParams(location.search).get("contribution");
  state.selectedId = rows.some((item) => item.id === requestedContribution) ? requestedContribution
    : rows.some((item) => item.id === state.selectedId) ? state.selectedId : rows[0]?.id ?? null;
  renderProject();
  if (state.selectedId) state.detail = await request(`/api/contributions/${encodeURIComponent(state.selectedId)}`);
  renderDetail();
}

async function refresh() {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  try { await reloadData(); }
  catch (error) { showError(`Could not load data: ${actionError(error)}`); }
  finally { setBusy(false); }
}

async function selectContribution(id) {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  state.selectedId = id; state.detail = null;
  renderList(); renderDetail();
  try { state.detail = await request(`/api/contributions/${encodeURIComponent(id)}`); renderDetail(); }
  catch (error) { showError(`Could not load details: ${actionError(error)}`); }
  finally { setBusy(false); }
}

async function mutate(suffix, body, label) {
  if (state.busy || !state.detail) return;
  clearMessages(); setBusy(true);
  const id = state.selectedId;
  let saved = false;
  try {
    const result = await request(`/api/contributions/${encodeURIComponent(id)}/${suffix}`, body);
    saved = true;
    // Storage events notify other tabs. Every score shown here is re-read from the backend.
    try { localStorage.setItem("contribution-graph-update", `${Date.now()}-${Math.random()}`); } catch { /* Manual refresh remains available. */ }
    await reloadData();
    const token = result.tokenMint ?? result.tokenFrozen ?? result.tokenResolved;
    const tokenNote = token?.skipped ? ` Token processing incomplete: ${token.skipped}.`
      : token?.kind === "DIRECT" || token?.kind === "COMMISSION" ? ` ${points(token.amount)} Tokens created.`
        : token?.kind === "FREEZE" ? " Related Tokens are frozen."
          : token?.finalAmount !== undefined && /[1-9]/.test(token?.correction?.debtExact ?? "0")
            ? ` Tokens processed; ${token.correction.debtExact} remains due. Check the Token Workspace.`
            : token?.finalAmount !== undefined ? ` Tokens updated to the final score of ${points(token.finalAmount)}.` : "";
    $("success").textContent = `${id}: ${label} saved. Team score: ${$("team-score").textContent} pts.${tokenNote}`;
    $("success").hidden = false;
  } catch (error) {
    if (saved) { state.detail = null; renderDetail(); }
    showError(saved ? `Action saved, but refresh failed: ${actionError(error)}. Select Refresh Data.` : `Action failed: ${actionError(error)}`);
  } finally { setBusy(false); }
}

async function review(decision) {
  if (state.busy || !state.detail) return;
  const note = $("review-note").value.trim();
  if (decision === "DISPUTE" && !note) { showError("Enter a dispute reason."); $("review-note").focus(); return; }
  if (decision === "ADJUST" && (!state.preview?.scoreChanged || !$("score-form").reportValidity())) return;
  await mutate("reviews", { reviewer_id: $("actor").value, decision, note, ...(decision === "ADJUST" ? scoreChanges() : {}) }, decisionNames[decision]);
}

$("refresh").addEventListener("click", refresh);
$("review-project").addEventListener("change", () => {
  localStorage.setItem("contribution-project", $("review-project").value);
  state.selectedId = null;
  refresh();
});
$("status-filter").addEventListener("change", refresh);
$("actor").addEventListener("change", () => { clearMessages(); invalidatePreview(); });
$("contribution-list").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-id]");
  if (button) selectContribution(button.dataset.id);
});
for (const id of ["completion", "support-value", "quality"]) $(id).addEventListener("input", invalidatePreview);
$("evidence-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const reference = $("evidence-reference").value.trim();
  if (!reference) { showError("Enter an evidence note or link."); return; }
  await mutate("evidence", { submitted_by: $("actor").value, kind: $("evidence-kind").value, reference }, "Add evidence");
});
$("score-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy || !state.detail) return;
  clearMessages(); setBusy(true);
  try {
    state.preview = await request(`/api/contributions/${encodeURIComponent(state.selectedId)}/preview`, scoreChanges());
    $("preview-result").textContent = `Proposed / previous final score ${points(state.preview.proposedScore)} → ${points(state.preview.updatedScore)} pts; current team score ${points(state.preview.currentScore)} pts. ${state.detail.contribution.status === "PENDING" && !state.preview.scoreChanged ? "The score is unchanged; you can confirm directly." : "Preview not saved."}`;
  } catch (error) { state.preview = null; showError(`Could not preview score: ${error.message}`); }
  finally { setBusy(false); }
});
$("confirm").addEventListener("click", () => review("CONFIRM"));
$("adjust").addEventListener("click", () => review("ADJUST"));
$("dispute").addEventListener("click", () => review("DISPUTE"));
$("resolve").addEventListener("click", async () => {
  const resolution = $("review-note").value.trim();
  if (!resolution) { showError("Enter a resolution."); $("review-note").focus(); return; }
  if (!state.preview || !$("score-form").reportValidity()) return;
  await mutate("resolve", { resolved_by: $("actor").value, resolution, ...scoreChanges() }, "Resolve dispute");
});
refresh();
window.addEventListener("focus", refresh);
window.addEventListener("storage", (event) => {
  if (event.key === "contribution-graph-update" || event.key === "contribution-project") refresh();
});
document.addEventListener("languagechange", () => { if (state.dashboard) updateTimestamp(); });
