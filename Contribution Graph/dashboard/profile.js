const profileForm = document.getElementById("profile-form");
const profileStatus = document.getElementById("profile-status");
async function loadProfile() {
  const identity = await window.HacKUAuth.refresh();
  if (!identity.authenticated) { profileStatus.textContent = "请先登录查看个人资料。"; profileForm.hidden = true; return; }
  const response = await fetch("/api/profile", {cache:"no-store"}); const profile = await response.json();
  if (!response.ok) { profileStatus.textContent = profile.detail || "资料读取失败。"; return; }
  for (const key of ["memberId", "display_name", "email", "avatar_url", "bio"]) profileForm.elements[key].value = ({memberId:profile.memberId,display_name:profile.displayName,email:profile.email || "",avatar_url:profile.avatarUrl,bio:profile.bio})[key];
  profileStatus.textContent = profile.emailVerified ? "邮箱已验证。" : "邮箱尚未验证；邮箱登录和邮箱邀请暂不可用。";
}
profileForm.addEventListener("submit", async (event) => {
  event.preventDefault(); const values = Object.fromEntries(new FormData(profileForm));
  try { const response = await fetch("/api/profile", {method:"PATCH",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify({display_name:values.display_name,bio:values.bio,avatar_url:values.avatar_url})}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "资料保存失败。"); profileStatus.textContent = "资料已保存。"; }
  catch (error) { profileStatus.textContent = error.message; }
});
document.getElementById("email-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const response = await fetch("/api/profile/email", {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "验证邮件发送失败。"); profileStatus.textContent = "验证链接已发送。邮箱在完成验证前不会更改。"; }
  catch (error) { profileStatus.textContent = error.message; }
});
document.addEventListener("DOMContentLoaded", loadProfile);
