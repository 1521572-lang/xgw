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
    cfg.free_pool.providers = ["vpngate", "vpnbook"]  # списки GitHub — в своих тестах
    for name, value in cfg_values.items():
        setattr(cfg.free_pool, name, value)
    fetcher = _Fetcher(pages)
    clock = [1_800_000_000.0]
    pool = FreePool(cfg, paths, fetcher=fetcher, clock=lambda: clock[0], sleep=lambda s: None)
    pool.resolve = lambda name, bootstrap, **kwargs: ["198.51.100.99"]  # не настоящий DNS
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
                        lambda variant, cfg, xray_bin, run, **kwargs:
                        Outcome("OK", 0.4, 600_000, "PL"))
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
                        lambda variant, cfg, xray_bin, run, **kwargs:
                        Outcome("OK", 0.4, 600_000, "CY"))
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 1
    summary = pool.summary()
    assert (summary["ready"], summary["by_region"]) == (1, {"EU": 1})
    pool.cfg.free_pool.region = "auto"
    assert pool.summary()["by_region"] == {"EU": 1, "ASIA": 1}


# --- списки GitHub (после отчёта вехи М2а) ------------------------------------------------------


def _list_pages() -> dict:
    vless, every = providers.LIST_URLS[providers.IGARECK]
    [eternity] = providers.LIST_URLS[providers.MAHDIBLAND]
    return {
        vless: (200, _fixture("igareck-black-vless.txt")),
        every: (200, _fixture("igareck-black-all.txt")),
        eternity: (200, _fixture("mahdibland-eternity.txt")),
    }


def test_github_lists_become_xray_and_singbox_variants():
    """Файлы igareck: строки «#» — пояснения; VLESS (Reality, ws, xhttp), Trojan, VMess,
    Shadowsocks — Xray, Hysteria2 — только sing-box; страна — по флагу; повтор, адрес LAN и
    схема socks:// не принимаются."""
    documents = [(url, _list_pages()[url][1]) for url in providers.LIST_URLS[providers.IGARECK]]
    result = providers.parse_link_list(providers.IGARECK, documents, now=5.0)
    assert result.status is Status.SUCCESS and result.authoritative
    kinds = sorted((variant.protocol, variant.backend) for variant in result.variants)
    assert kinds == [("hysteria2", Backend.SINGBOX), ("shadowsocks", Backend.XRAY),
                     ("trojan", Backend.XRAY), ("vless", Backend.XRAY), ("vless", Backend.XRAY),
                     ("vless", Backend.XRAY), ("vmess", Backend.XRAY)]
    assert result.rejections == {"повтор": 1, "адрес сервера — не публичный IPv4": 1,
                                 "схема socks:// не принимается": 1}
    first = result.variants[0]
    assert (first.country_hint, first.address, first.port) == ("FI", "198.51.100.41", 443)
    assert first.name == "igareck 🇫🇮 Finland, Helsinki | 🌐 | [BL]"
    [ws] = [variant for variant in result.variants if variant.host == "cdn.example.net"]
    assert (ws.address, ws.country_hint) == ("", "DE")
    [hy2] = [variant for variant in result.variants if variant.backend == Backend.SINGBOX]
    assert hy2.transport == "udp" and hy2.singbox["main"]["type"] == "hysteria2"
    assert hy2.outbound is None and len({v.variant_id for v in result.variants}) == 7
    # Пустой файл или подмена без ссылок — прежний снимок остаётся.
    assert providers.parse_link_list(providers.IGARECK, [("u", "# только пояснения\n")],
                                     now=5.0).status is Status.SCHEMA_CHANGED


