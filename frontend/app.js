/* MedDesk 前端逻辑 — 调用 FastAPI */

const INTENT_LABEL = {
  appointment: "预约挂号",
  queue: "排队叫号",
  consultation: "医疗咨询",
  diagnosis: "症状诊断",
  chitchat: "一般对话",
};

const AGENT_LABEL = {
  AppointmentAgent: "预约 Agent",
  QueueAgent: "排队 Agent",
  ConsultationAgent: "咨询 Agent",
  DiagnosisAgent: "诊断 Agent",
  RouterAgent: "路由 Agent",
};

const state = {
  sessionId: localStorage.getItem("meddesk_sid") || "",
  busy: false,
  lastIntent: "",
  token: localStorage.getItem("meddesk_token") || "",
  user: null,
  platform: "password",
};

const ROLE_LABEL = {
  patient: "患者",
  doctor: "医生",
  admin: "管理员",
};

const el = {
  chatList: document.getElementById("chatList"),
  chatScroll: document.getElementById("chatScroll"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  btnSend: document.getElementById("btnSend"),
  btnReset: document.getElementById("btnReset"),
  btnNewSession: document.getElementById("btnNewSession"),
  sessionIdLabel: document.getElementById("sessionIdLabel"),
  healthPill: document.getElementById("healthPill"),
  healthText: document.getElementById("healthText"),
  intentStrip: document.getElementById("intentStrip"),
  intentMeta: document.getElementById("intentMeta"),
  scheduleForm: document.getElementById("scheduleForm"),
  scheduleDept: document.getElementById("scheduleDept"),
  scheduleDate: document.getElementById("scheduleDate"),
  scheduleResult: document.getElementById("scheduleResult"),
  queueForm: document.getElementById("queueForm"),
  queueDept: document.getElementById("queueDept"),
  queueName: document.getElementById("queueName"),
  queueResult: document.getElementById("queueResult"),
  diagProgress: document.getElementById("diagProgress"),
  diagHint: document.getElementById("diagHint"),
  serviceNav: document.getElementById("serviceNav"),
  quickPrompts: document.getElementById("quickPrompts"),
  toast: document.getElementById("toast"),
  authOverlay: document.getElementById("authOverlay"),
  authTabs: document.getElementById("authTabs"),
  authForm: document.getElementById("authForm"),
  authError: document.getElementById("authError"),
  btnLogin: document.getElementById("btnLogin"),
  btnRegister: document.getElementById("btnRegister"),
  btnSendSms: document.getElementById("btnSendSms"),
  btnLogout: document.getElementById("btnLogout"),
  btnOpenLogin: document.getElementById("btnOpenLogin"),
  btnSwitchAccount: document.getElementById("btnSwitchAccount"),
  btnComposerLogin: document.getElementById("btnComposerLogin"),
  composerGate: document.getElementById("composerGate"),
  accountRoot: document.getElementById("accountRoot"),
  accountTrigger: document.getElementById("accountTrigger"),
  accountMenu: document.getElementById("accountMenu"),
  accountAvatar: document.getElementById("accountAvatar"),
  accountName: document.getElementById("accountName"),
  accountRole: document.getElementById("accountRole"),
  menuAvatar: document.getElementById("menuAvatar"),
  menuName: document.getElementById("menuName"),
  menuRole: document.getElementById("menuRole"),
  menuUsername: document.getElementById("menuUsername"),
};

let WELCOME_TEMPLATE = null;

/* ── 工具 ─────────────────────────────────────────── */

function showToast(text, ms = 2600) {
  el.toast.textContent = text;
  el.toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.toast.hidden = true;
  }, ms);
}

function setSessionId(sid) {
  state.sessionId = sid || "";
  if (sid) localStorage.setItem("meddesk_sid", sid);
  else localStorage.removeItem("meddesk_sid");
  el.sessionIdLabel.textContent = sid ? `会话 ${sid}` : "开启新的导诊对话";
}

