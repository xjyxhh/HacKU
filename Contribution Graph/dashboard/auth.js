(() => {
  let identity = { authenticated: false };
  const csrf = () => decodeURIComponent(document.cookie.split("; ").find((item) => item.startsWith("hacku_csrf="))?.split("=").slice(1).join("=") || "");
  const headers = (extra = {}) => ({ ...extra, ...(csrf() ? { "X-CSRF-Token": csrf() } : {}) });
  window.HacKUAuth = { headers, get identity() { return identity; }, async refresh() {
    const response = await fetch("/api/auth/me", { cache: "no-store" });
    identity = await response.json();
    const status = document.getElementById("auth-status");
    if (status) status.textContent = identity.authenticated ? `Signed in: ${identity.displayName || identity.memberId}` : "Read-only access";
    const login = document.getElementById("auth-login");
    if (login) login.hidden = identity.authenticated;
    const logout = document.getElementById("auth-logout");
    if (logout) logout.hidden = !identity.authenticated;
    const addAdmin = document.getElementById("add-site-admin");
    if (addAdmin) addAdmin.hidden = !identity.siteAdmin;
    const appoint = document.getElementById("appoint-project-admin");
    if (appoint) appoint.hidden = !identity.siteAdmin;
    const changePassword = document.getElementById("change-password");
    if (changePassword) changePassword.hidden = !identity.authenticated;
    const activeProject = document.getElementById("project-select")?.value || document.getElementById("review-project")?.value || document.getElementById("token-project-select")?.value;
    const currentProject = identity.projects?.find((project) => project.id === activeProject);
    const role = currentProject?.role || (currentProject?.admin ? "OWNER" : null);
    const isAdmin = identity.siteAdmin || role === "OWNER";
    const canVerify = identity.siteAdmin || role === "OWNER" || role === "VERIFIER";
    document.querySelectorAll("form:not(#auth-form) button, form:not(#auth-form) input, form:not(#auth-form) select, form:not(#auth-form) textarea").forEach((control) => {
      const form = control.closest("form");
      if (form?.matches('[data-lifecycle], #request-unwind, #decide-unwind')) return;
      const allowed = identity.authenticated && (
        (["profile-form", "email-form", "project-form"].includes(form?.id))
        ||
        (["contribution-form", "evidence-form"].includes(form?.id) && ["OWNER", "MEMBER", "VERIFIER"].includes(role))
        || (form?.id === "score-form" && canVerify)
        || (form?.id === "contract-form" && ["OWNER", "MEMBER"].includes(role))
        || (form?.matches(".delivery-form") && form.dataset.contractor === identity.memberId)
        || (form?.matches(".settle-form, .contract-resolve-form") && canVerify)
        || isAdmin
      );
      if (form?.id === "register-form") {
        control.disabled = identity.authenticated;
        return;
      }
      control.disabled = !allowed;
    });
    document.querySelectorAll(".action-buttons button, #migrate, #reconcile, #sync-legacy").forEach((control) => { control.disabled = !isAdmin; });
    document.querySelectorAll("[data-approve]").forEach((control) => {
      const isParty = identity.memberId === control.dataset.principal || identity.memberId === control.dataset.contractor;
      control.disabled = !identity.authenticated || !canVerify || isParty;
    });
    document.querySelectorAll("[data-dispute]").forEach((control) => {
      const isParty = identity.memberId === control.dataset.principal || identity.memberId === control.dataset.contractor;
      control.disabled = !identity.authenticated || !isParty;
    });
    const registerForm = document.getElementById("register-form");
    registerForm?.querySelectorAll("input, button").forEach((control) => { control.disabled = identity.authenticated; });
    const projectForm = document.getElementById("project-form");
    projectForm?.querySelectorAll("input, button").forEach((control) => { control.disabled = !identity.authenticated; });
    const invitePanel = document.getElementById("invite-panel");
    if (invitePanel) invitePanel.hidden = !isAdmin;
    window.dispatchEvent(new CustomEvent("hacku:identity", {detail: identity}));
    return identity;
  } };
  document.addEventListener("DOMContentLoaded", () => {
    const actions = document.querySelector(".top-actions");
    if (!actions) return;
    const status = document.createElement("span"); status.id = "auth-status"; status.className = "auth-status"; status.textContent = "Read-only access";
    const login = document.createElement("button"); login.id = "auth-login"; login.className = "refresh-button"; login.type = "button"; login.textContent = "Log in";
    const logout = document.createElement("button"); logout.id = "auth-logout"; logout.className = "refresh-button"; logout.type = "button"; logout.textContent = "Log out"; logout.hidden = true;
    const dialog = document.createElement("dialog"); dialog.className = "auth-dialog";
    dialog.innerHTML = '<form id="auth-form"><h2>Member login</h2><label>Member ID or email<input name="member_id" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><p id="auth-error" role="alert"></p><p><a href="/register.html">Create an account</a> · <a href="/demo.html">View public demo</a></p><div><button type="button" id="auth-cancel">Cancel</button><button type="submit">Log in</button></div></form>';
    actions.append(status, login, logout); document.body.append(dialog);
    const settings = document.querySelector(".settings-menu");
    if (settings) {
      const addAdmin = document.createElement("button");
      addAdmin.id = "add-site-admin"; addAdmin.type = "button"; addAdmin.className = "settings-action"; addAdmin.textContent = "Add administrator"; addAdmin.hidden = true;
      settings.append(addAdmin);
      const changePassword = document.createElement("button");
      changePassword.id = "change-password"; changePassword.type = "button"; changePassword.className = "settings-action"; changePassword.textContent = "Change password"; changePassword.hidden = true;
      const appoint = document.createElement("button");
      appoint.id = "appoint-project-admin"; appoint.type = "button"; appoint.className = "settings-action"; appoint.textContent = "Appoint project administrator"; appoint.hidden = true;
      settings.append(changePassword, appoint);
      const passwordDialog = document.createElement("dialog"); passwordDialog.className = "auth-dialog";
      passwordDialog.innerHTML = '<form><h2>Change password</h2><label>Current password<input name="old_password" type="password" autocomplete="current-password" required></label><label>New password<input name="new_password" type="password" autocomplete="new-password" required></label><label>Confirm new password<input name="confirm_password" type="password" autocomplete="new-password" required></label><p role="alert"></p><div><button type="button" data-cancel>Cancel</button><button type="submit">Save password</button></div></form>';
      document.body.append(passwordDialog);
      changePassword.addEventListener("click", () => passwordDialog.showModal());
      passwordDialog.querySelector("[data-cancel]").addEventListener("click", () => passwordDialog.close());
      passwordDialog.querySelector("form").addEventListener("submit", async (event) => {
        event.preventDefault(); const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        const error = form.querySelector('[role="alert"]');
        if (values.new_password !== values.confirm_password) { error.textContent = "New passwords do not match."; return; }
        delete values.confirm_password;
        const button = form.querySelector('[type="submit"]'); button.disabled = true; button.textContent = "Saving…";
        try {
          const response = await fetch("/api/auth/change-password", {method:"POST", headers:headers({"Content-Type":"application/json"}), body:JSON.stringify(values)});
          const result = await response.json();
          if (!response.ok) { error.textContent = result.detail || "Could not change password."; return; }
          passwordDialog.close(); alert("Password changed. Sign in again."); location.reload();
        } catch { error.textContent = "Network error. Please try again."; }
        finally { button.disabled = false; button.textContent = "Save password"; }
      });
      const projectDialog = document.createElement("dialog"); projectDialog.className = "auth-dialog";
      projectDialog.innerHTML = '<form><h2>Appoint project administrator</h2><p id="project-admin-list"></p><label>Existing member ID<input name="member_id" required></label><p role="alert"></p><div><button type="button" data-cancel>Cancel</button><button type="submit">Appoint</button></div></form>';
      document.body.append(projectDialog);
      const currentProject = () => document.getElementById("project-select")?.value || document.getElementById("review-project")?.value || document.getElementById("token-project-select")?.value;
      appoint.addEventListener("click", async () => {
        const project = currentProject();
        if (!project) return;
        projectDialog.querySelector("h2").textContent = `Project administrators · ${project}`;
        projectDialog.querySelector("#project-admin-list").textContent = "Loading administrator list…";
        projectDialog.showModal();
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(project)}/admins`, {cache:"no-store"});
          if (!response.ok) throw new Error("Could not load administrators.");
          const result = await response.json();
          projectDialog.querySelector("#project-admin-list").textContent = result.memberIds.length ? `Current administrators: ${result.memberIds.join(", ")}` : "No project administrators appointed yet.";
        } catch { projectDialog.querySelector("#project-admin-list").textContent = "Could not load administrators."; }
      });
      projectDialog.querySelector("[data-cancel]").addEventListener("click", () => projectDialog.close());
      projectDialog.querySelector("form").addEventListener("submit", async (event) => {
        event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('[type="submit"]'); button.disabled = true;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(currentProject())}/admins`, {method:"POST", headers:headers({"Content-Type":"application/json"}), body:JSON.stringify(Object.fromEntries(new FormData(form)))});
          const result = await response.json();
          if (!response.ok) { form.querySelector('[role="alert"]').textContent = result.detail || "Could not appoint administrator."; return; }
          projectDialog.querySelector("#project-admin-list").textContent += `, ${result.memberId}`; form.reset(); await window.HacKUAuth.refresh();
        } catch { form.querySelector('[role="alert"]').textContent = "Network error. Please try again."; }
        finally { button.disabled = false; }
      });
      const adminDialog = document.createElement("dialog"); adminDialog.className = "auth-dialog";
      adminDialog.innerHTML = '<form id="site-admin-form"><h2>Add administrator</h2><label>Member ID<input name="member_id" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="new-password" required></label><p id="site-admin-error" role="alert"></p><div><button type="button" id="site-admin-cancel">Cancel</button><button type="submit">Add</button></div></form>';
      document.body.append(adminDialog);
      addAdmin.addEventListener("click", () => adminDialog.showModal());
      adminDialog.querySelector("#site-admin-cancel").addEventListener("click", () => adminDialog.close());
      adminDialog.querySelector("form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const result = await fetch("/api/admin/site-admins", { method: "POST", headers: headers({"Content-Type": "application/json"}), body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
        const error = adminDialog.querySelector("#site-admin-error");
        if (!result.ok) { const body = await result.json().catch(() => ({})); error.textContent = body.detail || "Could not add administrator. Please try again."; return; }
        adminDialog.close(); event.currentTarget.reset(); alert("Administrator added.");
      });
    }
    document.addEventListener("change", (event) => {
      if (["project-select", "review-project", "token-project-select"].includes(event.target.id)) window.HacKUAuth.refresh();
    });
    login.addEventListener("click", () => dialog.showModal());
    dialog.querySelector("#auth-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("form").addEventListener("submit", async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      const button = event.currentTarget.querySelector('[type="submit"]'); button.disabled = true;
      let response;
      try { response = await fetch("/api/auth/login", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(Object.fromEntries(form)) }); }
      catch { dialog.querySelector("#auth-error").textContent = "Network error. Please try again."; button.disabled = false; return; }
      button.disabled = false;
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        dialog.querySelector("#auth-error").textContent = response.status === 401
          ? "The member ID or password is incorrect."
          : result.detail === "same-origin request required"
            ? "The login request origin was rejected. Open the page from the same site and try again."
            : (result.detail || "The login request was rejected. Refresh the page and try again.");
        return;
      }
      dialog.close(); await window.HacKUAuth.refresh(); location.reload();
    });
    logout.addEventListener("click", async () => { await fetch("/api/auth/logout", { method:"POST", headers:headers() }); await window.HacKUAuth.refresh(); location.reload(); });
    const backToTop = document.createElement("button");
    backToTop.type = "button";
    backToTop.className = "back-to-top";
    backToTop.setAttribute("aria-label", "Back to top");
    backToTop.innerHTML = "<span aria-hidden=\"true\">↑</span>";
    document.body.append(backToTop);
    const syncBackToTop = () => backToTop.classList.toggle("is-visible", window.scrollY > 420);
    window.addEventListener("scroll", syncBackToTop, { passive: true });
    backToTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    syncBackToTop();
    window.HacKUAuth.refresh();
  });
})();
