"""オーナー宛て通知の共通テンプレート alert_mail のテスト（006と同一モジュールのコピー）。"""
import filecmp
import os
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_copies_are_identical():
    src = os.path.join(ROOT, "lambda", "lp_waitlist", "alert_mail.py")
    assert filecmp.cmp(src, os.path.join(ROOT, "lambda", "stripe_webhook", "alert_mail.py"), shallow=False)
    # 006の正本とも一致させる（片方だけ直す事故の防止）
    master = os.path.join(os.path.dirname(ROOT), "006_Zer0_CryptoBot", "lambda", "analyzer", "alert_mail.py")
    if os.path.exists(master):
        assert filecmp.cmp(src, master, shallow=False)


def test_owner_confirmed_sends_badged_html(lp_waitlist):
    with mock.patch.object(lp_waitlist, "_get_param", return_value="owner@example.com"), \
         mock.patch.object(lp_waitlist, "ses") as m_ses:
        lp_waitlist.notify_owner_confirmed("user@example.com")
    msg = m_ses.send_email.call_args.kwargs["Message"]
    assert msg["Subject"]["Data"] == "【入札情報ウォッチ】✅対応不要 事前登録が確認されました"
    assert "✅ 対応不要" in msg["Body"]["Html"]["Data"]
    assert "user@example.com" in msg["Body"]["Html"]["Data"]
    assert msg["Body"]["Text"]["Data"].startswith("【対応不要】事前登録が確認されました")


def test_stripe_owner_notice_levels(stripe_webhook):
    with mock.patch.object(stripe_webhook, "_get_param", return_value="owner@example.com"), \
         mock.patch.object(stripe_webhook, "ses") as m_ses:
        stripe_webhook._notify_owner("支払い済みだが配信停止済みのアドレスです", "本文\n\nアドレス: a@example.com",
                                     level="warning", action="手動で確認")
    msg = m_ses.send_email.call_args.kwargs["Message"]
    assert msg["Subject"]["Data"] == "【入札情報ウォッチ】⚠️要確認 支払い済みだが配信停止済みのアドレスです"
    assert ">アドレス</td>" in msg["Body"]["Html"]["Data"]


def test_stripe_owner_notice_falls_back_to_text(stripe_webhook):
    with mock.patch.object(stripe_webhook, "_get_param", return_value="owner@example.com"), \
         mock.patch.object(stripe_webhook, "ses") as m_ses, \
         mock.patch.object(stripe_webhook.alert_mail, "render_html", side_effect=ValueError):
        stripe_webhook._notify_owner("件名", "本文")
    assert m_ses.send_email.call_args.kwargs["Message"]["Body"] == {"Text": {"Data": "本文", "Charset": "UTF-8"}}
