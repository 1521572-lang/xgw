# Проверка XGW: российские адреса мимо Xray (Ф6)

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Выводы сохраняй в файлы, как написано (`$HOME/xgw-f6/…`).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, KDE Plasma (X11), браузер Chromium, XGW 0.1.18. Клон —
`~/zcod/xgw`. Код — ветка `direct-f6` (от `split-f4`; версия остаётся 0.1.18). **Сначала должна
быть пройдена программа Ф4** (`docs/TEST-PLAN-REAL-MACHINE-0.1.18-f4.md`, ветка `split-f4`): эта
ветка содержит её код.

Что нового (ASSUMPTIONS п. 246). В карточке «Устройства» панели — переключатель «Российские
адреса — мимо Xray» (по умолчанию выключен). Включён — трафик устройств, самой машины и
контейнеров на российские адреса (`geoip:ru` из `geoip.dat` Xray) пропускает само ядро, как
обычный роутер, а не Xray. DNS по-прежнему через Xray. Здесь, у разработчика, проверены только
текст правил (`nft -c`) и маленький `geoip.dat`; настоящий набор в тысячи сетей, его загрузку
и работу сайтов проверяет эта программа.

## 0. Запрещено

- `xgw net down`, `xgw disable`, `xgw uninstall`, `reboot`, сон машины, `install.sh --force` —
  **никогда**. Запуск, остановка и перезапуск служб `xgw*`, `tailscaled`, NetworkManager,
  `ssh`; ручные `nft` (кроме `nft list`), `ip`, `iptables`, `tc`, `sysctl -w`.
- Править `/etc/xgw` (в том числе `panel.json`), `/opt/xgw`, `/var/lib/xgw`, `/etc/systemd`,
  код XGW. Всё меняет заказчик в панели. Коммитить что-либо, кроме отчёта (§7).
- Писать в отчёт: адреса tailnet, имена `*.ts.net`, имена устройств и пользователей (имя
  пользователя → `<user>`), внешние IP, токены, адреса подписок, IP и домены серверов VPN.
  Можно: адреса устройств в домашней сети (`192.168.…`), число сетей, счётчики правил, страны.

## 1. Подготовка

Шаг 1.1. **Спроси заказчика** (дословно):

«Проверяю новое: российские адреса мимо Xray. По пунктам:
(1) Переустановка XGW с новым кодом: Xray перезапустится — интернет дома пропадёт на несколько
секунд.
(2) Попрошу включить в панели переключатель «Российские адреса — мимо Xray», открыть на
телефоне пару сайтов, потом выключить его и решить, оставить ли включённым.
Можно согласиться не на все пункты.»

Против пункта 1 — **стоп**. Против пункта 2 — §3 и §4 пропустить, в отчёте «не выполнялся».

Шаг 1.2. Папка и помощник проверки (только читает: настройки без подписок, `geoip.dat`,
таблицу nftables `ip xgw` и `capture.json`):

