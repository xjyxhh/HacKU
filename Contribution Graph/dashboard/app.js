const statusNames = { PENDING: "待验证", VERIFIED: "已验证", DISPUTED: "争议中", RESOLVED: "已解决" };
const typeNames = { CORE: "核心", SUPPORT: "支持", REVIEW: "审查", COORDINATION: "协调" };
const categories = ["CORE", "SUPPORT", "REVIEW", "COORDINATION"];
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value ?? 0);
const media = window.matchMedia("(max-width: 650px)");
let currentData = null;
let selectedId = null;

function namesById(items) {
  return Object.fromEntries(items.map((item) => [item.id, item.name]));
}

function filterValue(name) {
  return $(`${name}-filter`).value;
}

function filteredContributions() {
  if (!currentData) return [];
  const member = filterValue("member");
  const task = filterValue("task");
  const type = filterValue("type");
  const status = filterValue("status");
  const members = namesById(currentData.members);
  const rows = currentData.contributions.filter((item) =>
    (member === "ALL" || item.contributorId === member || item.helpedMemberId === member) &&
    (task === "ALL" || item.taskId === task) &&
    (type === "ALL" || item.type === type) &&
    (status === "ALL" || item.status === status)
  );
  const sort = $("sort-order").value;
  if (sort === "score-desc") rows.sort((a, b) => b.score - a.score);
  if (sort === "score-asc") rows.sort((a, b) => a.score - b.score);
  if (sort === "member") rows.sort((a, b) => (members[a.contributorId] ?? a.contributorId).localeCompare(members[b.contributorId] ?? b.contributorId, "zh-CN"));
  return rows;
}

function fillSelect(id, items, allLabel) {
  const select = $(id);
  const previous = select.value;
  select.replaceChildren(new Option(allLabel, "ALL"), ...items.map((item) => new Option(item.name, item.id)));
  select.value = items.some((item) => item.id === previous) ? previous : "ALL";
}

function renderMembers(data) {
  $("members-empty").hidden = data.members.length > 0;
  $("members").innerHTML = data.members.map((member) => `
    <button class="member ${filterValue("member") === member.id ? "is-active" : ""}" type="button" data-member-id="${safe(member.id)}" aria-pressed="${filterValue("member") === member.id}">
      <span class="member-top"><span class="identity"><span class="avatar" aria-hidden="true">${safe(member.name.slice(0, 1))}</span><span class="member-name">${safe(member.name)}</span></span><span class="share">${Number(member.contributionShare).toFixed(2)}%</span></span>
      <span class="member-score">${points(member.totalScore)} <small>分</small></span>
      <span class="breakdown">${categories.map((kind) => `<span>${typeNames[kind]} <b>${points(member.breakdown[kind])}</b></span>`).join("")}</span>
    </button>`).join("");
}