function scrollChat() {
  requestAnimationFrame(() => {
    el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
  });
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatConfidence(c) {
  if (c == null || Number.isNaN(c)) return "";
  return `置信度 ${(Number(c) * 100).toFixed(0)}%`;
}

function setBusy(busy) {
  state.busy = busy;
  el.btnSend.disabled = busy;
  el.chatInput.disabled = busy;
}

function clearChatUI() {
  if (!WELCOME_TEMPLATE) {
    WELCOME_TEMPLATE = document.querySelector(".msg.welcome");
  }
  const welcome = WELCOME_TEMPLATE ? WELCOME_TEMPLATE.cloneNode(true) : null;
  el.chatList.replaceChildren();
  if (welcome) {
    el.chatList.appendChild(welcome);
  }
  el.chatScroll.classList.add("is-empty");
  setIntent("");
  el.intentMeta.textContent = "";
  el.diagProgress
    .querySelectorAll(".progress-item")
    .forEach((item) => item.classList.remove("is-done"));
  el.diagHint.textContent = "开始症状诊断后，这里会显示已收集信息。";
  el.scheduleResult.innerHTML = `<p class="empty">选择科室后查询今日排班。</p>`;
  el.queueResult.innerHTML = `<p class="empty">取号后可在此查看号序与等待时间。</p>`;
  el.chatInput.value = "";
  el.chatInput.style.height = "auto";
  if (isLoggedIn()) el.chatInput.focus();
}

function setIntent(intent) {
  const chips = el.intentStrip.querySelectorAll(".intent-chip");
  chips.forEach((chip) => {
    chip.classList.toggle("is-on", chip.dataset.intent === intent);
  });
}

function updateDiagProgress(collected) {
  const fields = ["main_symptom", "duration", "symptom_features", "accompanying"];
  const items = el.diagProgress.querySelectorAll(".progress-item");
  items.forEach((item) => {
    const key = item.dataset.field;
    const done = !!(collected && collected[key]);
    item.classList.toggle("is-done", done);
  });
  if (collected && Object.keys(collected).length) {
    el.diagHint.textContent = `已采集 ${fields.filter((f) => collected[f]).length}/${fields.length} 项关键信息。`;
  } else {
    el.diagHint.textContent = "开始症状诊断后，这里会显示已收集信息。";
  }
}

/* ── 消息渲染 ─────────────────────────────────────── */

function appendUser(text) {
  const article = document.createElement("article");
  article.className = "msg user";
  article.innerHTML = `<div class="msg-body">${escapeHtml(text)}</div>`;
  el.chatList.appendChild(article);
  scrollChat();
}

function appendAssistant(reply, meta = {}) {
  const article = document.createElement("article");
  article.className = "msg assistant";

  const tags = [];
  if (meta.intent && INTENT_LABEL[meta.intent]) {
    tags.push(`<span class="tag intent">${INTENT_LABEL[meta.intent]}</span>`);
  }
  if (meta.agent && AGENT_LABEL[meta.agent]) {
    tags.push(`<span class="tag agent">${AGENT_LABEL[meta.agent]}</span>`);
  }
  if (meta.confidence != null && meta.confidence > 0) {
    tags.push(`<span class="tag mono">${formatConfidence(meta.confidence)}</span>`);
  }
  if (meta.needs_clarification) {
    tags.push(`<span class="tag warn">需要澄清</span>`);
  }

  const tagsHtml = tags.length
    ? `<div class="msg-meta">${tags.join("")}</div>`
    : "";

  article.innerHTML = `<div class="msg-body">${escapeHtml(reply)}${tagsHtml}</div>`;
  el.chatList.appendChild(article);
  scrollChat();
}

function appendTyping() {
  const article = document.createElement("article");
  article.className = "msg assistant";
  article.id = "typingMsg";
  article.innerHTML = `<div class="msg-body"><span class="typing"><span class="sr-only">正在回复</span><i></i><i></i><i></i></span></div>`;
  el.chatList.appendChild(article);
  scrollChat();
}

function removeTyping() {
  const node = document.getElementById("typingMsg");
  if (node) node.remove();
}

/* ── API ──────────────────────────────────────────── */

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch (_) {
      /* ignore */
    }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/* ── 认证 ──────────────────────────────────────────── */

function isLoggedIn() {
  return !!(state.token && state.user);
}

function setAccountMenuOpen(open) {
  if (!el.accountMenu || !el.accountTrigger) return;
  if (!isLoggedIn()) {
    el.accountMenu.hidden = true;
    el.accountTrigger.setAttribute("aria-expanded", "false");
    return;
  }
  el.accountMenu.hidden = !open;
  el.accountTrigger.setAttribute("aria-expanded", open ? "true" : "false");
}

function openLoginDialog(reason = "") {
  if (isLoggedIn()) {
    // 已登录仍点登录 → 视为切换账号
    setAccountMenuOpen(false);
  }
  return requireLogin(reason);
}

function setAuthSession(token, user) {
  state.token = token || "";
  state.user = user || null;
  if (token) localStorage.setItem("meddesk_token", token);
  else localStorage.removeItem("meddesk_token");
  renderUser();
}

function renderUser() {
  const logged = isLoggedIn();
  const name = logged ? (state.user.display_name || state.user.username) : "";
  const roleLabel = logged ? (ROLE_LABEL[state.user.role] || state.user.role) : "";
  const initial = logged ? (name || "用").slice(0, 1) : "";

  // 左下角：未登录显示 CTA，已登录显示账号行（用 class 双保险）
  if (el.btnOpenLogin) {
    el.btnOpenLogin.hidden = logged;
    el.btnOpenLogin.classList.toggle("is-hidden", logged);
  }
  if (el.accountTrigger) {
    el.accountTrigger.hidden = !logged;
    el.accountTrigger.classList.toggle("is-hidden", !logged);
  }
  // 未登录时清掉默认「张」字，避免误显示
  if (!logged && el.accountAvatar) el.accountAvatar.textContent = "";

  if (logged) {
    el.accountName.textContent = name;
    el.accountRole.textContent = roleLabel;
    if (el.accountAvatar) el.accountAvatar.textContent = initial;
    if (el.menuAvatar) el.menuAvatar.textContent = initial;
    if (el.menuName) el.menuName.textContent = name;
    if (el.menuRole) el.menuRole.textContent = roleLabel;
    if (el.menuUsername) el.menuUsername.textContent = `@${state.user.username}`;
    if (el.queueName && !el.queueName.value) el.queueName.value = name;
  } else {
    setAccountMenuOpen(false);
    if (el.accountMenu) el.accountMenu.hidden = true;
  }

  // 输入区登录门禁
  const form = el.chatForm;
  if (el.composerGate) el.composerGate.hidden = logged;
  if (form) form.classList.toggle("is-locked", !logged);
  if (el.chatInput) {
    el.chatInput.readOnly = !logged;
    el.chatInput.placeholder = logged
      ? "描述您的需求，例如：我想预约明天看内科…"
      : "登录后开始对话";
  }
  if (el.btnSend) {
    el.btnSend.textContent = logged ? "发送" : "登录";
  }
}

/** 立刻显示登录框（不依赖 Promise，给按钮点击用） */
function showLoginModal() {
  const overlay = document.getElementById("authOverlay");
  if (!overlay) {
    showToast("登录组件未加载，请刷新页面");
    return;
  }
  overlay.hidden = false;
  overlay.style.display = "grid";
  showAuthError("");
  if (el.accountMenu) el.accountMenu.hidden = true;
  if (el.accountTrigger) el.accountTrigger.setAttribute("aria-expanded", "false");
  const pane = el.authForm?.querySelector(
    `.auth-pane[data-platform="${state.platform || "password"}"]`
  );
  const first = pane?.querySelector("input");
  first?.focus();
}

/** 弹出登录框；resolve(true)=已登录，resolve(false)=取消 */
function requireLogin(reason = "") {
  if (isLoggedIn()) return Promise.resolve(true);
  showLoginModal();
  if (reason) showToast(reason, 3000);

  return new Promise((resolve) => {
    if (state._loginResolve) {
      const prev = state._loginResolve;
      state._loginResolve = null;
      prev(false);
    }
    state._loginResolve = resolve;
  });
}

function settleLogin(ok) {
  const resolve = state._loginResolve;
  state._loginResolve = null;
  if (resolve) resolve(!!ok);
}

function showAuthError(msg) {
  if (!msg) {
    el.authError.hidden = true;
    el.authError.textContent = "";
    return;
  }
  el.authError.hidden = false;
  el.authError.textContent = msg;
}

function activePlatform() {
  return state.platform;
}

function switchPlatform(platform) {
  state.platform = platform;
  el.authTabs.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.platform === platform);
  });
  el.authForm.querySelectorAll(".auth-pane").forEach((pane) => {
    pane.hidden = pane.dataset.platform !== platform;
  });
  showAuthError("");
}

