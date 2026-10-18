# Программа испытаний XGW 0.1.13 на реальной машине

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.12** в боевом режиме: от него работает интернет всего дома.

Что нового в 0.1.13 (по итогам испытаний 0.1.12):

- В лестнице профилей обхода появилась ступень **«обычный sing-box»** (метка `[sb]`). Сервер,
  который умеют оба ядра и который на Xray не отвечает, шлюз теперь пробует так: Xray с
  дроблением (`[xray+frag]`) → **обычный sing-box (`[sb]`)** → sing-box с дроблением
  (`[sb+frag]`) → (при «заморозке») sing-box с mux (`[sb+mux]`). В 0.1.12 ступени `[sb]` не
  было, и серверы, которым помогал именно обычный sing-box, шлюз сам не находил.
- `sudo xgw logs --export` теперь отдаёт архив тому, кто вызвал sudo: распаковать его можно без
  sudo.

Цели:

1. Поставить 0.1.13 (шаг 2), проверить службы и метки (шаг 3).
2. Проверить экспорт журналов под sudo (шаг 4).
3. **Главное:** посчитать, сколько серверов шлюз в режиме `auto` **сам** переводит на
   обычный sing-box `[sb]` (шаг 5), и сравнить с контрольной пробой, как в шаге 5 программы
   0.1.12 (шаг 6).
4. Проверить, что выученный `[sb]` переживает пересборку конфига и перезапуск демона (шаг 5), а
   закрепление ядра вручную после `auto` не «застревает» (шаг 7).

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft`, `ip`, `iptables`, `sysctl -w` — **никогда**.
- Запускать `sing-box` и `xray` вручную, править их файлы, останавливать или перезапускать
  `xgw-xray` и `xgw-singbox`. (Перезапуск самого демона `xgw` — только в шаге 5.5.)
- Открывать или скачивать адреса подписок (curl, браузер), копировать ссылки серверов.
- Править код XGW.
- Коммитить что-либо, кроме отчёта (§10). Файлы из `~/xgw-0.1.13-test` в Git **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов, свой
  внешний IP. Серверы называй по имени или тегу (`spare-nl-1a2b`).

Аварийный выход, если пропал интернет: `sudo xgw disable` (интернет пойдёт напрямую), затем
сообщить заказчику.

**Остановись и спроси заказчика** перед шагами 5.5, 6 и 7 — там это написано отдельно.

## 1. Подготовка

Шаг 1.1. Каталог для результатов:

```bash
mkdir -p ~/xgw-0.1.13-test/before ~/xgw-0.1.13-test/after && chmod 700 ~/xgw-0.1.13-test && cd ~/xgw-0.1.13-test && date
```

Ожидается: печатается дата. Дальше все команды выполняй из этого каталога.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw servers > before/servers.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt
```

Ожидается: `xgw 0.1.12` и строка «Итог: OK — …, WARN — …, FAIL — 0».
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

Шаг 1.3. Скрипт подсчёта меток. Скопируй команду целиком (до строки `EOF` включительно):

```bash
cat > ~/xgw-0.1.13-test/labels.py <<'EOF'
"""Метки серверов по видам: python3 labels.py servers.json inventory.json"""
import collections, json, sys
status = json.load(open(sys.argv[1], encoding="utf-8"))
inventory = json.load(open(sys.argv[2], encoding="utf-8"))
kind = {item["fingerprint"]: item.get("core") or "dual" for item in inventory["servers"]}
LABEL = {"xray:default": "xray", "xray:fragment": "xray+frag", "singbox:default": "sb",
         "singbox:tls_fragment": "sb+frag", "singbox:mux_padded": "sb+mux"}
NAME = {"dual": "оба ядра", "xray": "только Xray", "singbox": "только sing-box"}
counts = collections.defaultdict(collections.Counter)
for entry in status["members"] + status["spares"]:
    counts[kind.get(entry["fingerprint"], "dual")][LABEL.get(entry.get("profile"), "?")] += 1
for key in ("dual", "xray", "singbox"):
    if counts[key]:
        print(f"{NAME[key]}: " + ", ".join(f"[{l}] {n}" for l, n in sorted(counts[key].items())))
print(f"ИТОГО оба ядра на [sb]: {counts['dual']['sb']}")
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-0.1.13-test/labels.py').read()); print('labels.py OK')"
```

Ожидается: `labels.py OK`.

Шаг 1.4. Скрипт сравнения с контрольной пробой (он понадобится в шаге 6.6):