```bash
mkdir -p "$HOME/xgw-f6" && chmod 700 "$HOME/xgw-f6" && cd "$HOME/xgw-f6" && cat > f6check.py <<'EOF'
"""Ф6: российские адреса мимо Xray — что включено и что загружено в ядро. Только читает:
config.toml и panel.json (без подписок), geoip.dat Xray, таблицу nftables ip xgw, capture.json."""
import json
import subprocess
import sys
import time

sys.path.insert(0, "/opt/xgw/lib")
from xgw import config, managed  # noqa: E402
from xgw.net import nft  # noqa: E402
from xgw.paths import Paths  # noqa: E402

paths = Paths.from_env()
cfg, _warnings = config.load(paths.config_file)
panel = managed.load(managed.path_for(paths.config_file))[0]["kernel_direct"]
print(f"переключатель: {'вкл' if cfg.routing.kernel_direct else 'выкл'} (в panel.json: {panel}); "
      f"не действует: {nft.kernel_direct_reason(cfg) if cfg.routing.kernel_direct else '—'}")
networks, warnings = nft.direct_networks(cfg, paths.xray_dir / "geoip.dat")
print(f"direct_ips: {cfg.routing.direct_ips}; сетей по geoip.dat: {len(networks)}; "
      f"предупреждения: {list(warnings) or 'нет'}")
started = time.monotonic()
listed = subprocess.run(["nft", "list", "table", "ip", "xgw"], capture_output=True, text=True)
spent = time.monotonic() - started
print(f"nft list table ip xgw: {spent:.2f} с, {len(listed.stdout) // 1024} КБ")
try:
    saved = json.loads((paths.var / "capture.json").read_text(encoding="utf-8")).get("direct4")
except (OSError, ValueError):
    saved = None
if not nft.has_set(listed.stdout, nft.DIRECT_SET):
    print(f"набор direct4 в ядре: нет; отпечаток в capture.json: {saved}")
    sys.exit(0)
data = json.loads(subprocess.run(["nft", "-j", "list", "set", "ip", "xgw", nft.DIRECT_SET],
                                 capture_output=True, text=True, check=True).stdout)
elements = next(item["set"].get("elem", []) for item in data["nftables"] if "set" in item)
same = saved == nft.direct_digest(networks)
print(f"набор direct4 в ядре: есть, сетей {len(elements)}; отпечаток в capture.json "
      f"{'совпадает' if same else 'НЕ совпадает'} с текущим")
for line in listed.stdout.splitlines():
    if "@direct4" in line:
        print("  правило: " + line.strip())
EOF
sha256sum f6check.py | cut -c1-16; sudo xgw status | grep -E '^Состояние|Перехват:' | tee before.txt
```

Ожидается: `f1e2a1246747ad33`; `Состояние: HEALTHY …`, `Перехват: включён …`. Записать как
есть.

Если не так: сумма другая — выполнить шаг заново, скопировав команду целиком; снова другая —
**стоп**, сообщить заказчику. Не `HEALTHY` — записать (это до установки) и продолжить.

## 2. Установка

Шаг 2.1. Код:

```bash
cd ~/zcod/xgw && git fetch && git checkout direct-f6 && git pull --ff-only && git log -1 --format='%h %s' && grep -q 'DIRECT_SET = "direct4"' src/xgw/net/nft.py && test -f src/xgw/geodat.py && echo "Ф6 в коде: есть"; cd "$HOME/xgw-f6"
```

Ожидается: «Ф6 в коде: есть». Записать хеш. Нет строки — **стоп**, сообщить заказчику.

Шаг 2.2. Установка:

```bash
cd ~/zcod/xgw && date '+%F %T' | tee "$HOME/xgw-f6/install-time.txt" && sudo sh packaging/install.sh --yes 2>&1 | tee "$HOME/xgw-f6/install.txt" | tail -6; echo "код ${PIPESTATUS[0]}"; cd "$HOME/xgw-f6"
```

Ожидается: «код 0», «демон xgw запущен». Код не 0 — **стоп**, сохранить вывод, сообщить
заказчику (сеть не тронута).

Шаг 2.3. Через минуту — шлюз в порядке, разгрузка выключена, `geoip.dat` читается:

```bash
sleep 60; cd "$HOME/xgw-f6" && sudo xgw status | grep -E '^Состояние|Перехват:' | tee after-install.txt; sudo python3 -I f6check.py | tee -a after-install.txt; sudo xgw diag | grep -i 'мимо Xray' | tee -a after-install.txt
```

Ожидается: `HEALTHY`, перехват включён; «переключатель: выкл (в panel.json: None)»; «сетей по
geoip.dat: N» — N от 3000 до 30000, «предупреждения: нет»; «набор direct4 в ядре: нет»; строка
diag «Российские адреса мимо Xray … выключено». Записать N и время `nft list`.

Если не так: не `HEALTHY` — подождать 2 минуты, повторить; снова нет — записать `sudo xgw
status` целиком (без адресов серверов) и продолжить. «сетей по geoip.dat: 0» или предупреждение
про `geoip.dat` — **дефект «geoip.dat не прочитан»**: записать вывод, §3 и §4 пропустить.
Помощник упал с ошибкой Python — **дефект «помощник»**: записать вывод целиком, §3–§4 без
шагов с `f6check.py`.

## 3. Включить (при согласии на пункт 2)

Шаг 3.1. **Попроси заказчика** (дословно):

