#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Генерация flowseal_lab.py (launcher) и translation.json из закреплённого источника Flowseal.

Использование: make_flowseal.py <source.json> <outdir>
Самопроверка: каждая опция каждого профиля либо переведена, либо профиль исключён
с записанной причиной; неучтённые опции прерывают сборку.
"""
import json, re, sys
from pathlib import Path

SRC = Path(sys.argv[1])
OUTDIR = Path(sys.argv[2])

m = json.loads(SRC.read_text(encoding="utf-8"))
assert m["commit"] == "2401b7a13837139b0265632464ba563dddbf80d8"
assert len(m["configurations"]) == 22

REF_TS = -600000
REF_BADSEQ = -10000
REF_BADACK = -66000
REF_REPEATS = 1

DISCORD_PORTS = "19294-19344,50000-50100"
GAME_TCP, GAME_UDP = "%GameFilterTCP%", "%GameFilterUDP%"

NOTES_TS = ("fooling=ts: инкремент в BAT не задан; подставлен справочный TS_INCREMENT_DEFAULT="
            f"{REF_TS} (zapret1 1e1d1e2), версия bundled winws не сопоставлена — ADAPTED (п.5)")
NOTES_ACK = (f"default ACK badseq не задан в BAT; подставлен справочный {REF_BADACK} — ADAPTED (п.5)")
NOTES_ALTORDER = ("altorder=1 не поддержан pinned Lua zapret2 1.0.7; переведено без altorder — ADAPTED (п.5)")
NOTES_HOSTFAKE = ("hostfakesplit без midhost: default-разрез хоста в winws не задан (master zapret1); "
                  "nfqws2 hostfakesplit без midhost тоже не разрезает — поведение соответствует")
NOTES_PAYLOAD = ("fake-http переведён отдельным блоком filter-l7=http, payload=http_req (одна стадия nfqws2 "
                 "не выбирает blob по типу payload) — ADAPTED")
NOTES_MDISORDER = ("multidisorder без split-pos: default winws не установлен (dp->splits пуст); "
                   "подставлен pos=midsld (исторический default zapret1) — ADAPTED")
NOTES_BUILTIN = ("fake-tls=! — встроенный fake исходного winws; заменён builtin fake_default_tls "
                 "nfqws2 (680 байт), побайтовое совпадение не доказано — ADAPTED (п.5)")
NOTE_GAME = ("GameFilter disabled (service.bat: GameFilter=12): порт 12 не встречается в тестовом потоке")
NOTE_DISCORD = ("Discord/STUN UDP-порты 19294-19344,50000-50100 и hostlist discord.media не "
                "участвуют в тестовом YouTube-потоке")
NOTE_WF = ("wf-tcp/wf-udp — фильтры WinDivert (Windows-only); в nfqws2 эквивалент — правила "
           "очереди XGW; объём ограничен тестовым YouTube-потоком")
NOTE_GAMEFILTER_SUBST = "значение disabled-режима GameFilter=12 подразумевается в %GameFilter*%"
NOTE_IPID = "ip-id=zero применён ко всем стадиям профиля (winws задаёт глобально на профиль)"


def blob_name(basename):
    basename = basename.replace("%BIN%", "")
    return "fl_" + basename.replace("-", "_").replace(".", "_")


def hex_blob_name(hexstr):
    return "fl_hex_" + hexstr[2:].lower()


def optmap(options):
    o = {}
    for k, v in options:
        o.setdefault(k, [])
        o[k].append(v)
    return {k: (vs[0] if len(vs) == 1 else vs) for k, vs in o.items()}


class OD(dict):
    def get_list(self, k):
        v = self.get(k)
        if v is None:
            return []
        return v if isinstance(v, list) else [v]


def classify(o):
    ftcp, fudp = o.get("filter-tcp"), o.get("filter-udp")
    fl7 = o.get("filter-l7")
    hl = o.get_list("hostlist")
    ipset = o.get_list("ipset")
    desync = o.get("dpi-desync", "")
    if fudp == GAME_UDP or GAME_UDP in str(fudp):
        return "GAME_EXCLUDED", NOTE_GAME
    if fudp == DISCORD_PORTS:
        return "DISCORD_EXCLUDED", NOTE_DISCORD
    if ftcp == GAME_TCP or GAME_TCP in str(ftcp):
        return "GAME_EXCLUDED", NOTE_GAME
    if "discord.media" in str(o.get("hostlist-domains", "")):
        return "DISCORD_EXCLUDED", NOTE_DISCORD
    if fudp == "443" and hl and any("list-general" in h for h in hl):
        return "Q", "QUIC по hostlist (list-general)"
    if fudp == "443" and ipset:
        return "I", "QUIC по ipset"
    if fl7 and "quic" in fl7 and not fudp:
        return "Q_EXP", "QUIC по filter-l7 без filter-udp (EXP)"
    if ftcp and hl and any("list-google" in h for h in hl):
        return "G", "TCP 443 Google-профиль (list-google)"
    if ftcp and hl and any("list-general" in h for h in hl):
        return "H", "TCP 80,443 общий профиль (list-general)"
    if ftcp and ipset:
        return "S", "TCP ipset-профиль (ipset-all)"
    if ftcp and "syndata" in desync and not hl and not ipset:
        return "S09", "IPv4 syndata+multidisorder без положительных списков"
    raise ValueError(f"unclassified profile: ftcp={ftcp} fudp={fudp} hl={hl} ipset={ipset} desync={desync}")


def fooling_args(fooling, o):
    args, notes = [], []
    for p in (fooling or "").split(","):
        p = p.strip()
        if not p:
            continue
        if p == "ts":
            args.append(f"tcp_ts={REF_TS}")
            notes.append(NOTES_TS)
        elif p == "badseq":
            inc = o.get("dpi-desync-badseq-increment")
            args.append(f"tcp_seq={int(inc) if inc is not None else REF_BADSEQ}")
            ack = o.get("dpi-desync-badack-increment")
            if ack is not None:
                args.append(f"tcp_ack={int(ack)}")
            else:
                args.append(f"tcp_ack={REF_BADACK}")
                notes.append(NOTES_ACK)
        elif p == "md5sig":
            args.append("tcp_md5")
        else:
            raise ValueError(f"unknown fooling: {p}")
    return args, notes


def translate_stages(o, ipid_zero):
    blobs, stages, notes = [], [], []
    desyncs = [x.strip() for x in o.get_list("dpi-desync")[0].split(",")]
    repeats = o.get("dpi-desync-repeats")
    rep = f":repeats={int(repeats)}" if repeats is not None else ""
    ipid_arg = ":ip_id=zero" if ipid_zero else ""
    fargs, fnotes = fooling_args(o.get("dpi-desync-fooling"), o)
    notes += fnotes
    tls_mod = o.get("dpi-desync-fake-tls-mod")
    tls_mod_arg = f":tls_mod={tls_mod}" if tls_mod and tls_mod != "none" else ""
    split_pos = o.get("dpi-desync-split-pos")
    seqovl = o.get("dpi-desync-split-seqovl")
    seqovl_pat = o.get("dpi-desync-split-seqovl-pattern")
    fs_pattern = o.get("dpi-desync-fakedsplit-pattern")
    hfs_mod = o.get("dpi-desync-hostfakesplit-mod")
    is_udp_fake = bool(o.get("filter-udp"))
    # Источник blob стадии fake: явный fake-quic / fake-tls; если neither —
    # встроенный default fake исходного winws (эквивалент fake-tls=!), ADAPTED (п.5).
    fake_quic = o.get_list("dpi-desync-fake-quic")
    fake_tls = o.get_list("dpi-desync-fake-tls")
    builtin = "fake_default_quic" if is_udp_fake else "fake_default_tls"
    if fake_quic:
        fake_blobs, builtin = fake_quic, "fake_default_quic"
    elif fake_tls:
        fake_blobs, builtin = fake_tls, "fake_default_tls"
    else:
        fake_blobs = ["!"]

    def fake_stage(blob):
        a = f"fake:blob={blob}{rep}{tls_mod_arg}{ipid_arg}"
        return a + "".join(":" + x for x in fargs)

    for mode in desyncs:
        if mode == "fake":
            for b in fake_blobs:
                if b.startswith("0x"):
                    name = hex_blob_name(b)
                    blobs.append(("hex", name, b))
                elif b == "!":
                    name = builtin
                    notes.append(NOTES_BUILTIN)
                else:
                    name = blob_name(str(b).split("/")[-1])
                    blobs.append(("file", name, b))
                stages.append(fake_stage(name))
        elif mode == "multisplit":
            a = f"multisplit:pos={split_pos}" if split_pos is not None else "multisplit"
            if seqovl is not None:
                a += f":seqovl={int(seqovl)}"
            if seqovl_pat:
                name = blob_name(str(seqovl_pat).split("/")[-1])
                blobs.append(("file", name, seqovl_pat))
                a += f":seqovl_pattern={name}"
            stages.append(a + ipid_arg)
        elif mode == "fakedsplit":
            a = f"fakedsplit:pos={split_pos}" if split_pos is not None else "fakedsplit"
            if fs_pattern is not None:
                if fs_pattern.startswith("0x"):
                    name = hex_blob_name(fs_pattern)
                    blobs.append(("hex", name, fs_pattern))
                else:
                    name = blob_name(str(fs_pattern).split("/")[-1])
                    blobs.append(("file", name, fs_pattern))
                a += f":pattern={name}"
            stages.append(a + rep + tls_mod_arg + ipid_arg + "".join(":" + x for x in fargs))
        elif mode == "hostfakesplit":
            host = None
            altorder = False
            if hfs_mod:
                for part in str(hfs_mod).split(","):
                    if part.startswith("host="):
                        host = part[5:]
                    elif part == "altorder=1":
                        altorder = True
            a = "hostfakesplit"
            if host:
                a += f":host={host}"
            stages.append(a + rep + tls_mod_arg + ipid_arg + "".join(":" + x for x in fargs))
            notes.append(NOTES_ALTORDER if altorder else NOTES_HOSTFAKE)
        elif mode == "multidisorder":
            if split_pos is not None:
                a = f"multidisorder:pos={split_pos}"
            else:
                a = "multidisorder:pos=midsld"
                notes.append(NOTES_MDISORDER)
            stages.append(a + ipid_arg)
        elif mode == "syndata":
            stages.append("syndata" + "".join(":" + x for x in fargs))
        else:
            raise ValueError(f"unknown desync mode: {mode}")
    return blobs, stages, notes


def payload_arg(o, kind):
    fudp = o.get("filter-udp")
    fl7 = o.get("filter-l7")
    if fudp == "443" or (fl7 and "quic" in fl7):
        return "--payload=quic_initial", False
    desyncs = [x.strip() for x in o.get_list("dpi-desync")[0].split(",")]
    if kind == "S09":
        return "--payload=empty,tls_client_hello", False
    fake_http = o.get_list("dpi-desync-fake-http")
    if "fake" in desyncs and fake_http:
        return "--payload=tls_client_hello", True
    return "--payload=tls_client_hello", False


USED_KEYS = {
    "filter-tcp", "filter-udp", "filter-l7", "hostlist", "hostlist-exclude",
    "hostlist-domains", "ipset", "ipset-exclude", "ip-id", "dpi-desync",
    "dpi-desync-repeats", "dpi-desync-fooling", "dpi-desync-fake-tls",
    "dpi-desync-fake-quic", "dpi-desync-fake-http", "dpi-desync-split-pos",
    "dpi-desync-split-seqovl", "dpi-desync-split-seqovl-pattern",
    "dpi-desync-fakedsplit-pattern", "dpi-desync-fake-tls-mod",
    "dpi-desync-hostfakesplit-mod", "dpi-desync-badseq-increment",
    "dpi-desync-badack-increment", "dpi-desync-any-protocol", "dpi-desync-cutoff",
    "dpi-desync-fake-discord", "dpi-desync-fake-stun", "dpi-desync-fake-unknown",
    "dpi-desync-fake-unknown-udp", "filter-l3",
    "hostlist-exclude-domains",
}


def translate_profile(num, raw):
    o = OD(optmap(raw))
    kind, reason = classify(o)
    if kind.endswith("_EXCLUDED"):
        left = [k for k in o if k not in USED_KEYS]
        return kind, None, None, [reason], [], left
    notes = []
    ipid_zero = o.get("ip-id") == "zero"
    if ipid_zero:
        notes.append(NOTE_IPID)
    blobs, stages, snotes = translate_stages(o, ipid_zero)
    notes += snotes
    args = []
    if o.get("filter-tcp"):
        args.append(f"--filter-tcp={o['filter-tcp']}")
    if o.get("filter-udp"):
        args.append(f"--filter-udp={o['filter-udp']}")
    if o.get("filter-l7"):
        args.append(f"--filter-l7={o['filter-l7']}")
    for h in o.get_list("hostlist"):
        args.append("--hostlist=%LISTS%" + str(h).split("/")[-1].replace("%LISTS%", ""))
    for h in o.get_list("hostlist-exclude"):
        args.append("--hostlist-exclude=%LISTS%" + str(h).split("/")[-1].replace("%LISTS%", ""))
    if o.get("hostlist-domains"):
        args.append(f"--hostlist-domains={o['hostlist-domains']}")
    if o.get("hostlist-exclude-domains"):
        args.append(f"--hostlist-exclude-domains={o['hostlist-exclude-domains']}")
    for i in o.get_list("ipset"):
        args.append("--ipset=%LISTS%" + str(i).split("/")[-1].replace("%LISTS%", ""))
    for i in o.get_list("ipset-exclude"):
        args.append("--ipset-exclude=%LISTS%" + str(i).split("/")[-1].replace("%LISTS%", ""))
    parg, need_http = payload_arg(o, kind)
    # payload controls Lua invocation, not profile selection. Without an L7 filter
    # the TLS block shadows the HTTP block on their shared TCP ports.
    if not o.get("filter-l7") and parg == "--payload=tls_client_hello":
        args.append("--filter-l7=tls")
    elif not o.get("filter-l7") and parg == "--payload=quic_initial":
        args.append("--filter-l7=quic")
    args.append(parg)
    args += [f"--lua-desync={s}" for s in stages]
    http_block = None
    fake_http = o.get_list("dpi-desync-fake-http")
    if need_http and fake_http:
        repeats = o.get("dpi-desync-repeats")
        rep = f":repeats={int(repeats)}" if repeats is not None else ""
        fargs, _ = fooling_args(o.get("dpi-desync-fooling"), o)
        hb = [a for a in args if not a.startswith(("--payload=", "--lua-desync=", "--filter-l7="))]
        hb.append("--filter-l7=http")
        hb.append("--payload=http_req")
        for b in fake_http:
            name = blob_name(str(b).split("/")[-1])
            blobs.append(("file", name, b))
            hb.append(f"--lua-desync=fake:blob={name}{rep}" + "".join(":" + x for x in fargs))
        http_block = hb
        notes.append(NOTES_PAYLOAD)
    left = [k for k in o if k not in USED_KEYS]
    return kind, args, http_block, notes, blobs, left


def translate_config(conf):
    cid = conf["file"].removesuffix(".bat")
    blocks, meta, notes, blob_decls = [], [], [], {}
    unaccounted = []
    for prof in conf["all_profiles_in_source_order"]:
        num = prof["profile"]
        kind, block, http_block, pnotes, blobs, left = translate_profile(num, prof["options"])
        unaccounted += [(cid, num, k) for k in left]
        notes += pnotes
        for kind_b, name, val in blobs:
            blob_decls[name] = val
        if block is None:
            meta.append({"profile": num, "kind": kind, "status": "EXCLUDED_COVERAGE",
                         "note": pnotes[0] if pnotes else ""})
            continue
        blocks.append(block)
        meta.append({"profile": num, "kind": kind, "status": "INCLUDED",
                     "note": NOTES_PAYLOAD if http_block else ""})
        if http_block:
            blocks.append(http_block)
            meta.append({"profile": num, "kind": kind + "-HTTP", "status": "INCLUDED",
                         "note": NOTES_PAYLOAD})
    return cid, blocks, meta, sorted(set(notes)), blob_decls, unaccounted


translation = {"source_commit": m["commit"], "release_label": m.get("release_label"),
               "reference_defaults": {"ts": REF_TS, "badseq": REF_BADSEQ, "badack": REF_BADACK,
                                      "repeats": REF_REPEATS,
                                      "note": "справочный zapret1 1e1d1e2; версия bundled winws Flowseal не сопоставлена"},
               "global_note": NOTE_WF + "; " + NOTE_GAMEFILTER_SUBST,
               "configurations": {}}

chains = {}
problems = []
for conf in m["configurations"]:
    cid, blocks, meta, notes, blob_decls, unaccounted = translate_config(conf)
    if unaccounted:
        problems.append(unaccounted)
    # Декларации --blob перед использованием (п.6.3): имена → %LISTS%-файлы или 0xHEX
    blob_decl_args = {}
    for name, val in blob_decls.items():
        if val.startswith("0x"):
            blob_decl_args[name] = f"--blob={name}:{val}"
        else:
            # DATA-файлы устанавливаются с именем, равным имени blob
            blob_decl_args[name] = f"--blob={name}:%LISTS%{name}"
    decorated = []
    declared = set()
    for b in blocks:
        used = set()
        for a in b:
            for mm in re.finditer(r"(?:blob|seqovl_pattern|pattern)=([A-Za-z0-9_]+)", a):
                used.add(mm.group(1))
        pre = []
        for name in sorted(used):
            if name.startswith("fake_default_"):
                continue  # builtin nfqws2, авто-объявлен
            if name in blob_decl_args and name not in declared:
                pre.append(blob_decl_args[name])
                declared.add(name)
        decorated.append(pre + list(b))
    blocks = decorated
    chain = []
    for i, b in enumerate(blocks):
        if i:
            chain.append("--new")
        chain += b
    chains[cid] = chain
    translation["configurations"][cid] = {
        "file": conf["file"],
        "global_options_windows_only": conf["global_options"],
        "blocks": blocks,
        "profiles": meta,
        "blob_decls": blob_decls,
        "notes": notes,
    }

if problems:
    print("UNACCOUNTED OPTIONS:", problems, file=sys.stderr)
    sys.exit(1)

src_compact = {c["file"].removesuffix(".bat"): {"global": c["global_options"],
                                                "profiles": c["all_profiles_in_source_order"]}
               for c in m["configurations"]}

LAUNCHER_TEMPLATE = r"""#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Временный allowlist-launcher nfqws2 для реальной проверки методов Flowseal в XGW.
# Перевод опций Flowseal (winws, zapret1) в nfqws2/Lua выполнен генератором
# make_flowseal.py и зафиксирован в CHAINS ниже; исходные опции каждой конфигурации
# встроены в SOURCE_PROFILES для аудита (совпадают с helpers/flowseal-youtube-source.json).
# Управление unit/очередью/маршрутом остаётся у XGW. Контракт argv — как в nfq_lab.py (r3):
# launcher получает --qnum/--fwmark/--lua-init и собственные профили XGW, заменяет их
# проверенной цепочкой конфигурации Flowseal и execv реальный бинарник.
# Списки/блобы читаются только из DATA (root-owned 0755, файлы 0644) — nfqws2 после
# сброса UID повторно открывает их.
from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

