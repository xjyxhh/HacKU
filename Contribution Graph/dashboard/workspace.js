const ownedProjectsElement = document.getElementById("owned-projects");
const joinedProjectsElement = document.getElementById("joined-projects");
const errorElement = document.getElementById("error");
const emptyElement = document.getElementById("empty");

function renderProjects(element, projects) {
  element.replaceChildren(...projects.map((project) => {
    const card = document.createElement("article");
    card.className = "member-card";
    const title = document.createElement("h3");
    title.textContent = project.name;
    const details = document.createElement("p");
    details.textContent = `${project.role} · ${project.memberCount} 位成员 · ${project.taskCount} 项任务 · ${project.contributionCount} 条贡献 · ${project.pendingCount} 项待验证 · Token 余额 ${project.tokenBalance ?? "尚无账本"}`;
    const enter = document.createElement("a");
    enter.className = "nav-link";
    enter.href = `/?project=${encodeURIComponent(project.id)}`;
    enter.textContent = "进入项目";
    card.append(title, details, enter);
    return card;
  }));
}

async function loadWorkspace() {
  const response = await fetch("/api/workspace", { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `读取工作区失败 (${response.status})`);
  document.getElementById("greeting").textContent = `${data.profile.displayName} · 我的项目`;
  const owned = data.projects.filter((project) => project.role === "OWNER");
  const joined = data.projects.filter((project) => project.role !== "OWNER");
  renderProjects(ownedProjectsElement, owned);
  renderProjects(joinedProjectsElement, joined);
  document.getElementById("owned-empty").hidden = owned.length > 0;
  emptyElement.hidden = joined.length > 0;
}

document.getElementById("create-project").addEventListener("submit", async (event) => {
  event.preventDefault();
  errorElement.hidden = true;
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form));
    const response = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `创建失败 (${response.status})`);
    localStorage.setItem("contribution-project", body.id);
    location.assign(`/?project=${encodeURIComponent(body.id)}`);
  } catch (error) {
    errorElement.textContent = `创建项目失败：${error.message}`;
    errorElement.hidden = false;
    button.disabled = false;
  }
});

loadWorkspace().catch((error) => {
  errorElement.textContent = error.message;
  errorElement.hidden = false;
});
