# ThinkCentre: микрофрагментация, UDP noise и nfqws2 — приёмка на реальной машине

Исполнитель — модель на реальном Linux-шлюзе. Проверяется только код коммита CODE ниже.
Версия XGW остаётся 0.2.0. Ветка публикации — `gui-light`.

CODE = `eb47e83270cabe4b8dec9852eb9708d4a08f9266`.
BASE = `97af08130321318241be3afc5c54bc8e85b7e273` — только для сравнения старых падений тестов
и отката, не признак того, что на машине установлен именно этот коммит.

Цель — проверить фактическую работу доработок на Xray-core 26.10.21, sing-box, nftables и
nfqws2, а не только чтение JSON. Отдельно принимаются:

1. микрофрагментация Xray и одновременное TLS record/TCP fragmentation в sing-box;
2. режимы QUIC `reject/noise/proxy`, Xray UDP `noises`, Cloudflare/Discord/STUN-маршруты;
3. настраиваемые reserved CIDR, STUN и DNS `queryStrategy`;
4. восстановление `ip xgw` и `inet xgw_guard` после внешнего удаления правил;
5. безопасный запуск nfqws2, NFQUEUE с `bypass`, anti-loop и отсутствие рестарта Xray;
6. три L3/L4-профиля, offload, отказы worker и эскалация по вердиктам сканера;
7. штатный Xray + sing-box + nftables без nfqws2.

HTTP 2xx не доказывает обход DPI, воспроизведение видео или невидимость. Прямой трафик и fake
могут раскрывать домашний IP. Не заявлять победу над ТСПУ без фактического успешного сценария.

## 0. Границы и безопасность

Работать на Ubuntu 26.04 amd64 с локальным доступом к консоли. Не начинать разрушительные сетевые
проверки через единственное SSH-соединение. Не менять WAN, LAN, DHCP, Tailscale, подписки, пул,
ручной выбор и закрепление серверов. Не использовать `git reset --hard`, force push, `xgw net down`,
перезагрузку или остановку сторонних firewall/сервисов.

До каждого действия из списка получить отдельное явное согласие владельца:

- установка/замена кода и перезапуск служб XGW;
- скачивание или установка nfqws2/Lua/blob и любых пакетов;
- временный прямой выход, UDP fake и запуск nfqws2;
- остановка тестового worker и занятие тестовой NFQUEUE;
- отключение offload на WAN;
- удаление таблиц XGW и особенно `nft flush ruleset`.

Скачивание ничего не требуется для шагов 1–7. Не запускать `install_easy.sh`, общий unit zapret2,
`blockcheck` или внешние сценарии настройки firewall. Не смешивать бинарник и Lua разных выпусков.

Все приватные файлы — только под `umask 077`. В отчёт не включать URL подписок и проб, IP/домены и
имена серверов, теги, SNI, UUID/ключи, short_id, MAC, сырой JSON, конфиги, pcap, снимки экрана и
приватные журналы. Разрешены числа, коды состояний, версии, PASS/FAIL/NOT_RUN и обезличенные причины.

Статусы: PASS — ожидание выполнено; FAIL — фактическое несоответствие; BASELINE_FAIL — то же
падение воспроизведено на BASE; NOT_RUN — нет условия или согласия; PARTIAL — часть обязательных
проверок не выполнена. Не превращать NOT_RUN в PASS.

