"""The matched static/clone pair for the pinned zapret2 Lua runtime."""

from __future__ import annotations

LUA = """
assert(type(tls_mod_shim) == "function" and type(tls_client_hello_mod) == "function")
assert(type(rawsend_payload_segmented) == "function" and type(replay_first) == "function")
local samples = 0
local function report(source, outcome, reassembled)
    if samples >= 32 then return end
    samples = samples + 1
    DLOG_CONDUP("XGW_H05 n=" .. samples .. " source=" .. source ..
        " result=" .. outcome .. " reassembled=" .. (reassembled and 1 or 0))
    io.stdout:flush()
end

function xgw_h05_fake(ctx, desync)
    if not (desync.outgoing and desync.dis.tcp and
        desync.l7payload == "tls_client_hello" and replay_first(desync)) then return end
    local source = desync.arg.source
    local original = desync.reasm_data or desync.dis.payload
    local template
    if source == "static" then
        template = blob(desync, "fake_default_tls")
    elseif source == "clone" then
        template = tls_client_hello_mod(original, {})
    else
        error("xgw_h05_unknown_source", 0)
    end
    if not template then
        report(source, "no_template", desync.reasm_data)
        return
    end
    -- Upstream fake() calls tls_mod only when reasm_data exists.
    -- Apply the same mutations even for a ClientHello in a single packet.
    local modified = tls_mod_shim(desync, template, "rnd,rndsni", original)
    if type(modified) ~= "string" or #modified == 0 or
        modified == template or modified == original then
        report(source, "no_modified_fake", desync.reasm_data)
        return
    end
    local sent = rawsend_payload_segmented(desync, modified)
    report(source, sent and "sent" or "send_failed", desync.reasm_data)
    -- Continue with the same multisplit on the untouched original.
end
""".strip()


def arguments(source: str) -> list[str]:
    if source not in ("static", "clone"):
        raise ValueError("unknown_h05_source")
    return [f"--lua-init={LUA}", f"--lua-desync=xgw_h05_fake:source={source}:tcp_md5",
            "--lua-desync=multisplit:pos=1,midsld"]
