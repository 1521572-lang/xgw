"""Бесплатный пул (docs/FREEPOOL-PLAN.md): регионы, разбор профилей OpenVPN как недоверенного
языка, разбор ответов источников по очищенным настоящим образцам (tests/fixtures/freepool,
28.10.2026)."""

import base64
import json
from pathlib import Path

import links
import pytest

from xgw import config, managed
from xgw.freepool import ovpn, providers, regions
from xgw.freepool.models import Access, Backend, Status

FIXTURES = Path(__file__).parent / "fixtures" / "freepool"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- регионы ----------------------------------------------------------------------------------


def test_regions_follow_the_eu_list_and_un_m49():
    """EU — 27 стран ЕС (без Великобритании, Норвегии, Швейцарии, России, Турции); US — только
    США; ASIA — M49 и явное расширение TW. Группы пересекаются (Кипр)."""
    assert len(regions.EU) == 27
    for country in ("GB", "NO", "CH", "RU", "TR"):
        assert "EU" not in regions.regions_of(country)
    assert regions.regions_of("ca") == [] and regions.regions_of("US") == ["US"]
    assert regions.regions_of("CY") == ["EU", "ASIA"]
    assert regions.allowed("JP", "ASIA") and regions.allowed("TW", "ASIA")
    assert regions.allowed("DE", "auto") and not regions.allowed("BR", "auto")
    assert not regions.allowed("", "EU")


# --- профиль OpenVPN --------------------------------------------------------------------------


def test_real_profile_becomes_a_typed_description():
    """Настоящий профиль VPNBook: TCP, AES-256-GCM, нужен общий пароль; маршруты и DNS от
    провайдера — пометка «управляет XGW», не переносятся."""
    profile = ovpn.parse(_fixture("vpnbook-profile.ovpn"))
    assert profile.remotes[0].proto == "tcp" and profile.remotes[0].port == 443
    assert profile.ciphers[0] == "AES-256-GCM" and profile.auth == "SHA256"
    assert profile.needs_password and not profile.legacy_crypto
    assert "redirect-gateway" in profile.managed and "route-delay" in profile.managed
    assert profile.ca.startswith("-----BEGIN CERTIFICATE-----")


def _base() -> str:
    return _fixture("vpnbook-profile.ovpn")


@pytest.mark.parametrize("line, reason", [
    ("up /etc/evil.sh", "запрещена"),
    ("script-security 2", "запрещена"),
    ("plugin /usr/lib/x.so", "запрещена"),
    ("management 127.0.0.1 7505", "запрещена"),
    ("config other.conf", "запрещена"),
    ("auth-user-pass /etc/shadow", "путь к файлу"),
    ("ca /etc/ssl/ca.pem", "путь к файлу"),
    ("comp-lzo", "сжатие"),
    ("compress lz4", "сжатие"),
    ("socks-proxy 10.0.0.1 1080", "запрещена"),
    ("setenv FOO bar", "запрещена"),
    ("dev tap0", "dev tun"),
    ("totally-unknown-option 1", "неизвестная директива"),
])
def test_dangerous_or_unknown_directives_reject_the_profile(line, reason):
    """Профиль — недоверенный язык (R47): исполняемое, управление, пути, сжатие, прокси и
    неизвестное отклоняют профиль целиком, а не «чистятся»."""
    with pytest.raises(ovpn.OvpnRejected, match=reason):
        ovpn.parse(_base().replace("client\n", f"client\n{line}\n", 1))


def test_crypto_blocks_and_shape_are_checked():
    base = _base()
    with pytest.raises(ovpn.OvpnRejected, match="шифр BF-CBC"):
        ovpn.parse(base.replace("cipher AES-256-GCM", "cipher BF-CBC"))
    with pytest.raises(ovpn.OvpnRejected, match="нет <ca>"):
        ovpn.parse(base[:base.index("<ca>")] + base[base.index("</ca>") + 5:])
    with pytest.raises(ovpn.OvpnRejected, match="встроенный блок <connection>"):
        ovpn.parse(base + "<connection>\nremote 198.51.100.9 443\n</connection>\n")
    with pytest.raises(ovpn.OvpnRejected, match="не клиентский"):
        ovpn.parse(base.replace("client\n", "", 1))
    with pytest.raises(ovpn.OvpnRejected, match="256 КиБ"):
        ovpn.parse(base + "#" * (300 * 1024))
    two = ovpn.parse(base.replace("remote 198.51.100.30 443",
                                  "remote 198.51.100.30 443\nremote 198.51.100.31 53 udp"))
    assert [(r.host, r.port, r.proto) for r in two.remotes] == [
        ("198.51.100.30", 443, "tcp"), ("198.51.100.31", 53, "udp")]


