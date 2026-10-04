const projectId = new URLSearchParams(location.search).get("project");
const memberMessage = document.getElementById("members-message");
const escapeMember = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
async function loadMembers() {
  if (!projectId) { memberMessage.textContent = "Missing project ID. Open the members page from your workspace."; return; }
  await window.HacKUAuth.refresh();
  document.getElementById("project-label").textContent = `Project ${projectId}`;
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members`, {cache:"no-store"});
  const result = await response.json();
  if (!response.ok) { memberMessage.textContent = result.detail || "Member list unavailable."; return; }
  memberMessage.textContent = `${result.members.length} members. Owners manage projects, Members contribute, Verifiers review independently, and Viewers have read-only access.`;
  document.getElementById("members-list").innerHTML = result.members.map((member) => `<article class="panel workspace-card"><h2>${escapeMember(member.name)}</h2><p>${escapeMember(member.memberId)} · ${escapeMember(member.role)} · ${escapeMember(member.state)}</p>${member.state === "ACTIVE" ? `<label>Change role<select data-member-role="${escapeMember(member.memberId)}"><option ${member.role === "OWNER" ? "selected" : ""}>OWNER</option><option ${member.role === "MEMBER" ? "selected" : ""}>MEMBER</option><option ${member.role === "VERIFIER" ? "selected" : ""}>VERIFIER</option><option ${member.role === "VIEWER" ? "selected" : ""}>VIEWER</option></select></label>` : ""}</article>`).join("");
}
document.getElementById("member-invite-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const body = Object.fromEntries(new FormData(event.currentTarget));
  try { const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members/invite-existing`, {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(body)}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Invitation failed."); memberMessage.textContent = result.tokenLedgerState === "READY" ? `Added ${result.memberId} with role ${result.role}.` : "Member added; TOKEN_SETUP_PENDING: ledger sync failed. Retry initialization."; await loadMembers(); }
  catch (error) { memberMessage.textContent = error.message; }
});
document.getElementById("members-list").addEventListener("change", async (event) => {
  const select = event.target.closest("[data-member-role]"); if (!select) return;
  try { const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(select.dataset.memberRole)}/role`, {method:"PATCH",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify({role:select.value})}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Role update failed."); memberMessage.textContent = `Role updated to ${result.role}.`; await loadMembers(); }
  catch (error) { memberMessage.textContent = error.message; await loadMembers(); }
});
document.addEventListener("DOMContentLoaded", loadMembers);
