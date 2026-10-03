const form = document.getElementById("register-form");
const message = document.getElementById("message");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.hidden = true;
  const values = Object.fromEntries(new FormData(form));
  if (values.password !== values.confirm_password) {
    message.textContent = "两次输入的密码不一致。";
    message.hidden = false;
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: values.email,
        display_name: values.display_name,
        password: values.password,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `注册失败 (${response.status})`);
    location.replace("/workspace.html");
  } catch (error) {
    message.textContent = `注册失败：${error.message}`;
    message.hidden = false;
  } finally {
    button.disabled = false;
  }
});
