const profileForm = document.getElementById("profile-form");
const profileStatus = document.getElementById("profile-status");
async function loadProfile() {
  const identity = await window.HacKUAuth.refresh();
  if (!identity.authenticated) { profileStatus.textContent = "Sign in to view your profile."; profileForm.hidden = true; return; }
  const response = await fetch("/api/profile", {cache:"no-store"}); const profile = await response.json();
  if (!response.ok) { profileStatus.textContent = profile.detail || "Could not load profile."; return; }
  for (const key of ["memberId", "display_name", "email", "avatar_url", "bio"]) profileForm.elements[key].value = ({memberId:profile.memberId,display_name:profile.displayName,email:profile.email || "",avatar_url:profile.avatarUrl,bio:profile.bio})[key];
  profileStatus.textContent = profile.emailVerified ? "Email verified." : "Your email is unverified. Email sign-in and email invitations are unavailable.";
}
profileForm.addEventListener("submit", async (event) => {
  event.preventDefault(); const values = Object.fromEntries(new FormData(profileForm));
  try { const response = await fetch("/api/profile", {method:"PATCH",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify({display_name:values.display_name,bio:values.bio,avatar_url:values.avatar_url})}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not save profile."); profileStatus.textContent = "Profile saved."; }
  catch (error) { profileStatus.textContent = error.message; }
});
document.getElementById("email-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const response = await fetch("/api/profile/email", {method:"POST",headers:window.HacKUAuth.headers({"Content-Type":"application/json"}),body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not send verification email."); profileStatus.textContent = "Verification link sent. Your email will change after verification."; }
  catch (error) { profileStatus.textContent = error.message; }
});
document.addEventListener("DOMContentLoaded", loadProfile);
