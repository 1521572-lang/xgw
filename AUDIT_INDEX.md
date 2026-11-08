# AUDIT_INDEX.md — навигационная карта кода XGW для аудита

### 0. Метаданные

- Коммит: `b31f0dc2cdd01c7219f8fa57d888ec23e5037ec1` (ветка `freepool`, `origin/freepool`), карта составлена 2026-11-08.
- Стек: Python ≥ 3.11, только stdlib (`pyproject.toml:L1-L27`); точка входа CLI `xgw = xgw.cli:main` (`pyproject.toml:L20-L22`); GUI — Qt (`src/xgw/gui/`), веб-панель — свой HTTP-сервер (`src/xgw/watch/panel.py:L259-L372`).
- Прокси/VPN-ядра: **Xray-core** — основной, `/opt/xgw/xray`, юнит `xgw-xray.service`, управление `src/xgw/xraycore/service.py`, горячая правка через API-сокет (`src/xgw/generator/builder.py:L34-L40`, `src/xgw/xraycore/api.py`); **sing-box** — мосты для не-Xray протоколов, поколения blue/green через `systemd-run` (`src/xgw/apply/singbox_generation.py`, `src/xgw/apply/singbox_process.py`). Загрузка/обновление бинарников: `src/xgw/xraycore/binary.py:L135-L253`, `src/xgw/sbcore/binary.py:L55-L158`.
- Перехват трафика Ubuntu: nftables (TPROXY/TUN + независимый барьер `xgw_guard`), `ip rule`/`ip route`, dnsmasq (DHCP LAN), sysctl, ufw — всё в `src/xgw/net/`.
- Деплой: `packaging/install.sh:L10` → `python3 -m xgw install` → `src/xgw/install.py:L293-L675` (apt-пакеты, пользователи `xray`/`xgw-singbox`/`xgw-shadow`, юниты `packaging/xgw*.service`, nmcli LAN-профиль, sysctl, ufw, dnsmasq, первая сборка). Обновление демона — тот же установщик; обновление ядер — `xgw-core.service` → `src/xgw/cores.py:L196-L222`. Удаление: `src/xgw/uninstall.py:L65-L98`.
- Службы: `xgw.service` (демон), `xgw-net.service` (`xgw net up`, до network-pre), `xgw-xray.service`, `xgw-singbox.service`, `xgw-dhcp.service`, `xgw-core.service`, `xgw-fp@.service` (агенты бесплатного пула в PrivateNetwork).

### 1. Граф выполнения (Call Flow)

**1.1. Старт демона и инициализация сети**
- Загрузка ОС → `xgw-net.service` → `src/xgw/cli.py:main[L44-L330] -> src/xgw/cli.py:_cmd_net[L734-L778] -> src/xgw/net/capture.py:capture_for[L97-L100] -> src/xgw/net/capture.py:Capture.up[L785-L788] -> src/xgw/net/capture.py:Capture._load[L449-L518]` — ядро приведения сети.
- Внутри `_load`: `src/xgw/net/capture.py:Capture._prepare_tun[L404-L426] -> src/xgw/net/tun.py:ensure[L99-L112]` (создание TUN через `ip tuntap`); `src/xgw/net/capture.py:Capture._routes_up[L296-L314] -> src/xgw/net/iprule.py:ensure[L272-L291] / ensure_tun[L330-L342]` (ip rule + маршруты + blackhole); `src/xgw/net/nft.py:apply[L1149-L1171]` (обе таблицы nft одной транзакцией); `src/xgw/net/capture.py:_forwarding_on[L842-L848] / _congestion[L857-L880] -> src/xgw/net/sysctl.py:write[L79-L81]`; эталон правил — `src/xgw/net/capture.py:_baseline[L524-L553]`.
- Демон: `xgw.service` → `src/xgw/cli.py:_cmd_run[L834-L941] -> src/xgw/daemon.py:Daemon.__init__[L537-L929] -> src/xgw/daemon.py:Daemon.run[L930-L965] -> src/xgw/daemon.py:Daemon.tick[L1388-L1650]` (цикл watchdog, один шаг = один проход). Сверка правил каждый шаг: `src/xgw/daemon.py:Daemon._guard_capture[L2298-L2410]`. События сети будят демон: `src/xgw/watch/events.py:NetEvents[L116-L186]`.

