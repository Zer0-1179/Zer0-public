"""lp_waitlist Lambda のユニットテスト。
DynamoDBはmoto、SES送信はモックする(実メールは送らない)。
2026-07-10のFableレビュー修正(v0.13)の回帰テストを兼ねる。
"""
import base64
import hashlib
import hmac
import json
from unittest import mock

from conftest import fake_event


def test_register_new_email_sends_confirmation(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "User@Example.com"}))
    assert resp["statusCode"] == 200
    assert m_confirm.call_count == 1
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "pending"


def test_register_within_cooldown_does_not_resend(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
        m_confirm.reset_mock()
        resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    assert resp["statusCode"] == 200
    assert m_confirm.call_count == 0


def test_pending_resend_after_cooldown_expires(lp_waitlist):
    """#5の修正確認: pending状態でも確認メール未受信のユーザーがクールダウン後に再登録すると再送される。"""
    import time as time_mod

    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))

    lp_waitlist.dynamodb.Table("test-waitlist").update_item(
        Key={"email": "user@example.com"},
        UpdateExpression="SET last_confirm_sent_at = :t",
        ExpressionAttributeValues={":t": int(time_mod.time()) - 400},
    )
    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    assert resp["statusCode"] == 200
    assert m_confirm.call_count == 1


def test_confirm_activates_pending_and_sends_welcome(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    token = lp_waitlist.make_token("user@example.com", "confirm")

    with mock.patch.object(lp_waitlist, "send_welcome_email") as m_welcome, \
         mock.patch.object(lp_waitlist, "notify_owner_confirmed"):
        resp = lp_waitlist.handle_confirm(fake_event("/confirm", "GET", query={"email": "user@example.com", "token": token}))

    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "active"
    assert m_welcome.call_count == 1


def test_register_when_active_does_not_resend(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    token = lp_waitlist.make_token("user@example.com", "confirm")
    with mock.patch.object(lp_waitlist, "send_welcome_email"), mock.patch.object(lp_waitlist, "notify_owner_confirmed"):
        lp_waitlist.handle_confirm(fake_event("/confirm", "GET", query={"email": "user@example.com", "token": token}))

    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    import json
    # activeなアドレスへの再登録は、第三者によるメールアドレス列挙を防ぐため
    # 他のケースと同じ"registered"を返す(確認メール自体は送らない、Fable指摘、レビュー2026-07-11)。
    assert json.loads(resp["body"])["status"] == "registered"
    assert m_confirm.call_count == 0


def test_unsubscribe_post_marks_unsubscribed_with_user_reason(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    token = lp_waitlist.make_token("user@example.com", "unsubscribe")

    resp = lp_waitlist.handle_unsubscribe(
        fake_event("/unsubscribe", "POST", query={"email": "user@example.com", "token": token}), "POST"
    )
    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "user"


def test_confirm_does_not_reactivate_unsubscribed(lp_waitlist):
    """#6の修正確認: 配信停止済みアドレスは無期限の確認トークンを再アクセスしても復活しない。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "user@example.com"}))
    confirm_token = lp_waitlist.make_token("user@example.com", "confirm")
    unsub_token = lp_waitlist.make_token("user@example.com", "unsubscribe")
    with mock.patch.object(lp_waitlist, "send_welcome_email"), mock.patch.object(lp_waitlist, "notify_owner_confirmed"):
        lp_waitlist.handle_confirm(fake_event("/confirm", "GET", query={"email": "user@example.com", "token": confirm_token}))
    lp_waitlist.handle_unsubscribe(
        fake_event("/unsubscribe", "POST", query={"email": "user@example.com", "token": unsub_token}), "POST"
    )

    with mock.patch.object(lp_waitlist, "send_welcome_email") as m_welcome:
        resp = lp_waitlist.handle_confirm(fake_event("/confirm", "GET", query={"email": "user@example.com", "token": confirm_token}))

    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert m_welcome.call_count == 0


def test_unsubscribe_unregistered_address_creates_no_ghost_record(lp_waitlist):
    """#8の修正確認: 未登録アドレスへの配信停止操作は幽霊レコードを作らない。"""
    token = lp_waitlist.make_token("ghost@example.com", "unsubscribe")
    resp = lp_waitlist.handle_unsubscribe(
        fake_event("/unsubscribe", "POST", query={"email": "ghost@example.com", "token": token}), "POST"
    )
    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "ghost@example.com"}).get("Item")
    assert item is None


def test_history_detail_url_prefers_stored_url_and_falls_back(lp_waitlist):
    """ウェルカムメールの案件リンクは、collectorが保存したdetail_url(個別詳細ページ)を
    優先し、detail_urlを持たない旧レコードは公告一覧ページへフォールバックすること
    (モバイル向けメール改善、2026-07-12)。"""
    assert lp_waitlist.history_detail_url(
        {"detail_url": "https://example.com/detail", "kokoku_no": 1}
    ) == "https://example.com/detail"
    assert lp_waitlist.history_detail_url({"kokoku_no": 18145}) == (
        "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p?job=KokokuAnkenList&kokoku_no=18145"
    )


def test_register_blocked_for_bounce_suppressed_address(lp_waitlist, bounce_handler):
    """#3の修正確認: バウンス起因で停止されたアドレスは再登録で復活・再送されない。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "victim@example.com"}))
    bounce_handler.mark_unsubscribed("victim@example.com", reason="bounce")

    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "victim@example.com"}))

    assert resp["statusCode"] == 200
    assert m_confirm.call_count == 0
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "victim@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"


# ── LINE通知(v0.28) ─────────────────────────────────────────────

def test_register_line_channel_returns_liff_url_without_email(lp_waitlist):
    """channel=lineの登録は確認メールを送らず、line-link用トークン付きLIFF URLを返す。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email") as m_confirm:
        resp = lp_waitlist.handle_register(
            fake_event("/register", "POST", {"email": "line-user@example.com", "channel": "line"})
        )
    assert resp["statusCode"] == 200
    assert m_confirm.call_count == 0
    body = json.loads(resp["body"])
    assert body["status"] == "line_pending"
    assert "liff.line.me" in body["liff_url"]
    assert "email=line-user%40example.com" in body["liff_url"]
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "line-user@example.com"}).get("Item")
    assert item["status"] == "pending"
    assert item["channel"] == "line"


