document.addEventListener("DOMContentLoaded", async () => {
  const message = document.getElementById("verify-message");
  const token = location.hash.slice(1);
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  if (!token) { message.textContent = "验证链接缺少令牌，请从验证邮件重新打开。"; return; }
  try {
    const response = await fetch("/api/auth/verify-email", {method:"POST",headers:{"Content-Type":"application/json", ...(window.HacKUAuth?.headers?.() || {})},body:JSON.stringify({token})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "邮箱验证失败。");
    message.textContent = "邮箱验证成功。之后可以用邮箱登录和接受邮箱邀请。";
  } catch (error) { message.textContent = error.message; }
});