def test_list_servers_xray_does_not_accept_are_rejected_with_a_reason():
    """Отчёты М2а.1 и М2а.3: «Xray завершился с кодом 23» у серверов списков. Чего Xray 26.10.21
    не принимает (проверено xray run -test), — в отклонённые при разборе, без значений секретов."""
    uuid = "0b6a2a3c-1d2e-4f50-8a9b-0c1d2e3f4a5b"
    pbk = "A" * 43

    def ss(method, password="sspass1234567890"):
        user = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
        return f"ss://{user}@198.51.100.14:8388#{method}"

    def vless(query, name):
        return f"vless://{uuid}@198.51.100.10:443?{query}#{name}"

    reality = f"security=reality&sni=a.example.com&pbk={pbk}&fp=chrome&type=tcp"
    key16 = base64.b64encode(b"k" * 16).decode()
    text = "\n".join([
        ss("aes-256-gcm"), ss("AES-128-GCM"), ss("2022-blake3-aes-128-gcm", key16),
        ss("aes-256-cfb"), ss("rc4-md5"), ss("aes-192-gcm"), ss("none"),
        ss("2022-blake3-aes-256-gcm", key16),
        vless("security=tls&sni=a.example.com&type=tcp&flow=xtls-rprx-vision-udp443", "u443"),
        vless("security=tls&sni=a.example.com&type=tcp&flow=xtls-rprx-direct", "direct"),
        vless("security=tls&sni=a.example.com&type=h2&path=%2F", "h2"),
        vless("security=tls&sni=a.example.com&type=http&path=%2F", "http"),
        vless(reality + "&sid=ABCD", "sid-ok"), vless(reality + "&sid=abc", "sid-odd"),
        vless(reality + "&sid=0123456789abcdef01", "sid-long"),
        vless(f"security=reality&sni=a.example.com&pbk={pbk}=&type=tcp", "pbk-padded"),
        vless("type=tcp", "plain"), vless("security=none&type=ws&path=%2F", "plain-ws"),
        vless("encryption=mlkem768x25519plus.native.0rtt.a2V5&type=tcp", "vlessenc"),
        "trojan://trpass123456@198.51.100.12:443?security=none&type=tcp#trojan-plain",
        "trojan://trpass123456@198.51.100.12:443?sni=t.example.com&type=tcp#trojan-tls",
    ])
    result = providers.parse_link_list(providers.MAHDIBLAND, [("u", text)], now=1.0)
    assert sorted(variant.name.split()[-1] for variant in result.variants) == [
        "2022-blake3-aes-128-gcm", "AES-128-GCM", "aes-256-gcm", "sid-ok", "trojan-tls", "u443",
        "vlessenc"]
    assert result.rejections == {
        "шифр Shadowsocks aes-256-cfb — Xray его не принимает": 1,
        "шифр Shadowsocks rc4-md5 — Xray его не принимает": 1,
        "шифр Shadowsocks aes-192-gcm — Xray его не принимает": 1,
        "шифр Shadowsocks none — Xray его не принимает": 1,
        "ключ Shadowsocks 2022 не той длины": 1,
        "flow VLESS xtls-rprx-direct — убран из Xray": 1,
        "транспорт HTTP/2 (h2) — убран из Xray, заменён XHTTP": 2,
        "shortId REALITY — не пары hex до 16 знаков": 2,
        "ключ REALITY — не 43 знака base64url": 1,
        "VLESS без TLS и шифрования — Xray не пускает к публичному адресу": 2,
        "trojan без TLS — Xray не пускает к публичному адресу": 1,
    }


def test_probe_core_failure_is_told_without_secrets(tmp_path):
    """Временный Xray не запустился — в причине его строка отказа (последнее звено), а ключ
    из неё скрыт; так отчёт покажет, что именно не так с сервером списка."""
    from xgw.config import Config
    from xgw.freepool import probe
    from xgw.freepool.models import Variant

    key = base64.b64encode(b"q" * 16).decode()

    class Dead:
        returncode = 23

        def poll(self):
            return 23

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 23

    def spawn(argv, **kwargs):
        kwargs["stdout"].write(
            f"Failed to start: main: failed to create server > proxy/shadowsocks_2022: invalid "
            f"key: {key} > infra/conf: unknown cipher method: {key}\n".encode())
        kwargs["stdout"].flush()
        return Dead()

    variant = Variant(provider="mahdibland", backend=Backend.XRAY, protocol="shadowsocks",
                      host="", address="198.51.100.14", port=8388, transport="tcp", name="x",
                      country_hint="",
                      outbound={"protocol": "shadowsocks", "settings": {"servers": [{
                          "address": "198.51.100.14", "port": 8388,
                          "method": "2022-blake3-aes-128-gcm", "password": key}]}})
    outcome = probe.check_xray(variant, Config(), Path("/opt/xgw/xray/xray"), tmp_path,
                               spawn=spawn)
    assert outcome.verdict == "UNTESTED"
    assert outcome.error == "Xray завершился с кодом 23: unknown cipher method: ***"
    assert not list(tmp_path.iterdir())  # временный каталог убран вместе с выводом


