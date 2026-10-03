const $ = (id) => document.getElementById(id);
const message = $("message");

function showMessage(text, error = true) {
  message.textContent = text;
  message.className = error ? "error" : "notice";
  message.hidden = false;
}

function destination() {
  const requested = new URLSearchParams(location.search).get("next") || "/workspace.html";
  return requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
}

async function request(path, options) {
  const response = await fetch(path, { cache: "no-store", ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `请求失败 (${response.status})`);
  return data;
}

fetch("/api/auth/session", { cache: "no-store" }).then((response) => {
  if (response.ok) location.replace(destination());
}).catch(() => {});

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  message.hidden = true;
  try {
    await request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    location.replace(destination());
  } catch (error) {
    showMessage(`登录失败：${error.message}`);
  } finally {
    button.disabled = false;
  }
});

$("provision-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  const button = form.querySelector("button");
  button.disabled = true;
  message.hidden = true;
  try {
    await request("/api/admin/member-accounts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Token-Admin-Key": values.admin_key,
      },
      body: JSON.stringify({ member_id: values.member_id, password: values.password }),
    });
    form.reset();
    $("login-form").elements.identifier.value = values.member_id;
    showMessage("成员账号已保存，可以使用该成员 ID 和密码登录。", false);
  } catch (error) {
    showMessage(`开通账号失败：${error.message}`);
  } finally {
    button.disabled = false;
  }
});
