const projectId = new URLSearchParams(location.search).get("project");
const memberMessage = document.getElementById("members-message");
const escapeMember = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
async function loadMembers() {
  if (!projectId) { memberMessage.textContent = "缺少项目 ID，请从工作区打开项目成员页。"; return; }
  await window.HacKUAuth.refresh();
  document.getElementById("project-label").textContent = `项目 ${projectId}`;
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members`, {cache:"no-store"});
  const result = await response.json();
  if (!response.ok) { memberMessage.textContent = result.detail || "成员列表不可用。"; return; }
  memberMessage.textContent = `共 ${result.members.length} 位成员。Owner 管理项目，Member 参与贡献，Verifier 独立核验，Viewer 只读。`;
  document.getElementById("members-list").innerHTML = result.members.map((member) => `<article class="panel workspace-card"><h2>${escapeMember(member.name)}</h2><p>${escapeMember(member.memberId)} · ${escapeMember(member.role)} · ${escapeMember(member.state)}</p>${member.state === "ACTIVE" ? `<label>调整角色<select data-member-role="${escapeMember(member.memberId)}"><option ${member.role === "OWNER" ? "selected" : ""}>OWNER</option><option ${member.role === "MEMBER" ? "selected" : ""}>MEMBER</option><option ${member.role === "VERIFIER" ? "selected" : ""}>VERIFIER</option><option ${member.role === "VIEWER" ? "selected" : ""}>VIEWER</option></select></label>` : ""}</article>`).join("");
}
document.getElementById("member-invite-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const body = Object.fromEntries(new FormData(event.currentTarget));
  try { const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members/invite-existing`, {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(body)}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "邀请失败。"); memberMessage.textContent = result.tokenLedgerState === "READY" ? `已加入 ${result.memberId}，角色 ${result.role}。` : "成员已加入；TOKEN_SETUP_PENDING：账本同步失败，可重试初始化。"; await loadMembers(); }
  catch (error) { memberMessage.textContent = error.message; }
});
document.getElementById("members-list").addEventListener("change", async (event) => {
  const select = event.target.closest("[data-member-role]"); if (!select) return;
  try { const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(select.dataset.memberRole)}/role`, {method:"PATCH",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify({role:select.value})}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "角色调整失败。"); memberMessage.textContent = `角色已更新为 ${result.role}。`; await loadMembers(); }
  catch (error) { memberMessage.textContent = error.message; await loadMembers(); }
});
document.addEventListener("DOMContentLoaded", loadMembers);