**1.2. Генерация конфига и запуск/перезапуск ядра**
- `src/xgw/daemon.py:Daemon.tick[L1388] -> src/xgw/daemon.py:Daemon._refresh[L2465-L2487] -> src/xgw/daemon.py:Daemon._start_fetch[L2488-L2511]` (фоновый поток опроса подписок: `src/xgw/engine.py:collect[L212-L294] -> src/xgw/fetch.py:fetch_subscription[L277-L304]`, парсеры `src/xgw/parsers/`).
- Применение: `src/xgw/daemon.py:Daemon._refresh_done[L2512-L2555] -> _rebuild[L2644-L2694] -> _start_build[L2695-L2719]` (поток сборки: `src/xgw/engine.py:assemble[L513-L719] -> src/xgw/generator/builder.py:build[L662-L1043]` — конфиг Xray; `src/xgw/generator/singbox.py:build[L223-L318]` — конфиг sing-box; валидация бинарником: `src/xgw/generator/validate.py:_test_once[L74-L99]`, `src/xgw/generator/singbox.py:_check_once[L356-L382]`) `-> src/xgw/daemon.py:_finish_build[L2720-L2816] -> _apply[L2912-L2929] -> src/xgw/engine.py:apply_all[L1042-L1078]`.
- Xray: `src/xgw/apply/applier.py:Applier.apply[L97-L107] -> _apply_locked[L122-L190]` — либо план правок через API без рестарта, либо `src/xgw/apply/applier.py:_restart[L206-L212] -> _restart_and_wait[L229-L248] -> src/xgw/xraycore/service.py:SystemdXrayService[L49-L99]` (systemctl) или `PidfileXrayService.start[L229-L261]` (subprocess.Popen). Откат на last-good: `src/xgw/apply/applier.py:rollback[L108-L120] / _rollback[L249-L263]`.
- sing-box: `src/xgw/daemon.py:_apply_singbox[L5529-L5562] -> src/xgw/apply/singbox.py:SingboxCore.apply[L113-L143] -> src/xgw/apply/singbox_generation.py:prepare[L251-L310] / finish[L328-L357] -> src/xgw/apply/singbox_process.py:start[L68-L105]` (systemd-run с проверенным набором ограничений юнита), остановка `stop[L164-L175]`, восстановление поколений `recover[L378-L412]`.

**1.3. Цикл проверки узлов и переключение (failover)**
- Сбор сигналов: `src/xgw/daemon.py:Daemon.tick[L1414] -> _signals[L1652-L1750]` — метрики/API балансировщика, `src/xgw/daemon.py:_check_provider[L1920-L1936]`, сквозная проверка `_check_e2e[L1864-L1901] -> _e2e_get[L1902-L1913] -> src/xgw/watch/checks.py:http_get_via_proxy[L60-L193]`, утечка `_check_leak[L1956-L1961] -> src/xgw/watch/checks.py:trace_location[L526-L550]`.
- Вердикт о адресе проб: `src/xgw/daemon.py:_probe_target[L1985-L2064]` (`src/xgw/watch/target.py`). Машина состояний: `src/xgw/watch/states.py:StateMachine[L81-L111]`, значения `State[L26-L35]`.
- Замены: `src/xgw/daemon.py:_rotate[L3402-L3492]` (мёртвые → проверенные запасные) и `src/xgw/daemon.py:_rebalance[L3166-L3218]`; страж `_guard_step[L6479-L6530] -> _guard_episode[L6581-L6646] -> _guard_switch[L6667-L6710]`; основной сервер `_main_step[L5822-L5894] -> _choose_main[L5998-L6024] -> _promote[L6083-L6118]` — далее применяются цепочкой 1.2. Замеры скорости: `src/xgw/watch/speed.py:measure[L87-L121]`, сканы запасных `src/xgw/watch/scan.py:scan_node[L90-L140]`.
- Ядро не отвечает: `src/xgw/daemon.py:_handle_xray_down[L2216-L2243]` (systemd поднимет сам; после двух неудач — `src/xgw/apply/applier.py:rollback[L108]`, затем возврат версии ядра `src/xgw/daemon.py:_core_back[L5294-L5315]`). Утечка в домашнюю страну: `src/xgw/daemon.py:_handle_leak[L2245-L2274]` (смена сервера либо перезагрузка правил).

