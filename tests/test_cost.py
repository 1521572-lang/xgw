"""Стоимость серверов: лимит подписки, множитель расхода в имени, классы (cost.py)."""

import pytest

from xgw import cost
from xgw.config import Config
from xgw.model import ServerNode

PATTERN = cost.DEFAULT_MULTIPLIER_REGEX


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Имена серверов из подписки пользователя (вид из его VPN-клиента).
        ("🇳🇱 x10📶🛜 Нидерланды 🚀🚀 | AI", 10.0),
        ("x10 🛜 Европа 🚀🚀 АВТО", 10.0),
        ("x10 🛜 Германия 🚀🚀 АВТО", 10.0),
        ("🇩🇪 x100 обход белых списков LTE", 100.0),
        ("Германия x1", 1.0),
        ("х10 Германия", 10.0),  # кириллическая «х»
        ("×2 Франция", 2.0),
        ("X3 Finland", 3.0),
        ("x 5 Швеция", 5.0),
        ("x0.5 эконом", 0.5),
        ("x1,5 Польша", 1.5),
        ("x0 бесплатный", 0.0),
        ("Нидерланды", 1.0),  # без отметки — x1
        ("Box10 Латвия", 1.0),  # «x» внутри слова — не множитель
        ("xray-x2ray", 1.0),
        ("NL-x2", 2.0),
        ("", 1.0),
    ],
)
def test_multiplier_is_read_from_the_server_name(name, expected):
    assert cost.multiplier(name, PATTERN) == expected


def test_multiplier_pattern_is_configurable_and_can_be_switched_off():
    assert cost.multiplier("10x Германия", r"(\d+)x") == 10.0
    assert cost.multiplier("x10 Германия", "") == 1.0
    assert cost.multiplier("x10 Германия", None) == 1.0
    assert cost.multiplier("x10 Германия", r"x\d+") == 1.0  # без группы числа не прочесть
    assert Config().filters.multiplier_regex == PATTERN


def test_limited_subscriptions_are_those_with_a_traffic_total():
    quotas = {
        "limited": {"upload": 1, "download": 2, "total": 3 * 10**12},
        "unlimited": {"upload": 1, "download": 2, "total": 0},
        "expire-only": {"expire": 1_900_000_000},
        "broken": "нет",
    }
    assert cost.limited_sources(quotas) == {"limited"}
    assert cost.limited_sources({}) == set()


def _node(fingerprint: str, name: str, source: str, keep_tag: str | None = None) -> ServerNode:
    return ServerNode(fingerprint, name, "nl", "vless", "203.0.113.1", 443, {}, source,
                      keep_tag=keep_tag)


def test_costs_zero_for_unlimited_and_the_multiplier_for_limited():
    nodes = [
        _node("aaaa0000", "x10 Германия", "paid"),
        _node("bbbb0000", "x10 Германия", "free"),  # безлимит: множитель не в счёт
        _node("cccc0000", "Нидерланды", "paid"),
        _node("dddd0000", "x100 LTE", "manual"),  # ручные ссылки — безлимитные
        _node("eeee0000", "звено", "paid", keep_tag="chain-1"),
        # Тот же сервер в двух подписках: берётся дешёвый.
        _node("ffff0000", "x10 Финляндия", "paid"),
        _node("ffff0000", "x10 Финляндия", "free"),
    ]
    quotas = {"paid": {"total": 10**12}, "free": {"total": 0}}
    prices = cost.costs(nodes, quotas, PATTERN)
    assert prices == {
        "aaaa0000": 10.0, "bbbb0000": 0.0, "cccc0000": 1.0, "dddd0000": 0.0, "ffff0000": 0.0,
    }


def test_classes_put_priority_before_cost():
    prices = {"free": 0.0, "x1": 1.0, "x10": 10.0}
    levels = {"x10": "high"}
    assert cost.klass(levels, prices, "free") == cost.Klass(1, 0.0)
    assert cost.klass(levels, prices, "x10") == cost.Klass(0, 10.0)
    assert cost.klass(levels, prices, "unknown") == cost.Klass(1, 1.0)
    assert cost.best(levels, prices, ["free", "x1", "x10"]) == cost.Klass(0, 10.0)
    assert cost.best({}, prices, ["x1", "free"]) == cost.Klass(1, 0.0)
    assert cost.best({}, prices, []) is None
    assert sorted([cost.Klass(1, 10.0), cost.Klass(1, 0.0), cost.Klass(2, 0.0),
                   cost.Klass(1, 1.0)]) == [
        cost.Klass(1, 0.0), cost.Klass(1, 1.0), cost.Klass(1, 10.0), cost.Klass(2, 0.0)]


def test_labels():
    assert [cost.label(value) for value in (1.0, 10.0, 100.0, 0.5, 1.25)] == [
        "x1", "x10", "x100", "x0.5", "x1.25"]
    assert cost.describe(0.0) == "безлимит" and cost.describe(10.0) == "x10"
    assert cost.class_name(cost.Klass(1, 0.0), False) == "безлимитные серверы"
    assert cost.class_name(cost.Klass(2, 10.0), True) == (
        "лимитированные серверы x10 уровня «низкий»")


def test_bad_multiplier_pattern_is_reset_with_a_warning(tmp_path):
    from xgw import config

    path = tmp_path / "config.toml"
    path.write_text('[filters]\nmultiplier_regex = "(x"\n', encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.filters.multiplier_regex == PATTERN
    assert any("multiplier_regex" in warning for warning in warnings)
