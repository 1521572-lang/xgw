"use strict";

const modes = {
  off: "Выключен", standalone: "Без VPN", selective: "Выбранные домены с возвратом на VPN",
  compare: "Сравнение с VPN",
};
const phases = {
  reserved: "Очередь зарезервирована", owner_verified: "Владелец очереди подтверждён",
  owner_unverified: "Владелец очереди перестал подтверждаться", released: "Очередь освобождена",
  queue_drops: "Потери в очереди", worker_fault: "Диагностика остановки воркера",
};
const workerFaults = {
  hostlist_reload_failed: "Ошибка загрузки списка доменов",
  ipset_reload_failed: "Ошибка загрузки списка IP-адресов",
  lua_panic: "Неустранимая ошибка Lua",
  lua_error_observed: "В журнале этого запуска есть ошибка Lua",
};
const units = {"xgw-zapret2.service": "Выбранные домены", "xgw-nfqws2.service": "Общий обработчик"};
const vpnChecks = {pass: "Прошла", fail: "Не прошла", not_run: "Не запускалась"};
const probePhases = {connect: "туннель", tls: "TLS", request: "запрос",
  headers: "заголовки", body: "тело ответа"};
const probeFailures = {http: "ответ HTTP", proxy: "отказ прокси", connect: "соединение",
  tls: "ошибка TLS", timeout: "таймаут", stall: "нет данных", truncated: "неполный ответ",
  reset: "обрыв", io: "ошибка ввода-вывода", cancelled: "прервана"};
const probePageKinds = {terms: "Страница условий", watch: "Страница просмотра", other: "Другая страница"};
const jobStates = {idle: "Проверка не запускалась", queued: "Ожидает запуска",
  running: "Проверка идёт", restoring: "Возвращаются настройки", complete: "Проверка завершена",
  cancelled: "Проверка отменена", interrupted: "Прервана перезапуском",
  conflict: "Настройки изменены извне", failed: "Ошибка проверки",
  restore_failed: "Возврат настроек не подтверждён", unavailable: "Состояние недоступно"};
const number = new Intl.NumberFormat("ru");
const date = new Intl.DateTimeFormat("ru", {dateStyle: "short", timeStyle: "medium"});
const mebibytes = new Intl.NumberFormat("ru", {maximumFractionDigits: 2});
const el = id => document.getElementById(id);
const retryOverview = el("retry-overview");
const flowsealSettings = el("flowseal-exclusion-settings");
const exclusionsField = el("setting-flowseal-exclusions");
const put = (id, value) => { el(id).textContent = value ?? "—"; };
const count = value => Number.isSafeInteger(value) && value >= 0 ? number.format(value) : "Нет данных";
let epoch = null;
let timer;
let pending;
let failures = 0;
let needsLogin = false;
let latest = null;
let online = false;
let busy = false;
let draftKey = null;
let draftFlowsealExclusions = null;
let openingSettings = false;
let generation = 0;
let refreshAfterReply = false;

function controls() {
  const usable = online && !busy && !needsLogin && !openingSettings && latest;
  const job = latest?.job;
  const running = ["queued", "running", "restoring"].includes(job?.state);
  for (const button of document.querySelectorAll("[data-mode]")) {
    const mode = button.dataset.mode;
    button.disabled = !usable || running || draftKey !== null ||
      (mode === "off" ? !latest.can_off : (latest.blockers?.[mode]?.length ?? 1) > 0);
  }
  el("edit-settings").disabled = !usable || running || !latest.can_edit || draftKey !== null;
  for (const id of ["persistent-probe", "import-flowseal", "job-start", "job-reset"]) {
    if (el(id)) el(id).disabled = !usable || running || latest.mode !== "off" || draftKey !== null;
  }
  if (el("job-cancel")) el("job-cancel").disabled = !usable || !running;
  if (el("job-reset")) el("job-reset").disabled ||= job?.restore !== "pass";
  if (el("job-pin")) el("job-pin").disabled = !usable || running || !jobWinner(job)
    || latest.mode !== "off";
  el("settings-fields").disabled = busy;
  if (exclusionsField) exclusionsField.readOnly = latest?.can_edit_flowseal_exclusions !== true;
  el("settings-form").querySelector('[type="submit"]').disabled = !usable || !latest.can_edit;
  el("reload-settings").disabled = busy || needsLogin || Boolean(pending);
  if (retryOverview) {
    retryOverview.hidden = online || needsLogin || failures === 0;
    retryOverview.disabled = document.hidden || busy || Boolean(pending);
  }
}