**1.4. Штатная и аварийная остановка**
- SIGTERM демону: `src/xgw/cli.py:L845-L847` (stop.set) → `src/xgw/daemon.py:Daemon.run[L963-L965]` (выход цикла, закрытие базы). Xray/sing-box останавливает systemd (KillMode=mixed, `packaging/xgw.service:L9-L11`).
- Снять перехват: `src/xgw/cli.py:_cmd_net[L763-L771] -> src/xgw/net/capture.py:Capture.down[L820-L841]` — `src/xgw/net/nft.py:delete[L1173-L1178]` (обе таблицы), `src/xgw/net/capture.py:_routes_down[L316-L334] -> src/xgw/net/iprule.py:remove[L293-L307] / remove_tun[L344-L366]`, возврат ip_forward/BBR `_forwarding_restore[L850-L855] / _congestion_restore[L882-L893]`. TUN оставлен (держит Xray); удаляет только uninstall: `src/xgw/net/tun.py:remove[L114-L119]`.
- Полное удаление: `src/xgw/uninstall.py:Uninstaller.run[L65-L98]` → `_stop_units[L105-L121]` → `_rules[L123-L131]` → `_dnsmasq[L132-L144] -> src/xgw/net/dnsmasq.py:restore_system[L86-L102]` → `_nm[L145-L166] -> src/xgw/net/nm.py:restore_lan[L230-L256] / restore_wan[L319-L339]` → `_sysctl[L167-L176] -> src/xgw/net/sysctl.py:restore[L140-L143]` → `_sleep[L177-L183] -> src/xgw/net/sleep.py:unmask[L52-L55]` → `_ufw[L184-L193] -> src/xgw/net/ufw.py:remove_tproxy_rule[L145-L159]` → юниты/пользователи/файлы.
- Сбой установки (первая установка): откат сетевой части `src/xgw/install.py:L640-L653` через Uninstaller; обновление поверх работающего шлюза не откатывается — `src/xgw/install.py:L627-L639`.

### 2. Индекс взаимодействия с ОС Ubuntu (System Touchpoints)

