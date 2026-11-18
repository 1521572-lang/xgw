"""Selected-policy commands. No processes, probes or routing changes in HTTP threads."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from .. import config, managed, zapret2
from ..desync import schema
from ..paths import LockTimeout

EDITABLE = frozenset({"strategy", "domains", "probe_urls", "check_seconds",
                      "retry_seconds", "daily_probe_mb", "youtube_transport_probe"})
PROFILES = schema.SELECTED_PROFILES
MODES = ("off", "standalone", "selective")


def candidate(cfg, patch, *, editing=False):
    flat = schema.flatten(cfg.desync or schema.migrate(vars(cfg.zapret2)))
    flat.update(patch)
    mode = flat["mode"]
    if flat.get("youtube_transport_probe") and (mode != "off" or editing):
        if mode not in ("off", "selective"):
            raise schema.PolicyError("HTTPS-проверка YouTube и CDN доступна только для Selective.")
        awaiting_urls = (mode == "off" and cfg.zapret2.youtube_transport_probe
                         and not flat["probe_urls"])
        domains_changed = flat["domains"] != cfg.zapret2.domains
        if ((domains_changed or not awaiting_urls)
                and not schema.valid_youtube_domains(flat["domains"])):
            raise schema.PolicyError(
                "Для HTTPS-проверки введите только поддерживаемые домены YouTube, "
                "включая domain:youtube.com и domain:googlevideo.com, "
                "или подставьте список в форме."
            )
        if not awaiting_urls and not schema.valid_youtube_transport(
            "selective", flat["domains"], flat["probe_urls"]
        ):
            raise schema.PolicyError(
                "Сохраните HTTPS-адрес страницы YouTube и HTTPS-адрес CDN googlevideo.com "
                "с путём /videoplayback или /generate_204 без параметров, "
                "либо отключите HTTPS-проверку YouTube и CDN."
            )
    policy = schema.migrate(flat)
    projected = schema.project(policy)
    proposed = copy.copy(cfg)
    proposed.zapret2 = config.Zapret2(**projected)
    problems = zapret2.validate(proposed)
    if problems:
        raise schema.PolicyError("; ".join(problems))
    return policy, proposed


def reasons(cfg, mode, *, ready, capture):
    if mode not in MODES:
        return ["Сравнение пока не запускается из панели."]
    if mode == "off":
        return []
    result = []
    if not ready:
        result.append("Нет свежей связи с демоном.")
    if capture.get("mode") != "on":
        result.append("Сначала включите перехват XGW.")
    if cfg.zapret2.strategy not in PROFILES:
        result.append("Этот экспериментальный профиль пока не включается из панели.")
    try:
        _policy, proposed = candidate(cfg, {"mode": mode})
        if mode == "selective" and not zapret2.configured(proposed):
            result.append("Сохраните HTTPS-пробы страницы и видеосети выбранных доменов.")
        expires_at = zapret2.probe_expiry(proposed.zapret2) if mode == "selective" else None
        if expires_at is not None and expires_at - time.time() < 1:
            result.append("Истёк срок адреса CDN. Сохраните свежий адрес видео.")
    except schema.PolicyError as exc:
        result.append(str(exc))
    return result


def reply(ok, code, text, **extra):
    return {"ok": ok, "code": code, "text": text, "notes": [], **extra}


def command(config_path: Path, action: str, body: dict, *, ready, capture) -> dict:
    """CAS under the same interprocess lock used by every managed writer.

    Reread the effective TOML + panel policy under that lock. Preserve raw unrelated
    sections (including extensions unknown to this backend). Validation is on a copy,
    before atomic replacement. An unchanged policy does not even canonicalize the file.
    """
    field = action if action in ("mode", "probe", "import") else "settings"
    if (action not in ("mode", "settings", "probe", "import") or set(body) != {field, "expected"}
            or not isinstance(body.get("expected"), str)):
        return reply(False, "invalid", "Ожидаются настройки и ревизия expected.")
    patch = ({"mode": body[field]} if action == "mode" else
             {} if action in ("probe", "import") else body[field])
    if action == "probe" and body[field] != "persistent":
        return reply(False, "invalid", "Неизвестный вид CDN-пробы.")
    if action == "import" and body[field] != schema.LIVE_STRATEGY:
        return reply(False, "invalid", "Доступен только проверенный Flowseal ALT9.")
    if (not isinstance(patch, dict) or (action == "settings" and set(patch) - EDITABLE)
            or (action == "mode" and body[field] not in MODES)):
        return reply(False, "invalid", "Недопустимые поля или режим.")
    try:
        patch = schema.validate_patch(patch)
        if "strategy" in patch and patch["strategy"] not in PROFILES:
            return reply(False, "invalid", "Профиль пока недоступен для выбора из панели.")
        path = managed.path_for(config_path)
        with managed.file_lock(managed.lock_path(path), timeout=managed.LOCK_TIMEOUT,
                               poll=0.02, mode=0o600):
            cfg, _warnings = config.load(config_path)
            current = cfg.desync or schema.migrate(vars(cfg.zapret2))
            key = schema.fingerprint(current)
            if body["expected"] != key:
                return reply(False, "conflict", "Настройки изменены в другом окне. "
                             "Перечитайте их перед повторным сохранением.", config_key=key)
            if action == "probe":
                if (cfg.zapret2.mode != "off" or not cfg.zapret2.youtube_transport_probe
                        or len(cfg.zapret2.probe_urls) != 2):
                    return reply(False, "blocked", "Выключите режим и сохраните пару проб YouTube.")
                patch = {"probe_urls": [cfg.zapret2.probe_urls[0],
                         schema.persistent_youtube_probe(cfg.zapret2.probe_urls[1])]}
            if action == "import" or patch.get("strategy") == schema.LIVE_STRATEGY:
                from ..desync import flowseal

                try:
                    flowseal.live_arguments()
                except (OSError, ValueError):
                    return reply(False, "blocked",
                                 "Проверенные каталоги или ассеты Flowseal отсутствуют.")
            if action == "import":
                if cfg.zapret2.mode != "off":
                    return reply(False, "blocked", "Выключите режим перед импортом.")
                patch = {"strategy": schema.LIVE_STRATEGY, "youtube_transport_probe": False,
                         "domains": list(schema.YOUTUBE_DOMAINS)}
            policy, proposed = candidate(cfg, patch, editing=action == "settings")
            if policy == current:
                return reply(True, "unchanged", "Настройки уже сохранены.",
                             config_key=key, changed=False)
            if proposed.zapret2.mode != "off":
                blocked = reasons(proposed, proposed.zapret2.mode, ready=ready, capture=capture)
                if blocked:
                    return reply(False, "blocked", " ".join(blocked))
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not isinstance(raw, dict):
                return reply(False, "invalid_config", "Хранилище настроек повреждено.")
            raw["desync"], raw["zapret2"] = policy, {}
            managed.save(path, raw)
            return reply(True, "saved", "Настройки сохранены. Ожидается применение демоном.",
                         config_key=schema.fingerprint(policy), changed=True)
    except schema.PolicyError as exc:
        return reply(False, "invalid", str(exc))
    except (config.ConfigError, managed.ManagedError, json.JSONDecodeError, UnicodeError):
        return reply(False, "invalid_config", "Не удалось прочитать настройки шлюза.")
    except LockTimeout:
        return reply(False, "busy", "Настройки меняет другой процесс. Перечитайте состояние.")
    except OSError:
        return reply(False, "storage_error", "Не удалось сохранить настройки шлюза.")