function jobWinner(job) {
  if (job?.restore !== "pass" || job.rounds !== 2) return null;
  return job.candidates?.find(candidate => {
    const rows = job.results.filter(row => row.candidate === candidate);
    return rows.length === 2 && rows.every(row => row.transport === "https_reachable");
  });
}

for (const [id, action, fields] of [
  ["persistent-probe", "probe", () => ({probe: "persistent"})],
  ["import-flowseal", "import", () => ({import: "flowseal_alt9"})],
  ["job-start", "job/start", () => ({
    candidates: ["multisplit", "multidisorder", "fake_md5_split", "fake_seq",
      "fake_seq_split", "fake_md5", "hostfakesplit_md5", "fake_static_md5",
      "fake_clone_md5"], rounds: 2, budget_seconds: 3600,
  })],
  ["job-reset", "job/reset", () => ({id: latest.job.id})],
  ["job-pin", "job/pin", () => ({id: latest.job.id, candidate: jobWinner(latest.job)})],
]) {
  el(id)?.addEventListener("click", () => {
    if (!confirm("Применить выбранное действие zapret2? Проверка стратегий меняет маршруты " +
      "на время задания. Для возврата используйте отмену.")) return;
    command(action, {...fields(), expected: latest.config_key});
  });
}
el("job-cancel")?.addEventListener("click", () =>
  command("job/cancel", {id: latest.job.id}));

function settingsError(message) {
  const target = el("settings-error");
  if (target) {
    target.textContent = message;
    target.hidden = !message;
  } else {
    put("command-result", message);
  }
}

function openSettings() {
  if (!online || busy || !latest?.can_edit) return;
  const numbers = [
    ["setting-check", latest.check_seconds],
    ["setting-retry", latest.retry_seconds],
    ["setting-budget", latest.daily_probe_mb],
  ];
  if (numbers.some(([, value]) => !Number.isSafeInteger(value))) {
    put("command-result", "Настройки недоступны: панель не вернула интервалы или бюджет.");
    return;
  }
  draftKey = latest.config_key;
  const strategies = [...latest.strategies];
  if (!strategies.includes(latest.selected_strategy)) strategies.push(latest.selected_strategy);
  el("setting-strategy").replaceChildren(...strategies.map(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = latest.strategies.includes(value) ? value : value + " (сохранённый профиль)";
    return option;
  }));
  el("setting-strategy").value = latest.selected_strategy;
  el("setting-domains").value = latest.domains.join("\n");
  draftFlowsealExclusions = Array.isArray(latest.flowseal_exclude_domains) &&
    (latest.selected_strategy === "flowseal_alt9" || latest.flowseal_exclude_domains.length)
    ? latest.flowseal_exclude_domains.join("\n") : null;
  if (flowsealSettings && exclusionsField) {
    flowsealSettings.hidden = draftFlowsealExclusions === null;
    exclusionsField.value = draftFlowsealExclusions ?? "";
  }
  for (const [id, value] of numbers) el(id).value = value;
  el("setting-youtube").checked = latest.youtube_transport_probe;
  el("setting-clear").checked = false;
  for (const id of ["setting-page", "setting-media"]) {
    el(id).value = "";
    el(id).disabled = false;
  }
  const pageKind = probePageKinds[latest.youtube_probe_page_kind];
  const expiry = latest.probe_expiry?.find(probe => probe.probe === 2)?.expires_at;
  put("saved-probes", "Сохранено адресов: " + count(latest.probe_count) +
    (pageKind ? " · " + pageKind : "") +
    (expiry ? " · срок CDN до " + new Date(expiry * 1000).toLocaleString("ru-RU") : ""));
  updateProbePreset();
  put("settings-revision", "");
  settingsError("");
  put("command-result", "");
  el("settings-form").hidden = false;
  controls();
  el("setting-strategy").focus();
}