**Shell-команды и системные утилиты** (общий раннер: `src/xgw/net/cmd.py:run[L19-L44]`, argv-список, таймаут 15 с по умолчанию; `shell=True` в коде нет):
- `src/xgw/net/nft.py:L1141-L1178` — загрузка/удаление таблиц nft (ip, ip6, inet guard).
- `src/xgw/net/nft.py:L1200-L1236` — чтение листингов nft (сверка правил).
- `src/xgw/net/iprule.py:L145-L169, L190-L211, L226-L250, L281-L307, L330-L366, L380-L399` — ip rule/route add/del, локальная доставка, blackhole, чужие ранние правила.
- `src/xgw/net/tun.py:L50-L54, L78-L82, L99-L112, L114-L119` — ip link/tuntap/addr: создание и удаление TUN.
- `src/xgw/net/sysctl.py:L72-L81, L93-L143` — чтение/запись /proc/sys, файл в /etc/sysctl.d, возврат.
- `src/xgw/net/ufw.py:L36-L45, L57-L80, L117-L159` — статус ufw, свои правила, правка before.rules + reload.
- `src/xgw/net/dnsmasq.py:L86-L102` — остановка/отключение чужой службы dnsmasq; перезапуск своей `src/xgw/actions.py:L168-L171`.
- `src/xgw/net/nm.py:L66-L133, L165-L217, L230-L256, L273-L318` — nmcli: профили LAN/WAN, бэкап, восстановление.
- `src/xgw/net/sleep.py:L23-L55` — маскировка целей сна systemd (mask/unmask).
- `src/xgw/net/conncheck.py:L28-L31` — busctl: адрес проверки связности NetworkManager.
- `src/xgw/xraycore/service.py:L55-L99` — systemctl start/stop/restart/is-active xgw-xray.
- `src/xgw/apply/singbox_process.py:L68-L105, L107-L113, L164-L176, L184-L202` — systemd-run поколений sing-box, systemctl show/stop, уборка.
- `src/xgw/install.py:L685-L699, L701-L719, L721-L739, L740-L769, L919-L922, L1009, L1050-L1063, L1104-L1127, L1140-L1179, L1180-L1260, L1293` — apt-get, useradd/groupadd, systemctl enable/restart, sysctl, ufw, dnsmasq, юниты, первый запуск xgw-net.
- `src/xgw/uninstall.py:L105-L121, L203, L233, L272-L279` — остановка юнитов, daemon-reload, pkill трея, userdel.
- `src/xgw/cores.py:L196-L222` — запуск юнита обновления ядер; `src/xgw/diag.py:L248-L254, L366-L370, L427-L443, L480-L484, L594-L657, L683-L687, L814-L818, L888-L892, L953-L957, L1021-L1030, L1201-L1204, L1382-L1383` — диагностика: systemctl/journalctl/nft -c/unshare -n nft/ufw/ip.
- `src/xgw/tailscale.py:L139-L143, L179-L183, L212-L216, L228-L232, L258-L262, L301-L305, L345-L349, L374-L403` — CLI tailscale, чтение resolvectl.
- `src/xgw/freepool/backend.py:L131-L135, L160-L166, L195-L210, L225-L229, L261-L265, L284-L287, L305-L318, L329-L333` — veth/netns/юниты агентов пула, nft set пиров.
- `src/xgw/freepool/agent.py:L754-L760, L819-L823` — ip/nft внутри namespace агента.
- `src/xgw/watch/events.py:L29-L37, L118-L186` — постоянные подпроцессы ip monitor / busctl monitor / nft monitor.
- `src/xgw/watch/notify.py:L67-L78, L102-L106` — loginctl (оповещения сеанса).
- `src/xgw/usage.py:L94-L95, L268-L273` — своя таблица nft для учёта трафика.

**Сетевые интерфейсы, сокеты, метки, tproxy:**
- `src/xgw/net/tun.py:L31-L45, L99-L119` — постоянный TUN (tuntap, адрес 169.254.10.1/32, rp_filter).
- `src/xgw/net/nft.py:L276-L389, L516-L545` — сборка правил: TPROXY-метка, наборы direct4/direct_lan4/fp_peers, форвардинг и маскарад пула.
- `src/xgw/net/capture.py:L296-L334` — согласование ip rule с режимом (tproxy/tun).
- `src/xgw/marknet.py:L52-L90` — SO_MARK на сокетах самого шлюза (обход перехвата).
- `src/xgw/engine.py:L90-L101` — вычисление bypass-метки для запросов демона.
- `src/xgw/netcheck.py:L56-L145, L274-L428` — сырые UDP/STUN-сокеты, SOCKS-пробы (диагностика TSPU).
- `src/xgw/xraycore/api.py:L94-L100` — subprocess-обёртка gRPC-CLI к API-сокету Xray (`src/xgw/generator/builder.py:L34-L40`).

