const tg = window.Telegram?.WebApp;
const mode = new URL(window.location.href).searchParams.get("mode") === "admin" ? "admin" : "user";
const SERVICES = [
  "🍔 Яндекс Еда",
  "🚗 Купер",
  "🛒 Яндекс Лавка",
  "🛵 Самокат",
  "🥗 Delivery Club",
];

const ADMIN_FILTERS = [
  ["all", "Все"],
  ["new", "Новые"],
  ["in_progress", "В работе"],
  ["waiting_user", "Ждёт клиента"],
  ["done", "Завершённые"],
  ["rejected", "Отклонённые"],
];

const state = {
  mode,
  initData: tg?.initData || "",
  sessionToken: localStorage.getItem("sr_session_token") || "",
  bootstrap: null,
  selectedService: SERVICES[0],
  ticket: null,
  userMessages: [],
  adminFilter: "all",
  adminSearch: "",
  adminTickets: [],
  adminSelectedId: null,
};

const el = (id) => document.getElementById(id);

const dom = {
  heroTitle: el("heroTitle"),
  heroSubtitle: el("heroSubtitle"),
  modeBadge: el("modeBadge"),
  globalAlert: el("globalAlert"),
  userApp: el("userApp"),
  adminApp: el("adminApp"),

  telegramUserBadge: el("telegramUserBadge"),
  profileId: el("profileId"),
  profileUsername: el("profileUsername"),
  profileName: el("profileName"),
  channelLink: el("channelLink"),
  reviewsLink: el("reviewsLink"),
  agreementLink: el("agreementLink"),

  authTitle: el("authTitle"),
  authStatusChip: el("authStatusChip"),
  registerBox: el("registerBox"),
  loginBox: el("loginBox"),
  cabinetBox: el("cabinetBox"),
  registerLogin: el("registerLogin"),
  registerPassword: el("registerPassword"),
  registerButton: el("registerButton"),
  loginValue: el("loginValue"),
  loginPassword: el("loginPassword"),
  loginButton: el("loginButton"),
  logoutButton: el("logoutButton"),
  cabinetLogin: el("cabinetLogin"),
  resetPasswordToggle: el("resetPasswordToggle"),
  resetBox: el("resetBox"),
  resetLogin: el("resetLogin"),
  resetPassword: el("resetPassword"),
  resetButton: el("resetButton"),

  ticketFormCard: el("ticketFormCard"),
  serviceGrid: el("serviceGrid"),
  ticketAmount: el("ticketAmount"),
  ticketDescription: el("ticketDescription"),
  summaryCommission: el("summaryCommission"),
  summaryToPay: el("summaryToPay"),
  summaryAfter: el("summaryAfter"),
  createTicketButton: el("createTicketButton"),
  ticketFormChip: el("ticketFormChip"),

  activeTicketCard: el("activeTicketCard"),
  ticketTitle: el("ticketTitle"),
  ticketStatus: el("ticketStatus"),
  ticketService: el("ticketService"),
  ticketAmountValue: el("ticketAmountValue"),
  ticketCreated: el("ticketCreated"),
  ticketUpdated: el("ticketUpdated"),
  ticketDescriptionValue: el("ticketDescriptionValue"),

  chatCard: el("chatCard"),
  userMessages: el("userMessages"),
  userReplyInput: el("userReplyInput"),
  userReplyButton: el("userReplyButton"),

  adminSummary: el("adminSummary"),
  adminStatusChip: el("adminStatusChip"),
  adminFilters: el("adminFilters"),
  adminSearch: el("adminSearch"),
  adminSearchButton: el("adminSearchButton"),
  ticketCounter: el("ticketCounter"),
  ticketList: el("ticketList"),
  adminTicketTitle: el("adminTicketTitle"),
  adminTicketStatus: el("adminTicketStatus"),
  adminTicketMeta: el("adminTicketMeta"),
  adminTicketActions: el("adminTicketActions"),
  adminMessages: el("adminMessages"),
  adminReplyInput: el("adminReplyInput"),
  adminReplyButton: el("adminReplyButton"),
};