function formValue(name) {
  const pane = el.authForm.querySelector(`.auth-pane[data-platform="${activePlatform()}"]`);
  const input = pane?.querySelector(`[name="${name}"]`);
  return (input?.value || "").trim();
}

async function loadPlatforms() {
  try {
    const data = await api("/api/auth/platforms");
    const platforms = data.platforms || [];
    el.authTabs.innerHTML = platforms
      .map(
        (p, i) =>
          `<button type="button" class="auth-tab${i === 0 ? " is-active" : ""}" data-platform="${p.id}" role="tab">${p.label}</button>`
      )
      .join("");
    switchPlatform(platforms[0]?.id || "password");
  } catch (_) {
    el.authTabs.innerHTML = `
      <button type="button" class="auth-tab is-active" data-platform="password">账号密码</button>
      <button type="button" class="auth-tab" data-platform="phone">手机</button>
      <button type="button" class="auth-tab" data-platform="wechat">微信</button>
      <button type="button" class="auth-tab" data-platform="dingtalk">钉钉</button>`;
    switchPlatform("password");
  }
}

async function restoreSession() {
  if (!state.token) {
    state.user = null;
    renderUser();
    return;
  }
  try {
    const data = await api("/api/auth/me");
    state.user = data.user;
    renderUser();
  } catch (_) {
    // token 失效：本地清理，不强制弹登录框
    state.token = "";
    state.user = null;
    localStorage.removeItem("meddesk_token");
    renderUser();
  }
}

