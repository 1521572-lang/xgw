"""Тесты маскирования секретов (раздел 6.9: одна функция на всё)."""

from xgw.masking import mask_obj, mask_text, mask_url, mask_uuid


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
