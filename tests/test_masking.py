"""Тесты маскирования секретов (раздел 6.9: одна функция на всё)."""

from xgw.masking import collect_secrets, mask_obj, mask_text, mask_url, mask_uuid


def test_mask_uuid_keeps_last4():
    assert mask_uuid("11111111-2222-3333-4455-666666666661") == "****6661"
    assert mask_uuid("short") == "***"


def test_mask_url_leaves_domain_only():
    assert (
        mask_url("https://panel.example.com/sub/TOKEN?x=1") == "panel.example.com"
    )


def test_mask_text_secrets_and_urls():
    text = "подписка https://panel.example.com/sub/TOKEN пароль s3cret-key"
    result = mask_text(text, secrets=["s3cret-key"])
    assert "s3cret-key" not in result
    assert "TOKEN" not in result
    assert "panel.example.com" in result


def test_mask_text_uuids_and_long_tokens():
    result = mask_text("uuid 11111111-2222-3333-4455-666666666661 pbk " + "a" * 48)
    assert "11111111" not in result
    assert "****6661" in result
    assert "a" * 48 not in result


def test_mask_obj_nested():
    payload = {
        "url": "https://panel.example.com/sub/TOKEN",
        "nested": [{"id": "11111111-2222-3333-4455-666666666662"}],
        "port": 10085,
    }
    result = mask_obj(payload, secrets=["TOKEN"])
    assert result["port"] == 10085
    assert "TOKEN" not in str(result)
    assert "****6662" in str(result)


def test_share_links_are_masked_whole():
    """В ссылке сервера секрет — userinfo: пароль trojan/ss регуляркой UUID не поймать."""
    text = (
        "битая ссылка trojan://tr0jan-pass@203.0.113.20:443?security=tls#NL и "
        "ss://YWVzLTI1Ni1nY206cHc@203.0.113.40:8388 и VLESS://abc@h:1"
    )
    result = mask_text(text)
    assert "tr0jan-pass" not in result and "YWVzLTI1Ni1nY206cHc" not in result
    assert result.count("://***") == 3
    # похожие по написанию схемы ссылками серверов не считаются
    assert mask_text("wss://example.com/x class://y") == "wss://example.com/x class://y"


def test_telegram_bot_token_is_masked():
    token = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
    assert token not in mask_text(f"бот {token} не отвечает")


def test_collect_secrets_from_outbounds():
    outbounds = [
        {"protocol": "trojan",
         "settings": {"servers": [{"address": "203.0.113.20", "password": "tr0jan-pass"}]}},
        {"protocol": "vless",
         "settings": {"vnext": [{"users": [{"id": "11111111-2222-3333-4455-666666666661"}]}]},
         "streamSettings": {"realitySettings": {"publicKey": "PUBKEY123", "shortId": "abcd1234"}}},
        {"protocol": "socks", "settings": {"servers": [{"users": [{"user": "u", "pass": "pw"}]}]}},
    ]
    secrets = collect_secrets(outbounds)
    # UUID маскирует регулярка (оставляя 4 символа); слишком короткие значения не берём
    assert secrets == {"tr0jan-pass", "PUBKEY123", "abcd1234"}
    assert mask_text("ключ PUBKEY123 sid abcd1234", secrets) == "ключ *** sid ***"
