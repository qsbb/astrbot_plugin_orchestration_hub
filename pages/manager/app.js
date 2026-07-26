let bridge = null;

async function resolveBridge(timeout = 3000) {
  if (window.AstrBotPluginPage) return window.AstrBotPluginPage;
  if (typeof window.waitForAstrBotBridge === "function") {
    return window.waitForAstrBotBridge(timeout);
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    if (window.AstrBotPluginPage) return window.AstrBotPluginPage;
  }

  throw new Error("请从 AstrBot 插件管理页打开此页面");
}

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

function parseJsonResponse(value) {
  const data = typeof value === "string" ? JSON.parse(value) : value;
  if (data?.success === false) {
    throw new Error(data.error || data.detail || "请求失败");
  }
  return data?.data ?? data;
}

async function apiGet(name) {
  if (!bridge || typeof bridge.apiGet !== "function") {
    throw new Error("AstrBot 页面通信接口尚未就绪");
  }
  return parseJsonResponse(await bridge.apiGet(name));
}

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
  if (typeof bridge.ready === "function") await bridge.ready();
  document.getElementById("refresh").addEventListener("click", () => load().catch(showError));
  await load();
}

function showError(error) {
  document.getElementById("error").textContent = error?.message || String(error);
}

init().catch(showError);