**Дочерние процессы:**
- `src/xgw/xraycore/service.py:L101-L158` — ProcessXrayService (стенд): Popen, чтение лога, смерть-сразу-после-старта.
- `src/xgw/xraycore/service.py:L187-L286` — PidfileXrayService: Popen `xray run -c` (L245-L258), stop SIGTERM → SIGKILL (L263-L280),_pid-файл.
- `src/xgw/apply/singbox.py:L174-L232, L250-L278` — установка конфига sing-box, reload/рестарт, alive.
- `src/xgw/apply/singbox_generation.py:L251-L357, L378-L446` — пара поколений: старт нового, проверка мостов, promote, retire.
- `src/xgw/generator/validate.py:L74-L99` / `src/xgw/generator/singbox.py:L356-L382` — `run -test`/`check` дочерним бинарником с таймаутом 60 с.
- `src/xgw/freepool/agent.py:L705-L760` — агент пула: словарь детей-Popen, reader-поток вывода sstpc/pppd.
- `src/xgw/freepool/probe.py:L202-L330` — spawn процессов проверки бесплатных серверов.
- `src/xgw/tray.py:L327-L330, L494-L498, L598-L602` — Popen GUI/браузера из трея; `src/xgw/watch/shadow.py:L84-L88` — изолированный браузер тени; `src/xgw/desktop.py:L68-L112` — запуск приложений сеанса.

**Конфигурационные файлы и секреты:**
- `/etc/xgw/config.toml` — `src/xgw/config.py:load[L581-L615]` (валидация `_validate[L932-L1113]`).
- `/etc/xgw/panel.json` (подписки с URL и заголовками, устройства, режимы) — `src/xgw/managed.py:_update[L70-L90]` под файловой блокировкой, проверка URL `check_url[L671-L685]`, очистка заголовков `_clean_headers[L691-L719]`; вбрасывание идентификатора `happ_preset[L742-L753]` (значение из `gateway_hwid[L721-L731]`).
- `/var/lib/xgw/state.db` (SQLite: события, кэш подписок с их URL) — `src/xgw/store.py:Store[L62-L252]`.
- `/etc/xgw/xray/config.json`, pending, last-good, api-dirty — `src/xgw/paths.py:L65-L118`, запись `src/xgw/paths.py:atomic_write_bytes[L247-L290]` (0600/0640), смена `src/xgw/apply/applier.py:_promote[L275-L286]`, сохранение сборки `src/xgw/engine.py:persist[L937-L989]`; в конфиге ключи серверов — маскирование логов `src/xgw/masking.py`, регистрация секретов `src/xgw/cli.py:L932-L933`.
- `/etc/xgw/sing-box/config.json` и файлы поколений — `src/xgw/apply/singbox_process.py:config_write[L61-L66]` (права, chown), каталоги поколений `src/xgw/apply/singbox_generation.py:L251-L310`.
- `/etc/xgw/dnsmasq.conf` — `src/xgw/net/dnsmasq.py:write_conf[L54-L74]`, render `render[L149-L205]`; аренды `/var/lib/xgw/dhcp.leases` `read_leases[L103-L123]`.
- `/var/lib/xgw/capture.json` (состояние перехвата, сохранённые значения sysctl) — `src/xgw/net/capture.py:_state[L185-L199]`.
- `/run/xgw/status.json` — `src/xgw/watch/status.py:write_status[L798-L800]`, сборка `collect_status[L435-L742]`; шаги цикла `src/xgw/daemon.py:_loop_progress[L967-L979]`.
- `/etc/ufw/before.rules` — `src/xgw/net/ufw.py:L117-L159` (текстовая правка, бэкап).
- `/etc/sysctl.d/90-xgw.conf` — `src/xgw/net/sysctl.py:install[L93-L131]`.
- Бинарники ядер `/opt/xgw/{xray,sing-box}` — `src/xgw/xraycore/binary.py:L135-L253` (sha256), `src/xgw/sbcore/binary.py:L55-L158`, `src/xgw/cores.py:L350-L416`.

