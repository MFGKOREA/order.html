const loginForm = document.querySelector("#login");
const kitchen = document.querySelector("#kitchen");
const note = document.querySelector("#login-note");

function el(tag, text) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
}

function showLogin(message) {
  loginForm.hidden = false;
  kitchen.hidden = true;
  note.hidden = !message;
  note.textContent = message || "";
}

function render(snapshot) {
  loginForm.hidden = true;
  kitchen.hidden = false;
  kitchen.replaceChildren();
  const confirms = snapshot?.confirms || [];
  if (!confirms.length) {
    const empty = el("p", "지금 확인할 발주 없음");
    empty.className = "empty";
    kitchen.append(empty);
  }
  for (const item of confirms) {
    const form = el("form");
    form.className = "ticket";
    const button = el("button", `확인 #${item.id} ${item.text || ""}`.trim());
    button.type = "submit";
    form.append(button);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      sendConfirm(item.id, button);
    });
    kitchen.append(form);
  }
  const whoTitle = el("h2", "연결");
  const who = el("ul");
  who.className = "who";
  for (const pair of snapshot?.badges || []) {
    const li = el("li");
    li.append(el("span", pair[0]), Object.assign(el("b", pair[1]), { dataset: { state: pair[1] } }));
    who.append(li);
  }
  const railTitle = el("h2", "요청");
  const rail = el("ul");
  rail.className = "rail";
  const rows = snapshot?.timeline || [];
  if (!rows.length) rail.append(el("li", "아직 없음"));
  for (const item of rows) {
    const li = el("li");
    const when = el("span", `${(item.at || "").slice(11, 16)} ${item.id || ""} ${item.status || ""}`.trim());
    when.className = "when";
    li.append(when, document.createTextNode(`${item.from || ""}에서 ${item.to || ""} ${item.body || ""}`.trim()));
    rail.append(li);
  }
  const spend = el("p", snapshot?.spend || "");
  spend.className = "spend";
  kitchen.append(whoTitle, who, railTitle, rail, spend);
}

async function sendConfirm(taskId, button) {
  const storageKey = `confirm-${taskId}`;
  let idempotencyKey = sessionStorage.getItem(storageKey);
  if (!idempotencyKey) {
    idempotencyKey = `confirm-${taskId}-${crypto.randomUUID()}`;
    sessionStorage.setItem(storageKey, idempotencyKey);
  }
  button.disabled = true;
  const response = await fetch("/api/confirm", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ task_id: Number(taskId), idempotency_key: idempotencyKey }),
  });
  button.disabled = false;
  if (response.status === 401) showLogin("다시 들어가 주세요");
  else if (response.ok) sessionStorage.removeItem(storageKey);
}

async function load() {
  const response = await fetch("/api/snapshot", { headers: { accept: "application/json" } });
  if (response.status === 401) {
    showLogin("");
    return;
  }
  if (!response.ok) {
    showLogin("화면을 불러오지 못했습니다");
    return;
  }
  const body = await response.json();
  render(body.snapshot);
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ password: document.querySelector("#password").value }),
  });
  document.querySelector("#password").value = "";
  if (!response.ok) {
    showLogin("들어가지 못했습니다");
    return;
  }
  load();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
load();
setInterval(load, 3000);
