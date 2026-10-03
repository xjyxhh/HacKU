const statusNames = { PENDING: "待验证", VERIFIED: "已验证", DISPUTED: "争议中", RESOLVED: "已解决" };
const typeNames = { CORE: "核心", SUPPORT: "支持", REVIEW: "审查", COORDINATION: "协调" };
const decisionNames = { CONFIRM: "确认", ADJUST: "调整", DISPUTE: "提出争议" };
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value ?? 0);
const state = { dashboard: null, detail: null, selectedId: null, busy: false, preview: null };

async function request(path, body) {
  let key = sessionStorage.getItem("tokenAdminKey") || "";
  const send = () => fetch(path, {
    cache: "no-store",
    ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", ...(key ? { "X-Token-Admin-Key": key } : {}) }, body: JSON.stringify(body) }),
  });
  let response = await send();
  if (response.status === 403 && body !== undefined) {
    sessionStorage.removeItem("tokenAdminKey");
    key = prompt("请输入账本管理员密钥") || "";
    if (key) { sessionStorage.setItem("tokenAdminKey", key); response = await send(); }
  }
  const data = await response.json();
  if (!response.ok) {
    // FastAPI's schema errors contain an array; business errors contain a string.
    const detail = data.detail ?? data.error;
    const message = Array.isArray(detail)
      ? detail.map((item) => `${item.loc?.slice(1).join(".") || "输入"}：${item.msg}`).join("；")
      : detail || `请求失败 (${response.status})`;
    throw new Error(message);
  }
  return data;
}

function showError(message) { $("error").textContent = message; $("error").hidden = false; }
function clearMessages() { $("error").hidden = true; $("success").hidden = true; }
function memberName(id) { return state.dashboard?.members.find((member) => member.id === id)?.name ?? id; }
function taskName(id) { return state.dashboard?.tasks.find((task) => task.id === id)?.name ?? id; }
function visibleContributions() {
  return (state.dashboard?.contributions ?? []).filter((item) => $("status-filter").value === "ALL" || item.status === $("status-filter").value);
}

function renderProject() {
  const data = state.dashboard;
  const previousActor = $("actor").value;
  $("actor").innerHTML = data.members.map((member) => `<option value="${safe(member.id)}">${safe(member.name)}</option>`).join("");
  if (data.members.some((member) => member.id === previousActor)) $("actor").value = previousActor;
  $("project-name").textContent = data.project.name;
  $("team-score").textContent = points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("pending-count").textContent = data.contributions.filter((item) => item.status === "PENDING").length;
  $("disputed-count").textContent = data.contributions.filter((item) => item.status === "DISPUTED").length;
  $("contribution-count").textContent = data.contributions.length;
  $("updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN")}`;
  renderList();
}

function renderList() {
  const rows = visibleContributions();
  $("queue-empty").hidden = rows.length > 0;
  $("contribution-list").innerHTML = rows.map((item) => `
    <button class="queue-item" type="button" data-id="${safe(item.id)}" aria-pressed="${item.id === state.selectedId}" ${state.busy ? "disabled" : ""}>
      <span class="queue-top"><strong>${safe(memberName(item.contributorId))} · ${safe(item.id)}</strong><span class="status ${item.status.toLowerCase()}">${statusNames[item.status]}</span></span>
      <span class="type">${typeNames[item.type]}</span><div class="task-name">${safe(taskName(item.taskId))}</div><div class="queue-description">${safe(item.description)}</div>
      <div class="queue-score">${item.status === "PENDING" || item.status === "DISPUTED" ? "暂不计分" : `当前 ${points(item.score)} 分`}</div>
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
  $("contribution-status").textContent = statusNames[item.status];
  $("contribution-status").className = `status ${item.status.toLowerCase()}`;
  $("description").textContent = item.description;
  const meta = [
    ["关联任务", data.task.name], ["贡献类型", typeNames[item.type]],
    ["帮助对象", item.helped_member_id ? memberName(item.helped_member_id) : "未指定"],
    ["任务价值", `${points(data.task.taskValue)} 分`], ["完成比例", item.completion],
    ["支持分值", `${points(item.support_value)} 分`], ["质量系数", item.quality],
    ["提议 / 最终分值", `${points(data.proposedScore)} 分`], ["当前计入团队", `${points(data.currentScore)} 分`],
  ];
  $("contribution-meta").innerHTML = meta.map(([label, value]) => `<dt>${safe(label)}</dt><dd>${safe(value)}</dd>`).join("");
  $("score-explanation").textContent = item.status === "PENDING" || item.status === "DISPUTED"
    ? "这条贡献暂不计分。提议分值表示通过验证或解决争议后可计入的分数。"
    : "当前分数已计入成员总分和团队贡献占比。";
  $("evidence-list").innerHTML = data.evidence.length ? data.evidence.map((evidence) => `<li><span class="record-meta">${safe(memberName(evidence.submitted_by))} · ${safe(evidence.kind)}</span>${evidenceReference(evidence)}</li>`).join("") : '<li class="empty">暂无证据。</li>';
  $("verification-list").innerHTML = data.verifications.length ? data.verifications.map((review) => `<li><span class="record-meta">${safe(memberName(review.reviewer_id))} · ${decisionNames[review.decision]}</span>${safe(review.note || "未填写说明")}</li>`).join("") : '<li class="empty">暂无审核记录。</li>';
  $("dispute-list").innerHTML = data.disputes.length ? data.disputes.map((dispute) => `<li><span class="record-meta">${safe(memberName(dispute.raised_by))} · ${dispute.resolution === null ? "尚未解决" : "已解决"}</span>原因：${safe(dispute.reason)}${dispute.resolution === null ? "" : `<br>结论：${safe(dispute.resolution)}<br>解决者：${safe(memberName(dispute.resolved_by))}`}</li>`).join("") : '<li class="empty">暂无争议记录。</li>';
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
  const locked = state.busy || !item || !hasActor;
  $("refresh").disabled = state.busy;
  $("actor").disabled = state.busy || !(state.dashboard?.members.length);
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
  $("action-hint").textContent = !item ? "" : item.status === "RESOLVED" ? "争议已解决，可查看最终结果和处理记录。"
    : self ? "不能确认、调整或解决自己的贡献；可以添加证据或提出争议。"
    : pending ? "直接确认现有提议分值；调整时先预览，分数必须实际变化。"
    : disputed ? "填写解决结论并预览最终分数，再提交解决结果。"
    : "贡献已验证；如需重新核实，填写原因后提出争议。";
}