«Откройте панель XGW, карточку „Устройства". Вверху — переключатель „Российские адреса — мимо
Xray". Включите его. Что написала панель вверху? Что написано под переключателем?»

Затем сразу:

```bash
cd "$HOME/xgw-f6" && date '+%F %T' | tee on-time.txt
```

Ожидается: «Российские адреса идут напрямую, мимо Xray» с пояснением; под переключателем —
«Включено: N российских сетей — напрямую ядром, мимо Xray…» (N — как в 2.3). Записать дословно.

Если не так: панель написала ошибку — **дефект «не включается»**: записать текст и перейти к
§5. Под переключателем «не действует: в routing.proxy_domains есть домены» — это не дефект:
записать и перейти к §5 (у заказчика свои домены через VPN, разгрузка им мешала бы).

Шаг 3.2. Через 30 секунд — что загружено:

```bash
sleep 30; cd "$HOME/xgw-f6" && sudo python3 -I f6check.py | tee on.txt
```

Ожидается: «переключатель: вкл (в panel.json: True); не действует: —»; «набор direct4 в ядре:
есть, сетей M; отпечаток … совпадает» — M не больше N из 2.3 (ядро может склеить соседние сети);
строки «правило:» — в prerouting (`iifname "<LAN>" ip daddr @direct4 th dport != 53 return`), в
output и containers (`ip daddr @direct4 th dport != 53 return`), в forward (`… ip daddr @direct4
counter packets … accept`) и в отбое QUIC (`ip daddr != @direct4`). Записать время `nft list` и
размер в КБ.

Если не так: «набор direct4 в ядре: нет» — подождать минуту, повторить; снова нет — **дефект
«набор не загружен»**: записать
`sudo journalctl -u xgw --since "$(cat on-time.txt)" --no-pager | grep -iE 'error|ошибк|nft|мимо Xray' | tail -15 | tee on-log.txt`.
«НЕ совпадает» — записать (проверится в 3.4). Время `nft list` больше 2 с — записать как
**наблюдение «nft list медленный»** и продолжить.

Шаг 3.3. **Попроси заказчика** (дословно):

«На телефоне в домашнем Wi-Fi откройте сайты ya.ru и gosuslugi.ru (или любые российские:
банк, маркетплейс). Открываются как обычно? Потом откройте ifconfig.co: какая страна в строке
Country?»

Ожидается: российские сайты открываются; ifconfig.co — страна сервера VPN (не Россия). Затем:

```bash
cd "$HOME/xgw-f6" && sudo python3 -I f6check.py | grep -E 'forward|counter' | tee traffic.txt; ya=$(curl -4 -s -m 10 https://ipv4-internet.yandex.net/api/v0/ip | tr -d '"'); co=$(curl -4 -s -m 10 https://ifconfig.co/ip); if echo "$ya" | grep -qE '^[0-9.]+$' && echo "$co" | grep -qE '^[0-9.]+$'; then [ "$ya" != "$co" ] && echo "машина: российский сайт видит адрес дома, зарубежный — адрес VPN" || echo "машина: адреса ОДИНАКОВЫЕ"; else echo "машина: адрес не узнать"; fi | tee -a traffic.txt
```

Ожидается: в правиле forward с `@direct4 counter packets P` — P больше нуля (трафик телефона к
российским сайтам пошёл ядром); «машина: российский сайт видит адрес дома, зарубежный — адрес
VPN». Адреса в отчёт не писать.

Если не так: российские сайты не открываются — **дефект «российские сайты не открываются»**:
попросить заказчика сразу выключить переключатель, записать ответ и `traffic.txt`, перейти к
§5. ifconfig.co показывает Россию или «машина: адреса ОДИНАКОВЫЕ» — **дефект «VPN не работает
при разгрузке»**: попросить выключить переключатель, записать, перейти к §5. P = 0 — записать
(телефон мог открыть сайты из кэша) и продолжить. «адрес не узнать» — записать и продолжить.

Шаг 3.4. Через 3 минуты — демон не перезагружает правила на каждом шаге:

```bash
sleep 180; cd "$HOME/xgw-f6" && sudo journalctl -u xgw --since "$(cat on-time.txt)" --no-pager | grep -c 'загружены заново' | sed 's/^/перезагрузок правил: /' | tee steady.txt; sudo python3 -I f6check.py | grep -E 'отпечаток|nft list' | tee -a steady.txt; sudo xgw diag | grep -i 'мимо Xray' | tee -a steady.txt
```