# --- VPN Gate ---------------------------------------------------------------------------------


def test_vpngate_csv_gives_openvpn_variants_with_hints():
    """CSV VPN Gate: маркер, заголовок, строки, замыкающая «*»; страна и показатели каталога —
    подсказки; каталог частичный (authoritative = False)."""
    result = providers.parse_vpngate(_fixture("vpngate.csv"), now=1000.0)
    assert result.status is Status.SUCCESS and result.complete_response
    assert not result.authoritative and result.rejected == 0
    assert len(result.variants) == 5
    first = result.variants[0]
    assert first.backend == Backend.OPENVPN and first.access == Access.FREE
    assert first.address.startswith("198.51.100.") and first.transport in ("tcp", "udp")
    assert dict(first.hints).keys() >= {"ping_ms", "speed_mbps", "score", "sessions"}
    assert first.profile is not None and first.profile.legacy_crypto  # AES-128-CBC + SHA1
    assert len(first.variant_id) == 32 and first.endpoint_id.startswith("vpngate|198.51.100.")
    assert len({variant.variant_id for variant in result.variants}) == 5


def test_vpngate_answer_with_crlf_lines_like_the_real_api():
    """Настоящий ответ API — строки CRLF (образец в репозитории хранится с LF)."""
    plain = providers.parse_vpngate(_fixture("vpngate.csv"), now=1.0)
    crlf = providers.parse_vpngate(_fixture("vpngate.csv").replace("\n", "\r\n"), now=1.0)
    assert crlf.status is Status.SUCCESS and crlf.complete_response
    assert [item.variant_id for item in crlf.variants] == [
        item.variant_id for item in plain.variants]


def test_vpngate_schema_drift_and_truncation_are_told_apart():
    text = _fixture("vpngate.csv")  # read_text: CRLF ответа уже стал \n
    truncated = providers.parse_vpngate(text.replace("\n*\n", "\n"), now=0)
    assert truncated.status is Status.PARTIAL and len(truncated.variants) == 5
    assert providers.parse_vpngate(text.replace("*vpn_servers", "<html>"), now=0).status \
        is Status.SCHEMA_CHANGED
    no_column = providers.parse_vpngate(text.replace("CountryShort", "Country_S"), now=0)
    assert no_column.status is Status.SCHEMA_CHANGED and "CountryShort" in no_column.detail
    lines = text.split("\n")
    broken = lines[2].rsplit(",", 1)[0] + ",!!!not-base64!!!"
    damaged = providers.parse_vpngate("\n".join([*lines[:2], broken, *lines[3:]]), now=0)
    assert damaged.rejected == 1 and len(damaged.variants) == 4


def test_vpngate_profile_with_a_script_is_rejected_alone():
    text = _fixture("vpngate.csv")
    lines = text.split("\n")
    row = lines[2].rsplit(",", 1)
    profile = base64.b64decode(row[1]).decode()
    evil = base64.b64encode(profile.replace("client\n", "client\nup /tmp/x.sh\n").encode())
    lines[2] = row[0] + "," + evil.decode()
    result = providers.parse_vpngate("\n".join(lines), now=0)
    assert result.rejected == 1 and len(result.variants) == 4
    assert any("запрещена" in reason for reason in result.rejections)


# --- VPNBook ----------------------------------------------------------------------------------


