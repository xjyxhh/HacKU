const statusNames = { PENDING: "待验证", VERIFIED: "已验证", DISPUTED: "争议中", RESOLVED: "已解决" };
const typeNames = { CORE: "核心", SUPPORT: "支持", REVIEW: "审查", COORDINATION: "协调" };
const categories = ["CORE", "SUPPORT", "REVIEW", "COORDINATION"];
const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const points = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value ?? 0);
let currentData = null;

function renderMembers(data) {
  $("members-empty").hidden = data.members.length > 0;
  $("members").innerHTML = data.members.map((member) => `
    <article class="member">
      <div class="member-top"><div class="identity"><span class="avatar">${safe(member.name.slice(0, 1))}</span><span class="member-name">${safe(member.name)}</span></div><span class="share">${Number(member.contributionShare).toFixed(2)}%</span></div>
      <div class="member-score">${points(member.totalScore)} <small>分</small></div>
      <div class="share-bar" aria-label="${safe(member.name)} 占比 ${Number(member.contributionShare).toFixed(2)}%"><span style="width:${Math.min(100, Math.max(0, Number(member.contributionShare) || 0))}%"></span></div>
      <div class="breakdown">${categories.map((kind) => `<span>${typeNames[kind]} <b>${points(member.breakdown[kind])}</b></span>`).join("")}</div>
    </article>`).join("");
}

function renderTasks(data) {
  $("tasks-empty").hidden = data.tasks.length > 0;
  $("tasks").innerHTML = data.tasks.map((task) => `
    <div class="task"><div><div class="task-name">${safe(task.name)}</div><div class="task-id">${safe(task.id)}</div></div><div class="task-value">${points(task.taskValue)} <small>价值</small></div></div>`).join("");
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function renderGraph(data) {
  const hasRelationships = data.relationships.length > 0;
  $("graph-empty").hidden = hasRelationships;
  $("graph-content").hidden = !hasRelationships;
  const svg = $("graph");
  svg.replaceChildren();
  $("relationships").replaceChildren();
  if (!hasRelationships) return;

  const byId = Object.fromEntries(data.members.map((member) => [member.id, member]));
  const tasks = Object.fromEntries(data.tasks.map((task) => [task.id, task]));
  const narrow = window.matchMedia("(max-width: 650px)").matches;
  svg.setAttribute("viewBox", narrow ? "0 0 300 360" : "0 0 760 300");
  const positions = Object.fromEntries(data.members.map((member, index) => {
    const angle = Math.PI + index * 2 * Math.PI / data.members.length;
    return [member.id, narrow
      ? { x: 150 + 86 * Math.cos(angle), y: 180 + 105 * Math.sin(angle) }
      : { x: 380 + 255 * Math.cos(angle), y: 150 + 95 * Math.sin(angle) }];
  }));
  const defs = svgElement("defs");
  const marker = svgElement("marker", { id: "arrow", markerWidth: 8, markerHeight: 8, refX: 7, refY: 3.5, orient: "auto" });
  marker.append(svgElement("path", { d: "M0 0 L7 3.5 L0 7 Z", fill: "#54a98f" }));
  defs.append(marker);
  svg.append(defs);

  for (const relation of data.relationships) {
    const from = positions[relation.fromMemberId];
    const to = positions[relation.toMemberId];
    if (!from || !to) continue;
    const dx = to.x - from.x, dy = to.y - from.y, distance = Math.hypot(dx, dy) || 1;
    const line = svgElement("line", {
      x1: from.x + dx * 32 / distance, y1: from.y + dy * 32 / distance,
      x2: to.x - dx * 39 / distance, y2: to.y - dy * 39 / distance,
      class: `graph-line ${relation.status === "PENDING" ? "pending" : relation.status === "DISPUTED" ? "disputed" : ""}`,
    });
    svg.append(line);
    const row = document.createElement("div");
    row.className = "relation";
    row.innerHTML = `<strong>${safe(byId[relation.fromMemberId]?.name ?? relation.fromMemberId)}</strong><span class="arrow">→</span><strong>${safe(byId[relation.toMemberId]?.name ?? relation.toMemberId)}</strong><small>${safe(tasks[relation.taskId]?.name ?? relation.taskId)} · ${safe(typeNames[relation.type] ?? relation.type)} · ${safe(statusNames[relation.status] ?? relation.status)} · ${relation.status === "PENDING" || relation.status === "DISPUTED" ? "暂不计分" : `${points(relation.score)} 分`}</small>`;
    $("relationships").append(row);
  }
  for (const member of data.members) {
    const point = positions[member.id];
    svg.append(svgElement("circle", { cx: point.x, cy: point.y, r: 31, class: "graph-node" }));
    const label = svgElement("text", { x: point.x, y: point.y + 4, class: "graph-label" });
    label.textContent = member.name;
    svg.append(label);
  }
  svg.setAttribute("aria-label", data.relationships.map((relation) => `${byId[relation.fromMemberId]?.name ?? relation.fromMemberId} 帮助 ${byId[relation.toMemberId]?.name ?? relation.toMemberId}，${statusNames[relation.status] ?? relation.status}`).join("；"));
}

function renderContributions() {
  if (!currentData) return;
  const filter = $("status-filter").value;
  const data = currentData;
  const members = Object.fromEntries(data.members.map((member) => [member.id, member.name]));
  const tasks = Object.fromEntries(data.tasks.map((task) => [task.id, task.name]));
  const rows = data.contributions.filter((item) => filter === "ALL" || item.status === filter);
  $("contributions-empty").hidden = rows.length > 0;
  $("contributions").innerHTML = rows.map((item) => `
    <tr><td><div class="contributor">${safe(members[item.contributorId] ?? item.contributorId)}</div><div class="description">${safe(item.description)}</div>${item.helpedMemberId ? `<div class="helped">帮助 ${safe(members[item.helpedMemberId] ?? item.helpedMemberId)}</div>` : ""}</td>
    <td>${safe(tasks[item.taskId] ?? item.taskId)}</td><td><span class="type">${safe(typeNames[item.type] ?? item.type)}</span></td>
    <td><span class="status ${item.status.toLowerCase()}">${safe(statusNames[item.status] ?? item.status)}</span></td>
    <td class="number">${item.status === "PENDING" || item.status === "DISPUTED" ? '<span class="no-score">暂不计分</span>' : `<span class="score">${points(item.score)}</span>`}</td></tr>`).join("");
}

function render(data) {
  currentData = data;
  $("project-name").textContent = data.project.name;
  $("team-score").textContent = points(data.members.reduce((sum, member) => sum + member.totalScore, 0));
  $("member-count").textContent = data.members.length;
  $("task-count").textContent = data.tasks.length;
  $("contribution-count").textContent = data.contributions.length;
  $("pending-count").textContent = `${data.contributions.filter((item) => item.status === "PENDING" || item.status === "DISPUTED").length} 条暂不计分`;
  renderMembers(data);
  renderTasks(data);
  renderGraph(data);
  renderContributions();
  $("updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
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
$("status-filter").addEventListener("change", renderContributions);
window.matchMedia("(max-width: 650px)").addEventListener("change", () => { if (currentData) renderGraph(currentData); });
refresh();
