const form = document.getElementById("profile-form");
const errorElement = document.getElementById("error");
const noticeElement = document.getElementById("notice");

async function loadProfile() {
  const [profileResponse, workspaceResponse] = await Promise.all([
    fetch("/api/profile", { cache: "no-store" }),
    fetch("/api/workspace", { cache: "no-store" }),
  ]);
  const profile = await profileResponse.json();
  const workspace = await workspaceResponse.json();
  if (!profileResponse.ok) throw new Error(profile.detail || "读取 Profile 失败");
  if (!workspaceResponse.ok) throw new Error(workspace.detail || "读取工作区失败");
  for (const [key, value] of Object.entries({
    display_name: profile.displayName,
    email: profile.email,
    bio: profile.bio,
    avatar_url: profile.avatarUrl,
    wallet_address: profile.walletAddress,
  })) {
    form.elements[key].value = value || "";
  }
  document.getElementById("project-count").textContent = workspace.projects.length;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorElement.hidden = true;
  noticeElement.hidden = true;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/api/profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `保存失败 (${response.status})`);
    noticeElement.textContent = "Profile 已更新。";
    noticeElement.hidden = false;
  } catch (error) {
    errorElement.textContent = error.message;
    errorElement.hidden = false;
  } finally {
    button.disabled = false;
  }
});

loadProfile().catch((error) => {
  errorElement.textContent = error.message;
  errorElement.hidden = false;
});
