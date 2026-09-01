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


def test_lambda_handler_complaint_event_unsubscribes_recipient(lp_waitlist, bounce_handler, caplog):
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
    assert "complainer@example.com" not in caplog.text
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "complainer@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "complaint"


def test_lambda_handler_transient_bounce_does_not_unsubscribe(lp_waitlist, bounce_handler, caplog):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "temp-fail@example.com"}))

    event = {
        "Records": [
            {
                "Sns": {
                    "Message": '{"eventType": "Bounce", "bounce": {"bounceType": "Transient", '
                    '"bounceSubType": "MailboxFull", "bouncedRecipients": '
                    '[{"emailAddress": "temp-fail@example.com"}]}}'
                }
            }
        ]
    }
    bounce_handler.lambda_handler(event, None)
    assert "transient bounce received; preserving subscription; subtype=MailboxFull" in caplog.text
    assert "temp-fail@example.com" not in caplog.text
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "temp-fail@example.com"}).get("Item")
    assert item["status"] == "pending"


def test_lambda_handler_permanent_bounce_unsubscribes_recipient(lp_waitlist, bounce_handler, caplog):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "gone@example.com"}))

    event = {
        "Records": [
            {
                "Sns": {
                    "Message": '{"eventType": "Bounce", "bounce": {"bounceType": "Permanent", '
                    '"bouncedRecipients": [{"emailAddress": "gone@example.com"}]}}'
                }
            }
        ]
    }
    bounce_handler.lambda_handler(event, None)
    assert "permanent bounce; unsubscribing recipient" in caplog.text
    assert "gone@example.com" not in caplog.text
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "gone@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "bounce"


def test_lambda_handler_unclassified_bounce_preserves_subscription(lp_waitlist, bounce_handler, caplog):
    with mock.patch.object(lp_waitlist, "send_confirmation_email"):
        lp_waitlist.handle_register(fake_event("/register", "POST", {"email": "unclear@example.com"}))

    event = {
        "Records": [
            {
                "Sns": {
                    "Message": '{"eventType": "Bounce", "bounce": {"bounceType": "Undetermined", '
                    '"bounceSubType": "untrusted-recipient-value", '
                    '"bouncedRecipients": [{"emailAddress": "unclear@example.com"}]}}'
                }
            }
        ]
    }
    bounce_handler.lambda_handler(event, None)
    assert "unclassified bounce received; preserving subscription; subtype=Other" in caplog.text
    assert "unclear@example.com" not in caplog.text
    assert "untrusted-recipient-value" not in caplog.text
    item = lp_waitlist.dynamodb.Table("test-waitlist").get_item(Key={"email": "unclear@example.com"}).get("Item")
    assert item["status"] == "pending"