```bash
cat > ~/xgw-0.1.13-test/compare.py <<'EOF'
"""Сравнение «что шлюз выбрал сам» (шаг 5) с контрольной пробой (шаг 6)."""
import json, re
BAD = {"TIMEOUT", "CONNECT_FAIL", "FROZEN", "STALL_BEFORE_BODY"}
GOOD = {"OK", "SLOW"}
LABEL = {"xray:default": "xray", "xray:fragment": "xray+frag", "singbox:default": "sb",
         "singbox:tls_fragment": "sb+frag", "singbox:mux_padded": "sb+mux"}

def key(tag):
    return tag.split("-", 1)[1] if "-" in tag else tag

def probe(path):
    found = {}
    for line in open(path, encoding="utf-8"):
        parts = line.split()
        if len(parts) >= 2 and re.match(r"^(proxy|spare)-", parts[0]):
            found[key(parts[0])] = parts[1]
    return found

def servers(path):
    status = json.load(open(path, encoding="utf-8"))
    return {key(e["tag"]): e for e in status["members"] + status["spares"]}

kind = {i["fingerprint"]: i.get("core") or "dual"
        for i in json.load(open("after/inventory.json", encoding="utf-8"))["servers"]}
auto = servers("after/servers-auto.json")
in_sb_mode = servers("after/servers-singbox.json")
xray, sb = probe("after/probe-xray-only.txt"), probe("after/probe-singbox.txt")
dual = {k: e for k, e in auto.items() if kind.get(e["fingerprint"], "dual") == "dual"}
helped = sorted(k for k in dual if xray.get(k) in BAD and sb.get(k) in GOOD)
plain = [k for k in helped if (in_sb_mode.get(k) or {}).get("profile") == "singbox:default"]
on_sb = sorted(k for k, e in dual.items() if e.get("profile") == "singbox:default")
print(f"A. оба ядра, шлюз сам перевёл на [sb] (шаг 5): {len(on_sb)}")
print(f"B. контроль: на Xray не отвечают, на sing-box отвечают (оба ядра): {len(helped)}")
print(f"   из них в контрольной пробе на обычном sing-box [sb]: {len(plain)}")
print("C. серверы из B — что выбрал шлюз сам:")
groups = {}
for k in helped:
    groups.setdefault(LABEL.get(dual[k].get("profile"), "?"), []).append(k)
for label, items in sorted(groups.items()):
    print(f"   [{label}] {len(items)}: " + ", ".join(items))
print(f"D. из B на обычном sing-box в пробе, а шлюз оставил на Xray: "
      f"{sum(1 for k in plain if not dual[k].get('profile', '').startswith('singbox:'))}")
extra = [k for k in on_sb if k not in helped]
print(f"E. на [sb] сам, но в контроле sing-box не помог: {len(extra)}"
      + (": " + ", ".join(f"{k} (Xray {xray.get(k, '-')}, sing-box {sb.get(k, '-')})"
                          for k in extra) if extra else ""))
print("F. таблица (сервер | имя | метка в auto | Xray | sing-box):")
for k in sorted(set(helped) | set(on_sb)):
    e = dual[k]
    print(f"   {k} | {e.get('name') or ''} | [{LABEL.get(e.get('profile'), '?')}] | "
          f"{xray.get(k, '-')} | {sb.get(k, '-')}")
EOF
python3 -c "import ast; ast.parse(open('$HOME/xgw-0.1.13-test/compare.py').read()); print('compare.py OK')"
```

Ожидается: `compare.py OK`.

Шаг 1.5. Метки до обновления:

```bash
sudo cat /var/lib/xgw/inventory.json > before/inventory.json && sudo xgw servers --json > before/servers.json && python3 labels.py before/servers.json before/inventory.json | tee before/labels.txt
```

Ожидается: строки «оба ядра: …», «только sing-box: …» и «ИТОГО оба ядра на [sb]: N». В 0.1.12 у
серверов обоих ядер `[sb]` сам не появлялся: ожидается `0` (если заказчик не закреплял ядро
вручную). Записать все строки.

## 2. Установка 0.1.13

Шаг 2.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && grep __version__ src/xgw/__init__.py && cd ~/xgw-0.1.13-test
```

(Если код лежит в другом каталоге — перейди в него вместо `~/xgw`.)
Ожидается: `__version__ = "0.1.13"`. Записать хеш.
Если версия другая: **стоп**, сообщить заказчику.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/xgw && date '+%F %T' | tee ~/xgw-0.1.13-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-0.1.13-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-0.1.13-test
```

Ожидается: «код 0». Время из `install-time.txt` — «время установки» в шагах ниже.
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.

## 3. Службы, метки, диагностика

Шаг 3.1:

```bash
sudo xgw --version; systemctl is-active xgw-net xgw-xray xgw xgw-dhcp xgw-singbox; sudo xgw diag > after/diag.txt; grep -E 'sing-box' after/diag.txt; tail -1 after/diag.txt
```

Ожидается: `xgw 0.1.13`, пять раз `active`, строки «sing-box: версия 1.14.3» и «конфиг: принят
sing-box check, мостов: N», итог «FAIL — 0».
Если FAIL не 0: записать строки с FAIL и спросить заказчика, продолжать ли.

## 4. Экспорт журналов под sudo

Шаг 4.1. Архив создаётся через sudo, но принадлежит тебе:

```bash
sudo xgw logs --export --out ~/xgw-0.1.13-test/export.tgz | head -2; stat -c '%U:%G %a' ~/xgw-0.1.13-test/export.tgz; echo "я: $(id -un):$(id -gn)"
```

Ожидается: «архив без секретов: …», затем строка вида `user:user 600` — **тот же
пользователь и группа**, что в строке «я: …», права `600`.
Если владелец `root:root`: записать как дефект «архив под sudo принадлежит root» и
продолжать.

Шаг 4.2. Распаковка **без sudo** и поиск секретов:

```bash
mkdir -p ~/xgw-0.1.13-test/export && tar -xzf ~/xgw-0.1.13-test/export.tgz -C ~/xgw-0.1.13-test/export; echo "распаковка: код $?"; stat -c '%U %a %n' ~/xgw-0.1.13-test/export/xgw-logs/journal.txt; cd ~/xgw-0.1.13-test/export && echo "найдено: $(grep -rnE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|vless://|vmess://|trojan://|hysteria2://|"password": "[^*]|"private_key": "[^*]|"secret": "[^*]' . | wc -l)"; cd ~/xgw-0.1.13-test
```

Ожидается: «распаковка: код 0» (ошибок вроде «Permission denied» нет), файл `journal.txt` —
твой, права `600`, и `найдено: 0`.
Если что-то нашлось — **не копировать** найденное в отчёт; написать «найдены секреты в <имя
файла>» и сообщить заказчику сразу.

## 5. Шлюз сам переводит серверы на обычный sing-box

Шаг 5.1. Ничего не трогать **60 минут** (`sleep 1800` два раза). За это время шлюз сам проверяет
запасные серверы и проводит неответившие по лестнице профилей. Демон перезапустился при
установке, поэтому каждый неответивший сервер получает новую попытку сразу, без шестичасового
ожидания.

```bash
sleep 1800; sleep 1800; date +%T
```

Шаг 5.2. Собрать итог (метки и события с момента установки):

```bash
T=$(cat ~/xgw-0.1.13-test/install-time.txt)
sudo cat /var/lib/xgw/inventory.json > after/inventory.json && sudo xgw servers --json > after/servers-auto.json && sudo xgw servers > after/servers-auto.txt && python3 labels.py after/servers-auto.json after/inventory.json | tee after/labels-auto.txt
sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E 'profile:|fragment:|профиль обхода' > after/events.txt; wc -l < after/events.txt
echo "закреплён обычный sing-box: $(grep -c 'на профиле «sing-box» — он закреплён' after/events.txt)"
echo "пробовал обычный sing-box: $(grep -cE 'пробую «sing-box»$' after/events.txt)"
echo "закреплён sing-box с дроблением: $(grep -c 'на профиле «sing-box с дроблением TLS» — он закреплён' after/events.txt)"
echo "ни один профиль не помог: $(grep -c 'не отвечает ни на одном профиле' after/events.txt)"
```

Ожидается:

- строка «ИТОГО оба ядра на [sb]: N» — **это главное число испытания (A)**; записать N;
- «закреплён обычный sing-box: M» — сколько раз шлюз сам закрепил `[sb]` (M может быть больше N:
  сервер мог стать участником и смениться);
- в `events.txt` строки вида «profile: «имя» не отвечает на профиле «Xray с дроблением
  ClientHello» — пробую «sing-box»» и «profile: «имя» отвечает на профиле «sing-box» — он
  закреплён (был «Xray»)».

Если N = 0 и «пробовал обычный sing-box: 0»: это не ошибка, если все запасные отвечают на Xray
(в `servers-auto.txt` у запасных только `OK`/`SLOW`). Записать и продолжать.

Шаг 5.3. Ядра не перезапускались — смена профиля шла через API:

```bash
systemctl show xgw-xray xgw-singbox -p ExecMainStartTimestamp; grep -c 'применено через API без перезапуска' after/events.txt
```

