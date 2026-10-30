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
    capture: "перехват", lifecycle: "перехват", lan: "сеть устройств", apply: "конфиг", config: "конфиг", generate: "сборка",
    rotation: "замена", rollback: "откат", pin: "выбор сервера", panel: "панель",
    subscription: "подписка", xray: "Xray", budget: "трафик проверок", leak: "утечка",
    probe: "адрес проверки", priority: "серверы в работе", reserve: "резервный сервер",
    main: "основной сервер", fragment: "дробление ClientHello", profile: "профиль обхода",
    singbox: "sing-box", core: "ядро сервера", dns: "bootstrap-DNS", tailscale: "Tailscale",
    guard: "контроль скорости", cores: "обновление ядер", netcheck: "проверка сети",
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
    remeasure: ["M21 12a9 9 0 1 1-2.64-6.36", "M21 3v6h-6"],
  };
  const RECORD_SECONDS = 300; // запись трафика устройства — 5 минут, остановить можно раньше

  let state = null;
  let acting = false;
  let timer = 0;
  let gone = false; // панель открыли в другой вкладке — эта больше ничего не делает
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
      // Фокус — для ярлыка и значка в трее: вкладку в фокусе они выводят вперёд, а не
      // открывают новую (tray.open_panel).
      const response = await fetch("/api/state", {
        cache: "no-store", credentials: "same-origin",
        headers: { "X-XGW-Focus": document.hasFocus() ? "1" : "0" },
      });
      if (response.status === 401) {
        location.reload();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state = await response.json();
      if (gone) return;
      $("banner").hidden = true;
      render();
    } catch (error) {
      if (gone) return;
      $("banner").textContent =
        "Нет связи с демоном XGW — пробую снова. Если так продолжается: sudo systemctl status xgw";
      $("banner").hidden = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (document.hidden || gone) return;
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
    draw("servers", [s.servers, s.sources, s.pin, s.subscriptions.length, s.links.length, s.state, s.reserve, s.stranded, s.class_warning, s.whitelist, s.sticky, (s.busy || {}).speed_one, Math.floor(s.now / 60)], () => renderServers(s));
    draw("main", [s.main, s.sticky, s.pin, s.members.length, (s.budget || {}).speed_mb], () => renderMain(s));
    draw("guard", [s.guard, Math.floor(s.now / 60)], () => renderGuard(s));
    draw("removed", s.removed, () => renderRemoved(s));
    draw("subs", [s.subscriptions, Math.floor(s.now / 60)], () => renderSubs(s));
    draw("links", s.links, () => renderLinks(s));
    // Идущая запись трафика: строки перерисовываются, только когда она началась или кончилась,
    // а время и размер меняются в метке — иначе кнопка «Остановить» уплывала бы из-под мыши.
    const recording = (s.records || {}).active;
    // Выбор сервера устройства — из включённых: строки перерисовываются, когда их набор меняется.
    const routable = s.servers.filter((row) => ["member", "spare", "waiting"].includes(row.status))
      .map((row) => [row.fingerprint, row.name, row.multiplier || 0]);
    draw("devices", [s.devices, s.lan, (s.records || {}).files, recording ? recording.name : "", routable, (s.kernel_direct || {}).reason], () => renderDevices(s));
    draw("direct", s.kernel_direct, () => renderDirect(s));
    const recTag = $("devices").querySelector(".tag.rec");
    if (recTag && recording) recTag.textContent = recordText(recording, s.now);
    draw("events", s.events, () => renderEvents(s));
    draw("tailscale", s.tailscale, () => renderTailscale(s));
    draw("phones", [s.phones, Math.floor(s.now / 60)], () => renderPhones(s));
    draw("cores", [s.cores, Math.floor(s.now / 60)], () => renderCores(s));
    setBusy($("cores-check"), s.busy.cores);
    draw("netcheck", [s.netcheck, Math.floor(s.now / 60)], () => renderNetcheck(s));
    draw("pool", [s.free_pool, Math.floor(s.now / 60)], () => renderPool(s));
    setBusy($("netcheck-run"), Boolean((s.netcheck || {}).running));
    draw("notes", [s.nodes, s.budget, s.probe_target, s.subscriptions.map((sub) => sub.name), s.probe_hosts, s.resolvers, s.tailscale_via_vpn, Math.floor(s.now / 60)], () => renderNotes(s));
    setBusy($("refresh"), s.busy.refresh);
    setBusy($("scan"), s.busy.scan);
    setBusy($("speed"), s.busy.speed);
    // Прогресс замеров: «Замер скорости 12 из 74» — пока идёт заход.
    const progress = s.speed_progress || {};
    $("speed").textContent = s.busy.speed && progress.total
      ? `Замер скорости ${progress.done || 0} из ${progress.total}` : "Замерить скорость";
    $("scan").hidden = !s.spares.length;
    $("refresh").hidden = !s.subscriptions.length;
    // Пока серверов нет, первое дело — добавить подписку: её блок идёт выше.
    document.body.dataset.empty = s.servers.length ? "0" : "1";
    const tailnet = Boolean(s.tailscale && s.tailscale.serve && s.tailscale.serve.on);
    $("foot").textContent = `XGW ${s.version}` + (s.xray.version ? ` · Xray ${s.xray.version}` : "")
      + (tailnet ? " · панель открывается на этой машине и с устройств tailnet"
        : " · панель открывается только на этой машине");
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

    // Проверочные хосты (ТЗ R3), bootstrap-DNS (R4a), Tailscale через VPN (R4b).
    const net = $("network-note");
    const netLines = [];
    const hosts = (s.probe_hosts || {}).hosts || [];
    if (hosts.length > 1) {
      const current = (s.probe_hosts || {}).current;
      netLines.push("Проверочные хосты: " + hosts.map((host) => host.host
        + (host.url === current ? " (активный)" : "")
        + (host.errors ? ` — ошибок ${host.errors}` : "")
        + (host.paused_until && host.paused_until > s.now ? `, пропускается до ${clock(host.paused_until)}` : "")).join("; ") + ".");
    }
    const resolvers = (s.resolvers || {}).results || [];
    const dead = resolvers.filter((item) => !item.ok);
    if (dead.length) {
      netLines.push(`bootstrap-DNS: не отвечают ${dead.length} из ${resolvers.length} (${dead.map((item) => item.entry).join(", ")}) — резолвер пробует их последними.`);
    }
    if (s.tailscale_via_vpn) {
      netLines.push("Tailscale временно идёт через VPN: серверы DERP напрямую не отвечают; когда ответят, он вернётся напрямую сам.");
    }
    net.hidden = !netLines.length;
    net.textContent = netLines.join(" ");

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
    // Серверы в порядке ещё не значит, что у устройств сети есть интернет.
    if (s.capture.mode === "on" && s.capture.lan_problem) return ["bad", "Нет интернета в сети"];
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

  // Жизненный цикл перехвата (daemon.Lifecycle): тон строки и слово после «Перехват:».
  const LIFECYCLE = {
    connected: ["ok", "работает", "трафик идёт через VPN"],
    connecting: ["warn", "подключается", "трафик ждёт, мимо VPN ничего не уходит"],
    blocked: ["bad", "заблокирован", "мимо VPN ничего не уходит"],
    open: ["warn", "временно напрямую", "трафик идёт мимо VPN"],
    off: ["off", "снят", "трафик идёт напрямую"],
  };

  function renderLifecycle(s, stale) {
    const line = $("lifecycle");
    const known = LIFECYCLE[s.capture.lifecycle];
    // Строку пишет демон: не отвечает он — она устарела.
    line.hidden = !known || stale;
    if (!known) return;
    const [tone, word, tail] = known;
    const reason = s.capture.lifecycle_reason;
    let text = `Перехват: ${word} — ${reason || tail}`;
    if (reason && s.capture.lifecycle === "blocked") text += `; ${tail}`;
    line.dataset.tone = tone;
    line.textContent = text;
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
      } else if (s.capture.lan_problem) {
        heroTone = "bad";
        sub = `Устройства сети без интернета: ${s.capture.lan_problem}`;
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
    renderLifecycle(s, stale);
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
      const shown = hasRtt(current) ? current.rtt_ms : current.delay_ms;
      const delay = shown !== null && shown !== undefined ? ` · ${shown} мс` : "";
      const speed = current.speed_mbps !== null && current.speed_mbps !== undefined ? ` · ${mbps(current.speed_mbps)}` : "";
      $("current-name").textContent = (current.name || current.tag) + speed + delay;
      $("current-name").title = current.name || current.tag;
    }
    $("unpin").hidden = !s.pin;
  }

  // --- серверы по подпискам -------------------------------------------------

  const hasDelay = (server) => server.delay_ms !== null && server.delay_ms !== undefined;
  const delayTone = (ms) => (ms < 250 ? "ok" : ms < 700 ? "warn" : "bad");
  const hasRtt = (server) => server.rtt_ms !== null && server.rtt_ms !== undefined;
  const rttTone = (ms) => (ms < 120 ? "ok" : ms < 300 ? "warn" : "bad");
  // Сетевая задержка (RTT) — короткий запрос в уже открытом соединении; время пробы целиком
  // (рукопожатия и файл) — в подсказке. Без RTT — как раньше, время пробы.
  function delayBadge(server, s, extra) {
    const probe = hasDelay(server) ? `проба целиком — ${server.delay_ms} мс` : "";
    if (hasRtt(server)) {
      const when = server.rtt_ts ? ` по замеру ${stamp(server.rtt_ts, s.now)}` : "";
      return el("span", {
        class: `delay ${rttTone(server.rtt_ms)}`, text: `${server.rtt_ms} мс`,
        title: [`Сетевая задержка (RTT)${when}`, probe, extra].filter(Boolean).join("; "),
      });
    }
    return el("span", {
      class: `delay ${delayTone(server.delay_ms)}`, text: `${server.delay_ms} мс`,
      title: [probe ? "Время пробы целиком" : "", extra].filter(Boolean).join("; "),
    });
  }

  function serverValue(server, s) {
    if (server.status === "member") {
      if (server.alive === false) return el("span", { class: "delay bad", text: "нет ответа" });
      if (!hasDelay(server) && !hasRtt(server)) {
        return el("span", { class: "delay none", text: server.alive ? "жив" : "проверяется" });
      }
      return delayBadge(server, s, "");
    }
    if (server.status === "spare") {
      const [tone, text] = VERDICTS[server.verdict] || ["none", server.verdict || "не проверялся"];
      // Задержка запасного — по его последней проверке (ядро его не пробует): после замера
      // по кнопке она свежая, как и скорость.
      if (hasDelay(server) || hasRtt(server)) {
        return delayBadge(server, s, `${capital(text)} — по проверке ${stamp(server.scanned, s.now)}`);
      }
      return el("span", { class: `delay ${tone}`, text });
    }
    return el("span", { class: "delay none", text: "—" });
  }

  // Скорость: 85 Мбит/с; ниже 10 — с одним знаком после запятой.
  const mbps = (value) => (value >= 10 ? `${Math.round(value)} Мбит/с` : `${decimal(value)} Мбит/с`);
  const hasSpeed = (server) => server.speed_mbps !== null && server.speed_mbps !== undefined;

  // Скорость по последнему замеру — рядом с задержкой; у запасных тоже (меньшей загрузкой).
  // Замер при занятом канале бледнее: чужая загрузка могла занизить цифру.
  function speedValue(server, s) {
    if (!hasSpeed(server) || (server.status !== "member" && server.status !== "spare")) return null;
    const busy = Boolean(server.speed_busy);
    // Сумма (0.1.18): сам замер и трафик клиентов через этот сервер за время замера.
    const parts = server.speed_bg_mbps
      ? ` (замер ${mbps(server.speed_test_mbps)} + трафик клиентов ${mbps(server.speed_bg_mbps)})` : "";
    return el("span", {
      class: `speed${busy ? " old" : ""}`, text: mbps(server.speed_mbps),
      title: `Скорость по замеру ${stamp(server.speed_ts, s.now)}${parts}`
        + (busy ? " — канал был занят, цифра может быть занижена" : ""),
    });
  }

  // Иконка у скорости (пожелание заказчика 24.10.2026): замер только этого сервера, без общего
  // замера всех. Крутится, пока сервер ждёт замера или замеряется. У x100 замеров нет вовсе.
  const probeTag = (tag) => `probe-${String(tag || "").split("-").slice(1).join("-")}`;
  function speedTool(server, s) {
    if (server.status !== "member" && server.status !== "spare") return null;
    const sticky = s.sticky || {};
    if (!sticky.on || !(sticky.unlimited_hours || sticky.limited_hours)) return null;
    if ((server.multiplier || 0) >= 100) return null;
    const asked = (s.busy && s.busy.speed_one) || [];
    const busy = Boolean(server.speed_queued)
      || [server.tag, server.fingerprint, probeTag(server.tag)].some((key) => asked.includes(key));
    const button = iconButton("remeasure", `Замерить скорость «${server.name}»`,
      (event) => act("speed/one", { tag: server.tag }, event.currentTarget));
    button.classList.add("speed-btn");
    button.title = busy ? "Скорость этого сервера замеряется…" : "Замерить скорость только этого сервера";
    if (busy) {
      button.dataset.busy = "1";
      button.disabled = true;
    }
    return button;
  }

  // Когда цифры скорости нет — почему (issue #1: пустое место ничего не объясняло).
  const speedNote = (server, s) => {
    if (hasSpeed(server)) return ` · замер скорости ${stamp(server.speed_ts, s.now)}`;
    // Участник не отвечает — это и так сказано в той же строке.
    if (server.status === "member" && server.alive === false && !server.speed_error) return "";
    return server.speed_note ? ` · ${server.speed_note}` : "";
  };

  // Пока трафик ведёт сервер, выбранный вручную, основной — только запасной план.
  const mainShown = (server, s) => Boolean(server.main) && !(s.pin && !s.pin.down);

  // 0.1.18: выученный обход блокировки («обход: xray+frag после STALL_BEFORE_BODY»), отметка
  // «нестабилен по ТСПУ» и скорость по реальному трафику через сервер («из трафика»).
  // 0.2.0: рейтинг сервера (скорость, задержка, стабильность, стоимость и приоритет вместе).
  function extraNote(server, s) {
    let text = "";
    if (typeof server.score === "number") {
      text += ` · рейтинг ${server.score.toFixed(2).replace(".", ",")}`;
    }
    const esc = server.escalation;
    if (esc) {
      // Дата — с какого времени сервер на обходе (отчёт f6b: без «с» её принимали за
      // время последней проверки).
      text += ` · обход${esc.ts ? ` с ${stamp(esc.ts, s.now)}` : ""}: ${esc.label}`
        + (esc.verdict ? ` (после ${esc.verdict})` : "");
    }
    if (server.unstable_until && server.unstable_until > s.now) {
      text += ` · нестабилен по ТСПУ: шлюз сам его в работу не ставит до ${stamp(server.unstable_until, s.now)}`;
    }
    if (server.closed_ts) {
      // Анти-ТСПУ 2.0: адрес закрыт целиком — обход (дробление, другое ядро) его не оживит.
      text += ` · адрес закрыт: напрямую не открывается (проверено ${stamp(server.closed_ts, s.now)}), обход не поможет`;
    }
    if (server.speed_passive_mbps !== null && server.speed_passive_mbps !== undefined
        && server.speed_passive_mbps >= 1) {
      text += ` · из трафика ${mbps(server.speed_passive_mbps)}`;
    }
    return text;
  }

  function serverNote(server, s) {
    if (server.status === "member") {
      const dead = server.alive === false && server.dead_since
        ? ` · не отвечает ${ago(server.dead_since, s.now).replace(" назад", "")}` : "";
      return `${mainShown(server, s) ? "основной" : "в работе"}${speedNote(server, s)}${dead}`
        + extraNote(server, s);
    }
    if (server.status === "spare") {
      const role = server.reserve
        ? "резервный: через него пойдёт трафик, если серверы в работе перестанут отвечать"
        : "запасной";
      return role + (server.scanned ? ` · проверен ${stamp(server.scanned, s.now)}` : "")
        + speedNote(server, s) + extraNote(server, s);
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
    "xray:split": ["Xray · нарезка", "Первые пакеты соединения уходят к серверу TCP-сегментами случайной длины: фильтр провайдера, который собирает ClientHello из частей, его не собирает. Шлюз переводит сервер сюда сам, если без этого он не отвечает."],
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
      el("div", { class: "values" }, speedTool(server, s), speedValue(server, s), serverValue(server, s)),
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

  // Контроль скорости (ТЗ R6–R7): идёт поиск замены придушенному или пауза после глобальной
  // просадки канала.
  function renderGuard(s) {
    const guard = s.guard || {};
    const note = $("guard-note");
    let text = "";
    if (guard.episode) {
      text = `Сервер «${guard.episode.name}» придушен (${mbps(guard.episode.mbps || 0)}): ищу замену — `
        + `замерено ${guard.episode.tried || 0} из ${guard.episode.total || 0} кандидатов, по одному.`;
    } else if (guard.cooldown_until && guard.cooldown_until > s.now) {
      text = "Глобальная просадка канала: ни один кандидат не был заметно быстрее — шлюз остаётся "
        + `на прежнем сервере, новые поиски — после ${clock(guard.cooldown_until)}.`;
    }
    note.hidden = !text;
    note.textContent = text;
  }

  // Основной сервер: весь трафик через самый быстрый из серверов в работе.
  function renderMain(s) {
    const box = $("main-box");
    box.hidden = !s.members.length;
    if (box.hidden) return;
    const sticky = s.sticky || {};
    const on = Boolean(sticky.on);
    $("sticky").setAttribute("aria-checked", String(on));
    const measuring = Boolean(sticky.unlimited_hours || sticky.limited_hours);
    $("speed").hidden = !on || !measuring;
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
      // 0.1.18: фоном — редко; основной — по своему трафику, при падении или «придушивании» —
      // поиск замены среди кандидатов (решение заказчика 24.10.2026).
      const spareEvery = sticky.spare_hours ? every(Math.max(sticky.spare_hours, sticky.unlimited_hours || 0)) : every(sticky.unlimited_hours);
      text += `${pinned ? " Замеры скорости идут и при ручном выборе:" : " Скорость замеряется фоном редко:"} серверы в работе — ${every(sticky.unlimited_hours)} (лимитированные — ${sticky.limited_hours === sticky.unlimited_hours ? "" : every(sticky.limited_hours) + ", "}меньшей загрузкой), запасные — ${spareEvery}, x100 — не замеряются; до ${s.budget && s.budget.speed_mb ? Math.round(s.budget.speed_mb) : 0} МБ в сутки.`
        + (sticky.guard ? " Скорость основного шлюз видит по его трафику, а если он упадёт или его «придушат», замерит кандидатов и перейдёт на быстрый. Скорость любого сервера можно обновить кнопкой у его строки." : "");
    }
    $("main-note").textContent = text;
  }

  function renderServers(s) {
    renderReserve(s);
    const used = s.servers.filter((server) => server.status !== "skipped");
    $("members-count").textContent = used.length ? String(used.length) : "";
    const ranked = s.servers.some((server) => (server.priority || "medium") !== "medium");
    // С 0.2.0 приоритет — вес в рейтинге, а не фильтр (issue #2).
    $("tier-note").hidden = !ranked;
    $("tier-note").textContent = ranked
      ? "Приоритет — вес в рейтинге сервера: «высокий» ×1,45, «низкий» ×0,65. В работе — лучшие по рейтингу из всех подписок; сервер уровня ниже встаёт в работу, если он заметно быстрее или если лучших не хватает."
      : "";
    // Тексты пишет шлюз: мёртвого заменить некем; лимитированные в работе из-за приоритета.
    $("stranded-note").hidden = !s.stranded;
    $("stranded-note").textContent = capital(s.stranded || "");
    $("class-note").hidden = !s.class_warning;
    $("class-note").textContent = capital(s.class_warning || "");
    // Белые списки (анти-ТСПУ 2.0): шлюз сам ничего не меняет — сервер включает заказчик.
    const wl = s.whitelist;
    $("whitelist-note").hidden = !wl;
    if (wl) {
      const offer = wl.offer;
      $("whitelist-text").textContent = `Похоже, провайдер включил белые списки (с ${stamp(wl.since, s.now)}): российские адреса открываются напрямую, а зарубежные — нет. Шлюз сам ничего не меняет.`
        + (offer ? ` Сервер для белых списков «${offer.name}» тратит квоту в ${offer.multiplier} раз быстрее${offer.answered ? "" : "; он пока не проверен"}.` : " Серверов для белых списков (x100) в подписках нет.");
      const button = $("whitelist-pin");
      // Уже выбран вручную — кнопка не нужна (вернуть автовыбор — кнопкой «Автовыбор»).
      button.hidden = !offer || Boolean(s.pin && sameServer(offer.tag, s.pin.tag));
      if (offer) {
        button.textContent = `Включить «${offer.name}»`;
        button.onclick = (event) => act("pin", { tag: offer.tag, ttl: "forever" }, event.currentTarget);
      }
    }
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
    const records = s.records || { files: [] };
    // Свой сервер устройства (Ф4): из включённых серверов; лимитированные — с пометкой.
    const choices = s.servers.filter((row) => ["member", "spare", "waiting"].includes(row.status))
      .map((row) => ({
        fingerprint: row.fingerprint,
        label: row.multiplier ? `${row.name} · лимит ×${row.multiplier}` : row.name,
      }));
    const direct = s.kernel_direct || {};
    // Бесплатный пул (М2б.1): выбор есть, пока наблюдение включено (пул проверяет серверы).
    const freePool = s.free_pool || { mode: "off" };
    const pool = { on: freePool.mode !== "off", flow: (freePool.summary || {}).traffic || null };
    fill($("devices"), s.devices.map((device) => deviceRow(device, records.active, s.now, choices, direct, pool)),
    "Устройств пока нет: адреса выдаются, когда устройство подключается к Wi-Fi роутера.");
    $("records-block").hidden = !records.files.length;
    fill($("records"), records.files.map(recordRow));
  }

  // Российские адреса ядром мимо Xray (Ф6) у этого компьютера и контейнеров: переключатель и
  // пояснение под ним. У устройств сети — свой выбор в их строках (directSelect).
  function renderDirect(s) {
    const direct = s.kernel_direct || {};
    $("kernel-direct").setAttribute("aria-checked", String(Boolean(direct.on)));
    let text = "Выключено: российские сайты этого компьютера идут напрямую через Xray. Включите — и "
      + "ядро будет пропускать их само, мимо Xray: меньше нагрузка, соединения не рвутся при его "
      + "перезапуске. У устройств сети — свой выбор в их строках.";
    if (direct.reason) text = `${direct.on ? "Включено, но не действует" : "Включить нельзя"}: ${direct.reason}.`;
    else if (direct.on && !direct.networks) text = "Включено, но сетей нет: geoip.dat не прочитан — российские сайты идут через Xray.";
    else if (direct.on) text = `Включено: ${direct.networks} российских сетей — напрямую ядром, мимо Xray. DNS — по-прежнему через Xray. У устройств сети — свой выбор в их строках.`;
    $("direct-note").textContent = text;
  }

  // Российские адреса устройства — мимо Xray (Ф6, пожелание заказчика из отчёта 25.10.2026:
  // у каждого устройства свой выбор). «Через Xray» — как у всех.
  function directSelect(device, direct) {
    const name = device.name || device.mac;
    const select = el("select", { class: "prio route", "aria-label": `Российские адреса устройства ${name}`,
      title: "Российские сайты этого устройства: через Xray (его выход «напрямую») или ядром шлюза, мимо Xray — меньше нагрузка, соединения не рвутся при перезапуске Xray" });
    select.append(el("option", { value: "", text: "Российские: через Xray" }));
    select.append(el("option", { value: "on", text: "Российские: мимо Xray" }));
    const before = device.kernel ? "on" : "";
    select.value = before;
    if (direct.reason && !device.kernel) {
      select.disabled = true;
      select.title = `Мимо Xray нельзя: ${direct.reason}`;
    }
    select.addEventListener("change", () => {
      act("device/direct", { mac: device.mac, on: select.value === "on" }, select)
        .then((ok) => { if (!ok) select.value = before; });
    });
    return select;
  }

  const megabytes = (bytes) => (bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(1).replace(".", ",")} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`);
  const minsec = (seconds) => `${Math.floor(seconds / 60)}:${two(Math.floor(seconds % 60))}`;
  const recordText = (active, now) =>
    `запись ${minsec(Math.max(0, now - active.started))} · ${megabytes(active.bytes)}`;

  // Запись трафика устройства (record.py): файл .pcap для Wireshark.
  function recordTool(device, active, now) {
    const name = device.name || device.mac;
    if (active && active.mac === device.mac) {
      return iconButton("stop", `Остановить запись трафика «${name}»`, () => act("record/stop", {}));
    }
    const button = iconButton("record", `Записать трафик «${name}»`, () => confirmRemove(
      `Записать трафик «${name}»?`,
      `Шлюз ${RECORD_SECONDS / 60} минут пишет все пакеты этого устройства в сети дома в файл для Wireshark (не больше 100 МБ). В файле видно, куда и сколько устройство отправляет; содержимое сайтов обычно зашифровано (HTTPS). Файл хранится на шлюзе — последние три записи; остановить можно раньше.`,
      () => act("record/start", { mac: device.mac, seconds: RECORD_SECONDS }), "Записать"));
    button.classList.add("rec-btn");
    if (active) {
      button.disabled = true;
      button.title = `Идёт запись трафика «${active.label}»`;
    }
    return button;
  }

  function recordRow(file) {
    const when = new Date(file.ended * 1000);
    const link = el("a", { class: "icon-btn", href: `/records/${encodeURIComponent(file.name)}`,
      download: `xgw-${file.name}`, title: "Скачать запись (.pcap)", "aria-label": "Скачать запись" });
    link.append(icon("download"));
    return el("li", {},
      el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: file.label || file.mac })),
        el("div", { class: "row-sub", text: `${when.toLocaleString("ru-RU")} · ${megabytes(file.bytes)} · пакетов ${file.packets}${file.why ? ` · ${file.why}` : ""}` })),
      el("div", { class: "row-tools" }, link,
        iconButton("remove", "Удалить запись", () => confirmRemove(
          "Удалить запись трафика?", `${file.label || file.mac}, ${when.toLocaleString("ru-RU")}`,
          () => act("record/remove", { name: file.name })))));
  }

  // Переключатель — «VPN для этого устройства»: включён по умолчанию. Устройство,
  // которое пущено мимо VPN в config.toml, панель не меняет — у него только метка.
  // Свой сервер устройства (Ф4): «Авто» — как у всех, через основной сервер. «Бесплатные
  // серверы» — через бесплатный пул (М2б.1): пул пуст — у устройства закрыто, не подписка.
  const POOL_ROUTE_TEXT = "Владельцы бесплатных серверов неизвестны и видят, к каким сайтам идёт устройство: содержимое сайтов с https защищено, без https — нет. Российские домены (.ru, .su, .рф) — напрямую, как у всех. Пока бесплатных серверов нет, зарубежные сайты у устройства закрыты: через подписку оно не пойдёт. Вернуть — «Сервер: авто».";

  function routeSelect(device, choices, pool) {
    const name = device.name || device.mac;
    const select = el("select", { class: "prio route", "aria-label": `Сервер для устройства ${name}`,
      title: "Через какой сервер идёт это устройство. Недоступен — временно через основной" });
    select.append(el("option", { value: "", text: "Сервер: авто" }));
    if (pool.on || device.route === "pool") {
      select.append(el("option", { value: "pool", text: "Бесплатные серверы" }));
    }
    let known = !device.route || device.route === "pool";
    for (const choice of choices) {
      known = known || choice.fingerprint === device.route;
      select.append(el("option", { value: choice.fingerprint, text: choice.label }));
    }
    if (!known) select.append(el("option", { value: device.route, text: "выбранный сервер выключен" }));
    select.value = device.route || "";
    select.addEventListener("change", () => {
      const before = device.route || "";
      const wanted = select.value;
      const send = () => act("device/route", { mac: device.mac, server: wanted }, select)
        .then((ok) => { select.value = ok ? wanted : before; });
      if (wanted === "pool") {
        select.value = before;
        confirmRemove(`Пустить «${name}» через бесплатные серверы?`, POOL_ROUTE_TEXT, send,
          "Через бесплатные", "primary");
        return;
      }
      send();
    });
    return select;
  }

  // Метка устройства через бесплатный пул: закрыто — пул выключен, серверов нет или все молчат.
  function poolTag(pool) {
    const closed = !pool.on || Boolean(pool.flow && pool.flow.closed);
    return closed
      ? { cls: "tag warn", text: "бесплатные серверы · закрыто",
          title: "Бесплатных серверов сейчас нет (или наблюдение выключено): зарубежные сайты у устройства закрыты, пока они не появятся. Вернуть на подписку — «Сервер: авто»" }
      : { cls: "tag on", text: "бесплатные серверы",
          title: pool.flow && pool.flow.server ? `Сейчас через «${pool.flow.server}»${pool.flow.country ? ` (${pool.flow.country})` : ""}` : "" };
  }

  function deviceRow(device, active, now, choices, direct, pool) {
    const title = el("div", { class: "row-title" }, el("span", { text: device.name || "без имени" }));
    if (device.offline) title.append(el("span", { class: "tag", text: "не в сети" }));
    if (active && active.mac === device.mac) {
      title.append(el("span", { class: "tag rec", text: recordText(active, now) }));
    }
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
        el("div", { class: "row-sub mono", text: `${device.ip} · ${device.mac}` }),
        device.bypass ? null
          : el("div", { class: "picks" }, routeSelect(device, choices, pool), directSelect(device, direct))),
      !device.bypass && device.route === "pool"
        ? el("span", { class: poolTag(pool).cls, text: poolTag(pool).text, title: poolTag(pool).title })
        : el("span", {
          class: device.bypass ? "tag warn" : "tag on",
          text: device.bypass ? (locked ? "мимо VPN · config.toml" : "мимо VPN")
            : (device.route ? (device.route_down ? "свой сервер молчит · через основной"
              : "свой сервер") : "через VPN"),
          title: locked ? "Задано в network.bypass_hosts: поменять можно только в config.toml"
            : (device.route_down ? "Свой сервер устройства не отвечает проверкам шлюза — пока он молчит, устройство идёт через основной; вернётся само" : ""),
        }),
      el("div", { class: "row-tools" }, recordTool(device, active, now), control));
  }

  // Tailscale: вход в tailnet, SSH, панель по tailnet и маршрут. Каждый переключатель —
  // одна команда tailscale на шлюзе, и только по нажатию.
  const TS_TEXT = {
    absent: "Tailscale не установлен. XGW работает и без него; чтобы заходить на шлюз с телефона и ноутбука, установите Tailscale по инструкции tailscale.com/download/linux — карточка оживёт сама.",
    stopped: "Tailscale установлен, но служба tailscaled не запущена: sudo systemctl enable --now tailscaled",
    unknown: "tailscaled работает, но не ответил — проверю снова.",
    login: "Шлюз ещё не в tailnet. Нажмите «Войти в Tailscale», откройте ссылку (или QR-код камерой телефона) и войдите в свою учётную запись Tailscale.",
    running: "Шлюз в tailnet: к нему можно зайти с телефона и ноутбука, где включён Tailscale.",
  };

  const httpsLink = (url) => (typeof url === "string" && url.startsWith("https://") ? url : "");

  function drawQr(svg, rows) {
    const NS = "http://www.w3.org/2000/svg";
    const size = rows.length + 8; // рамка в четыре модуля — так требует стандарт
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    let d = "";
    rows.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) if (row[x] === "1") d += `M${x + 4} ${y + 4}h1v1h-1z`;
    });
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("shape-rendering", "crispEdges");
    svg.replaceChildren(path);
  }

  function renderTailscale(s) {
    const t = s.tailscale || { state: "absent" };
    const running = t.state === "running";
    $("ts-text").textContent = TS_TEXT[t.state] || `Tailscale: состояние ${t.backend || "неизвестно"}.`;
    const chip = $("ts-chip");
    chip.hidden = !["running", "login"].includes(t.state);
    chip.className = running ? "tag on" : "tag warn";
    chip.textContent = running ? "в tailnet" : "нужен вход";
    $("ts-addr").hidden = !running || !(t.name || t.address);
    $("ts-addr").textContent = [t.name, t.address].filter(Boolean).join(" · ");

    $("ts-login").hidden = t.state !== "login";
    const auth = httpsLink(t.auth_url);
    $("ts-login-text").textContent = auth
      ? "Ссылка входа готова: откройте её здесь или наведите камеру телефона на QR-код."
      : t.login_pending ? "Жду ссылку входа от Tailscale…" : "";
    $("ts-login-text").hidden = !$("ts-login-text").textContent;
    $("ts-login-btn").hidden = Boolean(auth);
    setBusy($("ts-login-btn"), Boolean(t.login_pending && !auth));
    $("ts-auth").hidden = !auth;
    if (auth) $("ts-auth").href = auth;
    else $("ts-auth").removeAttribute("href");
    // У <svg> нет свойства hidden — только атрибут.
    const qrShown = Boolean(auth && t.auth_qr && t.auth_qr.length);
    $("ts-qr").toggleAttribute("hidden", !qrShown);
    if (qrShown) drawQr($("ts-qr"), t.auth_qr);

    $("ts-ssh-row").hidden = !running;
    $("ts-ssh").setAttribute("aria-checked", String(t.ssh === true));
    $("ts-ssh").disabled = t.ssh === null || t.ssh === undefined;
    $("ts-ssh-note").textContent = t.ssh === true
      ? `Вход — по учётной записи tailnet: ssh ПОЛЬЗОВАТЕЛЬ@${(t.name || "шлюз").split(".")[0]}. Кто и под каким пользователем — правила в консоли tailnet.`
      : t.ssh === false
        ? "Порт SSH в интернет не открывается: войти можно только с устройств вашего tailnet."
        : "Состояние SSH неизвестно: Tailscale не ответил.";

    const serve = t.serve || {};
    $("ts-serve-row").hidden = !running;
    $("ts-serve").setAttribute("aria-checked", String(Boolean(serve.on)));
    const url = httpsLink(serve.url);
    let note;
    if (!serve.on) note = "Панель откроется с устройств tailnet по https и порту 8443 — из интернета этот адрес недоступен.";
    else if (serve.pending) note = "Осталось разрешить HTTPS в tailnet: нажмите кнопку и подтвердите в консоли Tailscale.";
    else if (serve.live === false) note = "Tailscale сейчас не ведёт порт 8443 на панель — выключите и включите переключатель.";
    else note = "Открывается только на устройствах с включённым Tailscale.";
    $("ts-serve-note").textContent = note;
    $("ts-serve-url").hidden = !(serve.on && url && !serve.pending);
    $("ts-serve-url").textContent = url;
    if (url) $("ts-serve-url").href = url;
    const enable = httpsLink(serve.enable_url);
    $("ts-enable").hidden = !(serve.pending && enable);
    if (enable) $("ts-enable").href = enable;

    const funnel = t.funnel || {};
    $("ts-funnel-row").hidden = !running;
    $("ts-funnel").setAttribute("aria-checked", String(Boolean(funnel.on)));
    $("ts-funnel-note").textContent = !funnel.on
      ? "Адрес шлюза для приложения XGW на телефоне — из любой сети, без Tailscale на телефоне. Включается и кнопкой «Привязать телефон»."
      : funnel.pending ? "Осталось разрешить Funnel в tailnet: нажмите кнопку и подтвердите в консоли Tailscale."
        : funnel.live === false ? "Tailscale сейчас не ведёт адрес на шлюз — выключите и включите переключатель."
          : "Адрес открыт в интернет, но войти можно только с привязанного телефона (карточка «Телефоны»).";
    const funnelEnable = httpsLink(funnel.enable_url);
    $("ts-funnel-enable").hidden = !(funnel.pending && funnelEnable);
    if (funnelEnable) $("ts-funnel-enable").href = funnelEnable;

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

    $("ts-route-row").hidden = t.state === "absent";
    $("ts-route").value = t.route === "vpn" ? "vpn" : "direct";
    $("ts-route-note").textContent = t.route === "vpn"
      ? "Через VPN, пока Xray отвечает; когда не отвечает или VPN заблокирован — напрямую, чтобы шлюз остался доступен."
      : "Напрямую, мимо VPN: так работают прямые соединения. Провайдер видит, что это Tailscale, но не содержимое.";

    const cgnat = t.cgnat || [];
    $("ts-k5").hidden = !cgnat.length || t.netfilter_off === true;
    $("ts-k5-text").textContent = `Провайдер выдаёт адреса из 100.64.0.0/10 (${cgnat.join(", ")}): фаервол Tailscale отбрасывает их пакеты, и сеть провайдера у шлюза может пропасть.`;
    $("ts-k6").hidden = t.override_dns !== true;
  }

  // Устройство tailnet: через шлюз — через Xray или напрямую (выходной узел).
  function peerRow(peer) {
    const title = el("div", { class: "row-title" }, el("span", { text: peer.name || peer.ip }));
    if (!peer.online) title.append(el("span", { class: "tag", text: "не в сети" }));
    const vpn = !peer.direct;
    const control = el("button", {
      class: "switch", type: "button", role: "switch", "aria-checked": String(vpn),
      "aria-label": `Через VPN для устройства tailnet ${peer.name || peer.ip}`,
      title: vpn ? "Выпускать это устройство напрямую, мимо VPN" : "Вернуть это устройство в VPN",
      onclick: () => {
        const body = { ip: peer.ip, name: peer.name, direct: vpn };
        if (!vpn) return act("tailscale/direct", body);
        confirmRemove(`Выпускать «${peer.name || peer.ip}» напрямую?`,
          "Когда это устройство выходит в интернет через шлюз, его трафик пойдёт мимо Xray, без защиты VPN.",
          () => act("tailscale/direct", body), "Напрямую");
      },
    });
    return el("li", {},
      el("div", { class: "row-main" }, title,
        el("div", { class: "row-sub mono", text: [peer.ip, peer.os].filter(Boolean).join(" · ") })),
      el("span", { class: peer.direct ? "tag warn" : "tag on", text: peer.direct ? "напрямую" : "через VPN" }),
      el("div", { class: "row-tools" }, control));
  }

  // Телефоны с приложением XGW: «Привязать телефон» → QR-код → камера приложения.
  let qrWasShown = false; // QR был на экране — привязку стоит показать сообщением

  function renderPhones(s) {
    const p = s.phones || { list: [], pairing: {} };
    const list = p.list || [];
    const pairing = p.pairing || {};
    $("phones-count").textContent = list.length ? String(list.length) : "";
    $("phones-text").textContent = p.available === false
      ? "API приложения не запущен — подробности в журнале XGW."
      : list.length
        ? "Приложение XGW на этих телефонах управляет шлюзом из любой сети и берёт у него серверы для VPN телефона."
        : "Поставьте на телефон приложение XGW, нажмите «Привязать телефон» и наведите камеру приложения на QR-код. Больше ничего вводить не нужно.";
    const qrShown = Boolean(pairing.qr && pairing.qr.length);
    const waiting = Boolean(p.waiting);
    $("phones-pair").hidden = !(qrShown || waiting);
    $("phones-qr").toggleAttribute("hidden", !qrShown);
    if (qrShown) drawQr($("phones-qr"), pairing.qr);
    $("phones-pair-text").textContent = waiting
      ? "Осталось разрешить Funnel в tailnet: нажмите кнопку и подтвердите в консоли Tailscale — QR-код появится сам."
      : "Откройте приложение XGW на телефоне и наведите камеру на этот код.";
    $("phones-until").textContent = qrShown && pairing.until ? `Код действует до ${clock(pairing.until)} и подходит один раз.` : "";
    const enable = httpsLink(p.enable_url);
    $("phones-enable").hidden = !(waiting && enable);
    if (enable) $("phones-enable").href = enable;
    $("phones-add").hidden = qrShown || waiting || p.available === false;
    if (pairing.paired && qrWasShown && !qrShown) toast(`Телефон «${pairing.paired}» привязан`, []);
    qrWasShown = qrShown;
    fill($("phones"), list.map((phone) => el("li", {},
      el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: phone.name })),
        el("div", { class: "row-sub", text: `привязан ${stamp(phone.paired, s.now)}`
          + (phone.seen ? ` · на связи ${ago(phone.seen, s.now)}` : " · ещё не заходил") })),
      el("div", { class: "row-actions" },
        iconButton("edit", `Переименовать ${phone.name}`, () => {
          const name = window.prompt("Имя телефона", phone.name);
          if (name && name.trim() && name.trim() !== phone.name) act("phones/rename", { id: phone.id, name: name.trim() });
        }),
        iconButton("remove", `Отвязать ${phone.name}`, () => confirmRemove(
          `Отвязать «${phone.name}»?`,
          "Приложение на этом телефоне больше не сможет управлять шлюзом и получать серверы. VPN телефона продолжит работать на последних полученных серверах.",
          () => act("phones/revoke", { id: phone.id }), "Отвязать"))))),
    "");
  }

  // Ядра Xray и sing-box: новый выпуск на GitHub ставится кнопкой, шлюз проверяет его и при
  // сбое сам возвращает прежний; прежний лежит рядом — для кнопки «Вернуть …».
  function renderCores(s) {
    const c = s.cores || { rows: [] };
    const rows = c.rows || [];
    $("cores-card").hidden = !rows.length;
    const job = c.job || null;
    const running = Boolean(c.active);
    // «sing-box» пишется со строчной и в начале фразы.
    const sentence = (value) => (value.startsWith("sing-box") ? value : capital(value));
    let text = "";
    let bad = false;
    if (running) {
      text = job && job.state === "running" && job.stage ? sentence(job.stage) + "…" : "Ядро сейчас обновляется — подождите…";
    } else if (job && job.finished && s.now - job.finished < 86400) {
      text = sentence(job.text || "");
      bad = job.state === "failed";
    }
    $("cores-job").textContent = text;
    $("cores-job").hidden = !text;
    $("cores-job").className = bad ? "note bad" : "note";
    $("cores-job").setAttribute("role", bad ? "alert" : "status");
    fill($("cores"), rows.map((row) => coreRow(row, s, running)), "");
    $("cores-checked").textContent = c.checked
      ? `Выпуски на GitHub проверены ${stamp(c.checked, s.now)}` + (c.error ? ` — не всё удалось: ${c.error}` : "") + ". Шлюз проверяет их раз в сутки."
      : "Выпуски на GitHub ещё не проверялись — шлюз проверяет их раз в сутки.";
    $("cores-check").disabled = running;
  }

  function coreRow(row, s, running) {
    const title = el("div", { class: "row-title" }, el("span", { text: row.title }));
    if (row.withdrawn) title.append(el("span", { class: "tag rec", text: "убрана с GitHub" }));
    if (row.watch_until) title.append(el("span", { class: "tag warn", text: `наблюдение до ${stamp(row.watch_until, s.now)}` }));
    const origin = !row.installed ? "не установлен"
      : row.accepted ? `${row.installed} · обновлён из панели и проверен шлюзом`
        : row.installed === row.baseline ? `${row.installed} · проверен разработчиком XGW`
          : `${row.installed} · XGW проверен на ${row.baseline}`;
    const main = el("div", { class: "row-main" }, title, el("div", { class: "row-sub", text: origin }));
    const latest = row.latest;
    if (latest) {
      const published = Date.parse(latest.published || "");
      main.append(el("div", { class: "row-sub", text: `На GitHub есть ${latest.version}`
        + (latest.prerelease ? " (предварительный выпуск)" : "")
        + (Number.isFinite(published) ? ` от ${day(published / 1000)}` : "") }));
    }
    if (row.withdrawn) main.append(el("div", { class: "row-error", text: "Разработчики убрали эту версию с GitHub — так бывает, когда в ней находят опасную ошибку. Обновите ядро." }));
    const rejected = row.rejected;
    if (rejected && rejected.version && rejected.version !== row.installed) {
      main.append(el("div", { class: "row-error", text: rejected.kind === "rollback"
        ? `${rejected.version} убран: ${rejected.reason}`
        : `${rejected.version} не прошёл проверку на этом шлюзе: ${rejected.reason}` }));
    }
    if (row.watch_until && row.previous) {
      main.append(el("div", { class: "row-sub", text: `Если ядро перестанет отвечать, шлюз сам вернёт ${row.previous}.` }));
    }
    const tools = el("div", { class: "row-actions" });
    if (latest) {
      const again = rejected && rejected.version === latest.version && rejected.kind !== "rollback";
      tools.append(el("button", {
        class: "btn primary small-btn", type: "button", disabled: running,
        text: again ? "Попробовать снова" : `Обновить до ${latest.version}`,
        onclick: () => confirmRemove(
          `Обновить ${row.title} до ${latest.version}?`,
          `Шлюз скачает ${row.title} ${latest.version} с GitHub, сверит SHA-256 и проверит его на рабочем конфиге. На несколько секунд соединения оборвутся. Если новое ядро не запустится или запрос в интернет через серверы не пройдёт, шлюз сам вернёт ${row.installed}. Ещё сутки он следит за ядром.`,
          () => act("cores/update", { core: row.core, version: latest.version }), "Обновить", "primary"),
      }));
    }
    if (row.previous) {
      tools.append(el("button", {
        class: "btn ghost small-btn", type: "button", disabled: running,
        text: `Вернуть ${row.previous}`,
        onclick: () => confirmRemove(
          `Вернуть ${row.title} ${row.previous}?`,
          `Шлюз поставит прежнюю версию ${row.previous} вместо ${row.installed} и перезапустит ядро — на несколько секунд соединения оборвутся.`,
          () => act("cores/rollback", { core: row.core }), "Вернуть", "primary"),
      }));
    }
    return el("li", { class: "core-row", "data-core": row.core }, main, tools);
  }

  // Проверка сети (кнопка «Проверить сеть»): размер пакетов до сервера, UDP напрямую и через
  // VPN, утечки DNS и IPv6, чужие правила фаервола. Демон сам её не запускает.
  const CHECK_LEVELS = { OK: ["on", "в порядке"], WARN: ["warn", "внимание"], FAIL: ["rec", "ошибка"] };

  // Бесплатный пул (docs/FREEPOOL-PLAN.md, веха М1): наблюдение — трафик идёт через подписку.
  const POOL_SOURCES = {
    vpngate: "VPN Gate", vpnbook: "VPNBook",
    igareck: "GitHub igareck (проверены в России)", mahdibland: "GitHub mahdibland",
  };
  const POOL_STATUS = {
    SUCCESS: "ок", PARTIAL: "частично", UNAVAILABLE: "недоступен", RATE_LIMITED: "просит реже",
    SCHEMA_CHANGED: "формат изменился", DISABLED: "выключен",
    RESOURCE_LIMIT: "слишком большой ответ",
  };

  // Устройства через бесплатные серверы (М2б.1) — фраза в карточке пула.
  function poolFlowText(flow, devices) {
    if (!flow) return "";
    const names = (flow.devices || []).map((ip) => {
      const found = (devices || []).find((device) => device.ip === ip);
      return found && found.name ? found.name : ip;
    }).join(", ");
    if (flow.closed) {
      return ` Через бесплатные серверы: ${names} — закрыто: ${flow.members ? "все серверы пула молчат" : "допущенных серверов нет"}. Вернуть на подписку — «Сервер: авто» в списке устройств.`;
    }
    return ` Через бесплатные серверы: ${names} — сервер «${flow.server || "?"}»${flow.country ? ` (${flow.country})` : ""}, задержка ${flow.delay_ms || 0} мс; живых ${flow.alive || 0} из ${flow.members || 0}.`;
  }

  function renderPool(s) {
    const pool = s.free_pool || { mode: "off" };
    const on = pool.mode !== "off";
    const sum = pool.summary || null;
    $("pool-toggle").textContent = on ? "Выключить" : "Включить наблюдение";
    $("pool-refresh").hidden = !on;
    if (!on) {
      $("pool-text").textContent = "Альтернативный режим: бесплатные серверы (списки GitHub, VPN Gate, VPNBook) вместо подписки. Наблюдение собирает их списки через подписку и проверяет серверы, а трафик идёт как прежде — через подписку.";
      fill($("pool-sources"), [], "");
      return;
    }
    if (!sum) {
      $("pool-text").textContent = "Наблюдение включено: первый опрос источников — в ближайшую минуту.";
    } else {
      const regionsText = Object.entries(sum.by_region || {}).map(([name, count]) => `${name} ${count}`).join(", ");
      const failures = Object.entries(sum.tunnel_failures || {}).map(([code, count]) => `${code} ${count}`).join(", ");
      // Туннели — серверы SSTP VPN Gate (веха М2в; до неё — OpenVPN).
      const tunnels = sum.tunnel_backend
        ? `SSTP (VPN Gate) — ${sum.sstp || 0} (туннелем не проверить: ${sum.tunnel_backend}; адрес открыт — ${sum.reachable_tunnel || 0}, закрыт — ${sum.closed})`
        : `SSTP (VPN Gate) — ${sum.sstp || 0}, туннелем за сутки: попыток ${sum.tunnel_attempts || 0}, поднялось ${sum.tunnels_up || 0}${failures ? ` (отказы: ${failures})` : ""}, подключений за час ${sum.handshakes_hour || 0}${sum.handshakes_free_at ? `; суточный предел ${sum.handshakes_day_limit} подключений занят — новые проверки туннелем после ${day(sum.handshakes_free_at)} ${clock(sum.handshakes_free_at)}` : ""}`;
      const bySource = Object.entries(sum.ready_by_source || {}).map(([name, count]) => `${POOL_SOURCES[name] || name} — ${count}`).join(", ");
      $("pool-text").textContent = `Наблюдение (регион ${sum.region}): найдено ${sum.found}: из списков GitHub — ${sum.lists || 0}, ключей Outline — ${sum.outline ?? sum.supported_now}, ${tunnels}. Проверено ${sum.checked}, пригодно ${sum.ready}${regionsText ? ` (${regionsText})` : ""}${bySource ? `: ${bySource}` : ""}. Трафик проверок за сутки — ${sum.spent_mb} из ${sum.budget_mb} МБ; серверы списков GitHub — ${sum.lists_spent_mb || 0} МБ, без предела.${poolFlowText(sum.traffic, s.devices)}`;
      fill($("pool-sources"), (sum.sources || []).map((src) => el("li", { class: "check-row" },
        el("div", { class: "row-main" },
          el("div", { class: "row-title" }, el("span", { text: POOL_SOURCES[src.id] || src.id }),
            el("span", { class: `tag ${src.status === "SUCCESS" ? "ok" : src.status === "PARTIAL" ? "warn" : "bad"}`, text: POOL_STATUS[src.status] || src.status })),
          el("div", { class: "row-sub", text: (src.retrieved_at ? `список от ${stamp(src.retrieved_at, s.now)}` : "списка ещё нет")
            + (src.variants ? ` · вариантов ${src.variants}` : "")
            + (src.stale ? " · список устарел" : "") + (src.detail ? ` · ${src.detail}` : "") })))), "");
    }
  }

  function renderNetcheck(s) {
    const n = s.netcheck || {};
    fill($("netcheck"), (n.checks || []).map((check) => {
      const [kind, label] = CHECK_LEVELS[check.level] || ["", check.level];
      const main = el("div", { class: "row-main" },
        el("div", { class: "row-title" }, el("span", { text: check.name }), el("span", { class: `tag ${kind}`, text: label })),
        // «ufw …», «nftables.service …» — имена программ пишутся со строчной и в начале фразы.
        el("div", { class: "row-sub", text: /^[a-z]/.test(check.text) ? check.text : capital(check.text) }));
      if (check.advice) main.append(el("div", { class: "row-sub", text: "→ " + check.advice }));
      return el("li", { class: "check-row", "data-level": check.level }, main);
    }), "");
    $("netcheck-when").textContent = n.running ? "Проверяю сеть — это займёт до 15 секунд…"
      : n.at ? `Проверено ${stamp(n.at, s.now)} за ${Math.max(1, Math.round(n.took || 0))} с.`
        : "Ещё не проверялась. Проверка займёт до 15 секунд: размер пакетов до сервера, пропускает ли провайдер UDP, идёт ли UDP через сервер, не уходят ли DNS и IPv6 мимо VPN, чужие правила фаервола.";
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

  function confirmRemove(title, text, action, yes = "Убрать", tone = "danger") {
    $("confirm-title").textContent = title;
    $("confirm-text").textContent = text;
    $("confirm-yes").textContent = yes;
    $("confirm-yes").className = `btn ${tone === "primary" ? "primary" : "danger"}`;
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

  $("ts-login-btn").addEventListener("click", () => act("tailscale/login", {}, $("ts-login-btn")));
  $("ts-exit").addEventListener("click", () => {
    const on = $("ts-exit").getAttribute("aria-checked") !== "true";
    if (on) act("tailscale/exit", { on }, $("ts-exit"));
    else confirmRemove(
      "Шлюз больше не выходной узел?",
      "Устройства tailnet, что выходят в интернет через шлюз, останутся без интернета, пока на них не выберут другой выходной узел или не выключат его.",
      () => act("tailscale/exit", { on: false }, $("ts-exit")), "Выключить");
  });
  $("ts-ssh").addEventListener("click", () => {
    const on = $("ts-ssh").getAttribute("aria-checked") !== "true";
    if (on) act("tailscale/ssh", { on }, $("ts-ssh"));
    else confirmRemove(
      "Выключить SSH через Tailscale?",
      "Открытые сеансы Tailscale SSH оборвутся, новые не откроются. OpenSSH, если он стоит на шлюзе, не затрагивается.",
      () => act("tailscale/ssh", { on: false }, $("ts-ssh")), "Выключить");
  });
  $("ts-serve").addEventListener("click", () => {
    const on = $("ts-serve").getAttribute("aria-checked") !== "true";
    if (on) act("tailscale/serve", { on }, $("ts-serve"));
    else confirmRemove(
      "Выключить панель по tailnet?",
      location.hostname.endsWith(".ts.net")
        ? "Вы открыли панель по tailnet: эта страница перестанет открываться. На самом шлюзе панель останется."
        : "С устройств tailnet панель перестанет открываться. На самом шлюзе она останется.",
      () => act("tailscale/serve", { on: false }, $("ts-serve")), "Выключить");
  });
  $("ts-funnel").addEventListener("click", () => {
    const on = $("ts-funnel").getAttribute("aria-checked") !== "true";
    if (on) act("tailscale/funnel", { on }, $("ts-funnel"));
    else confirmRemove(
      "Выключить адрес для приложения?",
      "Приложение XGW на телефоне не сможет управлять шлюзом и обновлять серверы, пока адрес не включить снова. VPN телефона продолжит работать.",
      () => act("tailscale/funnel", { on: false }, $("ts-funnel")), "Выключить");
  });
  $("phones-add").addEventListener("click", () => act("phones/pair", {}, $("phones-add")));
  $("cores-check").addEventListener("click", () => act("cores/check", {}, $("cores-check")));
  $("netcheck-run").addEventListener("click", () => act("netcheck", {}, $("netcheck-run")));
  $("pool-toggle").addEventListener("click", () => act("freepool/mode", {
    mode: ((state || {}).free_pool || {}).mode === "observe" ? "off" : "observe" }, $("pool-toggle")));
  $("pool-refresh").addEventListener("click", () => act("freepool/refresh", {}, $("pool-refresh")));
  $("phones-cancel").addEventListener("click", () => act("phones/cancel", {}, $("phones-cancel")));
  $("ts-route").addEventListener("change", () => {
    const before = state && state.tailscale ? state.tailscale.route : "direct";
    act("tailscale/route", { route: $("ts-route").value }, $("ts-route"))
      .then((ok) => { if (!ok) $("ts-route").value = before; });
  });
  $("ts-k5-fix").addEventListener("click", () => confirmRemove(
    "Выключить фаервол Tailscale?",
    "Tailscale перестанет ставить свои правила (ts-input и другие) — фаервол шлюза держит XGW. Это нужно, когда провайдер выдаёт адреса из 100.64.0.0/10.",
    () => act("tailscale/fix", { name: "netfilter" }, $("ts-k5-fix")), "Выключить"));
  $("ts-k6-fix").addEventListener("click", () => confirmRemove(
    "Не принимать DNS из tailnet?",
    "DNS-запросы шлюза снова пойдут через VPN. Имена MagicDNS (*.ts.net) на самом шлюзе перестанут разрешаться; на других устройствах всё останется.",
    () => act("tailscale/fix", { name: "dns" }, $("ts-k6-fix")), "Не принимать"));

  $("unpin").addEventListener("click", () => act("unpin", {}, $("unpin")));
  $("refresh").addEventListener("click", () => act("refresh", {}));
  $("scan").addEventListener("click", () => act("scan", {}));
  $("speed").addEventListener("click", () => act("speed", {}));
  $("kernel-direct").addEventListener("click", () => {
    const on = $("kernel-direct").getAttribute("aria-checked") !== "true";
    act("direct", { on }, $("kernel-direct"));
  });
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

  // Шлюзу: вкладка скрылась (окно свёрнуто, открыта другая вкладка) или закрылась. По этому
  // ярлык решает: вывести вперёд свёрнутое окно или сразу открыть новую вкладку.
  function tell(how) {
    fetch("/api/state", {
      cache: "no-store", credentials: "same-origin", keepalive: true,
      headers: { "X-XGW-Focus": how },
    }).catch(() => {});
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimeout(timer);
      if (!gone) tell("hidden");
    } else if (!gone) load().then(schedule);
  });
  window.addEventListener("pagehide", () => tell("closed"));
  // Окно вывели вперёд (ярлык, значок в трее) — данные сразу свежие, и шлюз узнаёт о фокусе.
  window.addEventListener("focus", () => {
    if (!gone && !document.hidden) load().then(schedule);
  });

  // --- одна вкладка панели ----------------------------------------------------
  // Вкладку на экране ярлык «XGW» и значок в трее выводят вперёд (KWin), а когда её не
  // видно — открывают панель через xdg-open, и браузер даёт новую вкладку. Новая (она уже
  // впереди и со свежими данными) закрывает прежние, и вкладка XGW всегда одна: вывести
  // вперёд скрытую вкладку браузер не даёт. Закрыть себя страница может, только если в
  // истории вкладки одна запись (так её и открывают ярлык и значок); иначе она гаснет и
  // просит закрыть её вручную. Из двух открытых разом остаётся новейшая.

  function leave() {
    gone = true;
    clearTimeout(timer);
    window.close();
    setTimeout(() => { // закрыть не дали
      // Не «XGW …» в начале: окно с таким заголовком ярлык выводил бы вперёд (tray.KWIN_SCRIPT).
      document.title = "Панель XGW открыта в другой вкладке";
      document.body.className = "login";
      document.body.replaceChildren(el("main", { class: "card login-card" },
        el("img", { src: "/icon.svg", alt: "", width: 56, height: 56 }),
        el("h1", { text: "Панель открыта в другой вкладке" }),
        el("p", { class: "muted", text: "Её открыли заново — ярлыком «XGW», значком в трее или по ссылке. Эту вкладку можно закрыть." })));
    }, 300);
  }

  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel("xgw-panel");
    const me = { at: Date.now(), id: Math.random() };
    channel.onmessage = (event) => {
      const other = event.data || {};
      if (gone || typeof other.at !== "number") return;
      if (other.at > me.at || (other.at === me.at && other.id > me.id)) leave();
    };
    channel.postMessage(me);
    window.addEventListener("pageshow", (event) => { // вернули из кэша «назад»
      if (!event.persisted || gone) return;
      me.at = Date.now();
      channel.postMessage(me);
    });
  }

  load().then(schedule);
})();