def test_vpnbook_openvpn_page_gives_servers_and_the_shared_account():
    """Страница Next.js: серверы из данных страницы, по варианту на каждый протокол кнопки
    «Download», общая учётка; профиль — официальным запросом /api/openvpn."""
    result = providers.parse_vpnbook_openvpn(_fixture("vpnbook-openvpn.html"), now=0)
    assert result.status is Status.SUCCESS and result.authoritative
    servers = {dict(variant.extra)["server_id"] for variant in result.variants}
    assert len(result.variants) == 4 * len(servers) and len(servers) >= 6
    assert {variant.needs for variant in result.variants} == {"profile"}
    account = result.credentials["vpnbook"]
    assert account["username"] == "vpnbook" and account["password"] == "FakePass9"
    assert account["updated"] == "Oct 24, 2026"
    query = providers.vpnbook_profile_query(result.variants[0])
    assert query["protocol"] in providers.VPNBOOK_PROTOCOLS
    assert query["hostname"].endswith(".vpnbook.example")


def test_vpnbook_outline_keys_become_xray_shadowsocks():
    result = providers.parse_vpnbook_outline(_fixture("vpnbook-outline.html"), now=0)
    assert result.status is Status.SUCCESS and len(result.variants) == 3
    assert {variant.backend for variant in result.variants} == {Backend.XRAY}
    assert {variant.outbound["protocol"] for variant in result.variants} == {"shadowsocks"}
    assert {variant.country_hint for variant in result.variants} == {"PL", "CA"}


def test_vpnbook_page_without_data_is_schema_changed():
    assert providers.parse_vpnbook_openvpn("<html>maintenance</html>", now=0).status \
        is Status.SCHEMA_CHANGED
    assert providers.parse_vpnbook_outline("<html></html>", now=0).status \
        is Status.SCHEMA_CHANGED


# --- сбор через несущий канал и сводка (pool.py) ---------------------------------------------


