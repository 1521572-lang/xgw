"""Группы стран бесплатного пула (ТЗ R14): EU — страны Евросоюза, US — только США, ASIA — Азия
по статистической группировке ООН M49 (регион 142). Страны — коды ISO 3166-1 alpha-2.

EU — по официальному списку ЕС (european-union.europa.eu, 27 стран): Великобритания,
Норвегия, Швейцария, Россия и Турция туда не входят. ASIA — подрегионы M49 Центральная,
Восточная, Юго-Восточная, Южная и Западная Азия; Тайвань в списке M49 отдельно не указан и
добавлен явным расширением (ISO TW). Группы могут пересекаться (Кипр — EU и Западная Азия по
M49): это не ошибка.
"""

from __future__ import annotations

EU = frozenset((
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
))
US = frozenset(("US",))
ASIA_M49 = frozenset((
    # Центральная Азия
    "KZ", "KG", "TJ", "TM", "UZ",
    # Восточная Азия
    "CN", "HK", "MO", "KP", "JP", "MN", "KR",
    # Юго-Восточная Азия
    "BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN",
    # Южная Азия
    "AF", "BD", "BT", "IN", "IR", "MV", "NP", "PK", "LK",
    # Западная Азия
    "AM", "AZ", "BH", "CY", "GE", "IQ", "IL", "JO", "KW", "LB", "OM", "QA", "SA", "PS", "SY",
    "TR", "AE", "YE",
))
ASIA_EXTRA = frozenset(("TW",))  # явное расширение: в M49 Тайвань отдельно не указан
ASIA = ASIA_M49 | ASIA_EXTRA
GROUPS = {"EU": EU, "US": US, "ASIA": ASIA}
NAMES = {"EU": "Евросоюз", "US": "США", "ASIA": "Азия"}
VERSION = "eu27-2026 / un-m49 + TW"


def regions_of(country: str) -> list[str]:
    """Группы, в которые входит страна (код ISO2, любой регистр); пусто — ни в одну."""
    code = (country or "").strip().upper()
    return [name for name, members in GROUPS.items() if code in members]


def allowed(country: str, region: str) -> bool:
    """Подходит ли страна выбранному региону: auto — любая из групп EU/US/ASIA."""
    groups = regions_of(country)
    if region == "auto":
        return bool(groups)
    return region in groups
