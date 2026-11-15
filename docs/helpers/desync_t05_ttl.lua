-- Lab only. Run before the chosen strategy on outgoing ClientHello.
assert(type(autottl) == "function" and type(replay_first) == "function")
local ttl_options = parse_autottl("-1,1-20")
local count = 0

function xgw_ttl_observe(ctx, desync)
    if not desync.outgoing or desync.l7payload ~= "tls_client_hello" or
        not replay_first(desync) or count >= 32 then return end
    local received = desync.track and desync.track.incoming_ttl
    local expected = received and autottl(received, ttl_options)
    count = count + 1
    DLOG_CONDUP("XGW_T05_TTL hello=" .. count ..
        " track_ttl=" .. (received or 0) .. " predicted=" .. (expected or 0))
    io.stdout:flush()
end
