// Приложение XGW: пульт шлюза. В сеть страница не ходит — запросы, подпись и Keystore делает
// MainActivity.kt (объект XGW). Всё, что приходит от шлюза (имена серверов из подписок, имена
// устройств, тексты действий), вставляется только как текст — через textContent.
(() => {
  "use strict";

  const POLL_MS = 6000; // API шлюза принимает до 30 запросов в минуту с телефона
  const VPN_MS = 1500; // состояние VPN телефона — из самого приложения, без сети
  const FRESH_MS = 3600 * 1000; // список серверов старше часа — обновить при открытии
  const $ = (id) => document.getElementById(id);

  const STATES = {
    HEALTHY: ["ok", "Серверы в порядке"],
    DEGRADED: ["warn", "Часть серверов недоступна"],
    ALL_DEAD: ["bad", "Все серверы недоступны"],
    WAN_DOWN: ["bad", "Нет связи с провайдером"],
    XRAY_DOWN: ["bad", "Xray не отвечает"],
    LEAK: ["bad", "Трафик идёт мимо VPN"],
    PROBE_TARGET_UNREACHABLE: ["warn", "Адрес проверки недоступен"],
    RESERVE: ["warn", "Работает резервный сервер"],
  };

  let info = {};
  let link = "";
  let state = null;
  let acting = false;
  let timer = 0;
  let toastTimer = 0;
  let dialogYes = null;
  let vpnTimer = 0;
  let vpnBusy = false;

  // --- мост к MainActivity ---------------------------------------------------

  let seq = 0;
  const waiting = new Map();
  window.xgwDone = (id, text) => {
    const resolve = waiting.get(id);
    waiting.delete(id);
    if (resolve) resolve(JSON.parse(text));
  };
  const bridge = (method, ...args) => new Promise((resolve) => {
    seq += 1;
    waiting.set(seq, resolve);
    window.XGW[method](...args, seq);
  });
  const call = (method, path, body) => bridge("call", method, path, body ? JSON.stringify(body) : "");

  // Что сказать человеку, если шлюз не ответил «200».
  function problem(reply, pairing) {
    if (reply.status === 200) return "";
    if (reply.status === 0) {
      return `Нет связи со шлюзом${reply.error ? ` (${reply.error})` : ""}. Если на телефоне включён `
        + "другой VPN, выключите его: через VPN шлюз недоступен.";
    }
    if (reply.status === 403 && pairing) {
      return "Код не подошёл: он действует 10 минут и один раз. Нажмите «Привязать телефон» в "
        + "панели ещё раз и отсканируйте новый QR-код.";
    }
    if (reply.status === 403) {
      return "Шлюз не принял запрос: телефон отвязан в панели или ключ устарел. Привяжите "
        + "телефон заново: в панели — «Привязать телефон», здесь — кнопка ниже.";
    }
    if (reply.status === 421) {
      return "На шлюзе выключено «Приложение на телефоне» (Funnel): включите его в панели, "
        + "карточка «Tailscale».";
    }
    if (reply.status === 429) return "Слишком много запросов — подождите минуту.";
    return (reply.body && reply.body.error) || `Шлюз ответил HTTP ${reply.status}`;
  }

  // --- мелочи -------------------------------------------------------------------

  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "text") node.textContent = value;
      else if (key === "class") node.className = value;
      else if (key === "on") node.addEventListener("click", value);
      else node.setAttribute(key, value);
    }
    for (const child of children) if (child) node.append(child);
    return node;
  };
  const show = (id) => {
    for (const screen of ["welcome", "confirm", "gateway"]) $(screen).hidden = screen !== id;
  };
  const say = (id, text) => {
    $(id).textContent = text || "";
    $(id).hidden = !text;
  };
  const capital = (text) => (text ? text[0].toUpperCase() + text.slice(1) : "");
  const mbps = (value) => `${value >= 10 ? Math.round(value) : value.toFixed(1)} Мбит/с`;
  const clock = (seconds) => new Date(seconds * 1000).toLocaleTimeString("ru-RU");

  function toast(text, bad) {
    const node = $("toast");
    node.textContent = text;
    node.dataset.tone = bad ? "bad" : "";
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.hidden = true; }, bad ? 7000 : 4000);
  }

  function ask(title, text, yes, onYes, danger) {
    $("dialog-title").textContent = title;
    $("dialog-text").textContent = text;
    $("dialog-yes").textContent = yes;
    $("dialog-yes").className = `btn ${danger ? "danger" : "primary"}`;
    dialogYes = onYes;
    $("dialog").hidden = false;
  }
  const closeDialog = () => { $("dialog").hidden = true; dialogYes = null; };

  // «Назад» Android: сначала закрыть вопрос и подтверждение привязки.
  window.xgwBack = () => {
    if (!$("dialog").hidden) { closeDialog(); return true; }
    if (!$("confirm").hidden) { start(); return true; }
    return false;
  };

  // --- привязка -----------------------------------------------------------------

  // Приложение открыли ссылкой xgw://pair (камера телефона, adb) — к подтверждению.
  window.xgwLink = () => {
    const text = window.XGW.takeLink();
    if (text) offer(text);
  };

  function offer(text) {
    const check = JSON.parse(window.XGW.checkLink(text));
    if (!check.ok) {
      start();
      say(info.paired ? "link-error" : "welcome-error", check.error);
      return;
    }
    link = text;
    stop();
    $("confirm-host").textContent = check.host;
    $("confirm-device").textContent = info.device;
    say("confirm-replace", info.paired && info.host
      ? `Сейчас телефон привязан к шлюзу ${info.host}: эта привязка заменит прежнюю.` : "");
    say("confirm-error", "");
    $("confirm-yes").disabled = false;
    show("confirm");
  }

  async function scan() {
    say("welcome-error", "");
    const result = await bridge("scan");
    if (result.ok) offer(result.text);
    else if (result.loading) {
      say("welcome-error", "Сканер QR-кода загружается из Google Play — это бывает один раз. "
        + "Подождите полминуты и нажмите кнопку ещё раз.");
    } else if (!result.cancel) {
      say("welcome-error", `Сканер QR-кода не открылся: ${result.error}. Можно навести на QR-код `
        + "обычную камеру телефона и открыть ссылку — она откроет XGW.");
    }
  }

  async function pair() {
    $("confirm-yes").disabled = true;
    say("confirm-error", "");
    const reply = await bridge("pair", link);
    if (reply.status !== 200) {
      $("confirm-yes").disabled = false;
      say("confirm-error", problem(reply, true));
      return;
    }
    link = "";
    info = JSON.parse(window.XGW.info());
    toast(`Телефон привязан: в панели он «${info.name || info.device}»`);
    start();
  }

  // --- пульт ----------------------------------------------------------------------

  function stop() {
    clearTimeout(timer);
    timer = 0;
  }

  function schedule() {
    stop();
    if (!document.hidden && !$("gateway").hidden) timer = setTimeout(load, POLL_MS);
  }

  async function load() {
    const reply = await call("GET", "/api/state");
    if ($("gateway").hidden) return;
    $("gateway").classList.toggle("stale", reply.status !== 200);
    $("relink").hidden = reply.status !== 403;
    if (reply.status === 200) {
      state = reply.body;
      say("link-error", "");
      render(state);
    } else {
      say("link-error", problem(reply, false));
      if (state) render(state, true);
      // Отказ в подписи шлюз считает неудачным входом (10 в минуту закрывают вход всем):
      // с отвязанным ключом не опрашиваем — снова спросим, когда приложение откроют.
      if (reply.status === 403) return;
      if (reply.status === 429) {
        stop();
        timer = setTimeout(load, 60000);
        return;
      }
    }
    schedule();
  }

  async function act(name, body, done) {
    if (acting) return;
    acting = true;
    if (state) render(state);
    const reply = await call("POST", "/api/act", { name, ...body });
    acting = false;
    if (reply.status === 200) {
      const result = reply.body;
      toast(capital(result.text) || (result.ok ? "Готово" : "Не получилось"), !result.ok);
      if (done) done(result);
    } else {
      toast(problem(reply, false), true);
    }
    load();
  }

  function render(s, stale) {
    const capture = s.capture || {};
    // Серверы в порядке ещё не значит, что у устройств дома есть интернет (issue #1).
    const lanDead = capture.mode === "on" && capture.lan_problem;
    const [tone, label] = stale ? ["off", "Нет связи"]
      : lanDead ? ["bad", "Нет интернета в сети"]
        : (STATES[s.state] || ["off", s.state || "Нет данных"]);
    $("chip").dataset.tone = tone;
    $("chip").textContent = label;
    renderPower(s, tone);
    renderMembers(s);
    renderDevices(s);
    $("about-gw").textContent = s.version || "";
    $("updated").textContent = s.now ? `Состояние на ${clock(s.now)}` : "";
  }

  function renderPower(s, tone) {
    const mode = (s.capture || {}).mode;
    const on = mode === "on" || mode === "open";
    let title = "VPN шлюза выключен";
    let sub = "Интернет дома идёт напрямую, мимо VPN";
    let heroTone = "off";
    if (mode === "on") {
      title = "VPN шлюза включён";
      sub = tone === "bad" ? `Сейчас не работает: ${s.action || "нет связи"}` : "Устройства дома идут в интернет через VPN";
      if ((s.capture || {}).lan_problem) sub = `Устройства дома без интернета: ${s.capture.lan_problem}`;
      heroTone = tone === "bad" ? "bad" : "ok";
    } else if (mode === "open") {
      title = "VPN шлюза временно снят";
      sub = "Xray недоступен — трафик идёт напрямую, пока он не вернётся";
      heroTone = "warn";
    } else if (mode === "none") {
      title = "Перехват не настроен";
      sub = "В config.toml шлюза перехват выключен";
    }
    $("hero").dataset.tone = heroTone;
    $("power-title").textContent = title;
    $("power-sub").textContent = sub;
    const power = s.power || {};
    const button = $("power");
    button.textContent = on ? "Выключить VPN шлюза" : "Включить VPN шлюза";
    button.className = `btn wide ${on ? "danger-line" : "primary"}`;
    button.disabled = acting || !(on ? power.can_off : power.can_on);
    button.dataset.on = String(on);
    say("power-why", !on && !power.can_on ? capital(power.why) : "");

    const members = s.members || [];
    const pinned = s.pin && !s.pin.down ? members.find((member) => member.tag === s.pin.tag) : null;
    const current = pinned || (mode === "on"
      && (members.find((member) => member.selected) || members.find((member) => member.main)));
    if (current) {
      const how = pinned ? "Выбран вручную" : s.main && s.main.tag === current.tag ? "Основной сервер" : "Сейчас через";
      say("current", `${how}: ${current.name || current.tag}${metaText(current)}`);
    } else say("current", "");
  }

  const metaText = (member) => {
    const parts = [];
    if (member.speed_mbps !== null && member.speed_mbps !== undefined) parts.push(mbps(member.speed_mbps));
    if (member.delay_ms !== null && member.delay_ms !== undefined) parts.push(`${member.delay_ms} мс`);
    return parts.length ? ` · ${parts.join(" · ")}` : "";
  };

  function renderMembers(s) {
    const pin = s.pin;
    if (pin) {
      const chosen = (s.members || []).find((member) => member.tag === pin.tag);
      const name = (chosen && chosen.name) || pin.name || pin.tag;
      say("pin-note", pin.down
        ? `Выбранный вручную «${name}» не отвечает — трафик ведёт автовыбор.`
        : `Выбран вручную «${name}»: весь трафик идёт через него.`);
    } else say("pin-note", "");
    $("unpin").hidden = !pin;
    $("unpin").disabled = acting;

    const list = $("members");
    list.replaceChildren();
    for (const member of s.members || []) {
      const tags = [];
      if (pin && pin.tag === member.tag) tags.push(["on", "выбран"]);
      else if (member.main) tags.push(["on", "основной"]);
      if (member.selected && !(pin && pin.tag === member.tag)) tags.push(["", "сейчас"]);
      if (!member.alive) tags.push(["bad", "не отвечает"]);
      const meta = metaText(member).replace(/^ · /, "");
      list.append(el("li", {}, [el("button", {
        class: `row${member.alive ? "" : " dead"}`, type: "button",
        on: () => choose(member),
      }, [
        el("span", {}, [
          el("span", { class: "name", text: member.name || member.tag }),
          meta ? el("span", { class: "meta", text: meta }) : null,
        ]),
        el("span", { class: "side" }, tags.map(([cls, text]) => el("span", { class: `tag ${cls}`, text }))),
      ])]));
    }
    if (!(s.members || []).length) list.append(el("li", { class: "muted small", text: "Серверов в работе нет" }));
    $("spares").textContent = `Запасных серверов: ${s.spares || 0}`;

    const busy = s.busy || {};
    const button = (id, key, idle, running) => {
      $(id).textContent = busy[key] ? running : idle;
      $(id).disabled = acting || Boolean(busy[key]);
    };
    button("refresh", "refresh", "Обновить подписки", "Обновляю подписки…");
    button("scan-spares", "scan", "Проверить запасные", "Проверяю запасные…");
    const progress = s.speed_progress || {};
    button("speed", "speed", "Замерить скорость",
      progress.total ? `Замер скорости ${progress.done || 0} из ${progress.total}` : "Замеряю скорость…");
    $("speed").hidden = !(s.sticky && s.sticky.on);
  }

  function choose(member) {
    if (acting) return;
    if (s_pinned(member)) {
      ask("Вернуть автовыбор?", "Шлюз снова сам будет выбирать сервер.", "Автовыбор", () => act("unpin", {}));
      return;
    }
    ask(`Выбрать «${member.name || member.tag}»?`,
      "Весь трафик шлюза пойдёт через этот сервер, пока вы не вернёте автовыбор.",
      "Выбрать", () => act("pin", { tag: member.tag }));
  }
  const s_pinned = (member) => Boolean(state && state.pin && state.pin.tag === member.tag);

  function renderDevices(s) {
    const devices = s.devices || [];
    $("devices-card").hidden = !devices.length;
    const list = $("devices");
    list.replaceChildren();
    for (const device of devices) {
      const locked = device.bypass && !device.managed;
      const title = device.name || device.ip || device.mac;
      const meta = [device.name ? device.ip : "", device.offline ? "не в сети" : ""].filter(Boolean).join(" · ");
      const side = el("span", { class: "side" }, [
        el("span", {
          class: device.bypass ? "tag warn" : "tag on",
          text: device.bypass ? (locked ? "мимо VPN · config.toml" : "мимо VPN") : "через VPN",
        }),
      ]);
      if (!locked) {
        side.append(el("button", {
          class: "btn switch", type: "button",
          text: device.bypass ? "Вернуть в VPN" : "Пустить мимо VPN",
          on: () => act("device", { mac: device.mac, bypass: !device.bypass }),
        }));
      }
      list.append(el("li", { class: "row" }, [
        el("span", {}, [
          el("span", { class: "name", text: title }),
          meta ? el("span", { class: "meta", text: meta }) : null,
        ]),
        side,
      ]));
    }
    for (const button of list.querySelectorAll("button")) button.disabled = acting;
  }

  // --- VPN телефона (А3) ------------------------------------------------------------

  const when = (ms) => {
    const date = new Date(ms);
    const today = new Date().toDateString() === date.toDateString();
    const time = date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    return today ? `сегодня ${time}` : `${date.toLocaleDateString("ru-RU")} ${time}`;
  };
  const vpnInfo = () => JSON.parse(window.XGW.vpnInfo());

  function renderVpn() {
    const v = vpnInfo();
    const list = v.config ? `Серверов: ${v.config.servers || 0} · список от ${when(v.config.time)}`
      : "Списка серверов ещё нет — приложение возьмёт его у шлюза";
    let [tone, title, sub] = ["off", "VPN телефона выключен", list];
    if (v.state === "on") [tone, title] = ["ok", "VPN телефона включён"];
    else if (v.state === "starting") [tone, title, sub] = ["warn", "VPN телефона включается…", v.detail || list];
    const running = v.state === "on" || v.state === "starting";
    $("vpn").dataset.tone = tone;
    $("vpn-title").textContent = title;
    $("vpn-sub").textContent = sub;
    say("vpn-error", v.state === "error" ? v.detail : "");
    const button = $("vpn-power");
    button.textContent = vpnBusy ? "Подождите…" : running ? "Выключить VPN телефона" : "Включить VPN телефона";
    button.className = `btn wide ${running ? "danger-line" : "primary"}`;
    button.dataset.on = String(running);
    button.disabled = vpnBusy;
    $("vpn-fetch").disabled = vpnBusy;
  }

  function watchVpn() {
    clearInterval(vpnTimer);
    vpnTimer = 0;
    renderVpn();
    if (!document.hidden && !$("gateway").hidden) vpnTimer = setInterval(renderVpn, VPN_MS);
  }

  async function vpnPower() {
    if ($("vpn-power").dataset.on === "true") {
      window.XGW.vpnStop();
      setTimeout(renderVpn, 300);
      return;
    }
    vpnBusy = true;
    renderVpn();
    const result = await bridge("vpnStart");
    vpnBusy = false;
    renderVpn();
    if (!result.ok) toast(result.status === 200 || !("status" in result) ? result.error : problem(result, false), true);
  }

  async function vpnFetch(quiet) {
    if (vpnBusy) return;
    vpnBusy = true;
    renderVpn();
    const result = await bridge("vpnFetch");
    vpnBusy = false;
    renderVpn();
    if (result.ok) {
      if (!quiet) toast(`Список серверов обновлён: ${result.servers}`);
    } else if (!quiet) {
      toast(result.status === 200 ? result.error : problem(result, false), true);
    }
  }

  // --- запуск ----------------------------------------------------------------------

  function start() {
    info = JSON.parse(window.XGW.info());
    if (!info.paired) {
      stop();
      show("welcome");
      return;
    }
    $("host").textContent = info.host;
    $("about-host").textContent = info.host;
    $("about-name").textContent = info.name || info.device;
    $("about-version").textContent = info.version;
    show("gateway");
    load();
    watchVpn();
    const v = vpnInfo();
    if (!v.config || Date.now() - v.config.time > FRESH_MS) vpnFetch(true);
  }

  $("scan").addEventListener("click", scan);
  $("confirm-yes").addEventListener("click", pair);
  $("confirm-no").addEventListener("click", () => { link = ""; start(); });
  $("dialog-no").addEventListener("click", closeDialog);
  $("dialog").addEventListener("click", (event) => { if (event.target === $("dialog")) closeDialog(); });
  $("dialog-yes").addEventListener("click", () => {
    const run = dialogYes;
    closeDialog();
    if (run) run();
  });
  $("power").addEventListener("click", () => {
    if ($("power").dataset.on === "true") {
      ask("Выключить VPN шлюза?", "Интернет дома пойдёт напрямую, мимо VPN.", "Выключить",
        () => act("power", { on: false }), true);
    } else act("power", { on: true });
  });
  $("unpin").addEventListener("click", () => act("unpin", {}));
  $("relink").addEventListener("click", () => { window.XGW.forget(); state = null; start(); scan(); });
  $("refresh").addEventListener("click", () => act("refresh", {}));
  $("scan-spares").addEventListener("click", () => act("scan", {}));
  $("speed").addEventListener("click", () => act("speed", {}));
  $("vpn-power").addEventListener("click", vpnPower);
  $("vpn-fetch").addEventListener("click", () => vpnFetch(false));
  $("vpn-always").addEventListener("click", () => ask(
    "VPN всегда",
    "В настройках Android выберите XGW и включите «Постоянная VPN»: телефон сам включит VPN "
      + "после перезагрузки. «Блокировать соединения без VPN» — интернет только через VPN.",
    "Открыть настройки", () => window.XGW.vpnSettings(),
  ));
  $("forget").addEventListener("click", () => ask(
    "Отвязать телефон?",
    "Приложение забудет ключ и больше не войдёт на шлюз. В панели шлюза телефон останется в "
      + "списке — отвяжите его и там (карточка «Телефоны»).",
    "Отвязать", () => { window.XGW.forget(); state = null; start(); }, true,
  ));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stop();
      clearInterval(vpnTimer);
    } else if (!$("gateway").hidden) {
      load();
      watchVpn();
    }
  });

  start();
  window.xgwLink();
})();
