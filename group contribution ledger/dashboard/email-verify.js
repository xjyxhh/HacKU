document.addEventListener("DOMContentLoaded", async () => {
  const message = document.getElementById("verify-message");
  const token = location.hash.slice(1);
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  if (!token) { message.textContent = "The link has no token. Reopen it from the verification email."; return; }
  try {
    const response = await fetch("/api/auth/verify-email", {method:"POST",headers:{"Content-Type":"application/json", ...(window.HacKUAuth?.headers?.() || {})},body:JSON.stringify({token})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Email verification failed.");
    message.textContent = "Email verified. You can now sign in and accept invitations using this email.";
  } catch (error) { message.textContent = error.message; }
});
