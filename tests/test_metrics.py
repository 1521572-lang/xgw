"""Разбор /debug/vars: observatory alive/delay по outbound-тегам.

Формат сверен с живым Xray 26.3.27 (см. docstring модуля metrics).
"""

from xgw.xraycore.metrics import parse_duration, parse_observatory

REAL_SHAPE = {
    "observatory": {
        "proxy-a": {
            "alive": True,
            "delay": 4,
            "outbound_tag": "proxy-a",
            "health_ping": {"all": 2, "deviation": 209000, "average": 4809600,
                            "max": 5018600, "min": 4600600},
        },
        "proxy-b": {
            "outbound_tag": "proxy-b",
            "health_ping": {"all": 2, "fail": 2},
        },
    }
}


def test_real_shape_alive_and_delay():
    parsed = parse_observatory(REAL_SHAPE)
    assert parsed["proxy-a"] == {"alive": True, "delay": 0.004}
    assert parsed["proxy-b"] == {"alive": False, "delay": None}


def test_delay_from_average_when_missing():
    metrics = {"observatory": {"x": {"health_ping": {"all": 1, "average": 5_000_000}}}}
    parsed = parse_observatory(metrics)
    assert parsed["x"] == {"alive": False, "delay": 0.005}


def test_string_encoded_section_tolerated():
    import json

    metrics = {"observatory": json.dumps({"p": {"alive": True, "delay": "300ms"}})}
    parsed = parse_observatory(metrics)
    assert parsed["p"] == {"alive": True, "delay": 0.3}


def test_missing_section():
    assert parse_observatory({"stats": {}}) == {}


def test_parse_duration_units():
    assert parse_duration("500ms") == 0.5
    assert parse_duration(250) == 0.25  # delay в миллисекундах
    assert parse_duration(4_809_600, unit_ms=False) == 0.0048096  # average в наносекундах
    assert parse_duration("2s") == 2.0
    assert parse_duration("мусор") is None


def test_count_members_separates_unknown_from_dead():
    from xgw.xraycore.metrics import count_members

    observatory = parse_observatory(REAL_SHAPE)
    # proxy-a жив, proxy-b мёртв, proxy-c ядро ещё не проверяло; spare-* не считаются
    assert count_members(observatory, ["proxy-a", "proxy-b", "proxy-c"]) == (1, 1, 1)
    assert count_members({}, ["proxy-a", "proxy-b"]) == (0, 0, 2)