async function doLogin(ev) {
  ev.preventDefault();
  showAuthError("");
  const platform = activePlatform();
  const payload = { platform };

  if (platform === "password") {
    payload.username = formValue("username");
    payload.password = formValue("password");
    if (!payload.username || !payload.password) {
      showAuthError("请输入用户名和密码");
      return;
    }
  } else if (platform === "phone") {
    payload.phone = formValue("phone");
    payload.code = formValue("code");
    if (!payload.phone || !payload.code) {
      showAuthError("请输入手机号和验证码");
      return;
    }
  } else {
    payload.code = formValue("code");
    if (!payload.code) {
      showAuthError("请输入授权码");
      return;
    }
  }

  el.btnLogin.disabled = true;
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setAuthSession(data.token, data.user);
    el.authOverlay.hidden = true;
    showAuthError("");
    settleLogin(true);
    showToast(`欢迎，${data.user.display_name || data.user.username}`);
    loadDepartments();
  } catch (err) {
    // 登录失败：只提示，不 resolve 拦截 Promise（用户可继续重试）
    showAuthError(err.message);
  } finally {
    el.btnLogin.disabled = false;
  }
}

async function doRegister() {
  const platform = activePlatform();
  if (platform !== "password") {
    showAuthError("请切换到「账号密码」页签后注册，或直接用手机/微信登录自动开户");
    return;
  }
  const username = formValue("username");
  const password = formValue("password");
  if (!username || !password) {
    showAuthError("请先填写用户名和密码再注册");
    return;
  }
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password, display_name: username }),
    });
    setAuthSession(data.token, data.user);
    el.authOverlay.hidden = true;
    settleLogin(true);
    showToast("注册成功，已自动登录");
  } catch (err) {
    showAuthError(err.message);
  }
}

async function sendSms() {
  const phone = formValue("phone");
  if (!phone || phone.length < 11) {
    showAuthError("请输入 11 位手机号");
    return;
  }
  try {
    const data = await api("/api/auth/sms", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });
    showToast(data.message || "验证码已发送");
  } catch (err) {
    showAuthError(err.message);
  }
}

async function doLogout() {
  const token = state.token;
  setAccountMenuOpen(false);

  // 先本地登出，保证界面立刻可用
  state.token = "";
  state.user = null;
  localStorage.removeItem("meddesk_token");
  if (el.authOverlay) el.authOverlay.hidden = true;
  settleLogin(false);
  renderUser();

  if (token) {
    try {
      const res = await fetch("/api/auth/logout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) console.warn("logout http", res.status);
    } catch (err) {
      console.warn("logout api", err);
    }
  }
  showToast("已退出登录");
}

function bindAuth() {
  loadPlatforms();
  restoreSession();

  el.authTabs.addEventListener("click", (ev) => {
    const tab = ev.target.closest(".auth-tab");
    if (!tab) return;
    switchPlatform(tab.dataset.platform);
  });
  el.authForm.addEventListener("submit", doLogin);
  el.btnRegister.addEventListener("click", doRegister);
  el.btnSendSms.addEventListener("click", sendSms);

  // 左栏底部：事件委托，兼容节点被替换/缓存旧结构
  const foot = document.querySelector(".rail-foot");
  foot?.addEventListener("click", (ev) => {
    const loginBtn = ev.target.closest("#btnOpenLogin");
    if (loginBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      showLoginModal();
      return;
    }
    const trigger = ev.target.closest("#accountTrigger");
    if (trigger) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!isLoggedIn()) {
        showLoginModal();
        return;
      }
      setAccountMenuOpen(el.accountMenu?.hidden !== false);
      return;
    }
    const newSess = ev.target.closest("#btnNewSession");
    if (newSess) {
      ev.preventDefault();
      newSession();
    }
  });

  el.btnComposerLogin?.addEventListener("click", (ev) => {
    ev.preventDefault();
    showLoginModal();
  });

  el.btnSwitchAccount?.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    setAccountMenuOpen(false);
    showLoginModal();
  });

  el.btnLogout?.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    doLogout();
  });

  document.addEventListener("click", (ev) => {
    if (!el.accountMenu || el.accountMenu.hidden) return;
    if (el.accountRoot && !el.accountRoot.contains(ev.target)) {
      setAccountMenuOpen(false);
    }
  });

  el.authOverlay.addEventListener("click", (ev) => {
    if (ev.target === el.authOverlay) {
      el.authOverlay.hidden = true;
      settleLogin(false);
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      if (el.authOverlay && !el.authOverlay.hidden) {
        el.authOverlay.hidden = true;
        settleLogin(false);
      }
      setAccountMenuOpen(false);
    }
  });
}

