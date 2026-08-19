let bridge = null;
let eventsBound = false;
let loadPromise = null;
let connectionAttempt = 0;

function withTimeout(promise, timeout, code) {
  let timer;
  return Promise.race([
    Promise.resolve(promise),
    new Promise((_, reject) => {
      timer = window.setTimeout(() => reject(new Error(code)), timeout);
    }),
  ]).finally(() => window.clearTimeout(timer));
}

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
  if (!bridge) throw new Error("AstrBot 页面通信接口尚未就绪");
  if (loadPromise) return loadPromise;
  const refresh = document.getElementById("refresh");
  refresh.disabled = true;
  refresh.setAttribute("aria-busy", "true");
  document.getElementById("error").textContent = "";
  loadPromise = Promise.all([
    withTimeout(apiGet("overview"), 8000, "读取总览超时"),
    withTimeout(apiGet("services"), 8000, "读取服务列表超时"),
    withTimeout(apiGet("telemetry"), 8000, "读取近期调用超时"),
  ]).then(([overview, services, telemetry]) => {
    document.getElementById("services").textContent = overview.services;
    document.getElementById("instances").textContent = overview.instances;
    document.getElementById("revision").textContent = overview.revision;
    renderServices(services.services || []);
    renderCalls(telemetry.recent || []);
    document.getElementById("startup-error").hidden = true;
    document.getElementById("startup-error").textContent = "";
  }).finally(() => {
    loadPromise = null;
    refresh.disabled = false;
    refresh.removeAttribute("aria-busy");
  });
  return loadPromise;
}

function bindEvents() {
  if (eventsBound) return;
  eventsBound = true;
  document.getElementById("refresh").addEventListener("click", () => connectAndLoad().catch(showError));
}

async function connectAndLoad() {
  const attempt = ++connectionAttempt;
  if (!bridge) bridge = await resolveBridge();
  if (typeof bridge.ready === "function") {
    await withTimeout(bridge.ready(), 5000, "AstrBot 页面通信初始化超时，请点击刷新重试");
  }
  if (attempt !== connectionAttempt) return;
  document.getElementById("startup-error").hidden = true;
  await load();
}

async function init() {
  bindEvents();
  await connectAndLoad();
}

function showError(error) {
  const message = error?.message || String(error);
  const startup = document.getElementById("startup-error");
  startup.textContent = message;
  startup.hidden = false;
  document.getElementById("error").textContent = message;
}

init().catch(showError);
