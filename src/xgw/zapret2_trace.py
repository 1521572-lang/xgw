"""Обезличенные свидетельства обработки служебного раунда nfqws2 v1.0.7.

Lua сохраняет алгоритм и verdict стратегии. Счётчик send_ok означает принятие
rawsend ядром, а не доставку серверу. Полный debug и содержимое пакетов не нужны.
"""

from __future__ import annotations

import json
import re

from .net import cmd

# Интерфейсы закреплены по bol-van/zapret2, v1.0.7 (038c97e5), lua/zapret-antidpi.lua
# и nfq2/lua.c. Считаем вызовы C rawsend_dissect только внутри выбранной стратегии.
LUA = """
assert(type(multisplit) == 'function' and type(multidisorder) == 'function')
assert(type(rawsend_dissect) == 'function' and type(replay_first) == 'function')
local sequence = 0
function xgw_trace(ctx, desync)
    local strategy = desync.arg.strategy
    local original = strategy == 'multisplit' and multisplit or
        strategy == 'multidisorder' and multidisorder
    if not original then error('xgw_trace_strategy', 0) end
    local hello = desync.l7payload == 'tls_client_hello' and
        desync.outgoing and replay_first(desync)
    local calls, sent = 0, 0
    local send = rawsend_dissect
    rawsend_dissect = function(...)
        calls = calls + 1
        local ok = send(...)
        if ok then sent = sent + 1 end
        return ok
    end
    local ok, verdict = pcall(original, ctx, desync)
    rawsend_dissect = send
    sequence = sequence + 1
    if sequence <= 64 then
        local applied = ok and hello and verdict == VERDICT_DROP and
            sent >= 2 and sent == calls
        DLOG_CONDUP('XGW_Z2_TRACE seq=' .. sequence ..
            ' hello=' .. (hello and 1 or 0) .. ' send_calls=' .. calls ..
            ' send_ok=' .. sent .. ' applied=' .. (applied and 1 or 0) ..
            ' lua_errors=' .. (ok and 0 or 1))
    elseif sequence == 65 then
        DLOG_CONDUP('XGW_Z2_TRACE LIMIT')
    end
    io.stdout:flush()
    if not ok then error('xgw_trace_strategy_failed', 0) end
    return verdict
end
DLOG_CONDUP('XGW_Z2_TRACE READY')
io.stdout:flush()
""".strip()

# Проверяется на установленном nfqws2 с --intercept=0 до замены кода шлюза.
# Все отправки заменены заглушкой; тест не создаёт очередь и не посылает пакеты.
SELFTEST = """
local log, send, first = DLOG_CONDUP, rawsend_dissect, replay_first
local split, disorder = multisplit, multidisorder
local messages, count = {}, 0
DLOG_CONDUP = function(s) messages[#messages+1] = s end
local fake_send = function(value) count = count + 1; return value end
rawsend_dissect = fake_send
replay_first = function() return true end
local dis = {arg={strategy='multisplit'}, l7payload='tls_client_hello', outgoing=true}
multisplit = function(ctx, d)
    assert(ctx == 7 and d == dis)
    assert(rawsend_dissect(true) and rawsend_dissect(true))
    return VERDICT_DROP
end
assert(xgw_trace(7, dis) == VERDICT_DROP and count == 2)
assert(rawsend_dissect == fake_send)
assert(messages[#messages]:find('applied=1', 1, true))
multisplit = function() assert(not rawsend_dissect(false)); return VERDICT_PASS end
assert(xgw_trace(7, dis) == VERDICT_PASS and rawsend_dissect == fake_send)
multisplit = function() error('private_error', 0) end
local ok, err = pcall(xgw_trace, 7, dis)
assert(not ok and err == 'xgw_trace_strategy_failed' and rawsend_dissect == fake_send)
assert(messages[#messages]:find('lua_errors=1', 1, true))
multidisorder = function() return nil end
dis.arg.strategy = 'multidisorder'
assert(xgw_trace(7, dis) == nil and rawsend_dissect == fake_send)
for i=1,70 do xgw_trace(7, dis) end
assert(#messages == 65 and messages[65] == 'XGW_Z2_TRACE LIMIT')
DLOG_CONDUP, rawsend_dissect, replay_first = log, send, first
multisplit, multidisorder = split, disorder
DLOG_CONDUP('XGW_Z2_SELFTEST OK')
io.stdout:flush()
""".strip()