YOUTUBE_SCOPE = (
    "youtube.com", "googlevideo.com", "youtubei.googleapis.com",
    "youtube-nocookie.com", "ytimg.com", "ggpht.com",
)
FIELDS = {"binary", "strategy", "reassembly", "debug", "data_dir", "scope"}
DOMAIN = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")

CHAINS = @@CHAINS@@

SOURCE_PROFILES = @@SOURCE@@

BLOB_DECLS = @@BLOBS@@


def settings_check(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("settings_schema")
    binary = value["binary"]
    if (not isinstance(binary, str) or not PurePosixPath(binary).is_absolute()
            or any(c in binary for c in "\r\n\x00")):
        raise ValueError("binary_path")
    if not isinstance(value["strategy"], str) or value["strategy"] not in CHAINS:
        raise ValueError("strategy")
    if value["reassembly"] not in ("standard", "disabled") or type(value["debug"]) is not bool:
        raise ValueError("settings_type")
    if value["scope"] not in ("source", "youtube"):
        raise ValueError("scope")
    data = value["data_dir"]
    if (not isinstance(data, str) or not PurePosixPath(data).is_absolute()
            or any(c in data for c in "\r\n\x00")):
        raise ValueError("data_dir")
    return value


def secure_file(path, *, private=False, executable=False):
    if not path.is_absolute():
        raise ValueError("unsafe_path")
    # root-owned symlink на root-owned реальный файл безопасен: валидируется resolve()-путь
    # (отклонение от «без symlink»: установленный bundle /opt/xgw/zapret2/1.0.7 — symlink)
    path = Path(path).resolve(strict=True)
    target_isdir = stat.S_ISDIR(path.lstat().st_mode)
    items = [*reversed(path.parents), path]
    for idx, item in enumerate(items):
        info = item.lstat()
        is_last = idx == len(items) - 1
        want_dir = True if (not is_last or target_isdir) else False
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if want_dir else stat.S_ISREG(info.st_mode))):
            raise ValueError("unsafe_file")
    info = path.lstat()
    if private and stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("settings_permissions")
    if executable and not os.access(path, os.X_OK):
        raise ValueError("not_executable")