def test_line_link_activates_and_sends_welcome_push(lp_waitlist):
    """LIFFページからの正しいトークンでline_user_idが紐付きactive化され、
    ウェルカムプッシュとオーナー通知が送られる。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "line-user@example.com", "channel": "line"}))
    token = lp_waitlist.make_token("line-user@example.com", "line_link")

    with mock.patch.object(lp_waitlist, "send_line_push") as m_push, \
         mock.patch.object(lp_waitlist, "notify_owner_confirmed") as m_owner:
        resp = lp_waitlist.handle_line_link(fake_event("/line/link", "POST", {
            "email": "line-user@example.com", "token": token, "line_user_id": "U1234567890",
        }))

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "linked"
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "line-user@example.com"}).get("Item")
    assert item["status"] == "active"
    assert item["channel"] == "line"
    assert item["line_user_id"] == "U1234567890"
    assert m_push.call_count == 1
    assert m_owner.call_count == 1


def test_line_link_rejects_invalid_token(lp_waitlist):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "line-user@example.com", "channel": "line"}))

    resp = lp_waitlist.handle_line_link(fake_event("/line/link", "POST", {
        "email": "line-user@example.com", "token": "invalid-token", "line_user_id": "U1234567890",
    }))
    assert resp["statusCode"] == 400
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "line-user@example.com"}).get("Item")
    assert item["status"] == "pending"


def test_line_link_does_not_reactivate_unsubscribed(lp_waitlist):
    """handle_confirmと同じ方針: 配信停止済みアドレスはLIFF連携でも復活しない。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "line-user@example.com", "channel": "line"}))
    token = lp_waitlist.make_token("line-user@example.com", "line_link")
    lp_waitlist.dynamodb.Table("test-waitlist").update_item(
        Key={"email": "line-user@example.com"},
        UpdateExpression="SET #s = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":u": "unsubscribed"},
    )

    with mock.patch.object(lp_waitlist, "send_line_push") as m_push:
        resp = lp_waitlist.handle_line_link(fake_event("/line/link", "POST", {
            "email": "line-user@example.com", "token": token, "line_user_id": "U1234567890",
        }))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] == "unsubscribed"
    assert m_push.call_count == 0