FIELDS = ("hello", "send_calls", "send_ok", "applied", "lua_errors")
_ROW = re.compile(r"LUA: XGW_Z2_TRACE seq=(\d{1,3}) hello=([01]) "
                  r"send_calls=(\d{1,6}) send_ok=(\d{1,6}) applied=([01]) lua_errors=([01])")


def parse(text: str) -> dict:
    """Принимает только собственные строки. Чужой текст никогда не возвращается."""
    result = dict.fromkeys(FIELDS, 0)
    ready, complete, sequence = False, True, 0
    for line in text.splitlines():
        if line == "LUA: XGW_Z2_TRACE READY":
            complete = complete and not ready and not sequence
            ready = True
        elif match := _ROW.fullmatch(line):
            seq, hello, calls, sent, applied, errors = map(int, match.groups())
            complete = complete and ready and seq == sequence + 1 and seq <= 64
            if (sent > calls or applied > hello
                    or (applied and (sent < 2 or sent != calls or errors))):
                complete = False
            sequence = seq
            for key, value in zip(FIELDS, (hello, calls, sent, applied, errors), strict=True):
                result[key] += value
        elif line.startswith("LUA: XGW_Z2_TRACE"):
            complete = False  # лимит, неизвестная версия или повреждённая строка
    return {"state": "observed" if ready and complete else "incomplete", **result}


class Evidence:
    def __init__(self, runner, unit: str, queue: int):
        self.runner, self.unit, self.queue = runner, unit, queue
        self.invocation = ""
        self.before = self.delta = -1

    def packets(self) -> int:
        try:
            data = json.loads(self.runner(
                ["nft", "-j", "list", "chain", "inet", "xgw_guard", "zapret2_queue"],
                timeout=3))
            counts = []
            for entry in data.get("nftables", []):
                expr = entry.get("rule", {}).get("expr", [])
                if any(e.get("queue", {}).get("num") == self.queue for e in expr):
                    counts += [e["counter"]["packets"] for e in expr if "counter" in e]
            if len(counts) == 1 and type(counts[0]) is int and counts[0] >= 0:
                return counts[0]
        except (cmd.CommandError, OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return -1

    def begin(self) -> None:
        try:
            invocation = self.runner(
                ["systemctl", "show", self.unit, "-p", "InvocationID", "--value"], timeout=3
            ).strip()
            if re.fullmatch(r"[0-9a-f]{32}", invocation):
                self.invocation = invocation
        except (cmd.CommandError, OSError, ValueError):
            pass
        self.before = self.packets()

    def sample(self) -> None:
        after = self.packets()
        if 0 <= self.before <= after:
            self.delta = after - self.before

    def finish(self) -> dict:
        result = {"state": "unavailable", **dict.fromkeys(FIELDS, 0)}
        if self.invocation:
            try:
                # После остановки worker; синхронизация не даёт принять пустой журнал за успех.
                self.runner(["journalctl", "--sync"], timeout=3)
                result = parse(self.runner([
                    "journalctl", "--boot", "--no-pager", "-o", "cat", "-n", "128",
                    "_SYSTEMD_INVOCATION_ID=" + self.invocation,
                ], timeout=3))
            except (cmd.CommandError, OSError, ValueError):
                pass
        if self.delta < 0 and result["state"] == "observed":
            result["state"] = "incomplete"
        return {**result, "queue_packets": self.delta}
