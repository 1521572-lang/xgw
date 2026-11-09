"""Почему правило видео не применилось (отчёт youtube-route-r2): только чтение журнала демона.

Каждая строка сводится к готовой метке. Сам текст строк, адреса, домены и теги не выводятся.
Режим best не включается, настройки и службы не меняются.
"""
import collections
import re
import subprocess
import sys

UNIT = "xgw.service"
SINCE, UNTIL = "2026-11-09 11:15:00", "2026-11-09 11:53:00"
MUST_START_BY, MUST_END_AFTER = "11:20:00", "11:45:00"  # установка и конец наблюдения
TIMELINE_MAX = 60
VIDEO = "YouTube: выход для видео"

# Строка получает первую подходящую метку; порядок важен только для составных событий.
EVENTS = (
    ("build_started", "сборка конфига начата"),
    ("build_stale", "устаревшая сборка конфига отброшена"),
    ("build_finished", "конфиг собран в фоне"),
    ("generation_changed", "поколение sing-box сменено"),
    ("generation_prepare_failed", "подготовка поколения sing-box не выполнена"),
    ("generation_not_ready", "поколение sing-box не подготовлено"),
    ("media_chosen", "новые соединения видео YouTube идут через"),
    ("media_common", "видео YouTube идёт общим маршрутом"),
    ("media_not_saved", "выход для видео не записан"),
    ("media_not_confirmed", "выход для видео не подтверждён"),
    ("media_other_exit", "выход для видео: ядро выбирает другие серверы"),
    ("applied_api", "применено через API без перезапуска"),
    ("applied_restart", "применено с перезапуском Xray"),
    ("apply_deferred", "нужен перезапуск Xray — отложен"),
    ("apply_rejected", "конфиг отклонён, Xray работает на прежнем"),
    ("apply_rollback", "выполнен откат на last-good"),
    ("apply_failed", "откат на last-good не помог"),
    ("check_xray_failed", "конфиг не прошёл xray run -test"),
    ("check_singbox_failed", "конфиг не прошёл sing-box check"),
    ("no_servers", "после фильтров не осталось серверов"),
    ("no_server_dns", "ни один сервер не подходит"),
    ("api_error", "ошибка API"),
)
# Уточнения: у одной строки их может быть несколько. Все тексты — постоянные строки кода.
DETAILS = (
    ("outbounds_static", "основные outbounds"),
    ("inbounds_static", "основные inbounds"),
    ("capture_inbound", "изменение inbound перехвата"),
    ("api_partial", "ядро изменено через API частично"),
    ("previous_generation_busy", "предыдущее поколение ещё завершается"),
    ("no_old_generation", "нет исходного поколения"),
    ("wireguard", "параллельная смена WireGuard"),
    ("generation_needs_restart", "смена поколения потребовала бы перезапуска"),
    ("generation_check_failed", "новый sing-box не прошёл check"),
    ("bridge_request_failed", "не прошло настоящий запрос через мост"),
    ("generation_cancelled", "подготовка поколения была отменена"),
    ("source_changed", "исходный конфиг изменился во время проверки"),
    ("xray_refused_bridges", "Xray не принял новые мосты"),
    ("generation_stopped", "подготовленное поколение перестало отвечать"),
    ("api_not_ready", "API не готово к смене поколения"),
    ("api_unknown", "исход API неизвестен"),
    ("bridges_restored", "прежние мосты восстановлены"),
)
SECTION = re.compile(r"секция (log|api|metrics|stats|policy|burstObservatory|dns)(?![A-Za-z])")
BRIDGES = re.compile(r"мостов проверено ([0-9]+) из ([0-9]+)(?:: ((?:[a-z_]+ [0-9]+(?:, )?)+))?")
STAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T([0-9]{2}:[0-9]{2}:[0-9]{2})")


def journal():
    done = subprocess.run(
        ["journalctl", "--no-pager", "-o", "short-iso", "-u", UNIT, "--since", SINCE,
         "--until", UNTIL],
        capture_output=True, encoding="utf-8", errors="replace", timeout=120, check=True)
    return done.stdout.splitlines()


def classify(line):
    """Метка, уточнения. Метка None — строка к разбору не относится."""
    event = next((label for label, text in EVENTS if text in line), None)
    if event is None:
        return None, []
    details = [label for label, text in DETAILS if text in line]
    details += ["section_" + item for item in SECTION.findall(line)]
    found = BRIDGES.search(line)
    if found:
        details.append(f"bridges={found[1]}/{found[2]}")
        if found[3]:
            details.append("kinds=" + found[3].replace(", ", ",").replace(" ", ":"))
    return event, details


def main():
    lines = journal()
    stamps = [found[1] for found in map(STAMP.match, lines) if found]
    print(f"INFO journal_lines={len(lines)} first={min(stamps, default='-')} "
          f"last={max(stamps, default='-')}", flush=True)
    if not stamps or min(stamps) > MUST_START_BY or max(stamps) < MUST_END_AFTER:
        print("NOT_RUN journal_gone", flush=True)
        return 4
    print("OK journal_covers", flush=True)
    counts, video_counts, details_seen, rows = (collections.Counter(), collections.Counter(),
                                                collections.Counter(), [])
    for line in lines:
        event, details = classify(line)
        if event is None:
            continue
        video = VIDEO in line
        counts[event] += 1
        video_counts[event] += video
        details_seen.update(details)
        found = STAMP.match(line)
        moment = found[1] if found else "--:--:--"
        rows.append(" ".join([moment, event, *(["video"] if video else []), *details]))
    print("INFO events " + " ".join(f"{key}={counts[key]}" for key in sorted(counts)), flush=True)
    print("INFO video_events " + " ".join(
        f"{key}={video_counts[key]}" for key in sorted(video_counts) if video_counts[key]),
        flush=True)
    print("INFO details " + " ".join(
        f"{key}={details_seen[key]}" for key in sorted(details_seen)), flush=True)
    for row in rows[:TIMELINE_MAX]:
        print("T " + row, flush=True)
    print(f"INFO timeline_rows={len(rows)} shown={min(len(rows), TIMELINE_MAX)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # текст ошибки может содержать строки журнала
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
