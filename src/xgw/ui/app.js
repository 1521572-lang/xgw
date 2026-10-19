// Панель XGW. Всё, что приходит от шлюза (имена серверов из подписок, имена
// устройств, тексты событий), вставляется только как текст — через textContent.
(() => {
  "use strict";

  const POLL_MS = 3000;
  const STALE_S = 90;
  const MANUAL = "manual";
  const $ = (id) => document.getElementById(id);

  const STATES = {
    HEALTHY: ["ok", "Серверы в порядке"],
    DEGRADED: ["warn", "Часть серверов недоступна"],
    ALL_DEAD: ["bad", "Все серверы недоступны"],
    WAN_DOWN: ["bad", "Нет связи с провайдером"],
    XRAY_DOWN: ["bad", "Xray не отвечает"],
    LEAK: ["bad", "Трафик идёт мимо VPN"],
    // Серверы тут ни при чём: не отвечает сам файл, которым шлюз их проверяет.
    PROBE_TARGET_UNREACHABLE: ["warn", "Адрес проверки недоступен"],
    // Серверы в работе не отвечают, трафик несёт резервный (лимитированный) сервер.
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
    dns: "не используется: имя сервера не находится в DNS — шлюз проверит его снова через несколько часов или по кнопке «Обновить»",
    core: "не используется: сервер умеет только sing-box (hysteria2, TUIC, AnyTLS…), а он выключен, не установлен или ещё не заведён — установить: sudo xgw update-singbox",
  };
  const KINDS = {
    capture: "перехват", apply: "конфиг", config: "конфиг", generate: "сборка",
    rotation: "замена", rollback: "откат", pin: "выбор сервера", panel: "панель", telegram: "Telegram",
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
  };

  let state = null;
  let acting = false;
  let timer = 0;
  const drawn = {};
  const groups = new Map(); // источник → его раскрывающийся блок; живёт между перерисовками

  // --- мелочи ---------------------------------------------------------------

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

  // Перерисовывает блок, только если его данные изменились: иначе раскрытые
  // списки и фокус сбрасывались бы каждые три секунды.
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

  const two = (n) => String(n).padStart(2, "0");
  const capital = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : "");
  const sourceName = (source) => (source === MANUAL ? "Отдельные ссылки" : source || "Без подписки");

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

  function toast(text, notes, bad) {
    const node = el("div", { class: bad ? "toast bad" : "toast", role: bad ? "alert" : "status" }, capital(text));
    for (const note of notes || []) node.append(el("span", { class: "muted", text: note }));
    $("toasts").append(node);
    setTimeout(() => node.remove(), bad ? 9000 : 5000);
  }

  // --- обмен со шлюзом ------------------------------------------------------

  async function load() {
    try {
      const response = await fetch("/api/state", { cache: "no-store", credentials: "same-origin" });
      if (response.status === 401) {
        location.reload();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state = await response.json();
      $("banner").hidden = true;
      render();
    } catch (error) {
      $("banner").textContent =
        "Нет связи с демоном XGW — пробую снова. Если так продолжается: sudo systemctl status xgw";
      $("banner").hidden = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (document.hidden) return;
    timer = setTimeout(async () => {
      await load();
      schedule();
    }, POLL_MS);
  }

  async function act(name, body, busyNode) {
    if (acting) return false;
    acting = true;
    if (busyNode) busyNode.dataset.busy = "1";
    let ok = false;
    try {
      const response = await fetch(`/api/${name}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-XGW-Panel": "1" },
        body: JSON.stringify(body || {}),
      });
      if (response.status === 401) {
        location.reload();
        return false;
      }
      if (!response.ok) throw new Error((await response.text()).trim() || `HTTP ${response.status}`);
      const result = await response.json();
      ok = Boolean(result.ok);
      toast(result.text, result.notes, !ok);
    } catch (error) {
      toast(`Не получилось: ${error.message}`, [], true);
    } finally {
      acting = false;
      if (busyNode) delete busyNode.dataset.busy;
    }
    await load();
    schedule();
    return ok;
  }

  const setServers = (fingerprints, mode) => act("servers", { fingerprints, mode });
  // Приоритет сервера: в работе — серверы самого высокого уровня, на котором есть живые.
  const LEVELS = [["high", "Высокий"], ["medium", "Средний"], ["low", "Низкий"]];
  const LEVEL_NAMES = { high: "высокий", medium: "средний", low: "низкий" };
  const setDevice = (mac, bypass) => act("device", { mac, bypass });

  // --- отрисовка ------------------------------------------------------------

  function render() {
    const s = state;
    const stale = !s.updated || s.now - s.updated > STALE_S;
    renderChip(s, stale);
    renderHero(s, stale);
    draw("servers", [s.servers, s.sources, s.pin, s.subscriptions.length, s.links.length, s.state, s.reserve, Math.floor(s.now / 60)], () => renderServers(s));
    draw("main", [s.main, s.sticky, s.pin, s.members.length, (s.budget || {}).speed_mb], () => renderMain(s));
    draw("removed", s.removed, () => renderRemoved(s));
    draw("subs", [s.subscriptions, Math.floor(s.now / 60)], () => renderSubs(s));
    draw("links", s.links, () => renderLinks(s));
    draw("devices", [s.devices, s.lan], () => renderDevices(s));
    draw("events", s.events, () => renderEvents(s));
    draw("telegram", [s.telegram, Math.floor(s.now / 20)], () => renderTelegram(s));
    draw("notes", [s.nodes, s.budget, s.probe_target, s.subscriptions.map((sub) => sub.name)], () => renderNotes(s));
    setBusy($("refresh"), s.busy.refresh);
    setBusy($("scan"), s.busy.scan);
    setBusy($("speed"), s.busy.speed);
    $("scan").hidden = !s.spares.length;
    $("refresh").hidden = !s.subscriptions.length;
    // Пока серверов нет, первое дело — добавить подписку: её блок идёт выше.
    document.body.dataset.empty = s.servers.length ? "0" : "1";
    $("foot").textContent = `XGW ${s.version}` + (s.xray.version ? ` · Xray ${s.xray.version}` : "")
      + " · панель открывается только на этой машине";
  }

  const decimal = (value, digits = 1) => Number(value).toFixed(digits).replace(".", ",");

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
      ? `${s.probe_target}. Серверы не меняются, пока адрес не ответит; задайте в config.toml другой probe.url.`
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
    const lead = el("span", {}, "Проверки серверов расходуют около ", el("b", { text: `${perDay} в сутки` }),
      " и ", el("b", { text: `${decimal(budget.month_gb)} ГБ в месяц` }), ` (${parts.join(", ")}).`);
    const lines = [lead];
    for (const [name, share] of Object.entries(budget.quota_share || {})) {
      // Доля квоты — с множителями серверов: проба через x10 тратит вдесятеро больше.
      const exact = share < 1 ? "меньше 1" : `около ${Math.round(share)}`;
      lines.push(el("span", { text: ` За месяц это ${exact} % трафика подписки «${name}» (с учётом множителей серверов).` }));
    }
    note.classList.toggle("over", Boolean(budget.over));
    if (budget.over) {
      lines.push(el("span", { text: ` Это больше лимита ${budget.limit_mb} МБ в сутки (без сквозной проверки — ${Math.round(budget.total_mb)} МБ): `
        + "уменьшите число серверов в работе (filters.max_members) или увеличьте интервал (probe.interval)." }));
    }
    note.replaceChildren(...lines);
  }

  function health(s, stale) {
    if (!s.updated) return ["off", "Запускается…"];
    if (stale) return ["bad", "Демон XGW не отвечает"];
    if (!s.members.length) return ["off", "Серверов нет"];
    return STATES[s.state] || ["off", s.state || "Нет данных"];
  }

  function renderChip(s, stale) {
    const [tone, text] = health(s, stale);
    $("chip").dataset.tone = tone;
    $("chip").textContent = text;
  }

  function scopeText(capture) {
    // Контейнеры Docker — только когда Docker на машине есть и их перехват включён.
    const docker = Boolean(capture.containers && capture.docker);
    if (capture.lan && capture.local) {
      const machine = docker ? "Эта машина, контейнеры Docker" : "Эта машина";
      return `${machine} и сеть ${capture.lan_if} выходят через VPN`;
    }
    if (capture.lan) {
      return docker
        ? `Сеть ${capture.lan_if} и контейнеры Docker выходят через VPN`
        : `Сеть ${capture.lan_if} выходит через VPN`;
    }
    return docker ? "Эта машина и контейнеры Docker выходят через VPN" : "Эта машина выходит через VPN";
  }

  function renderHero(s, stale) {
    $("brand-note").textContent = "шлюз";
    const mode = s.capture.mode;
    const on = mode === "on";
    const [tone] = health(s, stale);
    const power = $("power");
    let title = "VPN выключен";
    let sub = "Трафик идёт напрямую, мимо VPN";
    let heroTone = "off";
    if (on) {
      title = "VPN включён";
      sub = scopeText(s.capture);
      // Пока хотя бы один сервер жив, VPN работает — кнопка остаётся зелёной;
      // о недоступных серверах говорит отметка в шапке.
      heroTone = tone === "bad" ? "bad" : "ok";
      if (s.capture.inbound_missing) {
        // Перехват включён, но Xray ещё не перезапущен с нужными настройками: правила
        // не загружены, иначе трафик ушёл бы в никуда.
        title = "VPN включается";
        sub = s.capture.blocked
          ? "Xray перезапускается с новыми настройками — до этого интернет закрыт, мимо VPN ничего не уходит"
          : "Xray перезапускается с новыми настройками — до этого трафик идёт напрямую";
        heroTone = "warn";
      } else if (tone === "bad") sub = `VPN включён, но сейчас не работает: ${s.action || "нет связи"}`;
      else if (s.capture.loaded === false) {
        heroTone = "bad";
        sub = "Правила сети не загружены — демон загрузит их заново";
      }
    } else if (mode === "open") {
      title = "VPN временно снят";
      sub = "Xray недоступен — трафик идёт напрямую, пока он не вернётся";
      heroTone = "warn";
    } else if (mode === "none") {
      title = "Перехват не настроен";
      sub = "XGW только управляет Xray: в config.toml перехват выключен";
    }
    $("hero").dataset.tone = heroTone;
    $("power-title").textContent = title;
    $("power-sub").textContent = sub;
    const pressed = on || mode === "open";
    power.setAttribute("aria-pressed", String(pressed));
    power.disabled = acting || !(pressed ? s.power.can_off : s.power.can_on);
    $("power-label").textContent = pressed ? "Выключить VPN" : "Включить VPN";
    power.title = pressed ? "Выключить VPN" : "Включить VPN";
    const why = !pressed && !s.power.can_on ? s.power.why : "";
    $("power-why").hidden = !why;
    $("power-why").textContent = capital(why);

    // Без перехвата трафик машины идёт напрямую — «сейчас через» было бы неправдой.
    // Выбранный вручную не отвечает (pin.down) — трафик ведёт автовыбор, его и показываем.
    const chosen = s.pin && !s.pin.down
      ? [...s.members, ...(s.servers || [])].find((server) => sameServer(server.tag, s.pin.tag))
      : null;
    const current = chosen || (on && !s.capture.inbound_missing
      && (s.members.find((member) => member.selected) || s.members.find((member) => member.main)));
    $("current").hidden = !current;
    if (current) {
      const main = !chosen && s.main && s.main.tag === current.tag;
      $("current-label").textContent = chosen
        ? (s.pin.until ? `Выбран вручную до ${stamp(s.pin.until, s.now)}` : "Выбран вручную")
        : main ? "Основной сервер" : "Сейчас через";
      const delay = current.delay_ms !== null && current.delay_ms !== undefined ? ` · ${current.delay_ms} мс` : "";
      const speed = current.speed_mbps !== null && current.speed_mbps !== undefined ? ` · ${mbps(current.speed_mbps)}` : "";
      $("current-name").textContent = (current.name || current.tag) + speed + delay;
      $("current-name").title = current.name || current.tag;
    }
    $("unpin").hidden = !s.pin;
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

  // Скорость: 85 Мбит/с; ниже 10 — с одним знаком после запятой.
  const mbps = (value) => (value >= 10 ? `${Math.round(value)} Мбит/с` : `${decimal(value)} Мбит/с`);
  const hasSpeed = (server) => server.speed_mbps !== null && server.speed_mbps !== undefined;

  // Скорость по последнему замеру — рядом с задержкой. У запасного замер сделан, пока он
  // был в работе, поэтому он бледнее.
  function speedValue(server, s) {
    if (!hasSpeed(server) || (server.status !== "member" && server.status !== "spare")) return null;
    const old = server.status === "spare";
    return el("span", {
      class: `speed${old ? " old" : ""}`, text: mbps(server.speed_mbps),
      title: old
        ? `Скорость по замеру ${stamp(server.speed_ts, s.now)}, когда сервер был в работе`
        : `Скорость по замеру ${stamp(server.speed_ts, s.now)}`,
    });
  }

  // Пока трафик ведёт сервер, выбранный вручную, основной — только запасной план.
  const mainShown = (server, s) => Boolean(server.main) && !(s.pin && !s.pin.down);

  function serverNote(server, s) {
    if (server.status === "member") {
      const dead = server.alive === false && server.dead_since
        ? ` · не отвечает ${ago(server.dead_since, s.now).replace(" назад", "")}` : "";
      const sticky = s.sticky || {};
      let measured = "";
      if (hasSpeed(server)) {
        measured = ` · замер скорости ${stamp(server.speed_ts, s.now)}`;
      } else if (server.speed_error) {
        measured = ` · замер скорости не удался ${stamp(server.speed_ts, s.now)}`;
      } else if (server.multiplier >= 100 && sticky.on && sticky.every_hours) {
        measured = " · скорость серверов x100 не замеряется";
      }
      return `${mainShown(server, s) ? "основной" : "в работе"}${measured}${dead}`;
    }
    if (server.status === "spare") {
      const role = server.reserve
        ? "резервный: через него пойдёт трафик, если серверы в работе перестанут отвечать"
        : "запасной";
      return role + (server.scanned ? ` · проверен ${stamp(server.scanned, s.now)}` : "")
        + (hasSpeed(server) ? ` · замер скорости ${stamp(server.speed_ts, s.now)}, когда был в работе` : "");
    }
    if (server.status === "disabled") {
      return server.pending ? "отключён — шлюз сейчас уберёт его из работы" : "отключён: шлюз к нему не обращается";
    }
    if (server.status === "skipped") return SKIPS[server.skip] || "не используется";
    return "включён — шлюз сейчас возьмёт его в работу";
  }

  // Пока шлюз не сопоставил сервер с подпиской, у него нет полного отпечатка —
  // отключить или убрать такой сервер нельзя (это длится до первого опроса подписок).
  const editable = (server) => server.fingerprint.length === 8;

  // Ядро, которое ведёт сервер, и профиль обхода (generator/profiles.py): «Xray» — обычное
  // соединение, остальное — то, до чего сервер довела блокировка провайдера.
  const PROFILES = {
    "xray:default": ["Xray", ""],
    "xray:fragment": ["Xray · дробление", "Первая запись TLS уходит к серверу частями (дробление ClientHello), и фильтр провайдера не видит в ней имя сайта. Шлюз включает дробление сам, если без него сервер не отвечает."],
    "singbox:default": ["sing-box", "Сервер ведёт второе ядро — sing-box: оно умеет протоколы, которых нет в Xray (hysteria2, TUIC, AnyTLS, WireGuard), и по-своему устанавливает TLS. Сервер, который умеют оба ядра, шлюз переводит сюда сам, если на Xray он не отвечал."],
    "singbox:tls_fragment": ["sing-box · дробление", "Сервер ведёт sing-box, а начало TLS режется на части (дробление TCP и записей TLS). Шлюз перевёл сервер сюда сам, когда на Xray он «замерзал»."],
    "singbox:mux_padded": ["sing-box · mux", "Сервер ведёт sing-box с мультиплексированием и паддингом: меняются размеры пакетов и тайминги внутри туннеля. Шлюз перевёл сервер сюда сам, когда он «замерзал» на прежних профилях."],
  };
  function coreBadge(server) {
    const profile = server.profile || (server.fragment ? "xray:fragment" : "");
    if (!profile || !PROFILES[profile]) return null;
    const [text, hint] = PROFILES[profile];
    const heavy = profile !== "xray:default";
    return el("span", {
      class: `tag ${profile.startsWith("singbox") ? "on" : ""}`, text,
      title: hint || "Сервер ведёт Xray, соединение обычное",
      ...(heavy ? {} : { "data-plain": "1" }),
    });
  }

  // Подписи короткие: длинная («Только sing-box») задавала ширину списка, и в строке сервера
  // не хватало места. Что значит выбор — в подсказке.
  const CORE_CHOICES = [["auto", "Авто"], ["xray", "Xray"], ["sing-box", "sing-box"]];

  function coreNode(server) {
    // Переключать есть что, только если сервер умеет оба ядра.
    if (server.status === "skipped" || !editable(server) || (server.capability || "dual") !== "dual") return null;
    const pin = server.core_pin || "auto";
    const node = el("select", {
      class: "prio", "aria-label": `Ядро ${server.name}`,
      title: "Ядро сервера: «Авто» — шлюз выбирает сам (Xray, а при блокировке — sing-box); «Xray» или «sing-box» — только это ядро",
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
      title: "Приоритет: шлюз берёт серверы самого высокого уровня, на котором есть живые",
      onchange: () => act("priority", { fingerprints: [server.fingerprint], level: node.value }, node)
        .then((ok) => { if (!ok) node.value = level; }),
    }, ...LEVELS.map(([value, text]) => el("option", { value, text })));
    node.value = level;
    return node;
  }

  function switchNode(server) {
    if (server.status === "skipped" || !editable(server)) return null;
    const on = server.status !== "disabled";
    const label = `${on ? "Отключить" : "Включить"} ${server.name}`;
    return el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(on),
      "aria-label": label, title: on ? "Отключить: шлюз перестанет к нему обращаться" : "Включить",
      onclick: () => setServers([server.fingerprint], on ? "disabled" : "enabled"),
    });
  }

  // Ручной выбор, как в клиентах VPN: весь трафик через этот сервер, пока не нажмёте
  // «Автовыбор». Выбрать можно и запасной; перестанет отвечать — шлюз временно уведёт
  // трафик на автовыбор и вернётся к нему, когда он ответит.
  function chooseNode(server, pinned) {
    if (pinned || (server.status !== "member" && server.status !== "spare")) return null;
    return el("button", {
      class: "btn small-btn choose", type: "button", text: "Выбрать",
      title: `Весь трафик — через «${server.name}», пока не нажмёте «Автовыбор»`,
      "aria-label": `Выбрать ${server.name}`,
      onclick: (event) => act("pin", { tag: server.tag, ttl: "forever" }, event.currentTarget),
    });
  }

  function serverRow(server, s) {
    const pinned = s.pin && sameServer(s.pin.tag, server.tag);
    const main = mainShown(server, s);
    const tone = server.status === "member"
      ? (server.alive === true ? "ok" : server.alive === false ? "bad" : "")
      : server.status === "spare" ? ((VERDICTS[server.verdict] || [""])[0]) : "";
    const title = el("div", { class: "row-title" }, el("span", { text: server.name, title: server.name }));
    if (pinned) {
      title.append(el("span", s.pin.down
        ? { class: "tag warn", text: "выбран · не отвечает", title: "Выбран вручную, но не отвечает: пока трафик ведёт автовыбор" }
        : { class: "tag on", text: "выбран вручную", title: "Весь трафик идёт через этот сервер, пока не нажмёте «Автовыбор»" }));
    } else if (main) {
      title.append(el("span", {
        class: "tag on", text: "основной",
        title: "Весь трафик идёт через этот сервер; другие серверы в работе наготове и подхватят трафик, если он перестанет отвечать",
      }));
    } else if (server.selected) title.append(el("span", { class: "tag on", text: "выбран" }));
    if (server.reserve) {
      title.append(el("span", {
        class: `tag ${s.state === "RESERVE" ? "warn" : ""}`, text: "резервный",
        title: "Резервный выход: через него трафик идёт, только когда все серверы в работе не отвечают. Шлюз проверяет его редко и коротким запросом — он тратит квоту подписки.",
      }));
    }
    const badge = coreBadge(server);
    if (badge) title.append(badge);
    if (server.multiplier !== undefined) {
      title.append(el("span", {
        class: "tag", text: multiplierText(server.multiplier),
        title: "Множитель расхода: столько трафика подписки уходит на каждый байт через этот сервер",
      }));
    }
    const classes = ["server"];
    if (server.selected || pinned || main) classes.push("selected");
    if (server.status === "disabled" || server.status === "skipped") classes.push("off");
    // Две строки (app.css, «.server»): имя с метками, скорость и задержка, под ними —
    // состояние и кнопки. В одной строке с кнопками имени места не оставалось.
    return el("li", { class: classes.join(" ") },
      el("span", { class: `dot ${tone}` }),
      title,
      el("div", { class: "values" }, speedValue(server, s), serverValue(server)),
      el("div", { class: "row-sub", text: serverNote(server, s) }),
      el("div", { class: "row-tools" },
        chooseNode(server, pinned),
        coreNode(server),
        priorityNode(server),
        switchNode(server),
        editable(server) ? iconButton("remove", `Убрать ${server.name} из списка`, () => confirmRemove(
          `Убрать сервер «${server.name}» из списка?`,
          "Шлюз перестанет к нему обращаться, и при обновлении подписки он не вернётся. Вернуть можно в разделе «Убранные» внизу списка.",
          () => setServers([server.fingerprint], "removed"))) : null));
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
          el("button", { class: "btn ghost", type: "button", text: "Включить все", onclick: all("enabled", (server) => server.status === "disabled") }),
          el("button", { class: "btn ghost", type: "button", text: "Отключить все", onclick: all("disabled", (server) => ["member", "spare", "waiting"].includes(server.status)) })),
        el("ul", { class: "list servers" }));
      groups.set(source, node);
    }
    return node;
  }

  function multiplierText(value) {
    return `x${String(Math.round(value * 100) / 100).replace(".", ",")}`;
  }

  function renderReserve(s) {
    const note = $("reserve-note");
    const reserve = s.reserve;
    note.hidden = !(reserve && s.state === "RESERVE");
    if (note.hidden) {
      note.textContent = "";
      return;
    }
    const price = reserve.cost ? ` (${multiplierText(reserve.cost)})` : "";
    note.textContent = `Серверы в работе не отвечают — трафик идёт через резервный сервер «${reserve.name}»${price}. `
      + (reserve.cost ? "Он тратит квоту подписки; " : "")
      + "шлюз ищет живые серверы среди запасных и вернётся к серверам в работе, как только они ответят.";
  }

  // Основной сервер: весь трафик через самый быстрый из серверов в работе.
  function renderMain(s) {
    const box = $("main-box");
    box.hidden = !s.members.length;
    if (box.hidden) return;
    const sticky = s.sticky || {};
    const on = Boolean(sticky.on);
    $("sticky").setAttribute("aria-checked", String(on));
    $("speed").hidden = !on || !sticky.every_hours;
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
        + "Шлюз меняет его, только если он перестанет отвечать или другой окажется заметно быстрее.";
    } else {
      text = "Весь трафик пойдёт через самый быстрый сервер в работе — шлюз выберет его, как только серверы ответят.";
    }
    if (on && sticky.every_hours) {
      text += `${pinned ? " Замеры скорости идут и при ручном выборе:" : " Скорость замеряется"} раз в ${sticky.every_hours} ч, до ${s.budget && s.budget.speed_mb ? Math.round(s.budget.speed_mb) : 0} МБ в сутки; лимитированные — меньшей загрузкой, чтобы не тратить квоту, x100 — не замеряются.`;
    }
    $("main-note").textContent = text;
  }

  function renderServers(s) {
    renderReserve(s);
    const used = s.servers.filter((server) => server.status !== "skipped");
    $("members-count").textContent = used.length ? String(used.length) : "";
    const ranked = s.servers.some((server) => (server.priority || "medium") !== "medium");
    $("tier-note").hidden = !ranked || !s.tier;
    $("tier-note").textContent = ranked && s.tier
      ? `Приоритет: в работе серверы уровня «${LEVEL_NAMES[s.tier] || s.tier}». Уровнем ниже шлюз пользуется, только когда живых выше нет.`
      : "";
    const sources = [...s.sources];
    for (const server of s.servers) if (!sources.includes(server.source)) sources.push(server.source);
    const nodes = [];
    for (const source of sources) {
      const servers = s.servers.filter((server) => server.source === source);
      const node = groupNode(source);
      node.servers = servers;
      const on = servers.filter((server) => ["member", "spare", "waiting"].includes(server.status)).length;
      const off = servers.filter((server) => server.status === "disabled").length;
      node.querySelector(".group-name").textContent = sourceName(source);
      node.querySelector(".group-count").textContent = servers.length
        ? `включено ${on} из ${servers.length}` : "серверов нет";
      const [enableAll, disableAll] = node.querySelectorAll(".group-tools .btn");
      enableAll.hidden = !off;
      disableAll.hidden = on < 2;
      node.querySelector(".group-tools").hidden = !off && on < 2;
      fill(node.querySelector("ul"), servers.map((server) => serverRow(server, s)),
        "Серверы этой подписки ещё не получены.");
      nodes.push(node);
    }
    for (const source of [...groups.keys()]) if (!sources.includes(source)) groups.delete(source);
    $("groups").replaceChildren(...nodes);
    const hasSources = s.subscriptions.length || s.links.length;
    $("servers-empty").hidden = nodes.length > 0;
    $("servers-empty").textContent = hasSources
      ? "Серверы ещё не получены. Обычно это занимает до минуты; если не появятся — смотрите события ниже."
      : "Серверов пока нет. Добавьте подписку — вставьте её адрес в поле «Подписки».";
    $("pin-note").hidden = !s.pin;
    const pinRow = s.pin ? s.servers.find((server) => sameServer(server.tag, s.pin.tag)) : null;
    const pinName = s.pin ? (pinRow && pinRow.name) || s.pin.name || s.pin.tag : "";
    $("pin-note").textContent = !s.pin ? ""
      : s.pin.down
        ? `Выбранный вручную «${pinName}» не отвечает — трафик идёт через серверы, выбранные автоматически. Когда он снова ответит, шлюз вернётся к нему.`
        : `Выбран вручную «${pinName}»${s.pin.until ? ` до ${stamp(s.pin.until, s.now)}` : ""}: весь трафик идёт через него. «Автовыбор» вверху вернёт выбор шлюзу.`;
  }

  function renderRemoved(s) {
    $("removed-box").hidden = !s.removed.length;
    $("removed-count").textContent = String(s.removed.length);
    fill($("removed"), s.removed.map((server) => el("li", { class: "off" },
      el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: server.name, title: server.name })),
        el("div", { class: "row-sub", text: sourceName(server.source) })),
      el("button", { class: "btn ghost", type: "button", text: "Вернуть", onclick: () => setServers([server.fingerprint], "enabled") }))));
  }

  // --- подписки, устройства, события ----------------------------------------

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
    const rows = s.subscriptions.map((sub) => {
      const title = el("div", { class: "row-title" }, el("span", { text: sub.name, title: sub.name }));
      if (!sub.secure) title.append(el("span", { class: "tag warn", text: "http, без шифрования" }));
      if (!sub.managed) title.append(el("span", { class: "tag", text: "из config.toml" }));
      const fetched = sub.fetched ? `обновлена ${ago(sub.fetched, s.now)}` : "ещё не получена";
      const main = el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub", text: `${sub.host} · серверов: ${sub.servers} · ${fetched}` }));
      if (sub.error) main.append(el("div", { class: "row-error", text: `Не обновилась: ${sub.error}` }));
      // Подписка без заголовка о трафике — безлимитная: её серверы квоту не тратят.
      const quota = sub.quota ? quotaNode(sub.quota, s.now)
        : sub.fetched ? el("div", { class: "row-sub", text: "Безлимитная: лимит трафика подписка не сообщает" }) : null;
      if (quota) main.append(quota);
      const actions = el("div", { class: "row-actions" });
      if (sub.managed) {
        actions.append(iconButton("edit", `Изменить подписку ${sub.name}`, () => editSubscription(sub)));
        actions.append(iconButton("remove", `Убрать подписку ${sub.name}`, () => confirmRemove(
          `Убрать подписку «${sub.name}»?`,
          "Её серверы пропадут из списка при следующем обновлении.",
          () => act("subscription/remove", { name: sub.name }))));
      }
      return el("li", {}, main, actions);
    });
    fill($("subs"), rows, s.links.length ? "" : "Подписок пока нет. Вставьте адрес подписки в поле выше и нажмите «Добавить».");
  }

  function editSubscription(sub) {
    const uaId = "edit-sub-ua";
    const headersId = "edit-sub-headers";
    const ua = el("input", {
      id: uaId,
      type: "text",
      spellcheck: false,
      autocomplete: "off",
      value: sub.user_agent || "",
      placeholder: "User-Agent (пусто — по умолчанию xgw/0.1)",
    });
    const headers = el("textarea", {
      id: headersId,
      rows: 3,
      spellcheck: false,
      autocomplete: "off",
      placeholder: "Дополнительные заголовки, по одному в строке: Name: Value",
    });
    try {
      headers.value = Object.entries(sub.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n");
    } catch (error) {
      headers.value = "";
    }
    const body = el("div", { class: "edit-sub" },
      el("label", { for: uaId, text: "User-Agent" }),
      ua,
      el("label", { for: headersId, text: "Заголовки" }),
      headers
    );
    $("edit-sub-title").textContent = `Изменить подписку «${sub.name}»`;
    $("edit-sub-body").replaceChildren(body);
    editSubCallback = async () => {
      const headerObj = {};
      for (const line of headers.value.split("\n")) {
        const idx = line.indexOf(":");
        if (idx > 0) {
          const key = line.slice(0, idx).trim();
          const val = line.slice(idx + 1).trim();
          if (key) headerObj[key] = val;
        }
      }
      return act("subscription/edit", {
        name: sub.name,
        user_agent: ua.value.trim(),
        headers: headerObj,
      });
    };
    $("edit-sub-dialog").showModal();
  }

  function renderLinks(s) {
    fill($("links"), s.links.map((link) => {
      const title = el("div", { class: "row-title" }, el("span", { text: link.label, title: link.label }));
      if (!link.managed) title.append(el("span", { class: "tag", text: "из config.toml" }));
      return el("li", {},
        el("div", { class: "row-main" }, title, el("div", { class: "row-sub", text: "отдельная ссылка сервера" })),
        link.managed ? iconButton("remove", "Убрать ссылку сервера", () => confirmRemove(
          "Убрать ссылку сервера?", link.label, () => act("link/remove", { id: link.id }))) : null);
    }));
  }

  function renderDevices(s) {
    $("devices-card").hidden = !s.lan.interface;
    $("devices-count").textContent = s.devices.length ? String(s.devices.length) : "";
    $("devices-note").textContent = s.lan.gateway ? `сеть ${s.lan.interface}, шлюз ${s.lan.gateway}` : "";
    fill($("devices"), s.devices.map(deviceRow),
    "Устройств пока нет: адреса выдаются, когда устройство подключается к Wi-Fi роутера.");
  }

  // Переключатель — «VPN для этого устройства»: включён по умолчанию. Устройство,
  // которое пущено мимо VPN в config.toml, панель не меняет — у него только метка.
  function deviceRow(device) {
    const title = el("div", { class: "row-title" }, el("span", { text: device.name || "без имени" }));
    if (device.offline) title.append(el("span", { class: "tag", text: "не в сети" }));
    const name = device.name || device.mac;
    const locked = device.bypass && !device.managed;
    let control = null;
    if (device.managed || !device.bypass) {
      const vpn = !device.bypass;
      control = el("button", {
        class: "switch", type: "button", role: "switch", "aria-checked": String(vpn),
        "aria-label": `VPN для устройства ${name}`,
        title: vpn ? "Пустить это устройство мимо VPN" : "Вернуть это устройство в VPN",
        onclick: () => {
          if (!vpn) return setDevice(device.mac, false);
          confirmRemove(
            `Пустить «${name}» мимо VPN?`,
            "Его трафик пойдёт напрямую, без шифрования и защиты от утечек, и не остановится, даже если Xray перестанет работать. Адрес устройства закрепится за ним.",
            () => setDevice(device.mac, true), "Пустить мимо VPN");
        },
      });
    }
    return el("li", {},
      el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub mono", text: `${device.ip} · ${device.mac}` })),
      el("span", {
        class: device.bypass ? "tag warn" : "tag on",
        text: device.bypass ? (locked ? "мимо VPN · config.toml" : "мимо VPN") : "через VPN",
        title: locked ? "Задано в network.bypass_hosts: поменять можно только в config.toml" : "",
      }),
      control ? el("div", { class: "row-tools" }, control) : null);
  }

  // Бот Telegram: токен → код, который отправляют боту → чат подключён. Токен в
  // страницу не возвращается; поле очищается сразу после отправки.
  function renderTelegram(s) {
    const t = s.telegram;
    const bot = t.username ? `@${t.username}` : "бота";
    const text = {
      unavailable: "Бот запускается…",
      off: "Бот присылает уведомления о сбоях и отвечает на команды (/status, /disable…). Создайте бота у @BotFather и вставьте его токен.",
      pairing: "Токен принят. Осталось подключить ваш чат.",
      connected: t.managed
        ? `Подключён ${bot}. В чате с ботом: /help — список команд. Управлять можно только в личной переписке.`
        : `Бот ${bot} задан в config.toml: менять его можно только там.`,
      notify: "Бот присылает уведомления, команды отключены (notify.commands в config.toml).",
      no_chat: "В config.toml задан токен бота, но не задан telegram_chat_id.",
    }[t.mode] || "";
    $("tg-text").textContent = text;
    const chip = $("tg-chip");
    chip.hidden = !["connected", "notify", "pairing"].includes(t.mode);
    chip.className = t.mode === "pairing" ? "tag warn" : "tag on";
    chip.textContent = t.mode === "pairing" ? "ждёт чат" : "подключён";
    $("tg-error").hidden = !t.error;
    $("tg-error").textContent = t.error || "";
    $("tg-form").hidden = t.mode !== "off";
    $("tg-pair").hidden = t.mode !== "pairing";
    if (t.mode === "pairing") {
      $("tg-pair-text").textContent = t.code
        ? `Откройте ${bot} в Telegram и отправьте ему сообщение:`
        : "Код истёк или ещё не получен. Нажмите «Новый код».";
      $("tg-cmd").hidden = !t.code;
      $("tg-cmd").textContent = t.code ? `/start ${t.code}` : "";
      $("tg-until").textContent = t.code ? `Код действует до ${clock(t.until)} и подходит один раз.` : "";
    }
    $("tg-actions").hidden = !(t.managed && ["pairing", "connected", "notify"].includes(t.mode));
  }

  function renderEvents(s) {
    fill($("events"), s.events.map((event) => el("li", {},
      el("time", { text: stamp(event.ts, s.now) }),
      el("div", { class: "row-main" },
        el("span", { class: "tag", text: KINDS[event.kind] || event.kind }), " ", event.detail))),
    "Событий пока нет.");
  }

  // --- окна -----------------------------------------------------------------

  let confirmed = null;
  let editSubCallback = null;

  function confirmRemove(title, text, action, yes = "Убрать") {
    $("confirm-title").textContent = title;
    $("confirm-text").textContent = text;
    $("confirm-yes").textContent = yes;
    confirmed = action;
    $("confirm-dialog").showModal();
  }

  // --- события страницы -----------------------------------------------------

  $("confirm-dialog").addEventListener("close", () => {
    const action = confirmed;
    confirmed = null;
    if ($("confirm-dialog").returnValue === "yes" && action) action();
  });

  $("edit-sub-dialog").addEventListener("close", async () => {
    const cb = editSubCallback;
    editSubCallback = null;
    if ($("edit-sub-dialog").returnValue === "save" && cb) {
      await cb();
    }
  });

  $("power").addEventListener("click", () => {
    if (!state) return;
    const pressed = $("power").getAttribute("aria-pressed") === "true";
    act("power", { on: !pressed }, $("power"));
  });

  $("tg-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = $("tg-token").value.trim();
    if (!token) {
      $("tg-token").focus();
      return;
    }
    if (await act("telegram/connect", { token }, $("tg-submit"))) $("tg-token").value = "";
  });
  $("tg-newcode").addEventListener("click", () => act("telegram/code", {}, $("tg-newcode")));
  $("tg-off").addEventListener("click", () => confirmRemove(
    "Отключить бота?", "Шлюз перестанет присылать уведомления в Telegram и отвечать на команды. Токен будет забыт.",
    () => act("telegram/disconnect", {}), "Отключить"));

  $("unpin").addEventListener("click", () => act("unpin", {}, $("unpin")));
  $("refresh").addEventListener("click", () => act("refresh", {}));
  $("scan").addEventListener("click", () => act("scan", {}));
  $("speed").addEventListener("click", () => act("speed", {}));
  $("sticky").addEventListener("click", () => {
    const on = $("sticky").getAttribute("aria-checked") !== "true";
    act("sticky", { on }, $("sticky"));
  });

  $("add").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("add-text").value.trim();
    if (!text) {
      $("add-text").focus();
      return;
    }
    if (await act("add", { text }, $("add-submit"))) $("add-text").value = "";
  });

  if (navigator.clipboard && navigator.clipboard.readText) {
    $("paste").hidden = false;
    $("paste").addEventListener("click", async () => {
      try {
        $("add-text").value = (await navigator.clipboard.readText()).trim();
        $("add-text").focus();
      } catch (error) {
        toast("Браузер не дал прочитать буфер — вставьте адрес сочетанием Ctrl+V", [], true);
      }
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(timer);
    else load().then(schedule);
  });

  load().then(schedule);
})();