### 3. Реестр подозрительных мест (Suspect Registry)

**Конкатенация при формировании команд/конфигов:**
- `src/xgw/net/nft.py:L1146-L1171` — правила nft собираются текстом из config.toml (имена интерфейсов, сети); санитизация имён только в `src/xgw/net/lan.py:L31-L37` — проверить все пути поступления.
- `src/xgw/net/dnsmasq.py:L149-L205` — конфиг dnsmasq рендерится из имён устройств/хостов аренд (валидация `src/xgw/net/lan.py:L50-L53` — проверить полноту).
- `src/xgw/freepool/backend.py:L160-L166` — элемент nft set собирается строкой из данных аренды пула.
- `src/xgw/net/ufw.py:L117-L144` — текстовая вставка в чужой `/etc/ufw/before.rules` (маркер и бэкап есть; сбой между atomic_write и `ufw reload` оставляет правила неприменимыми).
- `src/xgw/watch/panel.py:L259-L372` + `src/xgw/managed.py:L687-L719` — пользовательские строки (имена подписок, заголовки) попадают в panel.json и далее в запросы/конфиги; очистка есть, проверить каждый потребитель.
- Нигде не используется `shell=True`; все вызовы — argv-списки через `src/xgw/net/cmd.py:L19-L44-L44` (проверено grep).

**Голые try/except и проглоченные ошибки (особенно сеть):**
- `src/xgw/daemon.py:L939-L941` — весь `tick()` под blanket `except Exception` (демон живёт, но причина шага видна только в журнале).
- `src/xgw/daemon.py:L2268-L2270, L2294-L2296, L2383-L2409` — переприменение правил перехвата под broad except; при повторном сбое барьер `xgw_guard` может остаться в состоянии unknown/failed.
- `src/xgw/net/iprule.py:L233-L235` — `early()` глотает CommandError (чужие правила не замеченными остаются).
- `src/xgw/engine.py:L736-L738, L756-L758, L775-L777, L983-L985` — чтение базы рейтинга/состояния под `except Exception` — тихая деградация выбора серверов.
- `src/xgw/apply/singbox_generation.py:L306-L310` — `except BaseException` в отмене поколения (проверить, что не гасит Ctrl-C некорректно).
- `src/xgw/net/tun.py:L109-L111` — suppress OSError на rp_filter интерфейса (тестовый /proc; на реальной машине скрывает отказ).
- `src/xgw/daemon.py:L1078-L1101, L6429-L6433` — `_restore_tun`/учёт под broad except — сбой восстановления TUN не прерывает работу.
- `src/xgw/net/capture.py:L842-L848` — `_forwarding_on` пишет ip_forward без отлова OSError внутри `_load` (поймается выше как CaptureError — проверить порядок: правила уже загружены).

**Глобальное состояние из разных потоков:**
- `src/xgw/daemon.py:L2488-L2511, L2695-L2719, L2787-L2789` — фоновые потоки (подписки, сборка, подготовка поколения) и поток tick делят `self._fetch`/`self._build`: защита — deepcopy входов (L2700-L2703) и Event/Lock у `_Fetch` (`src/xgw/daemon.py:L486-L500`), у `_Build` lock нет — проверить гонку чтения `job.assembly`.
- `src/xgw/daemon.py:L1703-L1709, L1835-L1848` — conncheck-поток пишет `self._conncheck_found`, tick забирает; синхронизация только GIL.
- `src/xgw/daemon.py:L587-L591, L694-L697, L5335-L5338, L5373-L5376` — потоки freepool/cores/netmon; результаты передаются файлами/полями Daemon — проверить барьеры записи.
- `src/xgw/watch/panel.py:L322-L372` — панель (поток HTTP-сервера) вызывает действия над демоном и `capture` без общей блокировки с потоком tick (действия идут через `src/xgw/actions.py` и wake).
- `src/xgw/freepool/agent.py:L722-L734` — `children`/`state`/`log` агента трогают основной цикл и reader-поток без lock.
- `src/xgw/managed.py:L70-L90` — panel.json: несколько писателей, есть file_lock (образец корректности; сверять с ним остальные).