def test_github_list_in_base64_is_decoded():
    text = base64.b64encode(_fixture("mahdibland-eternity.txt").encode()).decode()
    result = providers.parse_link_list(providers.MAHDIBLAND, [("u", text)], now=1.0)
    assert len(result.variants) == 4 and result.rejections == {
        "схема ssr:// не принимается": 1}
    assert {variant.country_hint for variant in result.variants} == {"US", "DE", "PL", "CA"}


def test_github_lists_go_through_the_carrier_and_a_missing_file_is_partial(tmp_path):
    """Списки — через несущий канал, как каталоги; не скачался один файл — PARTIAL (снимок
    из того, что есть); интервал опроса — lists_refresh_min."""
    pages = _list_pages()
    del pages[providers.LIST_URLS[providers.IGARECK][1]]
    pool, fetcher, clock = _pool(tmp_path, pages, providers=["igareck", "mahdibland"])
    via = ("127.0.0.1", 10809)
    igareck, mahdibland = pool.refresh_due(via=via, mark=2)
    assert {proxy for _url, proxy in fetcher.calls} == {via}
    assert igareck.status is Status.PARTIAL and "файл списка не скачан" in igareck.detail
    assert len(pool.store.variants("igareck")) == 3 and mahdibland.status is Status.SUCCESS
    assert 0.8 * 7200 <= pool.next_refresh["mahdibland"] - clock[0] <= 1.2 * 7200


