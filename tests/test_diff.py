"""Тесты сравнения конфигов: путь API против полного перезапуска (ТЗ 6.7/9)."""

from test_generator import _build

from xgw.generator.diff import apply_plan, diff_configs


def _current():
    result, _cfg, _sel = _build()
    return result.config


def test_identical_configs_unchanged():
    config = _current()
    diff = diff_configs(config, json_copy(config))
    assert not diff.changed
    assert diff.plan is not None


def json_copy(payload):
    import json

    return json.loads(json.dumps(payload))


def test_new_outbound_and_probe_go_through_api():
    old = _current()
    new = json_copy(old)
    extra = json_copy(new["outbounds"][0])
    extra["tag"] = "proxy-xx-deadbeef"
    new["outbounds"].insert(0, extra)
    probe = json_copy(new["inbounds"][3])
    probe["tag"] = "probe-xx-deadbeef"
    probe["port"] = 20999
    new["inbounds"].append(probe)
    new["routing"]["rules"].insert(
        0,
        {"type": "field", "inboundTag": ["probe-xx-deadbeef"], "outboundTag": "proxy-xx-deadbeef"},
    )
    diff = diff_configs(old, new)
    assert diff.plan is not None
    added_tags = [outbound["tag"] for outbound in diff.plan.add_outbounds]
    assert added_tags == ["proxy-xx-deadbeef"]
    assert [inbound["tag"] for inbound in diff.plan.add_inbounds] == ["probe-xx-deadbeef"]
    assert diff.plan.routing is not None
    assert diff.plan.remove_outbound_tags == []
    assert diff.restart_reasons == []


def test_removed_outbound_is_rmo():
    old = _current()
    new = json_copy(old)
    removed = new["outbounds"].pop(0)  # участник
    probe_tag = "probe-" + removed["tag"].split("-", 1)[1]
    new["inbounds"] = [i for i in new["inbounds"] if i["tag"] != probe_tag]
    new["routing"]["rules"] = [
        rule for rule in new["routing"]["rules"]
        if rule.get("outboundTag") != removed["tag"]
    ]
    diff = diff_configs(old, new)
    assert diff.plan.remove_outbound_tags == [removed["tag"]]
    assert diff.plan.remove_inbound_tags


def test_dns_change_requires_restart():
    old = _current()
    new = json_copy(old)
    new["dns"]["servers"].append("9.9.9.9")
    diff = diff_configs(old, new)
    assert diff.plan is None
    assert "секция dns" in diff.restart_reasons


def test_dns_hosts_change_alone_does_not_require_restart():
    """Раздел 6.4: домен сервера, добавленного через API, попадает в hosts при
    следующем перезапуске — сам по себе перезапуска не требует."""
    old = _current()
    new = json_copy(old)
    new["dns"]["hosts"]["extra.example.com"] = ["203.0.113.99"]
    diff = diff_configs(old, new)
    assert diff.plan is not None and diff.plan.empty
    assert diff.restart_reasons == []
    assert diff.changed  # конфиг на диске обновить нужно
    assert any("dns.hosts" in note for note in diff.deferred)


def test_changed_outbound_and_probe_are_replaced():
    """Тег тот же, содержимое другое — старый обработчик снимается, ставится новый."""
    old = _current()
    new = json_copy(old)
    new["outbounds"][0]["streamSettings"]["tlsSettings"] = {"serverName": "changed.example.org"}
    new["inbounds"][3]["port"] = 20777
    diff = diff_configs(old, new)
    assert diff.changed and diff.restart_reasons == []
    assert [o["tag"] for o in diff.plan.replace_outbounds] == [new["outbounds"][0]["tag"]]
    assert [i["tag"] for i in diff.plan.replace_inbounds] == [new["inbounds"][3]["tag"]]
    assert diff.plan.add_outbounds == [] and diff.plan.remove_outbound_tags == []

    client = _RecordingClient()
    apply_plan(client, diff.plan)
    probe_tag, proxy_tag = new["inbounds"][3]["tag"], new["outbounds"][0]["tag"]
    assert client.calls == [f"rmi:{probe_tag}", "adi", f"rmo:{proxy_tag}", "ado"]


def test_static_outbound_change_requires_restart():
    """direct/block/dns-out — каркас: через них идёт служебный трафик ядра."""
    old = _current()
    new = json_copy(old)
    direct = next(o for o in new["outbounds"] if o["tag"] == "direct")
    direct["streamSettings"]["sockopt"]["mark"] = 7
    diff = diff_configs(old, new)
    assert diff.plan is None and "основные outbounds" in diff.restart_reasons


def test_burst_observatory_change_requires_restart():
    old = _current()
    new = json_copy(old)
    new["burstObservatory"]["pingConfig"]["interval"] = "60s"
    diff = diff_configs(old, new)
    assert diff.plan is None and diff.restart_reasons


def test_main_inbound_change_requires_restart():
    old = _current()
    new = json_copy(old)
    new["inbounds"][1]["port"] = 10818  # socks-in
    diff = diff_configs(old, new)
    assert diff.plan is None
    assert "основные inbounds" in diff.restart_reasons


def test_policy_change_requires_restart():
    old = _current()
    new = json_copy(old)
    new["policy"]["levels"]["0"]["connIdle"] = 300
    diff = diff_configs(old, new)
    assert diff.plan is None and "секция policy" in diff.restart_reasons


class _RecordingClient:
    def __init__(self):
        self.calls: list[str] = []

    def add_inbounds(self, inbounds):
        self.calls.append("adi")

    def add_outbounds(self, outbounds):
        self.calls.append("ado")

    def replace_routing(self, routing, *, append=False):
        self.calls.append("adrules")

    def remove_outbound(self, tag):
        self.calls.append(f"rmo:{tag}")

    def remove_inbound(self, tag):
        self.calls.append(f"rmi:{tag}")


def test_apply_plan_order_adi_ado_adrules_then_removals():
    client = _RecordingClient()
    from xgw.generator.diff import ApiPlan

    ops = apply_plan(
        client,
        ApiPlan(
            add_inbounds=[{"tag": "probe-a"}],
            add_outbounds=[{"tag": "proxy-a"}],
            routing={"rules": []},
            remove_outbound_tags=["proxy-b"],
            remove_inbound_tags=["probe-b"],
        ),
    )
    assert client.calls == ["adi", "ado", "adrules", "rmo:proxy-b", "rmi:probe-b"]
    assert len(ops) == 5