function renderTasks(data) {
  $("tasks-empty").hidden = data.tasks.length > 0;
  $("tasks").innerHTML = data.tasks.map((task) => `
    <button class="task ${filterValue("task") === task.id ? "is-active" : ""}" type="button" data-task-id="${safe(task.id)}" aria-pressed="${filterValue("task") === task.id}">
      <span><span class="task-name">${safe(task.name)}</span><span class="task-id">${safe(task.id)}</span></span>
      <span class="task-value">${points(task.taskValue)} <small>价值</small></span>
    </button>`).join("");
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function renderGraph(data, rows) {
  const byContribution = Object.fromEntries(data.relationships.map((item) => [item.contributionId, item]));
  const relationships = rows.map((item) => byContribution[item.id]).filter(Boolean);
  $("relationship-count").textContent = `${relationships.length} 条关系`;
  $("graph-empty").hidden = relationships.length > 0;
  $("graph-content").hidden = relationships.length === 0;
  const svg = $("graph");
  svg.replaceChildren();
  $("relationships").replaceChildren();
  if (!relationships.length) return;

  const members = namesById(data.members);
  const tasks = namesById(data.tasks);
  const narrow = media.matches;
  svg.setAttribute("viewBox", narrow ? "0 0 300 340" : "0 0 760 300");
  const positions = Object.fromEntries(data.members.map((member, index) => {
    const angle = Math.PI + index * 2 * Math.PI / data.members.length;
    return [member.id, narrow
      ? { x: 150 + 86 * Math.cos(angle), y: 170 + 105 * Math.sin(angle) }
      : { x: 380 + 255 * Math.cos(angle), y: 150 + 95 * Math.sin(angle) }];
  }));
  const defs = svgElement("defs");
  const marker = svgElement("marker", { id: "arrow", markerWidth: 8, markerHeight: 8, refX: 7, refY: 3.5, orient: "auto" });
  marker.append(svgElement("path", { d: "M0 0 L7 3.5 L0 7 Z" }));
  defs.append(marker);
  svg.append(defs);

  const pairCounts = new Map();
  for (const relation of relationships) {
    const pair = `${relation.fromMemberId}\u0000${relation.toMemberId}`;
    pairCounts.set(pair, (pairCounts.get(pair) ?? 0) + 1);
  }
  const pairIndexes = new Map();
  for (const relation of relationships) {
    const from = positions[relation.fromMemberId];
    const to = positions[relation.toMemberId];
    if (!from || !to) continue;
    const dx = to.x - from.x, dy = to.y - from.y, distance = Math.hypot(dx, dy) || 1;
    const x1 = from.x + dx * 34 / distance, y1 = from.y + dy * 34 / distance;
    const x2 = to.x - dx * 41 / distance, y2 = to.y - dy * 41 / distance;
    const pair = `${relation.fromMemberId}\u0000${relation.toMemberId}`;
    const index = pairIndexes.get(pair) ?? 0;
    pairIndexes.set(pair, index + 1);
    const bend = (index - (pairCounts.get(pair) - 1) / 2) * (narrow ? 44 : 58);
    const cx = (x1 + x2) / 2 - dy * bend / distance;
    const cy = (y1 + y2) / 2 + dx * bend / distance;
    const path = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
    const label = `${members[relation.fromMemberId] ?? relation.fromMemberId} 帮助 ${members[relation.toMemberId] ?? relation.toMemberId}，${tasks[relation.taskId] ?? relation.taskId}，${statusNames[relation.status] ?? relation.status}`;
    const group = svgElement("g", { class: `graph-edge ${selectedId === relation.contributionId ? "is-selected" : ""} ${relation.status === "PENDING" || relation.status === "DISPUTED" ? "is-unscored" : ""}`, role: "button", tabindex: "0", "aria-label": `查看贡献：${label}`, "data-contribution-id": relation.contributionId });
    group.append(svgElement("path", { d: path, class: "graph-hit" }));
    group.append(svgElement("path", { d: path, class: "graph-line" }));
    svg.append(group);
  }
  for (const member of data.members) {
    const point = positions[member.id];
    const group = svgElement("g", { class: `graph-member ${filterValue("member") === member.id ? "is-active" : ""}`, role: "button", tabindex: "0", "aria-label": `筛选成员 ${member.name}`, "data-member-id": member.id });
    group.append(svgElement("circle", { cx: point.x, cy: point.y, r: 31 }));
    const label = svgElement("text", { x: point.x, y: point.y + 4 });
    label.textContent = member.name;
    group.append(label);
    svg.append(group);
  }
  svg.setAttribute("aria-label", `成员帮助关系图，当前显示 ${relationships.length} 条关系。可用 Tab 键选择关系或成员。`);
  $("relationships").innerHTML = relationships.map((relation) => `
    <button class="relation ${selectedId === relation.contributionId ? "is-selected" : ""}" type="button" data-contribution-id="${safe(relation.contributionId)}" aria-pressed="${selectedId === relation.contributionId}">
      <span class="relation-names"><strong>${safe(members[relation.fromMemberId] ?? relation.fromMemberId)}</strong><span aria-hidden="true">→</span><strong>${safe(members[relation.toMemberId] ?? relation.toMemberId)}</strong></span>
      <span class="relation-meta">${safe(tasks[relation.taskId] ?? relation.taskId)} / ${safe(typeNames[relation.type] ?? relation.type)}</span>
      <span class="relation-foot"><span class="status ${relation.status.toLowerCase()}">${safe(statusNames[relation.status] ?? relation.status)}</span><span>${relation.status === "PENDING" || relation.status === "DISPUTED" ? "暂不计分" : `${points(relation.score)} 分`}</span></span>
    </button>`).join("");
}

function renderContributions(data, rows) {
  const members = namesById(data.members);
  const tasks = namesById(data.tasks);
  $("result-count").textContent = `${rows.length} / ${data.contributions.length} 条记录`;
  $("contributions-empty").hidden = rows.length > 0;
  $("contributions").innerHTML = rows.map((item) => `
    <tr class="${selectedId === item.id ? "is-selected" : ""}" data-row-id="${safe(item.id)}">
      <td><button class="row-select" type="button" data-contribution-id="${safe(item.id)}" aria-label="查看 ${safe(members[item.contributorId] ?? item.contributorId)} 的贡献 ${safe(item.description)}"><strong>${safe(members[item.contributorId] ?? item.contributorId)}</strong><span>${safe(item.description)}</span>${item.helpedMemberId ? `<small>帮助 ${safe(members[item.helpedMemberId] ?? item.helpedMemberId)}</small>` : ""}</button></td>
      <td data-label="任务">${safe(tasks[item.taskId] ?? item.taskId)}</td><td data-label="类型"><span class="type">${safe(typeNames[item.type] ?? item.type)}</span></td>
      <td data-label="状态"><span class="status ${item.status.toLowerCase()}">${safe(statusNames[item.status] ?? item.status)}</span></td>
      <td data-label="当前得分" class="number">${item.status === "PENDING" || item.status === "DISPUTED" ? '<span class="no-score">暂不计分</span>' : `<span class="score">${points(item.score)}</span>`}</td>
    </tr>`).join("");
}

function renderInteractive() {
  if (!currentData) return;
  const rows = filteredContributions();
  if (selectedId && !rows.some((item) => item.id === selectedId)) selectedId = null;
  renderMembers(currentData);
  renderTasks(currentData);
  renderGraph(currentData, rows);
  renderContributions(currentData, rows);
  $("clear-filters").disabled = ["member", "task", "type", "status"].every((name) => filterValue(name) === "ALL") && $("sort-order").value === "original";
}

function render(data) {
  currentData = data;
  fillSelect("member-filter", data.members, "全部成员");
  fillSelect("task-filter", data.tasks, "全部任务");
  $("project-name").textContent = data.project.name;
  $("team-score").textContent = points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("member-count").textContent = data.members.length;
  $("task-count").textContent = data.tasks.length;
  $("contribution-count").textContent = data.contributions.length;
  $("pending-count").textContent = `${data.contributions.filter((item) => item.status === "PENDING" || item.status === "DISPUTED").length} 条暂不计分`;
  renderInteractive();
  $("updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

function focusContribution(id) {
  selectedId = id;
  renderInteractive();
  const row = Array.from($("contributions").children).find((item) => item.dataset.rowId === id);
  if (row) {
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    row.querySelector("button")?.focus({ preventScroll: true });
  }
}

function setFilter(name, id) {
  const select = $(`${name}-filter`);
  select.value = select.value === id ? "ALL" : id;
  selectedId = null;
  renderInteractive();
  $("contribution-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refresh() {
  $("refresh").disabled = true;
  $("error").hidden = true;
  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `读取失败 (${response.status})`);
    render(data);
  } catch (error) {
    $("error").textContent = `无法读取项目数据：${error.message}`;
    $("error").hidden = false;
    $("updated").textContent = "数据读取失败";
  } finally {
    $("refresh").disabled = false;
  }
}

$("refresh").addEventListener("click", refresh);
for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).addEventListener("change", renderInteractive);
$("sort-order").addEventListener("change", renderInteractive);
$("clear-filters").addEventListener("click", () => {
  for (const name of ["member", "task", "type", "status"]) $(`${name}-filter`).value = "ALL";
  $("sort-order").value = "original";
  selectedId = null;
  renderInteractive();
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
  const target = event.target.closest("[data-member-id], [data-contribution-id]");
  if (!target) return;
  event.preventDefault();
  target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
});
media.addEventListener("change", renderInteractive);
refresh();
