// Приложение XGW: пульт шлюза. В сеть страница не ходит — запросы, подпись и Keystore делает
// MainActivity.kt (объект XGW). Всё, что приходит от шлюза (имена серверов из подписок, имена
// устройств, тексты действий), вставляется только как текст — через textContent.
// Пульт умеет то же, что панель шлюза (src/xgw/ui/app.js), кроме доступа к самому шлюзу
// (ASSUMPTIONS п. 232): отрисовка серверов, подписок и устройств — та же, по вкладкам.
(() => {
  "use strict";

  const POLL_MS = 6000; // API шлюза принимает до 60 запросов в минуту с телефона
  const STALE_S = 90;
  const VPN_MS = 1500; // состояние VPN телефона — из самого приложения, без сети
  const FRESH_MS = 3600 * 1000; // список серверов старше часа — обновить при открытии
  const RETRY_MS = 60 * 1000; // список старого вида при включённом VPN — пробовать раз в минуту
  const MANUAL = "manual";
  const RECORD_SECONDS = 300; // запись трафика устройства — 5 минут, остановить можно раньше
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
  const VERDICTS = {
    OK: ["ok", "в порядке"],
    SLOW: ["warn", "медленный"],
    FROZEN: ["bad", "замораживается"],
    STALL_BEFORE_BODY: ["bad", "не отвечает"],
    CONNECT_FAIL: ["bad", "недоступен"],
    TIMEOUT: ["bad", "тайм-аут"],
  };
  const SKIPS = {
    filter: "не используется: отсеян фильтром имён из config.toml",
    junk: "не используется: служебная запись подписки",
    ipv6: "не используется: адрес IPv6",
    dns: "не используется: имя сервера не находится в DNS — шлюз проверит его снова через несколько часов или по кнопке «Обновить подписки»",
    core: "не используется: сервер умеет только sing-box (hysteria2, TUIC, AnyTLS…), а он на шлюзе выключен, не установлен или ещё не заведён",
  };
  const KINDS = {
    capture: "перехват", lifecycle: "перехват", lan: "сеть устройств", apply: "конфиг", config: "конфиг", generate: "сборка",
    rotation: "замена", rollback: "откат", pin: "выбор сервера", panel: "панель",
    subscription: "подписка", xray: "Xray", budget: "трафик проверок", leak: "утечка",
    probe: "адрес проверки", priority: "серверы в работе", reserve: "резервный сервер",
    main: "основной сервер", fragment: "дробление ClientHello", profile: "профиль обхода",
    singbox: "sing-box", core: "ядро сервера",
    HEALTHY: "в порядке", DEGRADED: "часть недоступна", ALL_DEAD: "все недоступны",
    WAN_DOWN: "нет провайдера", XRAY_DOWN: "Xray", LEAK: "утечка",
    PROBE_TARGET_UNREACHABLE: "адрес проверки", RESERVE: "резервный сервер",
  };
  const ICONS = {
    remove: ["M6 6l12 12", "M18 6L6 18"],
    edit: ["M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7", "M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"],
    record: ["M12 6a6 6 0 1 0 0 12a6 6 0 1 0 0-12z"],
    stop: ["M7 7h10v10H7z"],
    download: ["M12 3v12", "M7 10l5 5 5-5", "M5 21h14"],
  };
  const TABS = ["home", "servers", "subs", "devices", "events"];

  let info = {};
  let link = "";
  let state = null;
  let stale = false;
  let acting = false;
  let timer = 0;
  let toastTimer = 0;
  let dialogYes = null;
  let vpnTimer = 0;
  let vpnBusy = false;
  let fetching = null; // обновление списка серверов, которое идёт сейчас (Promise)
  let fetchProblem = ""; // почему список не обновился в последний раз
  let fetchTried = 0;
  let tab = "home";
  const drawn = {};
  const groups = new Map(); // источник → его раскрывающийся блок; живёт между перерисовками

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
      const error = reply.error ? ` (${reply.error})` : "";
      // VPN XGW включён: приложение пробовало напрямую и через свой Xray — совет выключить
      // «другой VPN» тут ложный (испытание А3.1).
      const v = vpnInfo();
      if (v.state === "on") {
        return `Нет связи со шлюзом${error}.` + (v.config && v.config.outdated
          ? " В списке серверов VPN телефона ещё нет запасного пути пульта: приложение обновит "
            + "список, как только шлюз ответит (например, по мобильной сети)." : "");
      }
      return `Нет связи со шлюзом${error}. Если на телефоне включён другой VPN, выключите его: `
        + "через VPN шлюз недоступен.";
    }
    if (reply.status === 403 && pairing) {
      return "Код не подошёл: он действует 10 минут и один раз. Нажмите «Привязать телефон» в "
        + "панели ещё раз и отсканируйте новый QR-код.";
    }
    if (reply.status === 403) {
      return (reply.body && reply.body.error === "это действие в приложении недоступно")
        ? "Шлюз не знает этого действия: обновите XGW на шлюзе до версии с этим приложением."
        : "Шлюз не принял запрос: телефон отвязан в панели или ключ устарел. Привяжите "
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

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const d of ICONS[name]) {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.append(path);
    }
    return svg;
  }

  function iconButton(name, label, onclick) {
    const button = el("button", { class: "icon-btn", type: "button", title: label, "aria-label": label, onclick });
    button.append(icon(name));
    return button;
  }

  // Один ли это сервер: роль в теге меняется (запасной стал участником: spare-nl-8763 →
  // proxy-nl-8763), а страна и начало отпечатка — нет (pin.py).
  function sameServer(a, b) {
    const rest = (tag) => String(tag || "").split("-").slice(1).join("-");
    return Boolean(a && b) && rest(a) !== "" && rest(a) === rest(b);
  }

  // Перерисовывает блок, только если его данные изменились: иначе раскрытые списки и
  // открытый выбор приоритета закрывались бы при каждом опросе.
  function draw(key, data, render) {
    const text = JSON.stringify(data);
    if (drawn[key] === text) return;
    drawn[key] = text;
    render();
  }

  function fill(list, items, empty) {
    list.replaceChildren(...(items.length ? items : empty ? [el("li", { class: "empty", text: empty })] : []));
  }

  function setBusy(node, busy) {
    if (busy) node.dataset.busy = "1";
    else delete node.dataset.busy;
  }

  const show = (id) => {
    for (const screen of ["welcome", "confirm", "gateway"]) $(screen).hidden = screen !== id;
    $("tabs").hidden = id !== "gateway";
  };
  const say = (id, text) => {
    $(id).textContent = text || "";
    $(id).hidden = !text;
  };
  const two = (n) => String(n).padStart(2, "0");
  const capital = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : "");
  const sourceName = (source) => (source === MANUAL ? "Отдельные ссылки" : source || "Без подписки");
  const decimal = (value, digits = 1) => Number(value).toFixed(digits).replace(".", ",");
  // Скорость: 85 Мбит/с; ниже 10 — с одним знаком после запятой.
  const mbps = (value) => (value >= 10 ? `${Math.round(value)} Мбит/с` : `${decimal(value)} Мбит/с`);
  const seconds = (ts) => new Date(ts * 1000).toLocaleTimeString("ru-RU");

  function clock(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return `${two(d.getHours())}:${two(d.getMinutes())}`;
  }

  function day(ts) {
    const d = new Date(ts * 1000);
    return `${two(d.getDate())}.${two(d.getMonth() + 1)}`;
  }

  function stamp(ts, now) {
    if (!ts) return "—";
    return new Date(ts * 1000).toDateString() === new Date(now * 1000).toDateString()
      ? clock(ts) : `${day(ts)} ${clock(ts)}`;
  }

  function ago(ts, now) {
    const minutes = Math.max(0, Math.floor((now - ts) / 60));
    if (minutes < 1) return "только что";
    if (minutes < 60) return `${minutes} мин назад`;
    if (minutes < 48 * 60) return `${Math.floor(minutes / 60)} ч назад`;
    return `${Math.floor(minutes / 1440)} дн назад`;
  }

  function gigabytes(bytes) {
    const value = bytes / 1e9;
    return value >= 100 ? value.toFixed(0) : value.toFixed(1).replace(".", ",");
  }

  function toast(text, bad, notes) {
    const node = $("toast");
    node.replaceChildren(capital(text), ...(notes || []).map((note) => el("span", { class: "toast-note", text: note })));
    node.dataset.tone = bad ? "bad" : "";
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.hidden = true; }, bad ? 8000 : 4500);
  }

  // Вопрос перед действием; body — поля окна (правка подписки).
  function ask(title, text, yes, onYes, danger, body) {
    $("dialog-title").textContent = title;
    $("dialog-text").textContent = text || "";
    $("dialog-text").hidden = !text;
    $("dialog-body").replaceChildren(...(body ? [body] : []));
    $("dialog-yes").textContent = yes;
    $("dialog-yes").className = `btn ${danger ? "danger" : "primary"}`;
    dialogYes = onYes;
    $("dialog").hidden = false;
  }
  const closeDialog = () => { $("dialog").hidden = true; dialogYes = null; };

  // «Назад» Android: сначала закрыть вопрос и подтверждение привязки, потом — на «Главную».
  window.xgwBack = () => {
    if (!$("dialog").hidden) { closeDialog(); return true; }
    if (!$("confirm").hidden) { start(); return true; }
    if (!$("gateway").hidden && tab !== "home") { go("home"); return true; }
    return false;
  };

  function go(name) {
    tab = TABS.includes(name) ? name : "home";
    for (const item of TABS) $(`tab-${item}`).hidden = item !== tab;
    for (const button of $("tabs").querySelectorAll(".tab-btn")) {
      if (button.dataset.tab === tab) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    window.scrollTo(0, 0);
  }

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

  // --- обмен со шлюзом --------------------------------------------------------------

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
    stale = reply.status !== 200;
    $("gateway").classList.toggle("stale", stale);
    $("relink").hidden = reply.status !== 403;
    if (reply.status === 200) {
      state = reply.body;
      say("link-error", "");
      render(state);
    } else {
      say("link-error", problem(reply, false));
      if (state) render(state);
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

  // Действие — то же, что кнопка панели: {name, body}. Поля ещё и рядом с name — для шлюза
  // до А3.2: кнопки «Главной» работают и с ним. true — шлюз сделал.
  async function act(name, body, busyNode) {
    if (acting) return false;
    acting = true;
    if (busyNode) busyNode.dataset.busy = "1";
    let ok = false;
    const reply = await call("POST", "/api/act", { ...(body || {}), name, body: body || {} });
    acting = false;
    if (busyNode) delete busyNode.dataset.busy;
    if (reply.status === 200) {
      const result = reply.body;
      ok = Boolean(result.ok);
      toast(result.text || (ok ? "Готово" : "Не получилось"), !ok, result.notes);
    } else {
      toast(problem(reply, false), true);
    }
    await load();
    return ok;
  }

  const setServers = (fingerprints, mode) => act("servers", { fingerprints, mode });
  // Приоритет сервера: в работе — серверы самого высокого уровня, на котором есть живые.
  const LEVELS = [["high", "Высокий"], ["medium", "Средний"], ["low", "Низкий"]];
  const LEVEL_NAMES = { high: "высокий", medium: "средний", low: "низкий" };

  // --- отрисовка ------------------------------------------------------------

  function health(s) {
    if (stale) return ["off", "Нет связи"];
    if (!s.updated || s.now - s.updated > STALE_S) return ["bad", "Демон XGW не отвечает"];
    if (!(s.members || []).length) return ["off", "Серверов нет"];
    // Серверы в порядке ещё не значит, что у устройств дома есть интернет (issue #1).
    if ((s.capture || {}).mode === "on" && s.capture.lan_problem) return ["bad", "Нет интернета в сети"];
    return STATES[s.state] || ["off", s.state || "Нет данных"];
  }

  function render(s) {
    const [tone, label] = health(s);
    $("chip").dataset.tone = tone;
    $("chip").textContent = label;
    renderPower(s, tone);
    draw("servers", [s.servers, s.sources, s.pin, (s.subscriptions || []).length, (s.links || []).length, s.state, s.reserve, Math.floor(s.now / 60)], () => renderServers(s));
    draw("main", [s.main, s.sticky, s.pin, (s.members || []).length, (s.budget || {}).speed_mb], () => renderMain(s));
    draw("removed", s.removed, () => renderRemoved(s));
    draw("notes", [s.nodes, s.budget, s.probe_target], () => renderNotes(s));
    draw("subs", [s.subscriptions, Math.floor(s.now / 60)], () => renderSubs(s));
    draw("links", s.links, () => renderLinks(s));
    // Идущая запись трафика: строки перерисовываются, только когда она началась или кончилась,
    // а время и размер меняются в метке — иначе кнопка «Остановить» уплывала бы из-под пальца.
    const records = s.records || { files: [] };
    const recording = records.active;
    draw("devices", [s.devices, s.lan, records.files, recording ? recording.name : ""], () => renderDevices(s));
    const recTag = $("devices").querySelector(".tag.rec");
    if (recTag && recording) recTag.textContent = recordText(recording, s.now);
    draw("tailscale", s.tailscale, () => renderTailscale(s));
    draw("events", s.events, () => renderEvents(s));

    const busy = s.busy || {};
    const button = (id, key, idle, running) => {
      $(id).textContent = busy[key] ? running : idle;
      setBusy($(id), Boolean(busy[key]));
    };
    button("refresh", "refresh", "Обновить подписки", "Обновляю подписки…");
    button("scan-spares", "scan", "Проверить запасные", "Проверяю запасные…");
    // Прогресс замеров: «Замер скорости 12 из 74» — пока идёт заход.
    const progress = s.speed_progress || {};
    button("speed", "speed", "Замерить скорость",
      progress.total ? `Замер скорости ${progress.done || 0} из ${progress.total}` : "Замеряю скорость…");
    $("scan-spares").hidden = !(s.spares || []).length;
    $("refresh").hidden = !(s.subscriptions || []).length;
    $("about-gw").textContent = s.version || "";
    $("updated").textContent = s.now ? `· Состояние на ${seconds(s.now)}` : "";
  }

  function scopeText(capture) {
    // Контейнеры Docker — только когда Docker на машине есть и их перехват включён.
    const docker = Boolean(capture.containers && capture.docker);
    if (capture.lan && capture.local) {
      const machine = docker ? "Шлюз, контейнеры Docker" : "Шлюз";
      return `${machine} и устройства дома выходят через VPN`;
    }
    if (capture.lan) return docker ? "Устройства дома и контейнеры Docker выходят через VPN" : "Устройства дома выходят через VPN";
    return docker ? "Шлюз и контейнеры Docker выходят через VPN" : "Шлюз выходит через VPN";
  }

  // Жизненный цикл перехвата (daemon.Lifecycle): тон строки и слово после «Перехват:».
  const LIFECYCLE = {
    connected: ["ok", "работает", "трафик идёт через VPN"],
    connecting: ["warn", "подключается", "трафик ждёт, мимо VPN ничего не уходит"],
    blocked: ["bad", "заблокирован", "мимо VPN ничего не уходит"],
    open: ["warn", "временно напрямую", "трафик идёт мимо VPN"],
    off: ["off", "снят", "трафик идёт напрямую"],
  };

  function renderLifecycle(s) {
    const line = $("lifecycle");
    const capture = s.capture || {};
    const known = LIFECYCLE[capture.lifecycle];
    // Строку пишет демон: не отвечает он — она устарела.
    line.hidden = !known || !s.updated || s.now - s.updated > STALE_S;
    if (!known) return;
    const [tone, word, tail] = known;
    const reason = capture.lifecycle_reason;
    let text = `Перехват: ${word} — ${reason || tail}`;
    if (reason && capture.lifecycle === "blocked") text += `; ${tail}`;
    line.dataset.tone = tone;
    line.textContent = text;
  }

  function renderPower(s, tone) {
    const capture = s.capture || {};
    const mode = capture.mode;
    const on = mode === "on" || mode === "open";
    let title = "VPN шлюза выключен";
    let sub = "Интернет дома идёт напрямую, мимо VPN";
    let heroTone = "off";
    if (mode === "on") {
      title = "VPN шлюза включён";
      sub = scopeText(capture);
      heroTone = tone === "bad" ? "bad" : "ok";
      if (capture.inbound_missing) {
        // Перехват включён, но Xray ещё не перезапущен с нужными настройками.
        title = "VPN шлюза включается";
        sub = capture.blocked
          ? "Xray перезапускается с новыми настройками — до этого интернет закрыт, мимо VPN ничего не уходит"
          : "Xray перезапускается с новыми настройками — до этого трафик идёт напрямую";
        heroTone = "warn";
      } else if (capture.lan_problem) {
        heroTone = "bad";
        sub = `Устройства дома без интернета: ${capture.lan_problem}`;
      } else if (tone === "bad") sub = `Сейчас не работает: ${s.action || "нет связи"}`;
      else if (capture.loaded === false) {
        heroTone = "bad";
        sub = "Правила сети не загружены — демон загрузит их заново";
      }
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
    renderLifecycle(s);
    const power = s.power || {};
    const button = $("power");
    button.textContent = on ? "Выключить VPN шлюза" : "Включить VPN шлюза";
    button.className = `btn wide ${on ? "danger-line" : "primary"}`;
    button.disabled = acting || !(on ? power.can_off : power.can_on);
    button.dataset.on = String(on);
    say("power-why", !on && !power.can_on ? capital(power.why) : "");

    // Выбранный вручную не отвечает (pin.down) — трафик ведёт автовыбор, его и показываем.
    const members = s.members || [];
    const chosen = s.pin && !s.pin.down
      ? [...members, ...(s.servers || [])].find((server) => sameServer(server.tag, s.pin.tag))
      : null;
    const current = chosen || (mode === "on" && !capture.inbound_missing
      && (members.find((member) => member.selected) || members.find((member) => member.main)));
    $("current").hidden = !current;
    if (current) {
      const main = !chosen && s.main && s.main.tag === current.tag;
      $("current-label").textContent = chosen
        ? (s.pin.until ? `Выбран вручную до ${stamp(s.pin.until, s.now)}` : "Выбран вручную")
        : main ? "Основной сервер" : "Сейчас через";
      const delay = current.delay_ms !== null && current.delay_ms !== undefined ? ` · ${current.delay_ms} мс` : "";
      const speed = hasSpeed(current) ? ` · ${mbps(current.speed_mbps)}` : "";
      $("current-name").textContent = (current.name || current.tag) + speed + delay;
    }
    $("unpin").hidden = !s.pin;
  }

  // Сводка разбора подписок, предупреждение о недоступном адресе проверки и расход
  // трафика на проверки серверов — в сутки и в месяц.
  function renderNotes(s) {
    const nodes = s.nodes || {};
    const summary = $("nodes-note");
    summary.hidden = !(nodes.members || nodes.spares);
    if (!summary.hidden) {
      let text = `Узлов: ${nodes.members || 0} активных, ${nodes.spares || 0} запасных `
        + `(отброшено ${nodes.dropped || 0} недоступных/служебных, схлопнуто ${nodes.duplicates || 0} дублей)`;
      if (nodes.excluded) text += ` · отключено вами: ${nodes.excluded}`;
      summary.textContent = text;
    }

    const probe = $("probe-note");
    probe.hidden = !s.probe_target;
    probe.textContent = s.probe_target
      ? `${s.probe_target}. Серверы не меняются, пока адрес не ответит; задайте в config.toml шлюза другой probe.url.`
      : "";

    const budget = s.budget || {};
    const note = $("budget-note");
    note.hidden = !(budget.all_mb && (budget.members || budget.spares));
    if (note.hidden) return;
    const perDay = budget.all_mb >= 1000 ? `${decimal(budget.all_mb / 1000, 2)} ГБ` : `${Math.round(budget.all_mb)} МБ`;
    const parts = [`проба ${decimal(budget.probe_bytes / 1000)} КБ × ${budget.members} в работе каждые ${budget.interval_s} с`];
    if (budget.spares) parts.push(`${budget.spares} запасных раз в ${budget.scan_minutes} мин`);
    if (budget.speed_mb) parts.push(`замер скорости — до ${Math.round(budget.speed_mb)} МБ в сутки`);
    if (budget.cheap) parts.push(`из них ${budget.cheap} лимитированных — коротким запросом`);
    const lines = [el("span", {}, "Проверки серверов расходуют около ", el("b", { text: `${perDay} в сутки` }),
      " и ", el("b", { text: `${decimal(budget.month_gb)} ГБ в месяц` }), ` (${parts.join(", ")}).`)];
    for (const [name, share] of Object.entries(budget.quota_share || {})) {
      // Доля квоты — с множителями серверов: проба через x10 тратит вдесятеро больше.
      const exact = share < 1 ? "меньше 1" : `около ${Math.round(share)}`;
      lines.push(el("span", { text: ` За месяц это ${exact} % трафика подписки «${name}» (с учётом множителей серверов).` }));
    }
    note.classList.toggle("over", Boolean(budget.over));
    if (budget.over) {
      lines.push(el("span", { text: ` Это больше лимита ${budget.limit_mb} МБ в сутки (без сквозной проверки — ${Math.round(budget.total_mb)} МБ): `
        + "уменьшите число серверов в работе (filters.max_members) или увеличьте интервал (probe.interval) в config.toml шлюза." }));
    }
    note.replaceChildren(...lines);
  }

  // --- серверы по подпискам -------------------------------------------------

  function serverValue(server) {
    if (server.status === "member") {
      if (server.alive === false) return el("span", { class: "delay bad", text: "нет ответа" });
      if (server.delay_ms === null || server.delay_ms === undefined) {
        return el("span", { class: "delay none", text: server.alive ? "жив" : "проверяется" });
      }
      const tone = server.delay_ms < 250 ? "ok" : server.delay_ms < 700 ? "warn" : "bad";
      return el("span", { class: `delay ${tone}`, text: `${server.delay_ms} мс` });
    }
    if (server.status === "spare") {
      const [tone, text] = VERDICTS[server.verdict] || ["none", server.verdict || "не проверялся"];
      return el("span", { class: `delay ${tone}`, text });
    }
    return el("span", { class: "delay none", text: "—" });
  }

  const hasSpeed = (server) => server.speed_mbps !== null && server.speed_mbps !== undefined;

  // Скорость по последнему замеру — рядом с задержкой; замер при занятом канале бледнее.
  function speedValue(server) {
    if (!hasSpeed(server) || (server.status !== "member" && server.status !== "spare")) return null;
    return el("span", { class: `speed${server.speed_busy ? " old" : ""}`, text: mbps(server.speed_mbps) });
  }

  // Когда цифры скорости нет — почему.
  const speedNote = (server, s) => {
    if (hasSpeed(server)) {
      return ` · замер скорости ${stamp(server.speed_ts, s.now)}`
        + (server.speed_busy ? " (канал был занят — цифра может быть занижена)" : "");
    }
    if (server.status === "member" && server.alive === false && !server.speed_error) return "";
    return server.speed_note ? ` · ${server.speed_note}` : "";
  };

  // Пока трафик ведёт сервер, выбранный вручную, основной — только запасной план.
  const mainShown = (server, s) => Boolean(server.main) && !(s.pin && !s.pin.down);

  function serverNote(server, s) {
    if (server.status === "member") {
      const dead = server.alive === false && server.dead_since
        ? ` · не отвечает ${ago(server.dead_since, s.now).replace(" назад", "")}` : "";
      return `${mainShown(server, s) ? "основной" : "в работе"}${speedNote(server, s)}${dead}`;
    }
    if (server.status === "spare") {
      const role = server.reserve
        ? "резервный: через него пойдёт трафик, если серверы в работе перестанут отвечать"
        : "запасной";
      return role + (server.scanned ? ` · проверен ${stamp(server.scanned, s.now)}` : "")
        + speedNote(server, s);
    }
    if (server.status === "disabled") {
      return server.pending ? "отключён — шлюз сейчас уберёт его из работы" : "отключён: шлюз к нему не обращается";
    }
    if (server.status === "skipped") return SKIPS[server.skip] || "не используется";
    return "включён — шлюз сейчас возьмёт его в работу";
  }

  // Пока шлюз не сопоставил сервер с подпиской, у него нет полного отпечатка —
  // отключить или убрать такой сервер нельзя (это длится до первого опроса подписок).
  const editable = (server) => String(server.fingerprint || "").length === 8;

  // Ядро, которое ведёт сервер, и профиль обхода (generator/profiles.py).
  const PROFILES = {
    "xray:default": "Xray",
    "xray:fragment": "Xray · дробление",
    "singbox:default": "sing-box",
    "singbox:tls_fragment": "sing-box · дробление",
    "singbox:mux_padded": "sing-box · mux",
  };
  function coreBadge(server) {
    const profile = server.profile || (server.fragment ? "xray:fragment" : "");
    if (!profile || !PROFILES[profile] || profile === "xray:default") return null;
    return el("span", { class: `tag ${profile.startsWith("singbox") ? "on" : ""}`, text: PROFILES[profile] });
  }

  const CORE_CHOICES = [["auto", "Авто"], ["xray", "Xray"], ["sing-box", "sing-box"]];

  function coreNode(server) {
    // Переключать есть что, только если сервер умеет оба ядра.
    if (server.status === "skipped" || !editable(server) || (server.capability || "dual") !== "dual") return null;
    const pin = server.core_pin || "auto";
    const node = el("select", {
      class: "prio", "aria-label": `Ядро ${server.name}`,
      onchange: () => act("core", { fingerprint: server.fingerprint, core: node.value }, node)
        .then((ok) => { if (!ok) node.value = pin; }),
    }, ...CORE_CHOICES.map(([value, text]) => el("option", { value, text })));
    node.value = pin;
    return node;
  }

  function priorityNode(server) {
    if (server.status === "skipped" || !editable(server)) return null;
    const level = server.priority || "medium";
    const node = el("select", {
      class: `prio ${level}`, "aria-label": `Приоритет ${server.name}`,
      onchange: () => act("priority", { fingerprints: [server.fingerprint], level: node.value }, node)
        .then((ok) => { if (!ok) node.value = level; }),
    }, ...LEVELS.map(([value, text]) => el("option", { value, text })));
    node.value = level;
    return node;
  }

  function switchNode(server) {
    if (server.status === "skipped" || !editable(server)) return null;
    const on = server.status !== "disabled";
    return el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(on),
      "aria-label": `${on ? "Отключить" : "Включить"} ${server.name}`,
      onclick: () => setServers([server.fingerprint], on ? "disabled" : "enabled"),
    });
  }

  // Ручной выбор, как в клиентах VPN: весь трафик через этот сервер, пока не нажмёте
  // «Автовыбор». Выбрать можно и запасной.
  function chooseNode(server, pinned) {
    if (pinned || (server.status !== "member" && server.status !== "spare")) return null;
    return el("button", {
      class: "btn small-btn choose", type: "button", text: "Выбрать",
      "aria-label": `Выбрать ${server.name}`,
      onclick: (event) => act("pin", { tag: server.tag, ttl: "forever" }, event.currentTarget),
    });
  }

  function multiplierText(value) {
    return `x${String(Math.round(value * 100) / 100).replace(".", ",")}`;
  }

  function serverRow(server, s) {
    const pinned = s.pin && sameServer(s.pin.tag, server.tag);
    const main = mainShown(server, s);
    const tone = server.status === "member"
      ? (server.alive === true ? "ok" : server.alive === false ? "bad" : "")
      : server.status === "spare" ? ((VERDICTS[server.verdict] || [""])[0]) : "";
    const title = el("div", { class: "row-title" }, el("span", { class: "server-name", text: server.name }));
    if (pinned) {
      title.append(el("span", s.pin.down
        ? { class: "tag warn", text: "выбран · не отвечает" }
        : { class: "tag on", text: "выбран вручную" }));
    } else if (main) title.append(el("span", { class: "tag on", text: "основной" }));
    else if (server.selected) title.append(el("span", { class: "tag on", text: "выбран" }));
    if (server.reserve) title.append(el("span", { class: `tag ${s.state === "RESERVE" ? "warn" : ""}`, text: "резервный" }));
    const badge = coreBadge(server);
    if (badge) title.append(badge);
    if (server.multiplier !== undefined && server.multiplier !== null) {
      title.append(el("span", { class: "tag", text: multiplierText(server.multiplier) }));
    }
    const classes = ["server"];
    if (server.selected || pinned || main) classes.push("selected");
    if (server.status === "disabled" || server.status === "skipped") classes.push("off");
    return el("li", { class: classes.join(" ") },
      el("span", { class: `dot ${tone}` }),
      title,
      el("div", { class: "values" }, speedValue(server), serverValue(server)),
      el("div", { class: "row-sub", text: serverNote(server, s) }),
      el("div", { class: "row-tools" },
        chooseNode(server, pinned),
        coreNode(server),
        priorityNode(server),
        switchNode(server),
        editable(server) ? iconButton("remove", `Убрать ${server.name} из списка`, () => ask(
          `Убрать сервер «${server.name}» из списка?`,
          "Шлюз перестанет к нему обращаться, и при обновлении подписки он не вернётся. Вернуть можно в разделе «Убранные» внизу списка.",
          "Убрать", () => setServers([server.fingerprint], "removed"), true)) : null));
  }

  function groupNode(source) {
    let node = groups.get(source);
    if (!node) {
      const all = (mode, pick) => () => {
        const chosen = (node.servers || []).filter(pick).filter(editable).map((server) => server.fingerprint);
        if (chosen.length) setServers(chosen, mode);
      };
      node = el("details", { class: "group", open: true },
        el("summary", {}, el("span", { class: "group-name" }), el("span", { class: "group-count muted small" })),
        el("div", { class: "group-tools" },
          el("button", { class: "btn small-btn", type: "button", text: "Включить все", onclick: all("enabled", (server) => server.status === "disabled") }),
          el("button", { class: "btn small-btn", type: "button", text: "Отключить все", onclick: all("disabled", (server) => ["member", "spare", "waiting"].includes(server.status)) })),
        el("ul", { class: "list servers" }));
      groups.set(source, node);
    }
    return node;
  }

  function renderReserve(s) {
    const note = $("reserve-note");
    const reserve = s.reserve;
    note.hidden = !(reserve && s.state === "RESERVE");
    if (note.hidden) return;
    const price = reserve.cost ? ` (${multiplierText(reserve.cost)})` : "";
    note.textContent = `Серверы в работе не отвечают — трафик идёт через резервный сервер «${reserve.name}»${price}. `
      + (reserve.cost ? "Он тратит квоту подписки; " : "")
      + "шлюз ищет живые серверы среди запасных и вернётся к серверам в работе, как только они ответят.";
  }

  // Основной сервер: весь трафик через самый быстрый из серверов в работе.
  function renderMain(s) {
    const box = $("main-box");
    box.hidden = !(s.members || []).length;
    const sticky = s.sticky || {};
    const on = Boolean(sticky.on);
    const measuring = Boolean(sticky.unlimited_hours || sticky.limited_hours);
    $("speed").hidden = box.hidden || !on || !measuring;
    if (box.hidden) return;
    $("sticky").setAttribute("aria-checked", String(on));
    const pinned = Boolean(s.pin && !s.pin.down);
    let text;
    if (!on) {
      text = "Выключено: шлюз сам выбирает сервер с наименьшей задержкой и может менять его каждые полминуты.";
    } else if (pinned) {
      text = "Пока сервер выбран вручную, основной сервер не выбирается — шлюз выберет его, когда выбор снимут.";
    } else if (s.main) {
      const speed = s.main.mbps !== null && s.main.mbps !== undefined ? ` — ${mbps(s.main.mbps)}` : "";
      const basis = s.main.basis === "speed" ? "" : " (скорость ещё не замерена — выбран по задержке)";
      text = `Весь трафик идёт через «${s.main.name || s.main.tag}»${speed}${basis}. `
        + "Шлюз меняет его, если он перестанет отвечать (на сервер той же страны, если такой есть) "
        + "или если другой сервер — и запасной тоже — окажется заметно быстрее.";
    } else {
      text = "Весь трафик пойдёт через самый быстрый сервер в работе — шлюз выберет его, как только серверы ответят.";
    }
    if (on && measuring) {
      const every = (hours) => (hours ? `раз в ${hours} ч` : "не замеряются");
      text += `${pinned ? " Замеры скорости идут и при ручном выборе:" : " Скорость замеряется у всех живых серверов:"} безлимитных — ${every(sticky.unlimited_hours)}, лимитированных — ${every(sticky.limited_hours)} и меньшей загрузкой, x100 — не замеряются; до ${s.budget && s.budget.speed_mb ? Math.round(s.budget.speed_mb) : 0} МБ в сутки.`;
    }
    $("main-note").textContent = text;
  }

  function renderServers(s) {
    renderReserve(s);
    const servers = s.servers || [];
    const used = servers.filter((server) => server.status !== "skipped");
    $("members-count").textContent = used.length ? String(used.length) : "";
    const ranked = servers.some((server) => (server.priority || "medium") !== "medium");
    say("tier-note", ranked && s.tier
      ? `Приоритет: в работе серверы уровня «${LEVEL_NAMES[s.tier] || s.tier}». Уровнем ниже шлюз пользуется, только когда живых выше нет.`
      : "");
    const sources = [...(s.sources || [])];
    for (const server of servers) if (!sources.includes(server.source)) sources.push(server.source);
    const nodes = [];
    for (const source of sources) {
      const mine = servers.filter((server) => server.source === source);
      const node = groupNode(source);
      node.servers = mine;
      const on = mine.filter((server) => ["member", "spare", "waiting"].includes(server.status)).length;
      const off = mine.filter((server) => server.status === "disabled").length;
      node.querySelector(".group-name").textContent = sourceName(source);
      node.querySelector(".group-count").textContent = mine.length ? `включено ${on} из ${mine.length}` : "серверов нет";
      const [enableAll, disableAll] = node.querySelectorAll(".group-tools .btn");
      enableAll.hidden = !off;
      disableAll.hidden = on < 2;
      node.querySelector(".group-tools").hidden = !off && on < 2;
      fill(node.querySelector("ul"), mine.map((server) => serverRow(server, s)), "Серверы этой подписки ещё не получены.");
      nodes.push(node);
    }
    for (const source of [...groups.keys()]) if (!sources.includes(source)) groups.delete(source);
    $("groups").replaceChildren(...nodes);
    const hasSources = (s.subscriptions || []).length || (s.links || []).length;
    say("servers-empty", nodes.length ? "" : hasSources
      ? "Серверы ещё не получены. Обычно это занимает до минуты; если не появятся — смотрите «События»."
      : "Серверов пока нет. Добавьте подписку на вкладке «Подписки».");
    const pinRow = s.pin ? servers.find((server) => sameServer(server.tag, s.pin.tag)) : null;
    const pinName = s.pin ? (pinRow && pinRow.name) || s.pin.name || s.pin.tag : "";
    say("pin-note", !s.pin ? ""
      : s.pin.down
        ? `Выбранный вручную «${pinName}» не отвечает — трафик идёт через серверы, выбранные автоматически. Когда он снова ответит, шлюз вернётся к нему.`
        : `Выбран вручную «${pinName}»${s.pin.until ? ` до ${stamp(s.pin.until, s.now)}` : ""}: весь трафик идёт через него. «Автовыбор» на главной вернёт выбор шлюзу.`);
  }

  function renderRemoved(s) {
    const removed = s.removed || [];
    $("removed-box").hidden = !removed.length;
    $("removed-count").textContent = String(removed.length);
    fill($("removed"), removed.map((server) => el("li", { class: "off" },
      el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: server.name })),
        el("div", { class: "row-sub", text: sourceName(server.source) })),
      el("button", { class: "btn small-btn", type: "button", text: "Вернуть", onclick: () => setServers([server.fingerprint], "enabled") }))));
  }

  // --- подписки ---------------------------------------------------------------------

  function quotaNode(quota, now) {
    if (!quota) return null;
    const used = (quota.upload || 0) + (quota.download || 0);
    const total = quota.total || 0;
    let text = total
      ? `Израсходовано ${gigabytes(used)} ГБ из ${gigabytes(total)} ГБ, осталось ${gigabytes(Math.max(0, total - used))} ГБ`
      : `Безлимитная · израсходовано ${gigabytes(used)} ГБ`;
    if (quota.expire) text += ` · до ${day(quota.expire)}.${new Date(quota.expire * 1000).getFullYear()}`;
    const box = el("div", {}, el("div", { class: "row-sub", text }));
    if (total > 0) {
      const share = Math.min(1, used / total);
      const bar = el("div", { class: `quota ${share > 0.95 ? "bad" : share > 0.8 ? "warn" : ""}` }, el("span"));
      bar.firstChild.style.width = `${Math.round(share * 100)}%`;
      box.append(bar);
    }
    if (quota.expire && quota.expire < now) box.append(el("div", { class: "row-error", text: "Срок подписки истёк" }));
    return box;
  }

  function renderSubs(s) {
    const rows = (s.subscriptions || []).map((sub) => {
      const title = el("div", { class: "row-title" }, el("span", { text: sub.name }));
      if (!sub.secure) title.append(el("span", { class: "tag warn", text: "http, без шифрования" }));
      if (!sub.managed) title.append(el("span", { class: "tag", text: "из config.toml" }));
      const fetched = sub.fetched ? `обновлена ${ago(sub.fetched, s.now)}` : "ещё не получена";
      const main = el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub wrap", text: `${sub.host} · серверов: ${sub.servers} · ${fetched}` }));
      if (sub.error) main.append(el("div", { class: "row-error", text: `Не обновилась: ${sub.error}` }));
      // Подписка без заголовка о трафике — безлимитная: её серверы квоту не тратят.
      const quota = sub.quota ? quotaNode(sub.quota, s.now)
        : sub.fetched ? el("div", { class: "row-sub", text: "Безлимитная: лимит трафика подписка не сообщает" }) : null;
      if (quota) main.append(quota);
      const actions = el("div", { class: "row-actions" });
      if (sub.managed) {
        actions.append(iconButton("edit", `Изменить подписку ${sub.name}`, () => editSubscription(sub)));
        actions.append(iconButton("remove", `Убрать подписку ${sub.name}`, () => ask(
          `Убрать подписку «${sub.name}»?`, "Её серверы пропадут из списка при следующем обновлении.",
          "Убрать", () => act("subscription/remove", { name: sub.name }), true)));
      }
      return el("li", {}, main, actions);
    });
    fill($("subs"), rows, (s.links || []).length ? "" : "Подписок пока нет. Вставьте адрес подписки в поле выше и нажмите «Добавить».");
  }

  function editSubscription(sub) {
    const ua = el("input", {
      id: "edit-sub-ua", type: "text", spellcheck: "false", autocomplete: "off", autocapitalize: "off",
      placeholder: "пусто — по умолчанию xgw/0.1",
    });
    ua.value = sub.user_agent || "";
    const headers = el("textarea", {
      id: "edit-sub-headers", rows: 3, spellcheck: "false", autocomplete: "off", autocapitalize: "off",
      placeholder: "По одному в строке: Name: Value",
    });
    headers.value = Object.entries(sub.headers || {}).map(([key, value]) => `${key}: ${value}`).join("\n");
    const body = el("div", { class: "edit-sub" },
      el("label", { for: "edit-sub-ua", text: "User-Agent" }), ua,
      el("label", { for: "edit-sub-headers", text: "Заголовки" }), headers);
    ask(`Изменить подписку «${sub.name}»`, "", "Сохранить", () => {
      const parsed = {};
      for (const line of headers.value.split("\n")) {
        const at = line.indexOf(":");
        if (at > 0 && line.slice(0, at).trim()) parsed[line.slice(0, at).trim()] = line.slice(at + 1).trim();
      }
      act("subscription/edit", { name: sub.name, user_agent: ua.value.trim(), headers: parsed });
    }, false, body);
  }

  function renderLinks(s) {
    fill($("links"), (s.links || []).map((item) => {
      const title = el("div", { class: "row-title" }, el("span", { text: item.label }));
      if (!item.managed) title.append(el("span", { class: "tag", text: "из config.toml" }));
      return el("li", {},
        el("div", { class: "row-main" }, title, el("div", { class: "row-sub", text: "отдельная ссылка сервера" })),
        item.managed ? iconButton("remove", "Убрать ссылку сервера", () => ask(
          "Убрать ссылку сервера?", item.label, "Убрать", () => act("link/remove", { id: item.id }), true)) : null);
    }));
  }

  async function addSource() {
    const text = $("add-text").value.trim();
    if (!text) {
      $("add-text").focus();
      return;
    }
    if (await act("add", { text }, $("add-submit"))) $("add-text").value = "";
  }

  async function pasteSource() {
    const result = await bridge("paste");
    if (result.ok) {
      $("add-text").value = result.text.trim();
    } else toast("В буфере обмена нет текста — скопируйте адрес подписки или ссылку сервера", true);
  }

  // QR-код подписки или сервера (как в клиентах VPN); QR привязки к шлюзу — к привязке.
  async function scanSource() {
    const result = await bridge("scan");
    if (result.ok) {
      if (result.text.startsWith("xgw://")) offer(result.text);
      else $("add-text").value = result.text.trim();
    } else if (result.loading) toast("Сканер QR-кода загружается из Google Play — подождите полминуты и нажмите ещё раз", true);
    else if (!result.cancel) toast(`Сканер QR-кода не открылся: ${result.error}`, true);
  }

  // --- устройства и записи трафика --------------------------------------------------

  const megabytes = (bytes) => (bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(1).replace(".", ",")} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`);
  const minsec = (value) => `${Math.floor(value / 60)}:${two(Math.floor(value % 60))}`;
  const recordText = (active, now) => `запись ${minsec(Math.max(0, now - active.started))} · ${megabytes(active.bytes)}`;

  function renderDevices(s) {
    const lanOn = Boolean((s.lan || {}).interface);
    const devices = s.devices || [];
    $("devices-count").textContent = devices.length ? String(devices.length) : "";
    $("devices-note").textContent = !lanOn ? "Сеть для устройств на шлюзе не настроена."
      : "Устройство «мимо VPN» ходит в интернет напрямую. Красная точка — записать трафик устройства.";
    const records = s.records || { files: [] };
    fill($("devices"), devices.map((device) => deviceRow(device, records.active, s.now)),
      lanOn ? "Устройств пока нет: адреса выдаются, когда устройство подключается к Wi-Fi роутера." : "");
    $("records-block").hidden = !(records.files || []).length;
    fill($("records"), (records.files || []).map(recordRow));
  }

  function recordTool(device, active, now) {
    const name = device.name || device.mac;
    if (active && active.mac === device.mac) {
      return iconButton("stop", `Остановить запись трафика «${name}»`, () => act("record/stop", {}));
    }
    const button = iconButton("record", `Записать трафик «${name}»`, () => ask(
      `Записать трафик «${name}»?`,
      `Шлюз ${RECORD_SECONDS / 60} минут пишет все пакеты этого устройства в сети дома в файл для Wireshark (не больше 100 МБ). В файле видно, куда и сколько устройство отправляет; содержимое сайтов обычно зашифровано (HTTPS). Файл хранится на шлюзе — последние три записи; остановить можно раньше.`,
      "Записать", () => act("record/start", { mac: device.mac, seconds: RECORD_SECONDS })));
    button.classList.add("rec-btn");
    if (active) button.disabled = true;
    return button;
  }

  async function downloadRecord(file, button) {
    setBusy(button, true);
    button.disabled = true;
    toast("Скачиваю запись…");
    const result = await bridge("download", file.name);
    setBusy(button, false);
    button.disabled = false;
    if (result.ok) toast(`Запись сохранена: ${result.file}`);
    else toast(result.status === 404 ? "Этой записи на шлюзе уже нет" : problem(result, false), true);
  }

  function recordRow(file) {
    const when = new Date(file.ended * 1000).toLocaleString("ru-RU");
    const download = iconButton("download", "Скачать запись (.pcap)", () => downloadRecord(file, download));
    return el("li", {},
      el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: file.label || file.mac })),
        el("div", { class: "row-sub wrap", text: `${when} · ${megabytes(file.bytes)} · пакетов ${file.packets}${file.why ? ` · ${file.why}` : ""}` })),
      el("div", { class: "row-tools" }, download,
        iconButton("remove", "Удалить запись", () => ask(
          "Удалить запись трафика?", `${file.label || file.mac}, ${when}`,
          "Удалить", () => act("record/remove", { name: file.name }), true))));
  }

  // Переключатель — «VPN для этого устройства»: включён по умолчанию. Устройство, которое
  // пущено мимо VPN в config.toml, пульт не меняет — у него только метка.
  function deviceRow(device, active, now) {
    const title = el("div", { class: "row-title" }, el("span", { text: device.name || "без имени" }));
    if (device.offline) title.append(el("span", { class: "tag", text: "не в сети" }));
    if (active && active.mac === device.mac) title.append(el("span", { class: "tag rec", text: recordText(active, now) }));
    const name = device.name || device.mac;
    const locked = device.bypass && !device.managed;
    let control = null;
    if (device.managed || !device.bypass) {
      const vpn = !device.bypass;
      control = el("button", {
        class: "switch", type: "button", role: "switch", "aria-checked": String(vpn),
        "aria-label": `VPN для устройства ${name}`,
        onclick: () => {
          if (!vpn) return act("device", { mac: device.mac, bypass: false });
          ask(`Пустить «${name}» мимо VPN?`,
            "Его трафик пойдёт напрямую, без шифрования и защиты от утечек, и не остановится, даже если Xray перестанет работать. Адрес устройства закрепится за ним.",
            "Пустить мимо VPN", () => act("device", { mac: device.mac, bypass: true }), true);
        },
      });
    }
    return el("li", { class: "device" },
      el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub mono", text: `${device.ip} · ${device.mac}` }),
        el("span", {
          class: device.bypass ? "tag warn" : "tag on",
          text: device.bypass ? (locked ? "мимо VPN · config.toml" : "мимо VPN") : "через VPN",
        })),
      el("div", { class: "row-tools" }, recordTool(device, active, now), control));
  }

  // --- Tailscale: выход в интернет через шлюз, устройства tailnet, маршрут ---------------

  function renderTailscale(s) {
    const t = s.tailscale || {};
    const running = t.state === "running";
    $("ts-card").hidden = !t.state || t.state === "absent";
    const exit = t.exit || {};
    $("ts-exit-row").hidden = !running;
    $("ts-exit").setAttribute("aria-checked", String(exit.advertised === true));
    $("ts-exit").disabled = exit.advertised === null || exit.advertised === undefined;
    $("ts-exit-note").textContent = exit.advertised !== true
      ? "Телефон и ноутбук с Tailscale смогут выходить в интернет через шлюз и его VPN — без второго VPN на телефоне: Android держит один VPN, и это будет Tailscale."
      : exit.approved === false
        ? "Осталось одобрить один раз в консоли Tailscale: Machines → шлюз → Edit route settings → Use as exit node."
        : "На устройстве: Tailscale → Exit node → шлюз. Его интернет пойдёт через Xray шлюза; IPv6 через шлюз закрыт, чтобы не уйти мимо VPN.";
    const peers = t.peers || [];
    $("ts-peers-block").hidden = !running || !peers.length;
    fill($("ts-peers"), peers.map(peerRow));
    $("ts-route-row").hidden = $("ts-card").hidden;
    $("ts-route").value = t.route === "vpn" ? "vpn" : "direct";
    $("ts-route-note").textContent = t.route === "vpn"
      ? "Через VPN, пока Xray отвечает; когда не отвечает или VPN заблокирован — напрямую, чтобы шлюз остался доступен."
      : "Напрямую, мимо VPN: так работают прямые соединения. Провайдер видит, что это Tailscale, но не содержимое.";
  }

  function peerRow(peer) {
    const title = el("div", { class: "row-title" }, el("span", { text: peer.name || peer.ip }));
    if (!peer.online) title.append(el("span", { class: "tag", text: "не в сети" }));
    const vpn = !peer.direct;
    const body = { ip: peer.ip, name: peer.name, direct: vpn };
    const control = el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(vpn),
      "aria-label": `Через VPN для устройства tailnet ${peer.name || peer.ip}`,
      onclick: () => {
        if (!vpn) return act("tailscale/direct", body);
        ask(`Выпускать «${peer.name || peer.ip}» напрямую?`,
          "Когда это устройство выходит в интернет через шлюз, его трафик пойдёт мимо Xray, без защиты VPN.",
          "Напрямую", () => act("tailscale/direct", body), true);
      },
    });
    return el("li", { class: "device" },
      el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub mono", text: [peer.ip, peer.os].filter(Boolean).join(" · ") }),
        el("span", { class: peer.direct ? "tag warn" : "tag on", text: peer.direct ? "напрямую" : "через VPN" })),
      el("div", { class: "row-tools" }, control));
  }

  function renderEvents(s) {
    fill($("events"), (s.events || []).map((event) => el("li", {},
      el("time", { text: stamp(event.ts, s.now) }),
      el("div", { class: "row-main" },
        el("span", { class: "tag", text: KINDS[event.kind] || event.kind }), " ", event.detail))),
    "Событий пока нет.");
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
    if (v.state === "off" && v.detail) sub = `${v.detail}. ${list}`;
    if (v.state === "on") {
      [tone, title] = ["ok", "VPN телефона включён"];
      sub = `${list}. Tailscale на телефоне в это время не работает: Android держит один VPN`
        + (v.path === "vpn" ? `. Пульт ходит к шлюзу через VPN телефона${v.direct_error
          ? ` (напрямую не вышло: ${v.direct_error})` : ""}` : "");
    } else if (v.state === "starting") [tone, title, sub] = ["warn", "VPN телефона включается…", v.detail || list];
    const running = v.state === "on" || v.state === "starting";
    $("vpn").dataset.tone = tone;
    $("vpn-title").textContent = title;
    $("vpn-sub").textContent = sub;
    say("vpn-error", v.state === "error" ? v.detail : "");
    // Список, полученный до А3.1, — без входа пульта: VPN на нём работает, пульт по Wi-Fi — нет.
    say("vpn-old", v.config && v.config.outdated
      ? "Список серверов старого вида: в нём нет запасного пути пульта через VPN телефона. "
        + (fetching ? "Обновляю…"
          : `Приложение обновит его, как только шлюз ответит${fetchProblem ? ` (сейчас: ${fetchProblem})` : ""}.`)
      : "");
    const button = $("vpn-power");
    button.textContent = vpnBusy ? "Подождите…" : running ? "Выключить VPN телефона" : "Включить VPN телефона";
    button.className = `btn wide ${running ? "danger-line" : "primary"}`;
    button.dataset.on = String(running);
    button.disabled = vpnBusy;
    $("vpn-fetch").disabled = vpnBusy || Boolean(fetching);
    $("vpn-fetch").textContent = fetching ? "Обновляю…" : "Обновить серверы";
    $("vpn-notes").hidden = !running || v.notes;
    return v;
  }

  // Пока VPN включён на списке старого вида — раз в минуту пробовать взять новый: по мобильной
  // сети шлюз отвечает и напрямую, а новый список сам перезапускает Xray телефона.
  function vpnTick() {
    const v = renderVpn();
    if (v.state === "on" && v.config && v.config.outdated && !fetching
      && Date.now() - fetchTried > RETRY_MS) fetchServers();
  }

  function watchVpn() {
    clearInterval(vpnTimer);
    vpnTimer = 0;
    renderVpn();
    if (!document.hidden && !$("gateway").hidden) vpnTimer = setInterval(vpnTick, VPN_MS);
  }

  async function vpnPower() {
    if ($("vpn-power").dataset.on === "true") {
      window.XGW.vpnStop();
      setTimeout(renderVpn, 300);
      return;
    }
    vpnBusy = true;
    renderVpn();
    // Список старого вида — сначала обновить: пока VPN XGW не включён, Tailscale телефона ещё
    // работает, и шлюз обычно отвечает. Не вышло — VPN включается на прежнем списке.
    if (fetching) await fetching;
    const saved = vpnInfo().config;
    let old = "";
    if (saved && saved.outdated && !(await fetchServers()).ok) old = fetchProblem;
    const result = await bridge("vpnStart");
    vpnBusy = false;
    renderVpn();
    if (!result.ok) toast(result.status === 200 || !("status" in result) ? result.error : problem(result, false), true);
    else if (old) {
      toast(`VPN включается на прежнем списке серверов, без запасного пути пульта: обновить не удалось (${old})`, true);
    }
  }

  // Список серверов со шлюза — в фоне: кнопку VPN не занимает (в испытании А3.1 нажатие
  // пришлось на «Подождите…» тихого обновления при открытии). Обновление идёт одно за раз.
  function fetchServers() {
    if (!fetching) {
      fetchTried = Date.now();
      fetching = bridge("vpnFetch").then((result) => {
        fetching = null;
        fetchProblem = result.ok ? "" : result.status === 200 ? result.error
          : result.status === 0 ? `нет связи со шлюзом${result.error ? `: ${result.error}` : ""}`
            : problem(result, false);
        renderVpn();
        return result;
      });
      renderVpn();
    }
    return fetching;
  }

  async function vpnFetch() {
    const result = await fetchServers();
    if (result.ok) toast(`Список серверов обновлён: ${result.servers}`);
    else toast(result.status === 200 ? result.error : problem(result, false), true);
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
    go(tab);
    load();
    watchVpn();
    const v = vpnInfo();
    if (!v.config || v.config.outdated || Date.now() - v.config.time > FRESH_MS) fetchServers();
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
  for (const button of $("tabs").querySelectorAll(".tab-btn")) {
    button.addEventListener("click", () => go(button.dataset.tab));
  }
  $("power").addEventListener("click", () => {
    if ($("power").dataset.on === "true") {
      ask("Выключить VPN шлюза?", "Интернет дома пойдёт напрямую, мимо VPN.", "Выключить",
        () => act("power", { on: false }), true);
    } else act("power", { on: true }, $("power"));
  });
  $("unpin").addEventListener("click", () => act("unpin", {}, $("unpin")));
  $("relink").addEventListener("click", () => { window.XGW.forget(); state = null; start(); scan(); });
  $("refresh").addEventListener("click", () => act("refresh", {}));
  $("scan-spares").addEventListener("click", () => act("scan", {}));
  $("speed").addEventListener("click", () => act("speed", {}));
  $("sticky").addEventListener("click", () => {
    const on = $("sticky").getAttribute("aria-checked") !== "true";
    act("sticky", { on }, $("sticky"));
  });
  $("add-submit").addEventListener("click", addSource);
  $("paste").addEventListener("click", pasteSource);
  $("add-scan").addEventListener("click", scanSource);
  $("ts-exit").addEventListener("click", () => {
    const on = $("ts-exit").getAttribute("aria-checked") !== "true";
    if (on) act("tailscale/exit", { on }, $("ts-exit"));
    else ask("Шлюз больше не выходной узел?",
      "Устройства tailnet, что выходят в интернет через шлюз, останутся без интернета, пока на них не выберут другой выходной узел или не выключат его. Если так выходит этот телефон — и он тоже.",
      "Выключить", () => act("tailscale/exit", { on: false }, $("ts-exit")), true);
  });
  $("ts-route").addEventListener("change", () => {
    const before = state && state.tailscale ? state.tailscale.route : "direct";
    act("tailscale/route", { route: $("ts-route").value }, $("ts-route"))
      .then((ok) => { if (!ok) $("ts-route").value = before === "vpn" ? "vpn" : "direct"; });
  });
  $("vpn-power").addEventListener("click", vpnPower);
  $("vpn-notes").addEventListener("click", () => window.XGW.notesSettings());
  $("vpn-fetch").addEventListener("click", vpnFetch);
  $("vpn-always").addEventListener("click", () => ask(
    "VPN всегда",
    "В настройках Android выберите XGW и включите «Постоянная VPN»: телефон сам включит VPN "
      + "после перезагрузки. Но Android держит один VPN: пока включён VPN XGW, Tailscale на "
      + "телефоне не работает, а с «Постоянной VPN» Android будет сам возвращать VPN XGW. "
      + "Если пользуетесь Tailscale на телефоне, «Постоянную VPN» для XGW не включайте.",
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
