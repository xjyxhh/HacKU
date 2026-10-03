const errorElement = document.getElementById("error");

async function loadDemo() {
  const response = await fetch("/api/demo", { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `读取 Demo 失败 (${response.status})`);
  document.getElementById("project-name").textContent = data.project.name;
  document.getElementById("member-count").textContent = data.members.length;
  document.getElementById("task-count").textContent = data.tasks.length;
  document.getElementById("contribution-count").textContent = data.contributions.length;
  document.getElementById("total-score").textContent =
    data.members.reduce((sum, member) => sum + Number(member.totalScore), 0).toFixed(2);
  document.getElementById("members").innerHTML = data.members.map((member) =>
    `<article class="member-card"><h3>${escapeHtml(member.name)}</h3><p>${escapeHtml(member.totalScore)} 分 · ${escapeHtml(member.contributionShare)}%</p></article>`
  ).join("");
  document.getElementById("tasks").innerHTML = data.tasks.map((task) =>
    `<article class="member-card"><h3>${escapeHtml(task.name)}</h3><p>Mint Cap ${escapeHtml(task.taskValue)}</p></article>`
  ).join("");
  document.getElementById("contributions").innerHTML = data.contributions.map((item) =>
    `<article class="token-row"><div><strong>${escapeHtml(item.contributorId)} · ${escapeHtml(item.type)} · ${escapeHtml(item.status)}</strong><p>${escapeHtml(item.description)}</p></div><strong>${escapeHtml(item.score)}</strong></article>`
  ).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

loadDemo().catch((error) => {
  errorElement.textContent = error.message;
  errorElement.hidden = false;
});