async function sendChat(message) {
  const text = (message || "").trim();
  if (!text || state.busy) return;

  // 硬拦截：未登录不能对话
  if (!isLoggedIn()) {
    const ok = await requireLogin("请先登录后再开始对话");
    if (!ok || !isLoggedIn()) return;
  }

  el.chatScroll.classList.remove("is-empty");
  appendUser(text);
  appendTyping();
  setBusy(true);

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message: text,
        session_id: state.sessionId || null,
      }),
    });

    removeTyping();
    setSessionId(data.session_id);
    state.lastIntent = data.intent;
    setIntent(data.intent);
    el.intentMeta.textContent = data.agent
      ? `${AGENT_LABEL[data.agent] || data.agent} · ${formatConfidence(data.confidence)}`
      : formatConfidence(data.confidence);

    appendAssistant(data.reply || "（空回复）", data);

    if (data.intent === "diagnosis") {
      updateDiagProgress(data.collected_info || {});
    }
  } catch (err) {
    removeTyping();
    if (err.status === 401) {
      setAuthSession("", null);
      appendAssistant("登录已失效，请重新登录后再继续。", {});
      requireLogin("登录已过期");
      return;
    }
    appendAssistant(`请求失败：${err.message}`, {});
    showToast("对话请求失败");
  } finally {
    setBusy(false);
    if (isLoggedIn()) el.chatInput.focus();
  }
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    el.healthPill.classList.remove("warn", "err");
    el.healthPill.classList.add("ok");
    if (data.rag?.ready) {
      el.healthText.textContent = `就绪 · 知识库 ${data.rag.doc_count}`;
    } else if (data.rag?.initializing) {
      el.healthPill.classList.remove("ok");
      el.healthPill.classList.add("warn");
      el.healthText.textContent = "知识库初始化中…";
    } else {
      el.healthPill.classList.remove("ok");
      el.healthPill.classList.add("warn");
      el.healthText.textContent = data.rag?.message || "服务可用";
    }
  } catch (_) {
    el.healthPill.classList.remove("ok", "warn");
    el.healthPill.classList.add("err");
    el.healthText.textContent = "服务不可达";
  }
}

