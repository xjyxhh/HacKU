const workspaceMessage = document.getElementById("workspace-message");
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
async function loadWorkspace() {
  const identity = await window.HacKUAuth.refresh();
  if (!identity.authenticated) { workspaceMessage.textContent = "请先登录后查看个人工作区。"; return; }
  const response = await fetch("/api/workspace", {cache:"no-store"});
  const data = await response.json();
  if (!response.ok) { workspaceMessage.textContent = data.detail || "工作区暂不可用。"; return; }
  workspaceMessage.textContent = data.projects.length ? `成员 ID：${data.memberId}` : "这里还没有项目。你可以创建项目，或等待项目 Owner 邀请。";
  document.getElementById("workspace-projects").innerHTML = data.projects.map((project) => {
    const todos = project.todos || [];
    const todoNames = {ACCEPT:"接受委托", DELIVER:"提交交付证据", APPROVE:"独立批准委托", REVIEW:"审核贡献", EXIT:"处理成员退出"};
    return `<article class="panel workspace-card"><h2>${escapeHtml(project.name)}</h2><p>${escapeHtml(project.id)} · ${escapeHtml(project.role)} · ${escapeHtml(project.state)}</p><p>成员 ${project.memberCount} · 任务 ${project.taskCount}</p>${project.balanceState === "READY" ? `<p>可用 Token：${escapeHtml(project.balanceExact)} · 冻结：${escapeHtml(project.frozenExact)}</p>` : `<p role="status">Token 余额暂不可用：${project.tokenLedgerState === "READY" ? "账本读取失败" : "账本待初始化"}</p>`}${project.tokenLedgerState === "READY" ? "<p>独立账本：已就绪</p>" : "<p role=\"status\">TOKEN_SETUP_PENDING：账本待初始化，可到 Token 工作台重试。</p>"}<p>待办 ${todos.length}</p>${todos.length ? `<ul>${todos.map((todo) => `<li><a href="${escapeHtml(todo.href)}">${escapeHtml(todoNames[todo.kind] || todo.kind)} · ${escapeHtml(todo.objectId)}</a></li>`).join("")}</ul>` : "<p>目前没有待办。</p>"}<a href="/?project=${encodeURIComponent(project.id)}">打开项目看板</a> · <a href="/token.html?project=${encodeURIComponent(project.id)}">Token 工作台</a>${project.role === "OWNER" ? ` · <a href="/members.html?project=${encodeURIComponent(project.id)}">成员与角色</a>` : ""}</article>`;
  }).join("");
}
document.getElementById("project-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const form = event.currentTarget; const body = Object.fromEntries(new FormData(form));
  try {
    const response = await fetch("/api/projects", {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(body)});
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || "项目创建失败。");
    localStorage.setItem("contribution-project", result.id);
    if (result.tokenLedgerState !== "READY") workspaceMessage.textContent = "项目已创建并由你担任 Owner；TOKEN_SETUP_PENDING：账本初始化失败，可在 Token 工作台重试。";
    location.href = `/?project=${encodeURIComponent(result.id)}`;
  } catch (error) { workspaceMessage.textContent = error.message; }
});
document.addEventListener("DOMContentLoaded", loadWorkspace);