def test_line_webhook_verifies_signature(lp_waitlist):
    body = json.dumps({"events": []})
    bad_resp = lp_waitlist.handle_line_webhook(fake_event(
        "/line/webhook", "POST", headers={"x-line-signature": "wrong"}, raw_body=body,
    ))
    assert bad_resp["statusCode"] == 400

    good_sig = base64.b64encode(
        hmac.new(b"test-line-channel-secret", body.encode(), hashlib.sha256).digest()
    ).decode()
    good_resp = lp_waitlist.handle_line_webhook(fake_event(
        "/line/webhook", "POST", headers={"x-line-signature": good_sig}, raw_body=body,
    ))
    assert good_resp["statusCode"] == 200


def test_line_webhook_unfollow_unsubscribes_matching_user(lp_waitlist):
    """unfollowイベントを受けたline_user_idの購読者がunsubscribed化される。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "line-user@example.com", "channel": "line"}))
    token = lp_waitlist.make_token("line-user@example.com", "line_link")
    with mock.patch.object(lp_waitlist, "send_line_push"), mock.patch.object(lp_waitlist, "notify_owner_confirmed"):
        lp_waitlist.handle_line_link(fake_event("/line/link", "POST", {
            "email": "line-user@example.com", "token": token, "line_user_id": "U1234567890",
        }))

    body = json.dumps({"events": [{"type": "unfollow", "source": {"userId": "U1234567890"}}]})
    sig = base64.b64encode(
        hmac.new(b"test-line-channel-secret", body.encode(), hashlib.sha256).digest()
    ).decode()
    resp = lp_waitlist.handle_line_webhook(fake_event(
        "/line/webhook", "POST", headers={"x-line-signature": sig}, raw_body=body,
    ))
    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "line-user@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "line_block"


def test_register_line_channel_for_already_active_email_returns_liff_url(lp_waitlist):
    """バグ修正確認(2026-07-13発覚): 既にstatus=activeなメールアドレスがchannel=line
    で再登録した場合も、新規登録時と同じline_pending+liff_urlを返すこと。
    以前はactive早期リターンがchannelを見ずに一律"registered"を返しており、
    既存のメール購読者がLINEへ切り替えられなかった。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "existing@example.com"}))
    token = lp_waitlist.make_token("existing@example.com", "confirm")
    with mock.patch.object(lp_waitlist, "send_welcome_email"), mock.patch.object(lp_waitlist, "notify_owner_confirmed"):
        lp_waitlist.handle_confirm(fake_event("/confirm", "GET", query={"email": "existing@example.com", "token": token}))

    resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "existing@example.com", "channel": "line"}))
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "line_pending"
    assert "liff.line.me" in body["liff_url"]


def test_register_line_channel_for_bounce_suppressed_email_returns_liff_url_but_blocked_at_link(lp_waitlist, bounce_handler):
    """バウンス抑制済みアドレスでもchannel=lineは同じ形のレスポンスを返す
    (判別不能性の維持)が、実際のLIFF連携(handle_line_link)では復活しない。"""
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "suppressed@example.com"}))
    bounce_handler.mark_unsubscribed("suppressed@example.com", reason="bounce")

    resp = lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "suppressed@example.com", "channel": "line"}))
    body = json.loads(resp["body"])
    assert body["status"] == "line_pending"

    token = lp_waitlist.make_token("suppressed@example.com", "line_link")
    link_resp = lp_waitlist.handle_line_link(fake_event("/line/link", "POST", {
        "email": "suppressed@example.com", "token": token, "line_user_id": "U999",
    }))
    assert json.loads(link_resp["body"])["status"] == "unsubscribed"
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "suppressed@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