function closeSettings() {
  draftKey = null;
  draftFlowsealExclusions = null;
  if (exclusionsField) exclusionsField.value = "";
  el("setting-page").value = "";
  el("setting-media").value = "";
  el("settings-form").hidden = true;
  controls();
  el("edit-settings").focus();
}

async function command(action, body) {
  if (busy || !online || needsLogin) return;
  busy = true;
  generation += 1;
  clearTimeout(timer);
  pending?.abort();
  controls();
  put("command-result", "Сохранение…");
  const request = new AbortController();
  const timeout = setTimeout(() => request.abort(), 15000);
  try {
    const response = await fetch("/api/zapret2/" + action, {
      method: "POST", credentials: "same-origin", signal: request.signal,
      headers: {"Content-Type": "application/json", "X-XGW-Panel": "1"},
      body: JSON.stringify(body),
    });
    if (response.status === 401) needsLogin = true;
    if (!response.ok) throw new Error("command response unavailable");
    const result = await response.json();
    put("command-result", result.text);
    if (result.code === "conflict") {
      put("settings-revision", "Конфликт ревизии. Правки сохранены в форме. Перечитайте настройки.");
    }
    if (result.ok && action === "settings") {
      closeSettings();
      el("command-result").focus();
    }
  } catch {
    put("command-result", needsLogin ? "Сессия завершилась. Войдите в панель снова." :
      "Результат команды неизвестен. Перечитываем состояние. Автоматического повтора нет.");
  } finally {
    clearTimeout(timeout);
    busy = false;
    online = false;
    controls();
    // A GET started before this mutation may still be unwinding after abort.
    if (!pending) refresh();
  }
}