def scope_swap(block, scope):
    # ADAPTED_SCOPE=youtube: положительный фильтр блока (list-general / ipset-all)
    # заменяется точным набором YouTube-доменов; excludes и blob сохраняются (п.7.3/7.4).
    if scope != "youtube":
        return block
    out = []
    for arg in block:
        if arg.startswith(("--hostlist=", "--ipset=", "--hostlist-domains=")):
            continue
        out.append(arg)
    pos = 0
    for i, arg in enumerate(out):
        if arg.startswith(("--filter-tcp=", "--filter-udp=", "--filter-l7=")):
            pos = i + 1
    out.insert(pos, "--hostlist-domains=" + ",".join(YOUTUBE_SCOPE))
    return out


def _split_new(chain):
    out = [[]]
    for arg in chain:
        if arg == "--new":
            out.append([])
        else:
            out[-1].append(arg)
    return out


def build_arguments(incoming, settings):
    settings_check(settings)
    if len(incoming) < 5:
        raise ValueError("runtime_arguments")
    qnum, mark, lib, antidpi = incoming[:4]
    if not re.fullmatch(r"--qnum=[0-9]+", qnum) or not 1 <= int(qnum[7:]) <= 65535:
        raise ValueError("runtime_queue")
    if mark != "--fwmark=0x40000000":
        raise ValueError("runtime_mark")
    for arg, filename in ((lib, "zapret-lib.lua"), (antidpi, "zapret-antidpi.lua")):
        if not arg.startswith("--lua-init=@"):
            raise ValueError("runtime_lua")
        path = PurePosixPath(arg.removeprefix("--lua-init=@"))
        if not path.is_absolute() or path.name != filename:
            raise ValueError("runtime_lua")
    if not incoming[4].startswith("--filter-tcp="):
        raise ValueError("runtime_filter")
    preflight = incoming[-1] if incoming[-1] in ("--dry-run", "--intercept=0") else ""
    body = incoming[4:-1] if preflight else incoming[4:]
    allowed = ("--filter-tcp=", "--filter-udp=", "--filter-l7=", "--payload=",
               "--lua-desync=", "--blob=")
    if any(arg != "--new" and not arg.startswith(allowed) for arg in body):
        raise ValueError("runtime_option")
    if any(any(c in arg for c in "\r\n\x00") for arg in incoming):
        raise ValueError("runtime_character")

    prefix = str(PurePosixPath(settings["data_dir"])) + "/"
    args = [settings["binary"], qnum, mark, lib, antidpi,
            "--debug=1" if settings["debug"] else "--debug=0"]
    if settings["reassembly"] == "disabled":
        args.append("--reasm-disable=tls_client_hello")
    for i, block in enumerate(_split_new(CHAINS[settings["strategy"]])):
        block = scope_swap(block, settings["scope"])
        resolved = [a.replace("%LISTS%", prefix) for a in block]
        for a in resolved:
            for opt in ("--hostlist=", "--hostlist-exclude=", "--ipset=", "--ipset-exclude="):
                if a.startswith(opt) and a[len(opt):].startswith(prefix):
                    secure_file(Path(a[len(opt):]))
        if i:
            args.append("--new")
        args += resolved
    if preflight:
        args.append(preflight)
    return args