class _Fetcher:
    """Подставной fetch.fetch_url: адрес → (код, тело, адрес после перенаправлений)."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls: list[tuple[str, object]] = []

    def __call__(self, url, **kwargs):
        from xgw.fetch import FetchError, FetchResult

        self.calls.append((url, kwargs.get("proxy")))
        page = self.pages.get(url)
        if page is None:
            raise FetchError("нет ответа")
        status, body, final = page if len(page) == 3 else (*page, url)
        return FetchResult(status=status, headers={}, body=body.encode("utf-8"), url=final)


def _pool(tmp_path, pages, **cfg_values):
    from xgw.config import Config
    from xgw.freepool.pool import FreePool
    from xgw.paths import Paths

    paths = Paths(root=tmp_path)
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    for name, value in cfg_values.items():
        setattr(cfg.free_pool, name, value)
    fetcher = _Fetcher(pages)
    clock = [1_800_000_000.0]
    pool = FreePool(cfg, paths, fetcher=fetcher, clock=lambda: clock[0], sleep=lambda s: None)
    return pool, fetcher, clock


def _pages():
    return {
        providers.VPNGATE_URL: (200, _fixture("vpngate.csv")),
        providers.VPNBOOK_OPENVPN_URL: (200, _fixture("vpnbook-openvpn.html")),
        providers.VPNBOOK_OUTLINE_URL: (200, _fixture("vpnbook-outline.html")),
    }


def test_catalogs_go_through_the_carrier_and_land_in_snapshots(tmp_path):
    """Каталоги — через несущий канал (http-in Xray подписки): proxy у каждого запроса; снимки
    обоих источников."""
    pool, fetcher, _clock = _pool(tmp_path, _pages())
    via = ("127.0.0.1", 10809)
    results = pool.refresh_due(via=via, mark=2)
    assert [result.status for result in results] == [Status.SUCCESS] * 2
    assert {proxy for _url, proxy in fetcher.calls} == {via}
    assert len(pool.store.variants("vpngate")) == 5
    book = pool.store.variants("vpnbook")
    assert {variant.backend for variant in book} == {Backend.OPENVPN, Backend.XRAY}
    assert pool.store.secrets()["shared"]["vpnbook"]["username"] == "vpnbook"
    summary = pool.summary()
    assert summary["found"] == len(pool.variants())
    assert {source["status"] for source in summary["sources"]} == {"SUCCESS"}
    assert "FakePass9" not in str(summary)  # секреты в сводку не попадают
    assert pool.refresh_due(via=via, mark=2) == []  # рано: интервал не прошёл


def test_foreign_host_or_failure_keeps_the_last_good_snapshot(tmp_path):
    """Ответ после перенаправления с чужого хоста не принимается; источник не ответил —
    прежний снимок остаётся, следующая попытка — после паузы."""
    pool, _fetcher, clock = _pool(tmp_path, _pages(), providers=["vpngate"])
    pool.refresh_due(via=None, mark=2)
    assert len(pool.store.variants("vpngate")) == 5
    clock[0] += 3600
    pool.fetcher.pages[providers.VPNGATE_URL] = (200, _fixture("vpngate.csv"),
                                                 "https://evil.example/api/iphone/")
    [result] = pool.refresh_due(via=None, mark=2)
    assert result.status is Status.SCHEMA_CHANGED and "чужого хоста" in result.detail
    assert len(pool.store.variants("vpngate")) == 5
    clock[0] += 3600
    del pool.fetcher.pages[providers.VPNGATE_URL]
    [result] = pool.refresh_due(via=None, mark=2)
    assert result.status is Status.UNAVAILABLE and len(pool.store.variants("vpngate")) == 5
    assert pool.next_refresh["vpngate"] - clock[0] < 2 * 60 * 1.3  # пауза после 2-й ошибки
    assert pool.summary()["sources"][0]["status"] == "UNAVAILABLE"


def test_checks_prefer_the_wanted_region_and_respect_the_budget(tmp_path, monkeypatch):
    """Сначала варианты с подсказкой нужного региона; OpenVPN до бэкенда — только TCP к адресу;
    бюджет суток исчерпан — проверок нет."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool.probe import Outcome

    pool, _fetcher, _clock = _pool(tmp_path, _pages(), region="ASIA", checks_per_step=3)
    pool.refresh_due(via=None, mark=2)
    first = pool.next_checks(3)
    assert all(regions.allowed(variant.country_hint, "ASIA") for variant in first)
    seen: list[str] = []
    monkeypatch.setattr(pool_module.probing, "check_openvpn_reach",
                        lambda variant, mark: seen.append(variant.variant_id)
                        or Outcome("REACHABLE", 0.1))
    monkeypatch.setattr(pool_module.probing, "check_xray",
                        lambda variant, cfg, xray_bin, run: Outcome("OK", 0.4, 600_000, "PL"))
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 3
    assert pool.summary()["reachable_openvpn"] == 3
    pool.cfg.free_pool.budget_mb = 64
    pool.cfg.free_pool.health_reserved_mb = 64  # на проверки ничего не остаётся
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 0


# --- режим и ссылки: config.toml, panel.json, xgw pool -----------------------------------------


def test_panel_mode_lies_over_config_toml(tmp_path):
    """Режим из панели (panel.json) сильнее config.toml; неизвестный режим не записывается;
    ссылки VPNJantit, вставленные в панель вехи М1, при загрузке отбрасываются."""
    path = tmp_path / "config.toml"
    path.write_text('[free_pool]\nmode = "off"\nregion = "US"\n', encoding="utf-8")
    store = managed.path_for(path)
    store.write_text(json.dumps({"free_pool_links": [links.TROJAN]}), encoding="utf-8")
    assert managed.set_free_pool_mode(store, "observe") is True
    assert managed.set_free_pool_mode(store, "observe") is False
    cfg, warnings = config.load(path)
    assert (cfg.free_pool.mode, cfg.free_pool.region) == ("observe", "US") and warnings == []
    assert "free_pool_links" not in json.loads(store.read_text(encoding="utf-8"))
    with pytest.raises(managed.ManagedError):
        managed.set_free_pool_mode(store, "turbo")


