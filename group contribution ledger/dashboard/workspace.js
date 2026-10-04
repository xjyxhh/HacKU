const workspaceMessage = document.getElementById("workspace-message");
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
async function loadWorkspace() {
  const identity = await window.HacKUAuth.refresh();
  if (!identity.authenticated) { workspaceMessage.textContent = "Sign in to view your workspace."; return; }
  const response = await fetch("/api/workspace", {cache:"no-store"});
  const data = await response.json();
  if (!response.ok) { workspaceMessage.textContent = data.detail || "Workspace unavailable."; return; }
  workspaceMessage.textContent = data.projects.length ? `Member ID: ${data.memberId}` : "No projects yet. Create one or wait for an invitation from a project Owner.";
  document.getElementById("workspace-projects").innerHTML = data.projects.map((project) => {
    const todos = project.todos || [];
    const todoNames = {ACCEPT:"Accept Commission", DELIVER:"Submit Delivery Evidence", APPROVE:"Approve Commission Independently", REVIEW:"Review Contribution", EXIT:"Review Member Exit"};
    return `<article class="panel workspace-card"><h2>${escapeHtml(project.name)}</h2><p>${escapeHtml(project.id)} · ${escapeHtml(project.role)} · ${escapeHtml(project.state)}</p><p>Members ${project.memberCount} · Tasks ${project.taskCount}</p>${project.balanceState === "READY" ? `<p>Available Tokens: ${escapeHtml(project.balanceExact)} · Frozen: ${escapeHtml(project.frozenExact)}</p>` : `<p role="status">Token balance unavailable: ${project.tokenLedgerState === "READY" ? "ledger could not be read" : "ledger setup is pending"}</p>`}${project.tokenLedgerState === "READY" ? "<p>Independent ledger: ready</p>" : "<p role=\"status\">TOKEN_SETUP_PENDING: retry initialization in the Token workspace.</p>"}<p>To-dos ${todos.length}</p>${todos.length ? `<ul>${todos.map((todo) => `<li><a href="${escapeHtml(todo.href)}">${escapeHtml(todoNames[todo.kind] || todo.kind)} · ${escapeHtml(todo.objectId)}</a></li>`).join("")}</ul>` : "<p>No to-dos right now.</p>"}<a href="/?project=${encodeURIComponent(project.id)}">Open Project Dashboard</a> · <a href="/token.html?project=${encodeURIComponent(project.id)}">Token Workspace</a>${project.role === "OWNER" ? ` · <a href="/members.html?project=${encodeURIComponent(project.id)}">Members and Roles</a>` : ""}</article>`;
  }).join("");
}
document.getElementById("project-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const form = event.currentTarget; const body = Object.fromEntries(new FormData(form));
  try {
    const response = await fetch("/api/projects", {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(body)});
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not create project.");
    localStorage.setItem("contribution-project", result.id);
    if (result.tokenLedgerState !== "READY") workspaceMessage.textContent = "Project created with you as Owner; TOKEN_SETUP_PENDING: retry initialization in the Token workspace.";
    location.href = `/?project=${encodeURIComponent(result.id)}`;
  } catch (error) { workspaceMessage.textContent = error.message; }
});
document.addEventListener("DOMContentLoaded", loadWorkspace);
