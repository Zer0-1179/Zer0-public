"""bounce_handler Lambda のユニットテスト。
2026-07-10のFableレビュー修正(v0.13、幽霊レコード対策)の回帰テストを兼ねる。
"""
from unittest import mock

from conftest import fake_event


def test_mark_unsubscribed_sets_status_and_reason(lp_waitlist, bounce_handler):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "victim@example.com"}))

    bounce_handler.mark_unsubscribed("victim@example.com", reason="bounce")

    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "victim@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "bounce"


def test_mark_unsubscribed_unregistered_address_creates_no_ghost_record(lp_waitlist, bounce_handler):
    """#8の修正確認: waitlist未登録アドレスへのバウンス/苦情処理は幽霊レコードを作らない。"""
    bounce_handler.mark_unsubscribed("ghost2@example.com", reason="complaint")

    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "ghost2@example.com"}).get("Item")
    assert item is None


def test_lambda_handler_complaint_event_unsubscribes_recipient(lp_waitlist, bounce_handler):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "complainer@example.com"}))

    event = {
        "Records": [
            {
                "Sns": {
                    "Message": '{"eventType": "Complaint", "complaint": {"complainedRecipients": '
                    '[{"emailAddress": "complainer@example.com"}]}}'
                }
            }
        ]
    }
    resp = bounce_handler.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "complainer@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "complaint"


def test_lambda_handler_transient_bounce_does_not_unsubscribe(lp_waitlist, bounce_handler):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "temp-fail@example.com"}))

    event = {
        "Records": [
            {
                "Sns": {
                    "Message": '{"eventType": "Bounce", "bounce": {"bounceType": "Transient", '
                    '"bouncedRecipients": [{"emailAddress": "temp-fail@example.com"}]}}'
                }
            }
        ]
    }
    bounce_handler.lambda_handler(event, None)
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "temp-fail@example.com"}).get("Item")
    assert item["status"] == "pending"