def main():
    if sys.argv[1:] == ["--list"]:
        print(json.dumps({cid: {"blocks": chain.count("--new") + 1}
                          for cid, chain in sorted(CHAINS.items())}, indent=2))
        return 0
    try:
        if os.geteuid() != 0:
            raise ValueError("root_required")
        script = Path(__file__).absolute()
        secure_file(script, executable=True)
        path = script.with_suffix(".json")
        secure_file(path, private=True)
        settings = settings_check(json.loads(path.read_text(encoding="utf-8")))
        binary = Path(settings["binary"])
        secure_file(binary, executable=True)
        if binary.samefile(script):
            raise ValueError("recursive_binary")
        data = Path(settings["data_dir"])
        secure_file(data)
        if stat.S_IMODE(data.lstat().st_mode) & 0o755 != 0o755:
            raise ValueError("data_permissions")
        args = build_arguments(sys.argv[1:], settings)
        for arg in args:
            if arg.startswith("--lua-init=@"):
                secure_file(Path(arg.removeprefix("--lua-init=@")))
        os.execv(str(binary), args)
    except (OSError, ValueError, TypeError):
        print("flowseal_lab: invalid or inaccessible settings/runtime files", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

launcher = (LAUNCHER_TEMPLATE
            .replace("@@CHAINS@@", json.dumps(chains, ensure_ascii=False, indent=1))
            .replace("@@SOURCE@@", json.dumps(src_compact, ensure_ascii=False, indent=1))
            .replace("@@BLOBS@@", json.dumps({cid: t["blob_decls"] for cid, t in translation["configurations"].items()},
                                             ensure_ascii=False, indent=1)))
(OUTDIR / "flowseal_lab.py").write_text(launcher, encoding="utf-8", newline="\n")
(OUTDIR / "translation.json").write_text(json.dumps(translation, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
import py_compile
try:
    py_compile.compile(str(OUTDIR / "flowseal_lab.py"), doraise=True)
except py_compile.PyCompileError as e:
    print(e, file=sys.stderr)
    sys.exit(1)
print("OK: translation.json + flowseal_lab.py written; chains:")
for cid, args in chains.items():
    print(f"  {cid}: {args.count('--new') + 1} blocks, {len(args)} args")
