document.addEventListener("DOMContentLoaded", async () => {
  await window.HacKUAuth.refresh();
  const response = await fetch("/api/demo", {cache:"no-store"}); const data = await response.json();
  document.getElementById("demo-steps").innerHTML = data.steps.map((step, index) => `<article class="panel workspace-card"><p class="kicker">STEP ${index + 1} · ${step.kind}</p><h2>${step.title}</h2><p>${step.detail}</p></article>`).join("");
});