def test_vpnjantit_settings_are_retired(tmp_path):
    """VPNJantit убран (28.10.2026): его ключ и имя в providers — не «неизвестные», а убранные;
    снимки его списков, оставшиеся с вехи М1, удаляются с диска."""
    from xgw.freepool.pool import FreePool
    from xgw.freepool.store import root
    from xgw.paths import Paths

    path = tmp_path / "config.toml"
    path.write_text('[free_pool]\nproviders = ["vpngate", "vpnjantit"]\n'
                    "vpnjantit_refresh_min = 60\n", encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.free_pool.providers == ["vpngate"]
    assert len(warnings) == 2 and all("VPNJantit из бесплатного пула убран" in item
                                      for item in warnings)
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    snapshots = root(paths) / "snapshots"
    snapshots.mkdir(parents=True)
    for name in ("vpnjantit.json", "vpnjantit.1.json", "vpngate.json"):
        (snapshots / name).write_text("{}", encoding="utf-8")
    FreePool(cfg, paths)
    assert sorted(item.name for item in snapshots.iterdir()) == ["vpngate.json"]


def test_bad_free_pool_settings_fall_back_with_warnings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[free_pool]\nmode = "on"\nregion = "MARS"\nproviders = ["vpngate", "other"]\n'
        'fallback_regions = ["US", "MOON"]\nbudget_mb = 100\nhealth_reserved_mb = 200\n'
        "checks_per_step = 50\n", encoding="utf-8")
    cfg, warnings = config.load(path)
    pool = cfg.free_pool
    assert pool.mode == "observe"  # трафик через пул — следующая веха, пока наблюдение
    assert (pool.region, pool.providers, pool.fallback_regions) == ("EU", ["vpngate"], ["US"])
    assert (pool.health_reserved_mb, pool.checks_per_step) == (100, 2)
    assert len([item for item in warnings if item.startswith("free_pool.")]) == 6
    path.write_text("", encoding="utf-8")
    assert config.load(path)[0].free_pool.mode == "off"  # без раздела — выключен


def test_pool_command_shows_the_summary_and_switches_the_mode(tmp_path, monkeypatch, capsys):
    """xgw pool status — та же сводка, что в панели; xgw pool mode — тот же panel.json."""
    from xgw.cli import main
    from xgw.paths import Paths

    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    Paths.from_env().ensure()
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    assert main(["pool", "--config", str(path), "mode", "observe"]) == 0
    assert "Наблюдение за бесплатным пулом включено" in capsys.readouterr().out
    assert managed.load(managed.path_for(path))[0]["free_pool_mode"] == "observe"
    assert main(["pool", "--config", str(path), "status", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary["mode"], summary["found"]) == ("observe", 0)
    assert [source["id"] for source in summary["sources"]] == list(config.FREE_POOL_PROVIDERS)
    assert main(["pool", "--config", str(path), "status"]) == 0
    text = capsys.readouterr().out
    assert "Бесплатный пул: наблюдение" in text and "VPN Gate: — · списка ещё нет" in text
    with pytest.raises(SystemExit):  # трафик через пул (on) — не в этой версии
        main(["pool", "--config", str(path), "mode", "on"])


def test_shared_password_is_masked_in_the_journal(tmp_path):
    """Пароль VPNBook короток для регулярок — после опроса он в списке маскируемых."""
    from xgw import log

    pool, _fetcher, _clock = _pool(tmp_path, _pages(), providers=["vpnbook"])
    pool.refresh_due(via=("127.0.0.1", 10809), mark=2)
    assert "FakePass9" in log._secrets


def test_regions_count_only_the_wanted(tmp_path, monkeypatch):
    """Пригодный сервер на Кипре (EU и ASIA) в строгом EU считается только в EU."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool.probe import Outcome

    pool, _fetcher, _clock = _pool(tmp_path, _pages(), checks_per_step=1, providers=["vpnbook"])
    pool.refresh_due(via=None, mark=2)
    [first] = pool.next_checks(1)
    assert first.backend == Backend.XRAY  # Outline: OpenVPN VPNBook без профиля — только туннелем
    monkeypatch.setattr(pool_module.probing, "check_xray",
                        lambda variant, cfg, xray_bin, run: Outcome("OK", 0.4, 600_000, "CY"))
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 1
    summary = pool.summary()
    assert (summary["ready"], summary["by_region"]) == (1, {"EU": 1})
    pool.cfg.free_pool.region = "auto"
    assert pool.summary()["by_region"] == {"EU": 1, "ASIA": 1}