async function loadDepartments() {
  try {
    const data = await api("/api/departments");
    const depts = data.data?.departments || [];
    const options = depts
      .map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`)
      .join("");
    el.scheduleDept.innerHTML = options || `<option value="">无科室</option>`;
    el.queueDept.innerHTML = options || `<option value="">无科室</option>`;
    if (depts.includes("内科")) {
      el.scheduleDept.value = "内科";
      el.queueDept.value = "内科";
    }
  } catch (err) {
    showToast(`科室加载失败：${err.message}`);
  }
}

function todayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function querySchedule(ev) {
  ev.preventDefault();
  // 排班查询允许未登录浏览；若需登录可在此加 requireLogin
  const department = el.scheduleDept.value;
  if (!department) return;
  const date = el.scheduleDate.value || todayStr();
  el.scheduleResult.innerHTML = `<p class="empty">查询中…</p>`;
  try {
    const data = await api("/api/schedule", {
      method: "POST",
      body: JSON.stringify({ department, date }),
    });
    if (!data.success) {
      el.scheduleResult.innerHTML = `<p class="empty">${escapeHtml(data.message || "查询失败")}</p>`;
      return;
    }
    const rows = data.data.schedule || [];
    if (!rows.length) {
      el.scheduleResult.innerHTML = `<p class="empty">该日期暂无排班。</p>`;
      return;
    }
    el.scheduleResult.innerHTML = rows
      .map(
        (r) => `
      <div class="sched-row">
        <strong>${escapeHtml(r.doctor)} · ${escapeHtml(r.title)}</strong>
        <span class="slots">${escapeHtml((r.periods || []).join(" / "))}</span>
        <span class="muted">${escapeHtml(r.specialty)} · 余号 ${r.available_slots ?? "—"}</span>
      </div>`
      )
      .join("");
  } catch (err) {
    el.scheduleResult.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
  }
}

async function takeNumber(ev) {
  ev.preventDefault();
  if (!isLoggedIn()) {
    const ok = await requireLogin("请先登录后再取号");
    if (!ok) return;
  }
  const department = el.queueDept.value;
  const patient_name = el.queueName.value.trim();
  if (!department || !patient_name) return;
  el.queueResult.innerHTML = `<p class="empty">取号中…</p>`;
  try {
    const data = await api("/api/queue/take", {
      method: "POST",
      body: JSON.stringify({ department, patient_name }),
    });
    if (!data.success) {
      el.queueResult.innerHTML = `<p class="empty">${escapeHtml(data.message || "取号失败")}</p>`;
      return;
    }
    const d = data.data;
    el.queueResult.innerHTML = `
      <div class="queue-card">
        <div class="num">${escapeHtml(String(d.queue_number ?? "—"))}</div>
        <div class="meta">${escapeHtml(d.department || department)} · ${escapeHtml(patient_name)}</div>
        <div class="meta">前面还有 ${d.ahead_count ?? 0} 人 · ${escapeHtml(d.estimated_wait || "—")}</div>
      </div>`;
    showToast(`取号成功：${d.queue_number} 号`);
  } catch (err) {
    el.queueResult.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
  }
}

async function resetSession() {
  if (state.sessionId) {
    try {
      await api("/api/session/reset", {
        method: "POST",
        body: JSON.stringify({ message: "reset", session_id: state.sessionId }),
      });
    } catch (err) {
      showToast(err.message);
    }
  }
  setSessionId("");
  clearChatUI();
}

function newSession() {
  setSessionId("");
  clearChatUI();
}

/* ── 事件绑定 ─────────────────────────────────────── */

el.chatForm.addEventListener("submit", (ev) => {
  ev.preventDefault();
  if (!isLoggedIn()) {
    requireLogin("请先登录后再开始对话");
    return;
  }
  const text = el.chatInput.value;
  el.chatInput.value = "";
  el.chatInput.style.height = "auto";
  sendChat(text);
});

el.chatInput.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    el.chatForm.requestSubmit();
  }
});

el.chatInput.addEventListener("input", () => {
  el.chatInput.style.height = "auto";
  el.chatInput.style.height = Math.min(el.chatInput.scrollHeight, 140) + "px";
});

el.serviceNav.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".rail-item");
  if (!btn) return;
  el.serviceNav.querySelectorAll(".rail-item").forEach((b) => b.classList.remove("is-active"));
  btn.classList.add("is-active");
  if (!isLoggedIn()) {
    requireLogin("请先登录后再使用该服务");
    return;
  }
  const prompt = btn.dataset.prompt || "";
  if (prompt) {
    el.chatInput.value = prompt;
    el.chatInput.focus();
  } else {
    el.chatInput.focus();
  }
});

el.chatList.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".chip, .service-tile");
  if (!btn) return;
  if (!isLoggedIn()) {
    requireLogin("请先登录后再开始对话");
    return;
  }
  sendChat(btn.dataset.q || btn.textContent);
});

el.btnReset.addEventListener("click", resetSession);
el.btnNewSession.addEventListener("click", newSession);
el.scheduleForm.addEventListener("submit", querySchedule);
el.queueForm.addEventListener("submit", takeNumber);

/* ── 初始化 ───────────────────────────────────────── */

function init() {
  WELCOME_TEMPLATE = document.querySelector(".msg.welcome");
  el.chatScroll.classList.add("is-empty");
  if (el.authOverlay) el.authOverlay.hidden = true;
  bindAuth();
  renderUser();
  setSessionId(state.sessionId);
  el.scheduleDate.value = todayStr();
  loadHealth();
  loadDepartments();
  setInterval(loadHealth, 30000);
}

init();
