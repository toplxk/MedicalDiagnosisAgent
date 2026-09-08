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
};

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
  el.sessionIdLabel.textContent = sid || "—";
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
  article.innerHTML = `<div class="msg-body"><span class="typing" aria-label="正在回复"><i></i><i></i><i></i></span></div>`;
  el.chatList.appendChild(article);
  scrollChat();
}

function removeTyping() {
  const node = document.getElementById("typingMsg");
  if (node) node.remove();
}

/* ── API ──────────────────────────────────────────── */

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

async function sendChat(message) {
  const text = message.trim();
  if (!text || state.busy) return;

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
    appendAssistant(`请求失败：${err.message}`, {});
    showToast("对话请求失败");
  } finally {
    setBusy(false);
    el.chatInput.focus();
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
  if (!state.sessionId) {
    showToast("当前还没有活动会话");
    return;
  }
  try {
    await api("/api/session/reset", {
      method: "POST",
      body: JSON.stringify({ message: "reset", session_id: state.sessionId }),
    });
    // 重置后新开会话，清空界面
    setSessionId("");
    location.reload();
  } catch (err) {
    showToast(err.message);
  }
}

function newSession() {
  setSessionId("");
  location.reload();
}

/* ── 事件绑定 ─────────────────────────────────────── */

el.chatForm.addEventListener("submit", (ev) => {
  ev.preventDefault();
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
  const prompt = btn.dataset.prompt || "";
  if (prompt) {
    el.chatInput.value = prompt;
    el.chatInput.focus();
  } else {
    el.chatInput.focus();
  }
});

el.quickPrompts?.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".chip");
  if (!btn) return;
  sendChat(btn.dataset.q || btn.textContent);
});

el.btnReset.addEventListener("click", resetSession);
el.btnNewSession.addEventListener("click", newSession);
el.scheduleForm.addEventListener("submit", querySchedule);
el.queueForm.addEventListener("submit", takeNumber);

/* ── 初始化 ───────────────────────────────────────── */

function init() {
  setSessionId(state.sessionId);
  el.scheduleDate.value = todayStr();
  loadHealth();
  loadDepartments();
  setInterval(loadHealth, 30000);
}

init();
