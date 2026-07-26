let bridge;

async function resolveBridge() {
  if (window.astrbot?.plugin?.page) return window.astrbot.plugin.page;
  if (typeof window.waitForAstrBotBridge === "function") return window.waitForAstrBotBridge();
  throw new Error("AstrBot Plugin Page bridge unavailable");
}

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const apiGet = (path) => bridge.request({method: "GET", path: `/astrbot_plugin_orchestration_hub/${path}`});

function renderServices(items) {
  document.getElementById("service-list").innerHTML = items.length ? items.map((item) => `<article class="item"><strong>${escapeHtml(item.service)}</strong> <code>${escapeHtml(item.version)}</code><div class="muted">${escapeHtml(item.provider_plugin)} · ${escapeHtml(item.state)} · ${escapeHtml(item.operations.join(", "))}</div></article>`).join("") : '<p class="muted">暂无已注册服务</p>';
}

function renderCalls(items) {
  document.getElementById("call-list").innerHTML = items.length ? items.slice().reverse().map((item) => `<article class="item"><strong>${escapeHtml(item.service)}:${escapeHtml(item.operation)}</strong><div class="muted">${escapeHtml(item.result)} · ${escapeHtml(item.duration_ms)} ms · ${escapeHtml(item.caller)}</div></article>`).join("") : '<p class="muted">暂无调用记录</p>';
}

async function load() {
  document.getElementById("error").textContent = "";
  const [overview, services, telemetry] = await Promise.all([apiGet("overview"), apiGet("services"), apiGet("telemetry")]);
  document.getElementById("services").textContent = overview.services;
  document.getElementById("instances").textContent = overview.instances;
  document.getElementById("revision").textContent = overview.revision;
  renderServices(services.services || []);
  renderCalls(telemetry.recent || []);
}

async function init() {
  bridge = await resolveBridge();
  await bridge.ready();
  document.getElementById("refresh").addEventListener("click", () => load().catch(showError));
  await load();
}

function showError(error) {
  document.getElementById("error").textContent = error?.message || String(error);
}

init().catch(showError);