function setBusy(value) {
  state.busy = value;
  document.querySelector(".detail-panel").setAttribute("aria-busy", String(value));
  updateControls();
}

function invalidatePreview() {
  state.preview = null;
  $("preview-result").textContent = "修改分值后先预览，再提交。";
  updateControls();
}

async function reloadData() {
  state.detail = null;
  renderDetail();
  const projects = await request("/api/projects");
  const preferred = localStorage.getItem("contribution-project") || "fintech";
  const projectId = projects.some((project) => project.id === preferred)
    ? preferred : projects[0]?.id;
  $("review-project").replaceChildren(...projects.map((project) => new Option(project.name, project.id)));
  if (!projectId) throw new Error("尚无项目");
  $("review-project").value = projectId;
  state.dashboard = await request(`/api/projects/${encodeURIComponent(projectId)}/dashboard`);
  const rows = visibleContributions();
  if (!rows.some((item) => item.id === state.selectedId)) state.selectedId = rows[0]?.id ?? null;
  renderProject();
  if (state.selectedId) state.detail = await request(`/api/contributions/${encodeURIComponent(state.selectedId)}`);
  renderDetail();
}

async function refresh() {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  try { await reloadData(); }
  catch (error) { showError(`读取失败：${error.message}`); }
  finally { setBusy(false); }
}

async function selectContribution(id) {
  if (state.busy) return;
  clearMessages(); setBusy(true);
  state.selectedId = id; state.detail = null;
  renderList(); renderDetail();
  try { state.detail = await request(`/api/contributions/${encodeURIComponent(id)}`); renderDetail(); }
  catch (error) { showError(`读取详情失败：${error.message}`); }
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
    const tokenNote = token?.skipped ? ` Token 处理未完成：${token.skipped}。`
      : token?.kind === "DIRECT" || token?.kind === "COMMISSION" ? ` 已生成 ${points(token.amount)} Token。`
        : token?.kind === "FREEZE" ? " 关联 Token 已冻结。"
          : token?.finalAmount !== undefined && /[1-9]/.test(token?.correction?.debtExact ?? "0")
            ? ` Token 已处理，仍有 ${token.correction.debtExact} 待追偿；请到 Token 工作台查看。`
            : token?.finalAmount !== undefined ? ` Token 已按最终分值 ${points(token.finalAmount)} 更新。` : "";
    $("success").textContent = `${id}：${label}，数据已保存。团队总分 ${$("team-score").textContent} 分。${tokenNote}`;
    $("success").hidden = false;
  } catch (error) {
    if (saved) { state.detail = null; renderDetail(); }
    showError(saved ? `操作已保存，但刷新失败：${error.message}。请点击刷新数据。` : `操作失败：${error.message}`);
  } finally { setBusy(false); }
}

async function review(decision) {
  if (state.busy || !state.detail) return;
  const note = $("review-note").value.trim();
  if (decision === "DISPUTE" && !note) { showError("请填写争议原因。"); $("review-note").focus(); return; }
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
  if (!reference) { showError("请填写证据说明或链接。"); return; }
  await mutate("evidence", { submitted_by: $("actor").value, kind: $("evidence-kind").value, reference }, "添加证据");
});
$("score-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy || !state.detail) return;
  clearMessages(); setBusy(true);
  try {
    state.preview = await request(`/api/contributions/${encodeURIComponent(state.selectedId)}/preview`, scoreChanges());
    $("preview-result").textContent = `提议 / 原最终分值 ${points(state.preview.proposedScore)} → ${points(state.preview.updatedScore)} 分；当前计入 ${points(state.preview.currentScore)} 分。${state.detail.contribution.status === "PENDING" && !state.preview.scoreChanged ? "分数未变化，可直接确认。" : "预览尚未保存。"}`;
  } catch (error) { state.preview = null; showError(`预览失败：${error.message}`); }
  finally { setBusy(false); }
});
$("confirm").addEventListener("click", () => review("CONFIRM"));
$("adjust").addEventListener("click", () => review("ADJUST"));
$("dispute").addEventListener("click", () => review("DISPUTE"));
$("resolve").addEventListener("click", async () => {
  const resolution = $("review-note").value.trim();
  if (!resolution) { showError("请填写解决结论。"); $("review-note").focus(); return; }
  if (!state.preview || !$("score-form").reportValidity()) return;
  await mutate("resolve", { resolved_by: $("actor").value, resolution, ...scoreChanges() }, "解决争议");
});
refresh();
window.addEventListener("focus", refresh);
window.addEventListener("storage", (event) => {
  if (event.key === "contribution-graph-update" || event.key === "contribution-project") refresh();
});