## 1. Зафиксировать исходники

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin gui-light
CODE=eb47e83270cabe4b8dec9852eb9708d4a08f9266
BASE=97af08130321318241be3afc5c54bc8e85b7e273
git cat-file -e "$CODE^{commit}"
git cat-file -e "$BASE^{commit}"
umask 077
D=$(mktemp -d "$HOME/xgw-desync-test.XXXXXXXX")
TARGET="$D/new"
PREV="$D/base"
git worktree add --detach "$TARGET" "$CODE"
git worktree add --detach "$PREV" "$BASE"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$CODE"
test "$(git -C "$PREV" rev-parse HEAD)" = "$BASE"
test -z "$(git -C "$TARGET" status --porcelain)"
printf 'D=%s\n' "$D"
```

Если основной репозиторий содержит неизвестные изменения — не удалять и не сбрасывать их; записать
STOP dirty_tree. Работать только из TARGET/PREV. Не брать более новый HEAD и не менять код в этом ТЗ.

Проверить, что в CODE есть `src/xgw/nfqws2.py`, `tests/test_nfqws2.py`, а `pyproject.toml` по-прежнему
содержит `dependencies = []` и `requires-python = ">=3.11"`. Иное — STOP wrong_code.

## 2. Инструменты и исходное состояние

Только чтение:

```bash
python3 --version
python3 -c 'import sys; assert sys.version_info >= (3, 11)'
command -v unshare
command -v nft
command -v systemctl
command -v ip
command -v ethtool || true
command -v curl || true
sudo xgw status --json >"$D/status-before.json"
sudo xgw diag --no-net >"$D/diag-before.txt" 2>&1; diag_before_rc=$?; printf 'diag_before_rc=%s\n' "$diag_before_rc"
sudo systemctl is-active xgw.service xgw-xray.service
sudo systemctl show xgw-xray.service -p MainPID --value >"$D/xray-pid-before"
sudo nft list tables >"$D/tables-before.txt"
sudo nft list ruleset >"$D/firewall-before.nft"
sudo cp -a /etc/xgw/config.toml "$D/config-before.toml"
sudo cp -a /opt/xgw/lib/xgw "$D/lib-before"
sudo nft list chain inet xgw_guard nfq_output >"$D/nfq-before.txt" 2>&1 || true
```

Записать версию Python, наличие инструментов, состояние capture/lifecycle, числа OK/WARN/FAIL diag,
есть ли nfqws2 и активный `xgw-nfqws2.service`. Сырые файлы не публиковать. Если демон или Xray не
работают, capture не `on`, конфиг не читается либо уже есть неизвестный NFQUEUE worker — STOP до
установки. Старые WARN не считать новым дефектом, но зафиксировать их число.

Проверить наличие nfqws2 во всех местах автопоиска: настроенный `zapret2.binary`, переменная
`XGW_NFQWS2_BIN`, `/opt/xgw/zapret2/*/nfqws2`, `/usr/local/sbin`, `/usr/sbin`, PATH. Не переименовывать
чужой бинарник ради сценария «отсутствует».

## 3. Тесты исходников без изменения системы

Обязательный минимальный набор на stdlib:

```bash
cd "$TARGET"
PYTHONPATH=src python3 -m unittest discover -s tests -p test_nfqws2.py -v
python3 -m compileall -q src/xgw tests/test_nfqws2.py
python3 -c 'import tomllib; tomllib.load(open("config.example.toml", "rb")); print("TOML OK")'
```

Ожидаются `Ran 5 tests` и `OK`, rc0 compileall и `TOML OK`. Любая ошибка — STOP до установки.

Если pytest уже установлен, без установки зависимостей выполнить:

```bash
PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_nfqws2.py tests/test_config.py tests/test_fragment.py tests/test_generator.py \
  tests/test_singbox.py tests/test_nft.py tests/test_profile_memory.py \
  >"$D/pytest-target.txt" 2>&1; target_rc=$?; printf 'target_rc=%s\n' "$target_rc"
PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
  >"$D/pytest-full.txt" 2>&1; full_rc=$?; printf 'full_rc=%s\n' "$full_rc"
```

Новый FAIL — STOP. Для отличия старого дефекта повторить ровно тот же набор из PREV и сравнить список
упавших тестов, не только их число. Если pytest отсутствует — NOT_RUN pytest, не ставить пакеты без
отдельного согласия. Это не отменяет обязательный unittest выше.

## 4. Установка с выключенным универсальным движком

До установки приватно сохранить текущие значения всех изменяемых настроек. В существующей секции
`[zapret2]` задать `engine = "off"`; не создавать вторую секцию и не менять старый `mode`. Если
старый код предупреждает о неизвестном ключе, это ожидаемо до обновления, не повод включать движок.

Получить согласие на установку CODE и перезапуск служб штатным установщиком. Затем:

```bash
cd "$TARGET"
sudo sh packaging/install.sh --yes
sudo xgw status --json >"$D/status-installed-off.json"
sudo xgw diag --no-net >"$D/diag-installed-off.txt" 2>&1; diag_rc=$?; printf 'diag_rc=%s\n' "$diag_rc"
sudo systemctl is-active xgw-nfqws2.service 2>&1 || true
sudo xgw net show >"$D/rules-installed-off.nft"
sudo unshare -n sh -c 'ip link set lo up; nft -c -f "$1"' sh "$D/rules-installed-off.nft"
```

`nft -c` выполнять только в новой network namespace: dry-run против активных таблиц хоста не нужен.
Если `unshare -n` недоступен, вместо него выполнить `sudo xgw net up`, затем проверить фактические
таблицы через `nft list`; live-применение требует согласия на установку и capture. Не отправлять
сгенерированный текст в `nft -f` без штатного `xgw net up`/`enable`.

Норма: установка rc0, capture/lifecycle восстановились, новых FAIL нет, Xray отвечает, HTTPS у
владельца работает, nfqws2 не запущен, в сгенерированных правилах нет цепочки `nfq_output`.
Наблюдать 5 минут обычной работы. PID Xray при установке может штатно измениться; зафиксировать факт,
не выдавать это за отказ горячей смены профиля.

При неуспехе не импровизировать: сохранить коды, остановить тестирование и с согласия владельца
вернуть установленный пакет из PREV тем же установщиком либо восстановить файлы из `lib-before`.
Восстановить работоспособность до продолжения других задач.

## 5. Генерация Xray и sing-box на реальных ядрах

При `zapret2.engine=off` и прежнем QUIC-режиме:

```bash
sudo xgw generate --out "$D/base.json"
```

Команда должна выполнить настоящий `xray run -test`; если создан `$D/base.singbox.json`, также должен
пройти настоящий `sing-box check`. `NOT_RUN binary_missing` допустимо только при фактически
отсутствующем ядре; на целевом стенде Xray 26.10.21 обязателен.

Проверить приватно, печатая только OK:

```bash
sudo python3 - "$D/base.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1], encoding="utf-8"))
out = {o.get("tag"): o for o in c["outbounds"]}
assert out["fragment"]["settings"]["fragment"] == {
    "packets": "tlshello", "length": "5-20", "interval": "5-15"}
assert out["split"]["settings"]["fragment"] == {
    "packets": "1-3", "length": "10-30", "interval": "5-10"}
rules = c["routing"]["rules"]
cf = next(r for r in rules if r.get("network") == "tcp"
          and r.get("port") == "2053,2083,2087,2096,8443")
assert cf.get("balancerTag") == "auto"
assert rules[-1].get("balancerTag") == "auto"
print("OK xray fragment/split/cloudflare")
PY
```

Если существует sing-box JSON, проверить каждый TLS-блок вариантов `f` и `m`: `record_fragment=true`,
`fragment=true`, `fragment_fallback_delay="30ms"`. У варианта `d` этих полей быть не должно. Проверить
и основной outbound, и `detour`/extra TLS-блоки. Если ни один сервер не поддерживает sing-box TLS,
записать NOT_RUN singbox_live_config, не создавать фиктивный сервер.

Для DNS при текущем `query_strategy="auto"`: без IPv6-проксирования ожидается `UseIPv4`, с ним —
`PreferIPv4`. Дополнительно без apply сгенерировать конфиги с явными `UseIPv4`, `PreferIPv4`, `AsIs`
и проверить точное поле `dns.queryStrategy`. После каждого изменения конфигурация должна читаться без
новых предупреждений. Вернуть исходное значение.

## 6. Живая проверка фрагментации

Сначала выполнить 5 обычных проб выбранного рабочего сервера через `sudo xgw probe <тег>` и записать
только вердикты, байты и медиану времени; тег в отчёт не переносить.

С отдельным согласием временно установить `[fragment] mode="always"`, сохранив остальные параметры,
выполнить `sudo xgw apply --now`, дождаться применения и повторить те же 5 проб. Норма: нет новых
CONNECT_FAIL/TIMEOUT, HTTPS работает на шлюзе и у клиента LAN. Разница задержки записывается как
наблюдение, жёсткого порога нет. Вернуть исходный `fragment.mode` и применить.

Если доступны tcpdump и локальная консоль, отдельно согласовать короткий приватный захват только одного
тестового TLS-соединения на WAN. Подтвердить ClientHello больше 1460 байт и дробление начала TLS,
учитывая, что TSO/GSO могут скрывать реальные сегменты на снимке хоста. Не писать собственный
обработчик пакетов и не публиковать pcap. Без захвата результатом является только config_and_xray_test,
а не доказанный разрыв SNI/PQ ClientHello.

Для sing-box проверить живой TLS только если соответствующий вариант реально выбран штатным профилем.
Не менять pin ради теста. Иначе NOT_RUN singbox_live_tls при пройденном `sing-box check` выше.

## 7. QUIC, UDP noises и дополнительные маршруты

Все четыре комбинации проверить сначала через `xgw generate` и `xgw net show`, без apply:

| block_quic | quic_mode | Ожидание |
|---|---|---|
| true | `""` | reject, обратная совместимость |
| false | `""` | proxy, без reject и direct-noise |
| true | `"noise"` | noise имеет приоритет, reject отсутствует |
| true | `"proxy"` | proxy имеет приоритет, reject отсутствует |

Для `reject` в nft должен быть прежний UDP/443 reject. Для `noise` его быть не должно; Xray должен
содержать `direct-noise` с числом элементов `settings.noises`, равным `noise_count`, и каждый элемент
`{"type":"rand","packet":"64-1200","delay":"5-15"}` при дефолтах. Отдельное UDP-правило должно
содержать ровно активные порты 443, Discord `19294-19344,50000-50100` и порты настроенных STUN.
Для `proxy` ни `direct-noise`, ни его UDP-правила быть не должно. Во всех режимах catch-all остаётся
последним, а Cloudflare TCP-правило стоит перед ним.

Проверить валидацию только копии через `PYTHONPATH="$TARGET/src" python3` и
`xgw.config.load(копия)`, не применяя её и не перенося `panel.json`: `noise_count=1` и `5`
заменяются на 3, неверные диапазоны packet/delay — на дефолты, неизвестный `quic_mode` — на
совместимость с `block_quic`, плохие CIDR/порты/STUN пропускаются с предупреждением. Проверить
значения assertions; предупреждения записать кодами, не копировать приватные значения.
При смене DNS/CIDR/STUN в живом конфиге также сохранить соседний `panel.json`: `generate` читает его
вместе с TOML. Не менять управляемые панелью поля.

После согласия на живой UDP применить `noise`. Выполнить доступные реальные сценарии:

- HTTP/3 на шлюзе через curl только если `curl -V` действительно показывает HTTP/3;
- HTTPS/QUIC у клиента LAN по выбору владельца;
- Discord Voice: подключение и двусторонняя речь, отдельно шлюз/LAN по наличию клиента;
- `sudo xgw diag --netcheck`: STUN/UDP и остальные проверки сравнить с исходными;
- обычный TCP HTTPS и VPN одновременно продолжают работать.

Отсутствие HTTP/3-клиента или Discord — NOT_RUN соответствующей части. Не ставить браузер/curl ради
этого ТЗ. Не называть decoy успешными только по наличию исходящих UDP-пакетов: нужен ответ/рабочий
сценарий. После проверки вернуть исходный QUIC-режим и подтвердить возврат правил.

Cloudflare-порты проверить живым HTTPS только к известному владельцу endpoint, который действительно
слушает выбранный порт. Не считать timeout произвольного адреса дефектом маршрутизации.

## 8. Reserved CIDR, STUN и восстановление nftables

Сгенерировать правила с дефолтными `capture.reserved_cidrs` и с одной документационной тестовой сетью
`198.51.100.0/24` без apply. В обеих генерациях обязаны сохраняться `127.0.0.0/8` и `::1/128`; в
тестовой генерации дополнительно должна появиться указанная сеть. Проверить `nft -c` только в
`unshare -n`, как в шаге 4. Затем вернуть исходный список и перезагрузить штатные правила через
`sudo xgw net up`, если capture включён. Живую доступность частной сети проверять только к
существующему ресурсу владельца.

Изменить `network.stun_servers` на уже доступный владельцу endpoint, выполнить generate/netcheck и
проверить, что используются только его порт и адрес. Если своего STUN нет, оставить дефолты; проверка
настраиваемого endpoint — NOT_RUN. Не добавлять публичные адреса в отчёт.

Перед удалением правил сохранить полный `nft list ruleset`, получить отдельное согласие и заранее
согласовать восстановление каждого стороннего firewall его родным средством (`iptables-restore`,
`nftables.service`, NetworkManager и т. п.). Не выполнять `nft -f firewall-before.nft`: снимок не
является безопасной транзакцией восстановления. Если есть не-XGW таблицы и нет проверенного способа
их вернуть — live flush NOT_RUN. Не выполнять по удалённому SSH без локальной консоли.

Сначала при capture on и `zapret2.engine=off` с согласия удалить только таблицы XGW:

```bash
sudo nft delete table ip xgw
sudo nft delete table inet xgw_guard
```

В течение 90 секунд демон должен сам восстановить обе таблицы без ручного `xgw net up` и без рестарта
Xray. Проверять `nft list table`, `xgw status --json`, HTTPS на шлюзе/LAN каждые 5 секунд. Записать
время восстановления и отсутствие новых FAIL.

Затем, только при локальной консоли и отдельном согласии, выполнить один:

```bash
sudo nft flush ruleset
```

Ожидание то же: XGW восстанавливает `ip xgw` и `inet xgw_guard`, capture возвращается в рабочее
состояние, fail-closed не остаётся долговременно открытым. Восстановить сторонние таблицы строго по
заранее согласованному плану; повторный flush для этого не делать. Сравнить итоговый набор таблиц с
исходным. Любая потеря связи — прекратить испытания и восстанавливать систему, не ждать следующего шага.

## 9. Подготовка nfqws2

Сначала убедиться, что старый `[zapret2] mode` — `off`: selective/compare и универсальный engine не
должны работать одновременно. Сохранить значения `binary`, `lua_dir`, `queue_num`, engine-настроек.

Если nfqws2/Lua уже установлены, использовать один существующий официальный комплект. Иначе показать
владельцу точный release/commit bol-van/zapret2, архитектуру, пути и SHA-256; скачивать только после
согласия. Не собирать и не ставить зависимости молча. Допустим штатный комплект
`/opt/xgw/zapret2/1.0.7` либо существующие явные `binary/lua_dir`.

Требования: исполнимый nfqws2, `zapret-lib.lua`, `zapret-antidpi.lua`; файлы и все родительские
каталоги принадлежат root и не доступны на запись группе/остальным. TLS/QUIC blob должны быть
встроенными либо найденными движком; внешний `stun.bin` нужен только для STUN fake. Зафиксировать
версию и хеши приватно. Проверить `nfqws2 --version`; штатный dry-run XGW с `--intercept=0` выполняется
при первом старте и не должен приводить к отправке пакетов.

Проверить `sudo cat /proc/sys/net/netfilter/nf_conntrack_acct`: при выключенном accounting
`ct packets` может не считать пакеты. Если значение не `1`, получить отдельное согласие на временное
`sudo sysctl -w net.netfilter.nf_conntrack_acct=1` для теста и записать исходное значение. Не менять
постоянные sysctl в этом ТЗ. Если владелец не согласен — NFQ packet-limit live test NOT_RUN, общий
итог не выше PARTIAL; наличие строк `ct packets` в тексте правил само по себе PASS не доказывает.

Убедиться, что очередь 200 свободна и нет чужого listener. Чужую очередь не останавливать; при занятости
выбрать свободный `engine_queue` и использовать его во всех последующих проверках.

## 10. Запуск, NFQUEUE и три профиля

Задать:

```toml
[zapret2]
engine = "auto"
engine_profile = "seqovl"
engine_queue = 200
engine_offload = true
```

Не перезаписывать этим фрагментом другие поля секции. Дождаться шага демона. Сохранять PID Xray до
каждой смены профиля и сравнивать после.

```bash
sudo xgw status --json >"$D/nfq-active.json"
sudo systemctl is-active xgw-nfqws2.service
sudo nft list chain inet xgw_guard nfq_output >"$D/nfq-output.txt"
sudo cat /proc/net/netfilter/nfnetlink_queue >"$D/queues-active.txt"
```

В JSON ожидается `capture.nfqws2.state="active"`, profile `seqovl`, выбранный queue. В nft обязательны:

- `queue num N bypass`;
- `ct packets <= 8` для TCP и `<= 4` для UDP;
- anti-loop `meta mark & 0x40000000 == 0x40000000 return`;
- разрешение той же метки в egress guard после loopback-проверок;
- очередь для точного `mark_bypass` и, при наличии sing-box, его UID;
- исключения local/reserved/loopback;
- отсутствие правила, отправляющего неограниченный объём соединения в userspace.

Проверить новые TCP HTTPS-соединения Xray, обычный direct по уже существующему правилу владельца и
sing-box, если он реально используется. LAN проверить отдельно. UDP 443/Discord/STUN — по условиям
шага 7. Нет direct/sing-box пути — NOT_RUN, не добавлять новый маршрут ради проверки.

Для каждого доступного пути до/после соединения сравнить приватно `nft list chain` и поля очереди в
`/proc/net/netfilter/nfnetlink_queue`: должны увеличиться счётчик пакетов именно целевого правила и
приватная статистика очереди. Один только active worker и HTTP 200 не доказывают попадание в NFQUEUE.
При отсутствии роста записать FAIL nfq_path_not_observed, указать протокол/путь без адресов, и не
продолжать DPI effectiveness по этому пути. Для direct обязательно подтвердить, что используется
именно существующий direct-выход Xray: если фактически пакеты выходят с меткой Xray bypass, записать
FAIL direct_not_covered, а не PASS.

По очереди задать `engine_profile` = `hostfakesplit`, затем `disorder-badseq`, затем снова `seqovl`.
После каждого изменения дождаться active и проверить:

1. transient unit жив, очередь та же, `capture.nfqws2.profile` изменился;
2. PID nfqws2 сменился при смене профиля, PID Xray — нет;
3. новые TLS/HTTPS-соединения работают либо честно зафиксирован отказ профиля;
4. в приватном `/proc/<nfq-pid>/cmdline` присутствуют аргументы именно выбранного профиля:
   - seqovl: `multisplit:pos=2,sniext+1:seqovl=679`;
   - hostfakesplit: fake `tls_mod=rnd,dupsid,sni=www.google.com:tcp_ts=+100` и
     `hostfakesplit:host=www.google.com:altorder=1:tcp_ts=+100`;
   - disorder-badseq: fake с `tcp_seq=-10000` и `multidisorder:pos=1,midsld`;
   - во всех: `--fwmark=0x40000000`, выбранный `--qnum`, оба Lua-init и UDP fake.

До `disorder-badseq` сохранить `ethtool -k <WAN>` приватно. При активном профиле включённые ранее
`generic-receive-offload`, `generic-segmentation-offload`, `tcp-segmentation-offload` и
`tx-checksum-ip-generic` должны быть выключены. После ухода с профиля либо `engine=off` каждое поле
должно вернуться к исходному состоянию, а не безусловно включиться. Сравнить весь снимок offload.
Отдельно проверить восстановление после перезапуска только `xgw.service`, если владелец согласен:
значения до запуска профиля и после окончательного выключения обязаны совпасть.

Не интерпретировать успешный HTTPS как доказательство конкретного seqovl/badseq на проводе без pcap.
Отдельно записать config/runtime PASS и DPI effectiveness PASS/NOT_RUN.

## 11. Отказы и fail-open

Все действия ниже — с согласия, по одному, с восстановлением перед следующим.

### 11.1. Остановка worker

При active выполнить `sudo systemctl stop xgw-nfqws2.service` и сразу открыть новые TCP/UDP-соединения.
Благодаря `queue ... bypass` трафик не должен встать до следующего шага демона. Демон обязан заметить
отказ и заново запустить worker с тем же профилем; Xray не перезапускается. Записать время восстановления.
Если вместо перезапуска получен fallback, проверить доступность трафика и причину по журналу; это не PASS
автоматического восстановления.

### 11.2. Занятая очередь

Выключить engine и дождаться остановки штатного worker. Выполнить `sudo xgw enable`, затем проверить,
что `nfq_output` удалена. Запустить отдельный тестовый listener той же очереди через transient unit
`xgw-test-queue-busy.service` из проверенного nfqws2 с `--qnum=N`, без Lua/desync и без сетевых проб;
проверить listener по `/proc/net/netfilter/nfnetlink_queue`. Включить engine auto и снова применить
`sudo xgw enable`, чтобы появилась NFQUEUE при включённом capture. Ожидается
`capture.nfqws2.state="fallback"`, reason `queue_busy`; XGW не должен убивать чужой listener или
менять Xray. Остановить именно `xgw-test-queue-busy.service`, дождаться штатного active. Не
отправлять трафик в заведомо занятую тестовую очередь.

### 11.3. Небезопасные файлы

Не менять права установленного комплекта. Сделать приватную копию nfqws2 и двух Lua в D, оставить
бинарник исполнимым, намеренно разрешить группе запись одного Lua, направить `binary/lua_dir` на копию.
Ожидается fallback `unsafe_files` или `unsafe_directory` до запуска worker. Восстановить исходные пути
и дождаться active. Скопированные исполняемые файлы не оставлять доступными другим пользователям.

### 11.4. Отсутствие движка и off

При реально отсутствующем nfqws2 `engine=auto` должен дать off/not_found, без `nfq_output`, с рабочими
Xray/sing-box/nftables. Если бинарник установлен и доступен автопоиску, живой absent-сценарий NOT_RUN;
не прятать системный файл. Независимо от этого `engine=off` обязан остановить worker, убрать очередь
после пересборки, восстановить offload и сохранить обычный VPN/direct. После изменения на off выполнить
`sudo xgw enable` и проверить отсутствие `nfq_output` в фактической таблице; одного остановленного
worker недостаточно. Отсутствие движка как таковое не является ошибкой и не мешает PASS fallback/off.

## 12. Эскалация сканера

Не блокировать сервер ручными правилами и не подменять вердикты. Использовать только естественный отказ
существующего сервера либо отдельно согласованный лабораторный сценарий. До наблюдения вернуть
`fragment.mode="auto"`, engine auto и исходные профили.

Если сканер получает `FROZEN`, `BODY_RESET` или `STALL_BEFORE_BODY`, лестница при доступном nfqws2 должна
содержать Xray fragment → Xray split → nfqws2 seqovl → hostfakesplit → disorder-badseq → sing-box.
У участника в работе смена ядра на sing-box не разрешена; допускаются Xray/NFQ-ступени. При отсутствии
nfqws2 NFQ-ступени пропускаются. Порядок может быть изменён свежей памятью удачного/неудачного профиля —
это штатно, записать фактический порядок и наличие памяти без имён серверов.

Для естественной эскалации проверить: профиль в статусе, смену PID только nfqws2, неизменный PID Xray,
вердикт и число байт пробы, закрепление успешного профиля либо возврат прежнего. Отсечку 16–20 КиБ по
`STALL_BEFORE_BODY` фиксировать только по фактическому результату сканера, не выдумывать случай.

Если за 60 минут наблюдения естественного подходящего вердикта не было — NOT_RUN natural_escalation.
Это не FAIL и не доказательство лестницы; аргументы и горячие переключения уже проверены шагом 10.

## 13. Завершение и откат настроек

Сначала задать `engine=off`, дождаться остановки worker, отсутствия тестовой очереди и восстановления
offload. Выполнить `sudo xgw enable` и проверить удаление `nfq_output`. Остановить только созданные
тестовые transient units. Вернуть QUIC, fragment, DNS, CIDR, STUN, engine_profile/queue и старый
zapret2 mode к исходным значениям. Вернуть исходное `net.netfilter.nf_conntrack_acct`, если оно менялось
для теста; проверить `/proc/sys/net/netfilter/nf_conntrack_acct`. После восстановления настроек снова
применить capture штатной командой.

Важно: если исходный конфиг не содержал `engine`, а обнаруживаемый nfqws2 остаётся на машине, простое
байтовое восстановление конфига включит auto. В этом случае оставить единственное согласованное
отличие `engine="off"` либо получить согласие на постоянный auto. Не удалять существующий внешний
zapret2 без разрешения.

Финально:

```bash
sudo xgw status --json >"$D/status-after.json"
sudo xgw diag --no-net >"$D/diag-after.txt" 2>&1; diag_after_rc=$?; printf 'diag_after_rc=%s\n' "$diag_after_rc"
sudo nft list tables >"$D/tables-after.txt"
sudo systemctl is-active xgw-nfqws2.service xgw-test-queue-busy.service 2>&1 || true
sudo systemctl show xgw-xray.service -p MainPID --value >"$D/xray-pid-after"
```

Норма: прежний capture/lifecycle и HTTPS, новых FAIL нет, сторонние таблицы восстановлены, тестовых
worker/queue нет, offload совпадает с исходным, WAN/LAN/Tailscale/пул/pin/подписки не менялись. Если
код откатывался, указать фактический итоговый коммит. Не оставлять остановленный xgw.service.

## 14. Отчёт и критерии приёмки

Создать `docs/TEST-REPORT-REAL-MACHINE-0.2.0-desync-nfqws2-ДАТА.md`. В отчёт включить:

```text
Дата; CODE/BASE; фактически установленный код до/после; ОС/архитектура; версии Python/Xray/sing-box/nfqws2:
Согласия по каждому опасному действию (без приватных значений):
Исходное и конечное состояние: capture/lifecycle; diag OK/WARN/FAIL; HTTPS шлюз/LAN:
Unittest/compileall/TOML; pytest target/full; новые FAIL или BASELINE_FAIL; NOT_RUN:
Xray generate/run -test; fragment/split; sing-box check и TLS f/m; живые пробы и задержки:
QUIC-матрица; noises; Cloudflare/Discord/STUN; DNS; reserved CIDR:
Восстановление после delete/flush; время; сторонний firewall восстановлен (да/нет/NOT_RUN):
NFQUEUE active; bypass/anti-loop/ct limits; Xray/direct/sing-box/LAN; PID Xray сохранён при профилях:
Три профиля; фактические аргументы; offload до/после; восстановление после рестарта демона:
Остановка worker/fail-open/recovery; queue_busy; unsafe_files; off/not_found:
Естественная эскалация либо NOT_RUN; вердикты/байты без серверов и URL:
Что осталось на машине; какие настройки отличаются от исходных и почему:
Итог PASS / PARTIAL / FAIL / STOP; первый непройденный шаг; нерешённые проблемы:
```

Полный PASS требует: реальные проверки конфигов обоими ядрами, рабочий fallback без движка/off,
восстановление таблиц, active NFQUEUE с корректными правилами и подтверждение счётчиками на всех
доступных Xray/direct/sing-box путях, горячую смену трёх профилей без рестарта Xray, fail-open при
остановке worker и восстановление offload. Живые Discord/direct/sing-box/flush и естественная эскалация
при отсутствии условия или согласия помечаются NOT_RUN; для полной приёмки это PARTIAL, а не скрытый
PASS. Если `nf_conntrack_acct` остался выключен, полный NFQUEUE PASS невозможен. Отсутствие самого
nfqws2 не является FAIL fallback/off, но ограничивает NFQ-часть NOT_RUN.

Перед публикацией отчёта проверить diff и `git diff --check`; не включать никакие приватные артефакты D.
Commit/push отчёта выполнять только отдельно и без force, если владелец разрешил публикацию результата.