for (const button of document.querySelectorAll("[data-mode]")) {
  button.addEventListener("click", () => {
    if (button.disabled || !latest) return;
    const mode = button.dataset.mode;
    const expected = latest.config_key;
    const warning = mode === "standalone"
      ? "Переключить весь шлюз на интернет без VPN? Выбранные домены пойдут через zapret2, остальные напрямую. VPN-соединения прервутся. При отказе выбранные домены блокируются без автоматического VPN."
      : mode === "selective"
        ? "Направлять выбранные домены через домашний IP после проверки? При отказе новые соединения вернутся на VPN. Это ещё не подтверждает воспроизведение видео."
        : "Выключить обработку выбранных доменов? Обычная маршрутизация будет восстановлена. Если общий движок настроен на auto, он возобновит работу. Смена режима может прервать соединения.";
    if (window.confirm(warning)) command("mode", {mode, expected});
  });
}
el("edit-settings").addEventListener("click", () => {
  if (!online || busy || openingSettings || draftKey !== null || !latest?.can_edit) return;
  openingSettings = true;
  put("command-result", "Загружаем настройки…");
  controls();
  refresh();
});
el("cancel-settings").addEventListener("click", closeSettings);
el("reload-settings").addEventListener("click", async () => {
  if (!window.confirm("Заменить введённые правки текущими настройками шлюза?")) return;
  if (await refresh()) openSettings();
});
function updateProbePreset() {
  const enabled = el("setting-youtube").checked;
  el("use-youtube-domains").hidden = !enabled || !latest?.youtube_domains?.length;
  el("use-probe-terms").hidden = !enabled || el("setting-clear").checked;
  if (el("cdn-replacement-hint")) {
    const canReplace = enabled && latest?.can_replace_cdn_probe && !el("setting-clear").checked;
    el("cdn-replacement-hint").hidden = !canReplace;
    put("cdn-replacement-hint", canReplace ? "Чтобы обновить пробу CDN, заполните только её адрес." : "");
  }
}
el("setting-youtube").addEventListener("change", updateProbePreset);
el("use-youtube-domains").addEventListener("click", () => {
  el("setting-domains").value = latest.youtube_domains.join("\n");
  el("setting-domains").focus();
});
el("use-probe-terms").addEventListener("click", () => {
  el("setting-page").value = "https://www.youtube.com/t/terms";
  el("setting-media").focus();
});
el("setting-clear").addEventListener("change", () => {
  for (const id of ["setting-page", "setting-media"]) {
    el(id).disabled = el("setting-clear").checked;
    if (el(id).disabled) el(id).value = "";
  }
  updateProbePreset();
});
el("settings-form").addEventListener("submit", event => {
  event.preventDefault();
  if (draftKey === null || busy || !online) return;
  settingsError("");
  if (!event.currentTarget.reportValidity()) {
    settingsError("Заполните обязательные поля. Проверьте интервалы и бюджет.");
    return;
  }
  const settings = {
    strategy: el("setting-strategy").value,
    domains: el("setting-domains").value.split(/\r?\n/).map(s => s.trim().toLowerCase()).filter(Boolean),
    check_seconds: Number(el("setting-check").value),
    retry_seconds: Number(el("setting-retry").value),
    daily_probe_mb: Number(el("setting-budget").value),
    youtube_transport_probe: el("setting-youtube").checked,
  };
  if (draftFlowsealExclusions !== null && exclusionsField && !exclusionsField.readOnly) {
    const exclusions = exclusionsField.value.split(/\r?\n/).map(s => s.trim().toLowerCase()).filter(Boolean);
    if (exclusions.join("\n") !== draftFlowsealExclusions) settings.flowseal_exclude_domains = exclusions;
  }
  const page = el("setting-page").value.trim();
  const cdn = el("setting-media").value.trim();
  if (el("setting-clear").checked) settings.probe_urls = [];
  else if (page && cdn) settings.probe_urls = [page, cdn];
  else if (page || cdn) {
    if (!page && settings.youtube_transport_probe && latest?.can_replace_cdn_probe) {
      settings.cdn_probe_url = cdn;
    } else {
      settingsError("Для замены заполните оба адреса.");
      return;
    }
  }
  command("settings", {settings, expected: draftKey});
});

function probeText(row, missing) {
  if (!row) return missing;
  const parts = [row.ok ? "Прошла" : "Не прошла"];
  if (probePageKinds[row.page_kind]) parts.push(probePageKinds[row.page_kind]);
  if (Number.isFinite(row.started_at) && row.started_at > 0) {
    parts.push(date.format(new Date(row.started_at * 1000)));
  }
  if (probePhases[row.phase]) parts.push(probePhases[row.phase]);
  if (!row.ok && probeFailures[row.kind]) parts.push(probeFailures[row.kind]);
  if (row.http) parts.push("HTTP " + row.http);
  if (row.connect_http) parts.push("CONNECT " + row.connect_http);
  if (Number.isSafeInteger(row.bytes)) parts.push(count(row.bytes) + " Б");
  if (Number.isSafeInteger(row.first_tls_timeout_ms)) {
    parts.push("Повтор после TLS-таймаута за " + count(row.first_tls_timeout_ms) + " мс");
    parts.push("Всего " + count(row.elapsed_ms) + " мс");
  } else if (Number.isSafeInteger(row.elapsed_ms)) parts.push(count(row.elapsed_ms) + " мс");
  return parts.join(" · ");
}

