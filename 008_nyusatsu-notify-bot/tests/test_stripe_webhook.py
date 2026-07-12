"""stripe_webhook Lambda のユニットテスト。
DynamoDBはmoto、SES送信はモックする(実メールは送らない)。
署名は共有シークレット"whsec_test_secret"(conftest.pyでSSMに登録)を使って
実際のStripeアルゴリズム通りに計算する。
"""
import hashlib
import hmac
import json
import time
from unittest import mock

SECRET = "whsec_test_secret"


def make_event(payload_obj: dict, timestamp: int | None = None, secret: str = SECRET) -> dict:
    payload = json.dumps(payload_obj)
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signed_payload = f"{ts}.{payload}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return {
        "headers": {"stripe-signature": f"t={ts},v1={sig}"},
        "body": payload,
        "isBase64Encoded": False,
    }


def checkout_completed_event(email: str, customer="cus_123", subscription="sub_123", **kwargs):
    return make_event(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer_details": {"email": email},
                    "customer": customer,
                    "subscription": subscription,
                }
            },
        },
        **kwargs,
    )


def subscription_deleted_event(customer="cus_123", **kwargs):
    return make_event(
        {"type": "customer.subscription.deleted", "data": {"object": {"customer": customer}}},
        **kwargs,
    )


def payment_failed_event(customer="cus_123", next_payment_attempt=None, **kwargs):
    return make_event(
        {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": customer, "next_payment_attempt": next_payment_attempt}},
        },
        **kwargs,
    )


def test_invalid_signature_rejected(stripe_webhook):
    event = checkout_completed_event("user@example.com", secret="wrong_secret")
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 400


def test_expired_timestamp_rejected(stripe_webhook):
    event = checkout_completed_event("user@example.com", timestamp=int(time.time()) - 600)
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 400


def test_checkout_completed_activates_existing_subscriber(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(Item={"email": "user@example.com", "status": "pending", "registered_at": 1})

    resp = stripe_webhook.lambda_handler(checkout_completed_event("User@Example.com"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "active"
    assert item["payment_status"] == "paid"
    assert item["stripe_customer_id"] == "cus_123"
    assert item["stripe_subscription_id"] == "sub_123"


def test_checkout_completed_auto_registers_unknown_email(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")

    with mock.patch.object(stripe_webhook, "_notify_owner") as m_notify:
        resp = stripe_webhook.lambda_handler(checkout_completed_event("newpayer@example.com"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "newpayer@example.com"}).get("Item")
    assert item["status"] == "active"
    assert item["payment_status"] == "paid"
    assert item["source"] == "stripe"
    assert m_notify.call_count == 1


def test_checkout_completed_does_not_reactivate_bounce_suppressed(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "bounced@example.com",
            "status": "unsubscribed",
            "unsubscribed_reason": "bounce",
            "registered_at": 1,
        }
    )

    with mock.patch.object(stripe_webhook, "_notify_owner") as m_notify:
        resp = stripe_webhook.lambda_handler(checkout_completed_event("bounced@example.com"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "bounced@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert "payment_status" not in item
    assert m_notify.call_count == 1


def test_duplicate_checkout_completed_is_idempotent(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(Item={"email": "user@example.com", "status": "pending", "registered_at": 1})

    event = checkout_completed_event("user@example.com")
    stripe_webhook.lambda_handler(event, None)
    resp = stripe_webhook.lambda_handler(event, None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["status"] == "active"
    assert item["payment_status"] == "paid"


def test_subscription_deleted_marks_canceled(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(subscription_deleted_event(customer="cus_123"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "canceled"


def test_payment_failed_ignored_while_retrying(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(customer="cus_123", next_payment_attempt=1234567890), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"


def test_payment_failed_marks_past_due_when_retries_exhausted(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(customer="cus_123", next_payment_attempt=None), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "past_due"


def test_unhandled_event_type_returns_200(stripe_webhook):
    event = make_event({"type": "customer.created", "data": {"object": {}}})
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 200
