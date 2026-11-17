"""Selected-policy commands. No processes, probes or routing changes in HTTP threads."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .. import config, managed, zapret2
from ..desync import schema
from ..paths import LockTimeout

EDITABLE = frozenset({"strategy", "domains", "probe_urls", "check_seconds",
                      "retry_seconds", "daily_probe_mb", "youtube_transport_probe"})
# Importing experimental assets and starting comparisons are separate acceptance stages.
PROFILES = tuple(p for p in schema.SELECTED_PROFILES if p != schema.LIVE_STRATEGY)
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
                "с путём /videoplayback или отключите HTTPS-проверку YouTube и CDN."
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
    field = "mode" if action == "mode" else "settings"
    if (action not in ("mode", "settings") or set(body) != {field, "expected"}
            or not isinstance(body.get("expected"), str)):
        return reply(False, "invalid", "Ожидаются настройки и ревизия expected.")
    patch = {"mode": body[field]} if action == "mode" else body[field]
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