**Отсутствие таймаутов / ожидание завершения:**
- `src/xgw/tray.py:L327-L330, L494-L498, L598-L602` — Popen GUI/браузера без wait/таймаута (потенциальные зомби).
- `src/xgw/watch/events.py:L118-L186` — мониторные Popen живут без таймаута (по конструкции); stop даёт 0,5 с — проверить потерю событий при остановке.
- `src/xgw/xraycore/service.py:L245-L261` — ожидание смерти Xray после старта — 1 с поллинг (короче grace; смерть позже не замечается до systemd).
- Основные сетевые пути таймауты имеют: `src/xgw/net/cmd.py:L19-L44` (15 с), `src/xgw/fetch.py:L30-L31, L195-L268`, `src/xgw/watch/checks.py:L23-L24, L60-L93`, `src/xgw/netcheck.py:L50-L51`, `src/xgw/generator/validate.py:L83-L87`, `src/xgw/xraycore/api.py:L94-L100` — проверить только вызовы с `check=False` на ожидаемость кода.

**Падение оставляет хост без интернета или с пробитым kill-switch:**
- `src/xgw/net/iprule.py:L330-L342, L380-L390` — blackhole default (metric 4096) в таблице TUN: при исчезновении TUN-интерфейса помеченный трафик машины/контейнеров уходит в чёрную дыру; демона нет — правила не убираются до перезагрузки (это и есть kill-switch; проверить восстановление `restore_tun` `src/xgw/net/capture.py:L693-L718` и юнита `xgw-xray.service` ExecStartPost `xgw net tun`).
- `src/xgw/net/capture.py:L820-L841` — `down()`: между `nft.delete` и `_routes_down` сбой оставляет ip rule/маршруты, ведущие в никуда (частичный демонтаж).
- `src/xgw/net/capture.py:L449-L518` — `_load`: при ошибке после `_routes_up`, но до применения nft — метки ставятся без потребителя; порядок операций продуман, проверить все исключения между шагами.
- `src/xgw/net/sleep.py:L44-L55` — mask целей сна: падение между mask и unmask (unmask только в uninstall) оставляет хост, который не засыпает.
- `src/xgw/install.py:L627-L653` — сбой обновления поверх работающего шлюза: откат сознательно не выполняется — возможна наполовину перенастроенная сеть (решение задокументировано в коде).
- `src/xgw/daemon.py:L2216-L2243` — `_handle_xray_down`: повторные `service.start()` без счётчика предела при постоянно падающей службе (защита restart_pending есть — проверить StartLimitBurst).
- `src/xgw/net/nft.py:L1162-L1171` — при сбое загрузки IPv6-таблицы fallback грузит только IPv4+guard: если `capture6`/`v6_guard` определены неверно, IPv6-трафик уйдёт мимо VPN (условие отбора — то самое).
- `src/xgw/watch/panel.py:L259-L372` + `src/xgw/actions.py:L160-L175` — действия панели (перезапуск dnsmasq, смена правил) исполняются от root в потоке панели: сбой посередине оставляет несогласованные правила/DHCP.

**Панель/привилегии (дополнительно для приоритетной проверки):**
- `src/xgw/watch/panel.py:L259-L372` — root HTTP-сервер (cookie-аутентификация); обработчики исполняют системные действия от root — границы входа.
- `src/xgw/managed.py:L671-L685` — проверка URL подписки (scheme/host) — единственный барьер перед fetch от имени демона.
