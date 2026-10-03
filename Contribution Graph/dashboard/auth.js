(() => {
  const nextPath = `${location.pathname}${location.search}${location.hash}`;
  const loginUrl = `/login.html?next=${encodeURIComponent(nextPath)}`;
  document.body.hidden = true;

  async function start() {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    if (response.status === 401) {
      location.replace(loginUrl);
      return null;
    }
    if (!response.ok) throw new Error(`登录状态读取失败 (${response.status})`);
    const member = await response.json();
    const previousMember = sessionStorage.getItem("authenticatedMember");
    if (previousMember && previousMember !== member.memberId) {
      sessionStorage.removeItem("tokenAdminKey");
    }
    sessionStorage.setItem("authenticatedMember", member.memberId);
    const actions = document.querySelector(".top-actions");
    if (actions) {
      const identity = document.createElement("span");
      identity.className = "session-identity";
      identity.textContent = `${member.memberName} · ${member.memberId}`;
      identity.setAttribute("aria-label", `当前登录成员 ${member.memberName}`);
      const logout = document.createElement("button");
      logout.className = "refresh-button";
      logout.type = "button";
      logout.textContent = "退出登录";
      logout.addEventListener("click", async () => {
        logout.disabled = true;
        try {
          const result = await fetch("/api/auth/logout", { method: "POST" });
          if (!result.ok) throw new Error(`退出失败 (${result.status})`);
          sessionStorage.removeItem("authenticatedMember");
          sessionStorage.removeItem("tokenAdminKey");
          location.replace("/login.html");
        } catch (error) {
          logout.disabled = false;
          logout.textContent = error.message;
        }
      });
      actions.append(identity, logout);
    }
    document.body.hidden = false;
    return member;
  }

  window.Auth = { member: null, ready: null };
  window.Auth.ready = start().then((member) => {
    window.Auth.member = member;
    return member;
  }).catch((error) => {
    document.body.hidden = false;
    const main = document.querySelector("main");
    if (main) {
      const warning = document.createElement("p");
      warning.className = "error";
      warning.textContent = error.message;
      main.prepend(warning);
    }
    return null;
  });
})();