function render(payload) {
  const card = payload.zapret2;
  if (!card || typeof card.state !== "string") throw new Error("invalid overview");
  latest = card;
  if (el("job-status")) {
    const job = card.job ?? {state: "idle"};
    const restored = {pass: "подтверждён", pending: "ожидается", unconfirmed: "не подтверждён"};
    put("job-status", (jobStates[job.state] || "Нет данных") +
      (job.restore ? " · возврат " + (restored[job.restore] || "нет данных") : ""));
    el("job-results").replaceChildren(...(job.results ?? []).map(row => {
      const item = document.createElement("li");
      item.textContent = row.candidate + " · круг " + row.round + " · " + row.transport
        + " · " + row.reason;
      return item;
    }));
  }
  online = true;
  if (draftKey !== null && draftKey !== card.config_key) {
    put("settings-revision", "Настройки шлюза изменились. Эта форма хранит прежнюю ревизию.");
  }
  put("mode-blockers", Object.entries(card.blockers ?? {})
    .filter(([mode, reasons]) => mode !== "compare" && reasons.length)
    .map(([mode, reasons]) => modes[mode] + ": " + reasons.join(" ")).join("\n"));
  controls();
  const confirmed = card.fresh === true && card.policy_matched === true;
  const evidence = confirmed ? card.evidence ?? {} : {};
  put("state", confirmed ? card.title : "Нет свежего подтверждения");
  el("state").dataset.tone = confirmed ? card.state : "waiting";
  put("detail", card.detail ?? "");
  put("mode", card.source === "engine" && card.engine_mode === "auto"
    ? "Общий обработчик" : modes[card.mode] || "—");
  put("profile", card.configured_strategy);
  put("running", confirmed ? card.strategy : null);
  put("queue", confirmed ? card.worker?.queue : null);
  put("https", evidence.transport === "https_reachable" ? "Доступен" : "Нет подтверждения");
  const probes = evidence.transport_probes ?? {};
  put("probe-page", probeText(probes.page, "Нет данных"));
  put("probe-cdn", probeText(probes.cdn, probes.page?.ok === false ? "Не запускалась" : "Нет данных"));
  if (el("last-transport-ok")) {
    put("last-transport-ok", evidence.last_transport_ok_at
      ? date.format(evidence.last_transport_ok_at * 1000) : "Нет данных");
  }
  const budget = card.probe_budget;
  const mib = 1024 * 1024;
  if (el("probe-budget")) {
    put("probe-budget", budget
      ? mebibytes.format(budget.remaining_bytes / mib) + " из " +
        mebibytes.format(budget.limit_bytes / mib) + " МиБ · сброс в 00:00 UTC"
      : "Нет данных");
  }
  put("playback", evidence.playback === "not_tested" ? "Не проверялось" : "Нет данных");
  put("vpn", vpnChecks[evidence.vpn_control] || "Нет данных");
  renderCounters(confirmed ? card.counters : null);

  const domains = Array.isArray(card.domains) ? card.domains : [];
  el("domain-list").replaceChildren(...domains.map(domain => {
    const item = document.createElement("li");
    item.textContent = domain;
    return item;
  }));
  el("domains-empty").hidden = domains.length > 0;
  put("domains-empty", "Домены не заданы");
  renderJournal(payload.journal);
}

function renderCounters(counters) {
  for (const [id, field] of [
    ["queued-original", "queued_original"], ["queued-reply", "queued_reply"],
    ["queue-dropped", "queue_dropped"], ["queue-overflow", "queue_overflow"],
    ["queue-netlink-dropped", "queue_netlink_dropped"],
  ]) {
    if (el(id)) put(id, count(counters?.[field]));
  }
}

