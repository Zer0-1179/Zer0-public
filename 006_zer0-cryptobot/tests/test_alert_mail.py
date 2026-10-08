"""通知メール共通テンプレート alert_mail のテスト。"""
import filecmp
import os

import alert_mail

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_copies_are_identical():
    """各Lambdaに置いたコピーが同一内容であること（片方だけ直す事故の防止）。"""
    src = os.path.join(ROOT, "lambda", "analyzer", "alert_mail.py")
    for d in ("executor", "failure_notifier"):
        assert filecmp.cmp(src, os.path.join(ROOT, "lambda", d, "alert_mail.py"), shallow=False), d


def test_detect_level():
    assert alert_mail.detect_level("【Zer0-CryptoBot】🚨SL不在 - BTC_JPY") == "critical"
    assert alert_mail.detect_level("【Zer0-CryptoBot】⚠️証拠金警告") == "warning"
    assert alert_mail.detect_level("【Zer0-CryptoBot】発注エラー - BTC_JPY") == "warning"
    assert alert_mail.detect_level("【CryptoBot】ロング約定 - BTC/JPY") == "info"
    assert alert_mail.detect_level("【Zer0-CryptoBot】注文キャンセル - BTC_JPY") == "info"


def test_decorate_subject_replaces_existing_emoji():
    assert alert_mail.decorate_subject("【Zer0-CryptoBot】🚨SL不在 - BTC_JPY") == "【Zer0-CryptoBot】🚨要対応 SL不在 - BTC_JPY"
    assert alert_mail.decorate_subject("【CryptoBot】ロング約定 - BTC/JPY") == "【CryptoBot】✅対応不要 ロング約定 - BTC/JPY"
    assert alert_mail.decorate_subject("⚠️証拠金警告", "warning") == "⚠️要確認 証拠金警告"


def test_render_html_structures_body():
    body = ("TP1・SL注文がともに喪失しています。手動対応が必要です。\n\n"
            "コイン：BTC_JPY\n方向：long\nTP1注文ID：123\n\n"
            "■ メモ\n・箇条書き<1>\nhttps://example.com/x\n\n"
            "aws lambda invoke --function-name X \\\n  --payload '{}' /tmp/o.json")
    h = alert_mail.render_html("【Zer0-CryptoBot】🚨注文喪失 - BTC_JPY", body, service="Zer0-CryptoBot", source="Executor")
    assert "🚨 要対応" in h and "#ff5c5c" in h
    assert "注文喪失 - BTC_JPY</h2>" in h
    assert ">コイン</td>" in h and ">TP1注文ID</td>" in h
    assert "<h3" in h and "メモ</h3>" in h
    assert "<li>箇条書き&lt;1&gt;</li>" in h
    assert '<a href="https://example.com/x"' in h
    assert "<pre" in h and "--payload" in h
    assert "あなたがすること" in h


def test_render_text_keeps_original_body():
    t = alert_mail.render_text("【CryptoBot】ロング約定 - BTC/JPY", "約定価格　：100円")
    assert t.startswith("【対応不要】ロング約定 - BTC/JPY")
    assert "約定価格　：100円" in t and "■ あなたがすること\n対応は不要です。" in t


def test_title_does_not_repeat_badge_after_decorate():
    subj = alert_mail.decorate_subject("【Zer0-CryptoBot】🚨注文喪失 - ETH_JPY")
    assert alert_mail.render_text(subj, "x").startswith("【要対応】注文喪失 - ETH_JPY")
    assert "注文喪失 - ETH_JPY</h2>" in alert_mail.render_html(subj, "x", service="s")
    # 二重に decorate しても重複しない
    assert alert_mail.decorate_subject(subj) == subj


def test_executor_send_email_falls_back_to_text_when_render_fails(executor, monkeypatch):
    ex = executor
    sent = []
    monkeypatch.setattr(ex, "_ses", type("S", (), {"send_email": staticmethod(lambda **k: sent.append(k))})())
    monkeypatch.setattr(ex.alert_mail, "render_html", lambda *a, **k: 1 / 0)
    ex._real_send_email("【Zer0-CryptoBot】🚨SL不在 - BTC_JPY", "本文")
    assert sent and sent[0]["Message"]["Body"] == {"Text": {"Data": "本文", "Charset": "UTF-8"}}
