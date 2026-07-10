"""lp_waitlist Lambda のユニットテスト。
DynamoDBはmoto、SES送信はモックする(実メールは送らない)。
2026-07-10のFableレビュー修正(v0.13)の回帰テストを兼ねる。
"""
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
    assert json.loads(resp["body"])["status"] == "already_registered"
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