function renderJournal(journal) {
  if (!journal?.available) {
    put("events-note", "Свежий журнал недоступен");
    el("event-list").replaceChildren();
    return;
  }
  const switched = epoch !== null && epoch !== journal.epoch;
  epoch = journal.epoch;
  const notes = [];
  if (switched) notes.push("Журнал перезапущен");
  if (journal.omitted > 0) notes.push("Более ранних событий: " + count(journal.omitted));
  if (!journal.events.length) notes.push("Событий пока нет");
  put("events-note", notes.join(" · "));
  el("event-list").replaceChildren(...journal.events.map(event => {
    const item = document.createElement("li");
    const stamp = document.createElement("time");
    const time = new Date(event.at * 1000);
    stamp.dateTime = time.toISOString();
    stamp.textContent = date.format(time);
    const description = document.createElement("span");
    const fields = [
      phases[event.phase], units[event.unit],
      "очередь " + count(event.queue), "поколение " + count(event.generation),
    ];
    if (event.phase === "queue_drops") {
      fields.push("переполнение +" + count(event.overflow_delta),
        "доставка netlink +" + count(event.netlink_delta));
    } else if (event.phase === "worker_fault" && workerFaults[event.reason]) {
      fields.push(workerFaults[event.reason]);
    }
    description.textContent = fields.join(" · ");
    item.append(stamp, description);
    return item;
  }));
}

function unavailable(message) {
  online = false;
  controls();
  put("state", message);
  el("state").dataset.tone = "waiting";
  for (const id of ["running", "queue", "https", "probe-page", "probe-cdn", "playback", "vpn"]) {
    put(id, "Нет данных");
  }
  renderCounters(null);
  put("detail", "");
  renderJournal(null);
}

async function refresh() {
  if (document.hidden || pending || needsLogin || busy) return false;
  clearTimeout(timer);
  const started = generation;
  const request = new AbortController();
  pending = request;
  controls();
  const timeout = setTimeout(() => request.abort(), 5000);
  try {
    const response = await fetch("/api/zapret2/overview", {
      cache: "no-store", credentials: "same-origin", signal: request.signal,
    });
    if (started !== generation || document.hidden) return false;
    if (response.status === 401) {
      needsLogin = true;
      unavailable("Войдите в XGW");
      return;
    }
    if (!response.ok) throw new Error("overview unavailable");
    const payload = await response.json();
    if (started !== generation || document.hidden) return false;
    render(payload);
    failures = 0;
    return true;
  } catch {
    if (!document.hidden && started === generation) {
      failures = Math.min(failures + 1, 4);
      unavailable("Связь с панелью прервана");
    }
  } finally {
    clearTimeout(timeout);
    pending = null;
    const repeat = refreshAfterReply || started !== generation;
    refreshAfterReply = false;
    const open = openingSettings;
    openingSettings = false;
    controls();
    if (open && started === generation && !document.hidden) {
      if (online) openSettings();
      else put("command-result", needsLogin ? "Войдите в XGW."
        : "Не удалось загрузить настройки. Повторите после восстановления связи.");
    }
    if (!document.hidden && !needsLogin && !busy) {
      timer = setTimeout(refresh, repeat ? 0 : 4000 * 2 ** failures);
    }
  }
}

const theme = el("theme");
try {
  const saved = localStorage.getItem("xgw-zapret2-theme");
  if (saved === "light" || saved === "dark") theme.value = saved;
} catch {
  // A private browser session can disable storage.
}
function applyTheme() { document.documentElement.dataset.zmTheme = theme.value; }
theme.addEventListener("change", () => {
  applyTheme();
  try { localStorage.setItem("xgw-zapret2-theme", theme.value); } catch { /* session only */ }
});
applyTheme();

document.addEventListener("visibilitychange", () => {
  clearTimeout(timer);
  if (document.hidden) {
    generation += 1;
    online = false;
    pending?.abort();
    controls();
  } else {
    refresh();
  }
});
window.addEventListener("focus", refresh);
window.addEventListener("pageshow", refresh);
window.addEventListener("online", () => {
  if (document.hidden || needsLogin || busy) return;
  if (pending) refreshAfterReply = true;
  else refresh();
});
retryOverview?.addEventListener("click", () => {
  if (!retryOverview.hidden) refresh();
});
refresh();
