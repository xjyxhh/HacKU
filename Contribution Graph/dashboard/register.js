document.getElementById("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("register-message");
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const response = await fetch("/api/auth/register", {method:"POST", headers:{"Content-Type":"application/json", ...(window.HacKUAuth?.headers?.() || {})}, body:JSON.stringify(Object.fromEntries(new FormData(form)))});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "账号创建失败，请重试。");
    message.textContent = `账号已保存。以后可用注册邮箱或成员 ID 登录。成员 ID：${result.memberId}。`;
    form.hidden = true;
    setTimeout(() => { location.href = "/workspace.html"; }, 1800);
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
});