function setAlert(text, type = "info") {
  if (!text) {
    dom.globalAlert.classList.add("hidden");
    dom.globalAlert.textContent = "";
    dom.globalAlert.className = "alert hidden";
    return;
  }
  dom.globalAlert.className = `alert ${type}`;
  dom.globalAlert.textContent = text;
  dom.globalAlert.classList.remove("hidden");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

function formatRub(value) {
  const num = Number(value || 0);
  return `${new Intl.NumberFormat("ru-RU").format(Math.round(num))} ₽`;
}

function parseAmount(value) {
  const normalized = String(value || "").replace(/\s+/g, "").replace(",", ".").replace(/[^\d.]/g, "");
  const num = Number(normalized);
  return Number.isFinite(num) ? num : 0;
}

async function apiGet(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  const res = await fetch(url.toString(), { credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.message || data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(path, payload = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.message || data.error || `HTTP ${res.status}`);
  return data;
}

function saveToken(token) {
  state.sessionToken = token || "";
  if (token) localStorage.setItem("sr_session_token", token);
  else localStorage.removeItem("sr_session_token");
}

function userPayload(extra = {}) {
  return {
    initData: state.initData,
    sessionToken: state.sessionToken,
    ...extra,
  };
}

function requireTelegram() {
  if (!state.initData) {
    setAlert("Открой это мини-приложение из Telegram. В обычном браузере авторизация Telegram недоступна.", "error");
    return false;
  }
  return true;
}

function updateHero() {
  dom.modeBadge.textContent = state.mode.toUpperCase();
  if (state.mode === "admin") {
    dom.heroTitle.textContent = "Web Admin — управление тикетами";
    dom.heroSubtitle.textContent = "Очередь заявок, статусы, назначение на себя и переписка с клиентами из одной панели.";
    dom.userApp.classList.add("hidden");
    dom.adminApp.classList.remove("hidden");
  } else {
    dom.heroTitle.textContent = "Личный кабинет клиента";
    dom.heroSubtitle.textContent = "Авторизация по логину и паролю, создание заявки, статус кейса и переписка с поддержкой внутри Mini App.";
    dom.userApp.classList.remove("hidden");
    dom.adminApp.classList.add("hidden");
  }
}

function renderUserProfile(bootstrap) {
  const user = bootstrap.user || {};
  dom.telegramUserBadge.textContent = user.username ? `@${user.username}` : "Telegram";
  dom.profileId.textContent = user.id || "—";
  dom.profileUsername.textContent = user.username ? `@${user.username}` : "—";
  dom.profileName.textContent = user.fullName || "—";
  dom.channelLink.href = bootstrap.links?.channel || "#";
  dom.reviewsLink.href = bootstrap.links?.reviews || "#";
  dom.agreementLink.href = bootstrap.links?.agreement || "#";
}

function renderServices() {
  dom.serviceGrid.innerHTML = "";
  SERVICES.forEach((service) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `service-card ${state.selectedService === service ? "active" : ""}`;
    btn.innerHTML = `<strong>${escapeHtml(service)}</strong><span>Нажми, чтобы выбрать</span>`;
    btn.addEventListener("click", () => {
      state.selectedService = service;
      renderServices();
    });
    dom.serviceGrid.appendChild(btn);
  });
}

function updateSummary() {
  const amount = parseAmount(dom.ticketAmount.value);
  const commission = amount * 0.25;
  const after = Math.max(0, amount - commission);
  dom.summaryCommission.textContent = formatRub(commission);
  dom.summaryToPay.textContent = formatRub(commission);
  dom.summaryAfter.textContent = formatRub(after);
  dom.ticketFormChip.textContent = amount >= 100 ? "можно отправлять" : "укажи сумму";
}

function renderAuthState(bootstrap) {
  const account = bootstrap.account || {};
  const locked = !account.hasPassword || !account.sessionValid;
  dom.registerBox.classList.add("hidden");
  dom.loginBox.classList.add("hidden");
  dom.cabinetBox.classList.add("hidden");
  dom.ticketFormCard.classList.add("hidden");
  dom.activeTicketCard.classList.add("hidden");
  dom.chatCard.classList.add("hidden");

  if (!account.hasPassword) {
    dom.authTitle.textContent = "Первичная настройка кабинета";
    dom.authStatusChip.textContent = "создай пароль";
    dom.registerBox.classList.remove("hidden");
    return;
  }

  if (!account.sessionValid) {
    dom.authTitle.textContent = "Вход в кабинет";
    dom.authStatusChip.textContent = "нужен вход";
    dom.loginBox.classList.remove("hidden");
    dom.loginValue.value = account.login || "";
    dom.resetLogin.value = account.login || "";
    return;
  }

  dom.authTitle.textContent = "Кабинет открыт";
  dom.authStatusChip.textContent = "авторизован";
  dom.cabinetBox.classList.remove("hidden");
  dom.cabinetLogin.textContent = account.login || "—";
  renderTicketState(bootstrap.ticket, bootstrap.messages || []);
}

function renderTicketState(ticket, messages) {
  state.ticket = ticket || null;
  state.userMessages = messages || [];
  if (!ticket) {
    dom.ticketFormCard.classList.remove("hidden");
    dom.activeTicketCard.classList.add("hidden");
    dom.chatCard.classList.add("hidden");
    return;
  }
  dom.ticketFormCard.classList.add("hidden");
  dom.activeTicketCard.classList.remove("hidden");
  dom.chatCard.classList.remove("hidden");
  dom.ticketTitle.textContent = `Заявка #${ticket.id}`;
  dom.ticketStatus.textContent = ticket.status_label || ticket.status || "—";
  dom.ticketService.textContent = ticket.service || "—";
  dom.ticketAmountValue.textContent = formatRub(ticket.amount || 0);
  dom.ticketCreated.textContent = ticket.created_at_label || "—";
  dom.ticketUpdated.textContent = ticket.updated_at_label || "—";
  dom.ticketDescriptionValue.textContent = ticket.description || "Без комментария";
  renderMessages(dom.userMessages, state.userMessages, "user");
}

function renderMessages(container, messages, side) {
  container.innerHTML = "";
  if (!messages?.length) {
    container.innerHTML = `<div class="empty-chat">Пока сообщений нет.</div>`;
    return;
  }
  messages.forEach((msg) => {
    const div = document.createElement("div");
    const role = msg.sender_role || "system";
    const mine = side === "user" ? role === "user" : role === "admin";
    div.className = `message ${mine ? "mine" : ""} ${role}`;
    const author = role === "user" ? "Клиент" : role === "admin" ? (msg.sender_name || "Поддержка") : "Система";
    const created = msg.created_at ? new Date(msg.created_at * 1000).toLocaleString("ru-RU") : "";
    div.innerHTML = `
      <div class="message-head">
        <span>${escapeHtml(author)}</span>
        <span>${escapeHtml(created)}</span>
      </div>
      <div class="message-body">${escapeHtml(msg.text || "")}</div>
    `;
    container.appendChild(div);
  });
  container.scrollTop = container.scrollHeight;
}

async function bootstrapUser() {
  if (!requireTelegram()) return;
  const data = await apiGet("/api/user/bootstrap", { initData: state.initData, sessionToken: state.sessionToken });
  state.bootstrap = data;
  renderUserProfile(data);
  renderAuthState(data);
}

async function registerCabinet() {
  const login = dom.registerLogin.value.trim().toLowerCase();
  const password = dom.registerPassword.value;
  if (!login || !password) return setAlert("Заполни логин и пароль.", "error");
  const data = await apiPost("/api/user/account/register", userPayload({ login, password }));
  saveToken(data.token);
  setAlert("Кабинет создан. Вход выполнен.", "success");
  await bootstrapUser();
}

async function loginCabinet() {
  const login = dom.loginValue.value.trim().toLowerCase();
  const password = dom.loginPassword.value;
  if (!login || !password) return setAlert("Введи логин и пароль.", "error");
  const data = await apiPost("/api/user/account/login", { initData: state.initData, login, password });
  saveToken(data.token);
  setAlert("Успешный вход.", "success");
  await bootstrapUser();
}

async function logoutCabinet() {
  try {
    await apiPost("/api/user/account/logout", { sessionToken: state.sessionToken });
  } catch (_) {}
  saveToken("");
  await bootstrapUser();
}

async function resetPassword() {
  const login = dom.resetLogin.value.trim().toLowerCase();
  const password = dom.resetPassword.value;
  if (!login || !password) return setAlert("Укажи новый логин и пароль.", "error");
  const data = await apiPost("/api/user/account/reset-password", { initData: state.initData, login, password });
  saveToken(data.token);
  setAlert("Пароль обновлён.", "success");
  dom.resetBox.classList.add("hidden");
  await bootstrapUser();
}

async function createTicket() {
  const amount = parseAmount(dom.ticketAmount.value);
  const description = dom.ticketDescription.value.trim();
  if (amount < 100 || amount > 100000) return setAlert("Сумма должна быть от 100 ₽ до 100000 ₽.", "error");
  const data = await apiPost("/api/user/tickets/create", userPayload({
    service: state.selectedService,
    amount,
    description,
  }));
  setAlert("Заявка создана.", "success");
  if (tg?.sendData) {
    tg.sendData(JSON.stringify({ action: "create_ticket", service: state.selectedService, amount, description }));
  }
  renderTicketState(data.ticket, data.messages || []);
}

async function sendUserReply() {
  if (!state.ticket) return;
  const text = dom.userReplyInput.value.trim();
  if (!text) return;
  const data = await apiPost(`/api/user/tickets/${state.ticket.id}/reply`, userPayload({ text }));
  dom.userReplyInput.value = "";
  renderTicketState(data.ticket, data.messages || []);
}

function renderAdminSummary(summary) {
  dom.adminSummary.innerHTML = "";
  const items = [
    ["Пользователи", summary.users || 0],
    ["Новые", summary.new || 0],
    ["В работе", summary.in_progress || 0],
    ["Ждут клиента", summary.waiting_user || 0],
    ["Завершены", summary.done || 0],
    ["Отклонены", summary.rejected || 0],
  ];
  items.forEach(([title, value]) => {
    const box = document.createElement("div");
    box.className = "summary-box dark";
    box.innerHTML = `<span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong>`;
    dom.adminSummary.appendChild(box);
  });
}

function renderAdminFilters() {
  dom.adminFilters.innerHTML = "";
  ADMIN_FILTERS.forEach(([key, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn ${state.adminFilter === key ? "primary" : "ghost"} compact`;
    btn.textContent = label;
    btn.addEventListener("click", async () => {
      state.adminFilter = key;
      renderAdminFilters();
      await loadAdminTickets();
    });
    dom.adminFilters.appendChild(btn);
  });
}

function renderAdminTicketList() {
  dom.ticketCounter.textContent = String(state.adminTickets.length);
  dom.ticketList.innerHTML = "";
  if (!state.adminTickets.length) {
    dom.ticketList.innerHTML = `<div class="empty">Тикеты не найдены.</div>`;
    return;
  }
  state.adminTickets.forEach((ticket) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `ticket-item ${state.adminSelectedId === ticket.id ? "active" : ""}`;
    item.innerHTML = `
      <div class="ticket-top">
        <strong>#${ticket.id} · ${escapeHtml(ticket.service)}</strong>
        <span>${escapeHtml(ticket.status_label || ticket.status)}</span>
      </div>
      <div class="ticket-meta">
        <span>User ${ticket.user_id}</span>
        <span>${formatRub(ticket.amount || 0)}</span>
      </div>
      <div class="ticket-desc">${escapeHtml(ticket.description || "Без комментария")}</div>
    `;
    item.addEventListener("click", () => openAdminTicket(ticket.id));
    dom.ticketList.appendChild(item);
  });
}

async function bootstrapAdmin() {
  if (!requireTelegram()) return;
  const data = await apiGet("/api/admin/bootstrap", { initData: state.initData });
  dom.adminStatusChip.textContent = "онлайн";
  renderAdminSummary(data.summary || {});
  state.adminTickets = data.tickets || [];
  renderAdminFilters();
  renderAdminTicketList();
}

async function loadAdminTickets() {
  const data = await apiGet("/api/admin/tickets", {
    initData: state.initData,
    status: state.adminFilter,
    search: state.adminSearch,
  });
  state.adminTickets = data.tickets || [];
  renderAdminTicketList();
}

async function openAdminTicket(ticketId) {
  const data = await apiGet(`/api/admin/tickets/${ticketId}`, { initData: state.initData });
  state.adminSelectedId = ticketId;
  renderAdminTicketList();
  const ticket = data.ticket;
  dom.adminTicketTitle.textContent = `Заявка #${ticket.id}`;
  dom.adminTicketStatus.textContent = ticket.status_label || ticket.status;
  dom.adminTicketMeta.innerHTML = `
    <div class="profile-grid">
      <div class="kv"><span>User ID</span><strong>${escapeHtml(ticket.user_id)}</strong></div>
      <div class="kv"><span>Сервис</span><strong>${escapeHtml(ticket.service)}</strong></div>
      <div class="kv"><span>Сумма</span><strong>${escapeHtml(formatRub(ticket.amount || 0))}</strong></div>
      <div class="kv"><span>Админ</span><strong>${escapeHtml(ticket.assigned_admin_name || "Не назначен")}</strong></div>
      <div class="kv"><span>Создана</span><strong>${escapeHtml(ticket.created_at_label || "—")}</strong></div>
      <div class="kv"><span>Обновлена</span><strong>${escapeHtml(ticket.updated_at_label || "—")}</strong></div>
    </div>
    <div class="ticket-desc">${escapeHtml(ticket.description || "Без комментария")}</div>
  `;
  renderAdminActions(ticket);
  renderMessages(dom.adminMessages, data.messages || [], "admin");
}

function renderAdminActions(ticket) {
  dom.adminTicketActions.innerHTML = "";
  const configs = [
    ["Назначить на себя", () => adminAction(ticket.id, "assign")],
    ["В работу", () => adminAction(ticket.id, "status", { status: "in_progress" })],
    ["Ждёт клиента", () => adminAction(ticket.id, "status", { status: "waiting_user" })],
    ["Завершить", () => adminAction(ticket.id, "status", { status: "done" })],
    ["Отклонить", () => adminAction(ticket.id, "status", { status: "rejected" })],
  ];
  configs.forEach(([title, handler], index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn ${index === 0 ? "secondary" : "ghost"} compact`;
    btn.textContent = title;
    btn.addEventListener("click", handler);
    dom.adminTicketActions.appendChild(btn);
  });
}

async function adminAction(ticketId, action, extra = {}) {
  await apiPost(`/api/admin/tickets/${ticketId}/${action}`, { initData: state.initData, ...extra });
  await bootstrapAdmin();
  await openAdminTicket(ticketId);
}

async function sendAdminReply() {
  if (!state.adminSelectedId) return;
  const text = dom.adminReplyInput.value.trim();
  if (!text) return;
  await apiPost(`/api/admin/tickets/${state.adminSelectedId}/reply`, { initData: state.initData, text });
  dom.adminReplyInput.value = "";
  await bootstrapAdmin();
  await openAdminTicket(state.adminSelectedId);
}

function bindEvents() {
  dom.registerButton?.addEventListener("click", () => runAction(registerCabinet));
  dom.loginButton?.addEventListener("click", () => runAction(loginCabinet));
  dom.logoutButton?.addEventListener("click", () => runAction(logoutCabinet));
  dom.resetPasswordToggle?.addEventListener("click", () => dom.resetBox.classList.toggle("hidden"));
  dom.resetButton?.addEventListener("click", () => runAction(resetPassword));
  dom.ticketAmount?.addEventListener("input", updateSummary);
  dom.createTicketButton?.addEventListener("click", () => runAction(createTicket));
  dom.userReplyButton?.addEventListener("click", () => runAction(sendUserReply));
  dom.userReplyInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); runAction(sendUserReply); }
  });
  dom.adminSearchButton?.addEventListener("click", () => runAction(async () => {
    state.adminSearch = dom.adminSearch.value.trim();
    await loadAdminTickets();
  }));
  dom.adminReplyButton?.addEventListener("click", () => runAction(sendAdminReply));
  dom.adminReplyInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); runAction(sendAdminReply); }
  });
}

async function runAction(fn) {
  try {
    setAlert("");
    await fn();
  } catch (err) {
    console.error(err);
    setAlert(err.message || "Ошибка", "error");
  }
}

async function init() {
  tg?.ready?.();
  tg?.expand?.();
  updateHero();
  bindEvents();
  renderServices();
  updateSummary();

  try {
    if (state.mode === "admin") await bootstrapAdmin();
    else await bootstrapUser();
  } catch (err) {
    console.error(err);
    setAlert(err.message || "Не удалось загрузить данные.", "error");
    if (state.mode === "admin") dom.adminStatusChip.textContent = "ошибка";
  }
}

init();
