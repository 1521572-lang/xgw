"use strict";

const modes = {
  off: "Выключен", standalone: "Без VPN", selective: "Выбранные домены с возвратом на VPN",
  compare: "Сравнение с VPN",
};
const phases = {
  reserved: "Очередь зарезервирована", owner_verified: "Владелец очереди подтверждён",
  owner_unverified: "Владелец очереди перестал подтверждаться", released: "Очередь освобождена",
};
const units = {"xgw-zapret2.service": "Выбранные домены", "xgw-nfqws2.service": "Общий обработчик"};
const vpnChecks = {pass: "Прошла", fail: "Не прошла", not_run: "Не запускалась"};
const number = new Intl.NumberFormat("ru");
const date = new Intl.DateTimeFormat("ru", {dateStyle: "short", timeStyle: "medium"});
const el = id => document.getElementById(id);
const put = (id, value) => { el(id).textContent = value ?? "—"; };
const count = value => Number.isSafeInteger(value) && value >= 0 ? number.format(value) : "Нет данных";
let epoch = null;
let timer;
let pending;
let failures = 0;
let needsLogin = false;

function render(payload) {
  const card = payload.zapret2;
  if (!card || typeof card.state !== "string") throw new Error("invalid overview");
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
  put("playback", evidence.playback === "not_tested" ? "Не проверялось" : "Нет данных");
  put("vpn", vpnChecks[evidence.vpn_control] || "Нет данных");
  put("queued-original", count(confirmed ? card.counters?.queued_original : null));
  put("queued-reply", count(confirmed ? card.counters?.queued_reply : null));
  put("queue-dropped", count(confirmed ? card.counters?.queue_dropped : null));

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
    description.textContent = [
      phases[event.phase], units[event.unit],
      "очередь " + count(event.queue), "поколение " + count(event.generation),
    ].join(" · ");
    item.append(stamp, description);
    return item;
  }));
}

function unavailable(message) {
  put("state", message);
  el("state").dataset.tone = "waiting";
  for (const id of ["running", "queue", "https", "playback", "vpn",
    "queued-original", "queued-reply", "queue-dropped"]) put(id, "Нет данных");
  put("detail", "");
  renderJournal(null);
}

async function refresh() {
  if (document.hidden || pending || needsLogin) return;
  const request = new AbortController();
  pending = request;
  const timeout = setTimeout(() => request.abort(), 5000);
  try {
    const response = await fetch("/api/zapret2/overview", {
      cache: "no-store", credentials: "same-origin", signal: request.signal,
    });
    if (response.status === 401) {
      needsLogin = true;
      unavailable("Войдите в XGW");
      return;
    }
    if (!response.ok) throw new Error("overview unavailable");
    render(await response.json());
    failures = 0;
  } catch {
    if (!document.hidden) {
      failures = Math.min(failures + 1, 4);
      unavailable("Связь с панелью прервана");
    }
  } finally {
    clearTimeout(timeout);
    pending = null;
    if (!document.hidden && !needsLogin) {
      timer = setTimeout(refresh, 4000 * 2 ** failures);
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
  if (document.hidden) pending?.abort();
  else refresh();
});
refresh();