Ожидается: время запуска `xgw-xray` и `xgw-singbox` — не позже времени установки (из
`install-time.txt`), число — больше 0, если N больше 0.

Шаг 5.4. Пересборка конфига не сбрасывает выученный `[sb]`:

```bash
sudo xgw apply; sleep 30; sudo xgw servers --json > after/servers-after-apply.json && python3 labels.py after/servers-after-apply.json after/inventory.json | tail -1
```

Ожидается: «ИТОГО оба ядра на [sb]: N» — **то же N**, что в шаге 5.2 (разница в 1–2 допустима:
шлюз мог за эти минуты сам перевести ещё сервер или вернуть один на Xray при суточной
проверке — тогда в `sudo journalctl -u xgw --since "-5 min" -o cat | grep profile:` есть
событие об этом).
Если число упало до 0: записать как дефект «выученный [sb] сброшен пересборкой».

Шаг 5.5. **Спроси заказчика:** «Перезапущу демон XGW (не ядра): интернет не пропадёт, панель
секунд на десять станет недоступна. Можно?» Дождись согласия.

```bash
sudo systemctl restart xgw; sleep 120; systemctl is-active xgw; sudo xgw servers --json > after/servers-after-restart.json && python3 labels.py after/servers-after-restart.json after/inventory.json | tail -1
```

Ожидается: `active` и «ИТОГО оба ядра на [sb]: N» — то же N (±1–2, как в шаге 5.4).
Если `xgw` не `active`: **стоп**, `sudo journalctl -u xgw -n 40 --no-pager > after/xgw-fail.txt`,
сообщить заказчику.

## 6. Контрольная проба (как шаг 5 программы 0.1.12)

**Предупреди заказчика:** «10–15 минут все серверы будут работать сначала через второе ядро,
потом только через Xray; интернет будет, соединения могут обрываться». Дождись согласия.

Шаг 6.1. Копия конфига и проверка, что секции `[core]` ещё нет:

```bash
sudo cp /etc/xgw/config.toml ~/xgw-0.1.13-test/config.toml.bak && sudo chmod 600 ~/xgw-0.1.13-test/config.toml.bak && sudo grep -c '^\[core\]' /etc/xgw/config.toml
```

Ожидается: `0`. Если `1` или больше — **стоп**, шаг 6 пропустить, записать «секция уже есть».

Шаг 6.2. Все серверы, которые это умеют, — через sing-box:

```bash
printf '\n[core]\nmode = "sing-box"\n' | sudo tee -a /etc/xgw/config.toml >/dev/null && sudo xgw apply --now; sleep 90; sudo xgw servers --json > after/servers-singbox.json && python3 labels.py after/servers-singbox.json after/inventory.json
```

Ожидается: у серверов «оба ядра» — в основном `[sb]`.
Если `[sb]` нет совсем: подождать ещё 2 минуты и повторить последнюю часть команды (после `sleep
90;`); если снова нет — шаг 6.5 (вернуть) и записать.

Шаг 6.3:

```bash
sudo xgw probe --all > after/probe-singbox.txt; wc -l < after/probe-singbox.txt
```

Шаг 6.4. Только Xray — для контроля (серверы, которые умеет лишь sing-box, на это время
пропадут из списка):

```bash
sudo sed -i 's/^mode = "sing-box"$/mode = "xray"/' /etc/xgw/config.toml && sudo xgw apply --now; sleep 90; sudo xgw servers | grep -c '\[sb'; sudo xgw probe --all > after/probe-xray-only.txt; wc -l < after/probe-xray-only.txt
```

Ожидается: первое число `0`.

Шаг 6.5. Вернуть конфиг как было:

```bash
sudo install -m 600 -o root -g root ~/xgw-0.1.13-test/config.toml.bak /etc/xgw/config.toml && sudo grep -c '^\[core\]' /etc/xgw/config.toml; sudo xgw apply --now; sleep 60; sudo xgw servers --json > after/servers-restored.json && python3 labels.py after/servers-restored.json after/inventory.json | tail -1; date +%T
```

Ожидается: `0`, затем «ИТОГО оба ядра на [sb]: 0» (или то же число, что в шаге 1.5, если
заказчик закреплял ядро вручную) — после режима `xray` серверы обоих ядер
возвращаются на Xray, а не остаются на sing-box (так и задумано: выученное шлюз наберёт заново
сам, у каждого сервера — не раньше чем через 6 ч после его прошлой попытки; это запасные,
трафик через них не идёт). Если число больше 0 — записать как дефект «после возврата mode
серверы остались на [sb]».

Шаг 6.6. Сравнение:

```bash
python3 compare.py | tee after/compare.txt
```

Ожидается: строки A–F. В отчёт перенеси A, B, C, D, E и таблицу F (имена и теги серверов
можно, адреса — нет). Вывод одной фразой:

- D = 0 и A больше 0 → «шлюз сам находит серверы, которым помогает обычный sing-box»;
- D больше 0 → «шлюз сам нашёл не все: D серверов отвечают на обычном sing-box, а остались на
  Xray» и список из таблицы F (метка `[xray]` или `[xray+frag]`);
- B = 0 → «у этого провайдера обычный sing-box ни одному серверу не помог» (тогда A должно
  быть небольшим; серверы из E перечисли).

## 7. Ядро вручную и обратно

**Спроси заказчика:** «На пару минут переведу один рабочий сервер на sing-box и верну; интернет
не пропадёт». Дождись согласия.

Шаг 7.1. Выбери **участника** (блок «Участники») с меткой `[xray]` и запиши его тег:

```bash
sudo xgw servers | sed -n '1,8p'
```

Шаг 7.2 (вместо `TAG` — тег, например `proxy-nl-1a2b`):

```bash
TAG=proxy-xx-0000   # ← подставь тег
sudo xgw core $TAG sing-box && sleep 60 && sudo xgw servers | grep "$TAG"; sudo xgw core $TAG auto && sleep 60 && sudo xgw servers | grep "$TAG"
```

Ожидается: «только sing-box», через минуту у сервера метка `[sb]`; затем «выбирает шлюз», и
через минуту метка снова `[xray]` (в 0.1.13 выученный `[sb]` сохраняется, но `[sb]` от
закрепления после `auto` не остаётся).
Если тег «не найден» (участник сменился) — взять тег из свежего `sudo xgw servers` и повторить.
Если после `auto` осталась `[sb]`: подождать ещё 2 минуты и повторить `sudo xgw servers | grep
"$TAG"`; если так и осталось — записать как дефект «закреплённый sing-box не вернулся после
auto».

## 8. Итоговое состояние

Шаг 8.1:

```bash
systemctl is-active xgw-net xgw-xray xgw-singbox xgw xgw-dhcp; sudo grep -c '^\[core\]' /etc/xgw/config.toml; sudo xgw diag | tail -1; sudo xgw status | head -5; rm -rf ~/xgw-0.1.13-test/export ~/xgw-0.1.13-test/export.tgz
```

Ожидается: пять `active`, `0`, «FAIL — 0». Телефон и устройства заказчика — «через VPN».

## 9. Что смотреть, если что-то пошло не так

- Пропал интернет — `sudo xgw disable`, сообщить заказчику (§0).
- Команда `xgw` пишет «ошибка» — сохранить вывод в `after/`, записать в отчёт, перейти к
  следующему шагу, если шаг не помечен «стоп».

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.13-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW 0.1.13 на реальной машине

Код: <хеш>. Установка: <время>, код <0/…>.

## Итог
<3–5 предложений: что работает, что нет; сколько серверов шлюз сам перевёл на [sb] (A) и
сколько должен был по контрольной пробе (B, D)>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.5 метки до | | <ИТОГО оба ядра на [sb]> |
| 2 установка | пройден / нет | |
| 3 службы, diag | пройден / нет | |
| 4 экспорт под sudo | пройден / нет | <владелец архива, распаковка без sudo, найдено секретов> |
| 5.2 шлюз сам: [sb] | A = … | <сколько «закреплён обычный sing-box»> |
| 5.3 без перезапуска ядер | пройден / нет | |
| 5.4 после xgw apply | пройден / нет | <N до → N после> |
| 5.5 после перезапуска демона | пройден / нет | <N до → N после> |
| 6 контроль | B = …, D = … | <фраза из шага 6.6> |
| 6.5 возврат mode | пройден / нет | <ИТОГО оба ядра на [sb] после возврата> |
| 7 ядро вручную и обратно | пройден / нет | <метка после auto> |

## Шаг 5 — метки в auto
<вывод labels.py из after/labels-auto.txt>

## Шаг 6 — сравнение с контрольной пробой
<строки A–E из after/compare.txt>

| Сервер | Имя | Метка в auto | Xray | sing-box |
|---|---|---|---|---|

Вывод: <фраза из шага 6.6>.

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE 'vless://|vmess://|trojan://|ss://|hysteria2://|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' docs/TEST-REPORT-REAL-MACHINE-0.1.13-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.13-*.md && git commit -m
"Отчёт об испытаниях XGW 0.1.13 на реальной машине" && git push`.