Ожидается: «перезагрузок правил: 0» (одна допустима — сразу после включения); отпечаток
«совпадает»; diag — «Российские адреса мимо Xray … N сетей — напрямую ядром; DNS — через Xray».

Если не так: перезагрузок 2 и больше — **дефект «правила перезагружаются по кругу»**: записать
`steady.txt` и
`sudo journalctl -u xgw --since "$(cat on-time.txt)" --no-pager | grep -B2 'загружены заново' | tail -20 | tee steady-log.txt`.

## 4. Выключить и решить (при согласии на пункт 2)

Шаг 4.1. **Попроси заказчика** (дословно):

«Выключите переключатель „Российские адреса — мимо Xray". Что написала панель? Российские
сайты на телефоне по-прежнему открываются?»

Ожидается: «Российские адреса снова идут через Xray»; сайты открываются. Затем:

```bash
sleep 30; cd "$HOME/xgw-f6" && sudo python3 -I f6check.py | tee off.txt
```

Ожидается: «переключатель: выкл (в panel.json: False)»; «набор direct4 в ядре: нет; отпечаток в
capture.json: None».

Если не так: набор остался — подождать минуту, повторить; снова есть — **дефект «не
выключается»**: записать `off.txt`.

Шаг 4.2. **Спроси заказчика** (дословно):

«Оставить российские адреса мимо Xray включёнными? Если да — включите переключатель снова.»

Записать ответ. Если включил:

```bash
sleep 30; cd "$HOME/xgw-f6" && sudo python3 -I f6check.py | grep -E 'переключатель|в ядре' | tee final-choice.txt
```

Ожидается: «переключатель: вкл»; «набор direct4 в ядре: есть». Не включал — шаг пропустить.

## 5. Итог

Шаг 5.1.

```bash
cd "$HOME/xgw-f6" && sudo journalctl -u xgw --since "$(cat install-time.txt)" --no-pager | grep -c Traceback | sed 's/^/Traceback в xgw: /' | tee final.txt; sudo xgw diag | tail -1 | tee -a final.txt; sudo xgw status | grep -E '^Состояние|Перехват:' | tee -a final.txt
```

Ожидается: Traceback — 0; «FAIL — 0»; `HEALTHY`, перехват включён.

## 6. Если что-то пошло не так

- Установка не прошла (код не 0) — ничего не откатывать, сообщить заказчику.
- Пропал интернет или не открываются российские сайты — попросить заказчика выключить
  переключатель «Российские адреса — мимо Xray», записать, что было видно.
- Шлюз не `HEALTHY` — записать и продолжить; сеть руками не трогать.

## 7. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.18-f6-<ДАТА>.md` в клоне `~/zcod/xgw` (ветка
`direct-f6`), коммит «Отчёт: российские адреса мимо Xray», `git push`. Шаблон:

```markdown
# Отчёт: российские адреса мимо Xray (Ф6)

Код: <хеш>. Установка: <дата время>, код <…>. Согласие заказчика: пункты <…>.
f6check.py: <сумма, 16 знаков>.

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.2 до | — | состояние, перехват |
| 2.2 установка | … | код … |
| 2.3 после установки | … | HEALTHY, выкл, сетей по geoip.dat N, nft list … с |
| 3.1 включение | … / не выполнялся | что написала панель, текст под переключателем |
| 3.2 загружено | … | сетей в ядре M, отпечаток, правила, nft list … с / … КБ |
| 3.3 сайты | … | российские открываются, ifconfig.co — страна …, счётчик forward P, машина … |
| 3.4 устойчивость | … | перезагрузок правил …, diag … |
| 4.1 выключение | … | набора нет |
| 4.2 решение заказчика | — | оставить вкл / выкл |
| 5.1 итог | … | Traceback 0, FAIL — 0, HEALTHY |

## Выводы шагов
<файлы $HOME/xgw-f6/*.txt; имя пользователя → <user>; ответы заказчика дословно>

## Дефекты

## Наблюдения
```

Готово, когда отчёт запушен и заказчику сказано, где он лежит.