def test_github_servers_are_checked_without_the_budget(tmp_path, monkeypatch):
    """Серверы списков проверяются сверх checks_per_step (list_checks_per_step) и без бюджета:
    трафик — в своём учёте; бюджет каталогов исчерпан — списки всё равно проверяются.
    Hysteria2 — пробой sing-box; адрес — закреплённый публичный (dns.hosts)."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool.probe import Outcome

    pool, _fetcher, _clock = _pool(tmp_path, _list_pages(), providers=["igareck"],
                                   list_checks_per_step=8, checks_per_step=1)
    pool.refresh_due(via=None, mark=2)
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(pool_module.probing, "check_xray",
                        lambda variant, cfg, xray_bin, run, **kwargs:
                        seen.append(("xray", kwargs["hosts"]))
                        or Outcome("OK", 0.4, 3 * 1_048_576, "DE"))
    monkeypatch.setattr(pool_module.probing, "check_singbox",
                        lambda variant, cfg, singbox_bin, run, **kwargs:
                        seen.append(("sing-box", kwargs["hosts"]))
                        or Outcome("OK", 0.5, 2 * 1_048_576, "NL"))
    monkeypatch.setattr("xgw.generator.singbox.find_binary",
                        lambda explicit=None, paths=None: Path("/opt/xgw/sing-box/sing-box"))
    pool.cfg.free_pool.budget_mb = 64
    pool.cfg.free_pool.health_reserved_mb = 64  # бюджет каталогов — ноль
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 7
    assert [kind for kind, _hosts in seen].count("sing-box") == 1
    assert ("xray", {"cdn.example.net": ["198.51.100.99"]}) in seen
    summary = pool.summary()
    assert summary["spent_mb"] == 0 and summary["lists_spent_mb"] == 20.0
    assert (summary["lists"], summary["lists_singbox"], summary["ready"]) == (7, 1, 7)
    assert summary["ready_by_source"] == {"igareck": 7}  # пригодность — по выходу (DE, NL)
    assert "серверы списков GitHub — 20.0 МБ (без предела)" in pool_module.render(summary, 0)


def test_server_name_must_resolve_to_a_public_address(tmp_path, monkeypatch):
    """Имя сервера из списка разрешается резолверами шлюза; только служебные адреса в ответе
    (подмена, LAN) — проба не запускается."""
    from xgw.freepool import pool as pool_module

    pool, _fetcher, _clock = _pool(tmp_path, _list_pages(), providers=["igareck"],
                                   list_checks_per_step=8)
    pool.refresh_due(via=None, mark=2)
    pool.resolve = lambda name, bootstrap, **kwargs: ["192.168.1.1"]
    monkeypatch.setattr(pool_module.probing, "check_xray",
                        lambda *args, **kwargs: pytest.fail("проба к адресу LAN"))
    [ws] = [variant for variant in pool.variants() if variant.host == "cdn.example.net"]
    outcome = pool._check_proxy(ws, mark=2, xray_bin=Path("/opt/xgw/xray/xray"))
    assert (outcome.verdict, outcome.error) == ("UNTESTED", "у имени сервера нет публичного IPv4")


def test_records_of_vanished_servers_are_pruned(tmp_path):
    """Сервер пропал из списка — его итог проверки убирается из candidates.json; учёт трафика
    и подключений остаётся."""
    pool, _fetcher, clock = _pool(tmp_path, _list_pages(), providers=["mahdibland"])
    pool.refresh_due(via=None, mark=2)
    state = pool.store.candidates()
    ids = [variant.variant_id for variant in pool.variants()]
    state.update({key: {"checked_at": 1.0, "verdict": "OK"} for key in ids})
    state["gone" * 8] = {"checked_at": 1.0, "verdict": "OK"}
    state["_ledger"] = {"items": [[clock[0], 10]]}
    pool.store.save_candidates(state)
    clock[0] += 3 * 3600
    pool.refresh_due(via=None, mark=2)
    kept = pool.store.candidates()
    assert "gone" * 8 not in kept and set(ids) <= set(kept) and "_ledger" in kept


def test_singbox_probe_config_mirrors_the_bridge():
    """Временный sing-box: http-inbound с паролем, выход с routing_mark = mark_bypass, имена —
    через hosts-сервер DNS (как в основном конфиге). Проверено sing-box check (1.14.3)."""
    from xgw.config import Config
    from xgw.freepool import probe

    documents = [(url, _list_pages()[url][1]) for url in providers.LIST_URLS[providers.IGARECK]]
    [hy2] = [variant for variant in providers.parse_link_list(
        providers.IGARECK, documents, now=1.0).variants if variant.backend == Backend.SINGBOX]
    cfg = Config()
    config = probe.singbox_config(hy2, cfg, 18080, "p" * 16, {"h.example.org": ["198.51.100.9"]})
    [inbound] = config["inbounds"]
    assert (inbound["type"], inbound["listen"], inbound["listen_port"]) == (
        "http", "127.0.0.1", 18080)
    assert inbound["users"] == [{"username": "xgw-shadow", "password": "p" * 16}]
    [outbound] = config["outbounds"]
    assert (outbound["tag"], outbound["routing_mark"]) == ("pool", cfg.capture.mark_bypass)
    assert config["route"]["default_domain_resolver"] == "hosts"
    assert config["dns"]["servers"][0]["predefined"] == {"h.example.org": ["198.51.100.9"]}
    assert probe.singbox_config(replace_singbox(hy2, endpoint=True), cfg, 1, "p", {}) is None


def replace_singbox(variant, **changes):
    from dataclasses import replace

    return replace(variant, singbox={**variant.singbox, **changes})


def test_pool_command_prefers_the_daemon_summary(tmp_path, monkeypatch, capsys):
    """xgw pool status — сводка демона из status.json (как в панели), а не своя: отчёт М2а —
    своя писала «ещё не проверялся» при четырёх туннелях."""
    import time

    from xgw import cli
    from xgw.paths import Paths

    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    paths = Paths.from_env()
    paths.ensure()
    path = tmp_path / "config.toml"
    path.write_text('[free_pool]\nmode = "observe"\n', encoding="utf-8")
    daemon = {"mode": "observe", "region": "EU", "region_policy": "strict", "found": 9,
              "openvpn_backend": "", "tunnels_up": 4, "sources": []}
    paths.status_file.write_text(json.dumps({"updated": time.time(), "free_pool": daemon}),
                                 encoding="utf-8")
    monkeypatch.setattr(cli, "_daemon_down", lambda paths: False)
    assert cli.main(["pool", "--config", str(path), "status"]) == 0
    text = capsys.readouterr().out
    assert "OpenVPN туннелем: поднялось 4" in text and "недоступна" not in text

