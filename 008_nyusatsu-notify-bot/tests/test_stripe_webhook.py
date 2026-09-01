"""stripe_webhook Lambda のユニットテスト。
DynamoDBはmoto、SES送信はモックする(実メールは送らない)。
署名は共有シークレット"whsec_test_secret"(conftest.pyでSSMに登録)を使って
実際のStripeアルゴリズム通りに計算する。
"""
import hashlib
import hmac
import json
import logging
import time
from unittest import mock

SECRET = "whsec_test_secret"


def make_event(
    payload_obj: dict,
    timestamp: int | None = None,
    secret: str = SECRET,
    event_id: str | None = "evt_test",
    event_created: int | None = 100,
) -> dict:
    event_obj = dict(payload_obj)
    if event_id is not None:
        event_obj["id"] = event_id
    if event_created is not None:
        event_obj["created"] = event_created
    payload = json.dumps(event_obj)
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


def subscription_deleted_event(customer="cus_123", subscription="sub_123", **kwargs):
    return make_event(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": customer, "id": subscription}},
        },
        **kwargs,
    )


def payment_failed_event(customer="cus_123", subscription="sub_123", next_payment_attempt=None, **kwargs):
    return make_event(
        {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": customer,
                    "subscription": subscription,
                    "next_payment_attempt": next_payment_attempt,
                }
            },
        },
        **kwargs,
    )


def invoice_paid_event(customer="cus_123", subscription="sub_123", **kwargs):
    return make_event(
        {
            "type": "invoice.paid",
            "data": {"object": {"customer": customer, "subscription": subscription}},
        },
        **kwargs,
    )


def test_invalid_signature_rejected(stripe_webhook):
    event = checkout_completed_event("user@example.com", secret="wrong_secret")
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 400


def test_signature_secret_is_reloaded_after_rotation(stripe_webhook):
    """同一warm環境相当の連続invokeでも、更新後の署名secretを使う。"""
    ssm = __import__("boto3").client("ssm", region_name="ap-northeast-1")
    old_secret = "whsec_rotation_old"
    new_secret = "whsec_rotation_new"
    try:
        ssm.put_parameter(
            Name="/test/stripe-webhook-secret-secure",
            Value=old_secret,
            Type="SecureString",
            Overwrite=True,
        )
        with mock.patch.object(stripe_webhook, "_notify_owner"):
            first = stripe_webhook.lambda_handler(
                checkout_completed_event("old-secret@example.com", secret=old_secret, event_id="evt_old_secret"),
                None,
            )

        ssm.put_parameter(
            Name="/test/stripe-webhook-secret-secure",
            Value=new_secret,
            Type="SecureString",
            Overwrite=True,
        )
        with mock.patch.object(stripe_webhook, "_notify_owner"):
            second = stripe_webhook.lambda_handler(
                checkout_completed_event("new-secret@example.com", secret=new_secret, event_id="evt_new_secret"),
                None,
            )
        old_after_rotation = stripe_webhook.lambda_handler(
            checkout_completed_event("rejected-old-secret@example.com", secret=old_secret, event_id="evt_rejected_old"),
            None,
        )

        assert first["statusCode"] == 200
        assert second["statusCode"] == 200
        assert old_after_rotation["statusCode"] == 400
    finally:
        ssm.put_parameter(
            Name="/test/stripe-webhook-secret-secure",
            Value=SECRET,
            Type="SecureString",
            Overwrite=True,
        )


def test_expired_timestamp_rejected(stripe_webhook):
    event = checkout_completed_event("user@example.com", timestamp=int(time.time()) - 600)
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 400


def test_state_changing_event_without_stripe_metadata_rejected(stripe_webhook):
    event = checkout_completed_event("user@example.com", event_id=None, event_created=None)
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 400


def test_state_changing_event_with_invalid_stripe_metadata_rejected(stripe_webhook):
    bool_created = checkout_completed_event("user@example.com", event_created=True)
    empty_event_id = checkout_completed_event("user@example.com", event_id="")

    assert stripe_webhook.lambda_handler(bool_created, None)["statusCode"] == 400
    assert stripe_webhook.lambda_handler(empty_event_id, None)["statusCode"] == 400


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


def test_webhook_logs_do_not_include_email_or_stripe_identifiers(stripe_webhook, caplog):
    """WebhookログはメールアドレスやStripe識別子を含めない。"""
    email = "private@example.com"
    customer_id = "cus_private"
    subscription_id = "sub_private"
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(Item={"email": email, "status": "pending", "registered_at": 1})

    caplog.set_level(logging.INFO, logger=stripe_webhook.logger.name)
    resp = stripe_webhook.lambda_handler(
        checkout_completed_event(email, customer=customer_id, subscription=subscription_id), None
    )

    assert resp["statusCode"] == 200
    assert email not in caplog.text
    assert customer_id not in caplog.text
    assert subscription_id not in caplog.text


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
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(subscription_deleted_event(customer="cus_123"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "canceled"


def test_payment_failed_marks_past_due_when_retry_is_scheduled(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(customer="cus_123", next_payment_attempt=1234567890), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "past_due"


def test_payment_failed_marks_past_due_without_next_attempt(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(customer="cus_123", next_payment_attempt=None), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "past_due"


def test_invoice_paid_recovers_from_past_due(stripe_webhook):
    """past_dueだった購読者のカード再決済が成功(invoice.paid)したら、
    payment_statusをpaidへ自動復帰させる(Fable指摘、2026-07-14: 以前は復帰経路が
    なく、payment-requiredフラグ運用開始後に支払済みの顧客へ配信されない
    事故になりうる問題があった)。"""
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "past_due",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(invoice_paid_event(customer="cus_123"), None)

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"


def test_one_off_invoice_failure_does_not_change_subscription_status(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(subscription=None, event_id="evt_one_off", event_created=200), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"
    assert "stripe_last_event_id" not in item


def test_other_subscription_invoice_does_not_change_subscription_status(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    resp = stripe_webhook.lambda_handler(
        payment_failed_event(subscription="sub_other", event_id="evt_other", event_created=200), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"


def test_delayed_invoice_events_do_not_override_canceled_subscription(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    canceled = stripe_webhook.lambda_handler(
        subscription_deleted_event(event_id="evt_canceled", event_created=300), None
    )
    late_failure = stripe_webhook.lambda_handler(
        payment_failed_event(event_id="evt_late_failure", event_created=200), None
    )
    late_payment = stripe_webhook.lambda_handler(
        invoice_paid_event(event_id="evt_late_paid", event_created=250), None
    )

    assert canceled["statusCode"] == 200
    assert late_failure["statusCode"] == 200
    assert late_payment["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "canceled"
    assert item["stripe_last_event_id"] == "evt_canceled"


def test_same_second_cancellation_takes_precedence_over_invoice_paid(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "past_due",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    stripe_webhook.lambda_handler(subscription_deleted_event(event_id="evt_canceled", event_created=300), None)
    resp = stripe_webhook.lambda_handler(
        invoice_paid_event(event_id="evt_late_paid", event_created=300), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "canceled"


def test_newer_invoice_event_does_not_override_canceled_subscription(stripe_webhook, caplog):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )

    stripe_webhook.lambda_handler(subscription_deleted_event(event_id="evt_canceled", event_created=300), None)
    caplog.set_level(logging.INFO, logger=stripe_webhook.logger.name)
    resp = stripe_webhook.lambda_handler(
        invoice_paid_event(event_id="evt_newer_paid", event_created=400), None
    )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "canceled"
    assert "ignored a stale or terminal Stripe event" in caplog.text
    assert "payment recovered or confirmed" not in caplog.text


def test_basil_invoice_subscription_is_recognized(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "past_due",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )
    event = make_event(
        {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "parent": {
                        "type": "subscription_details",
                        "subscription_details": {"subscription": "sub_123"},
                    },
                }
            },
        },
        event_id="evt_basil",
        event_created=200,
    )

    assert stripe_webhook.lambda_handler(event, None)["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"


def test_basil_parent_subscription_wins_over_conflicting_legacy_value(stripe_webhook):
    """Basil parentを優先し、残存した旧形式値で別購読を参照しない。"""
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "stripe-e2e-test@example.com",
            "status": "pending",
            "payment_status": "paid",
            "source": "stripe-e2e-test",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )
    event = make_event(
        {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "subscription": "sub_legacy_conflict",
                    "parent": {
                        "type": "subscription_details",
                        "subscription_details": {"subscription": "sub_123"},
                    },
                }
            },
        },
        event_id="evt_basil_parent_wins",
        event_created=200,
    )

    assert stripe_webhook.lambda_handler(event, None)["statusCode"] == 200
    item = table.get_item(Key={"email": "stripe-e2e-test@example.com"})["Item"]
    assert item["status"] == "pending"
    assert item["source"] == "stripe-e2e-test"
    assert item["payment_status"] == "past_due"
    assert item["stripe_last_event_created"] == 200
    assert item["stripe_last_event_priority"] == 1
    assert item["stripe_last_event_id"] == "evt_basil_parent_wins"


def test_basil_parent_subscription_wins_when_legacy_value_is_empty(stripe_webhook):
    assert stripe_webhook._invoice_subscription_id(
        {
            "subscription": "",
            "parent": {
                "type": "subscription_details",
                "subscription_details": {"subscription": "sub_123"},
            },
        }
    ) == "sub_123"


def test_find_subscriber_uses_consistent_reads_for_every_scan(stripe_webhook):
    page_one = {"Items": [], "LastEvaluatedKey": {"email": "first-page"}}
    page_two = {
        "Items": [
            {
                "email": "user@example.com",
                "stripe_customer_id": "cus_123",
                "stripe_subscription_id": "sub_123",
            }
        ]
    }
    table = mock.Mock()
    table.scan.side_effect = [page_one, page_two]

    with mock.patch.object(stripe_webhook.dynamodb, "Table", return_value=table):
        subscriber = stripe_webhook._find_subscriber("cus_123", "sub_123")

    assert subscriber == page_two["Items"][0]
    assert table.scan.call_count == 2
    assert all(call.kwargs["ConsistentRead"] is True for call in table.scan.call_args_list)


def test_malformed_basil_parent_is_treated_as_one_off(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "registered_at": 1,
        }
    )
    event = make_event(
        {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "next_payment_attempt": None,
                    "parent": {"type": "subscription_details", "subscription_details": None},
                }
            },
        },
        event_id="evt_bad_parent",
        event_created=200,
    )

    assert stripe_webhook.lambda_handler(event, None)["statusCode"] == 200
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"


def test_update_rejects_scan_to_update_subscription_race(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "user@example.com",
            "status": "active",
            "payment_status": "paid",
            "stripe_customer_id": "cus_new",
            "stripe_subscription_id": "sub_new",
            "registered_at": 1,
        }
    )
    stale_subscriber = {
        "email": "user@example.com",
        "stripe_customer_id": "cus_old",
        "stripe_subscription_id": "sub_old",
    }

    updated = stripe_webhook._set_payment_status(
        stale_subscriber,
        "past_due",
        {"id": "evt_old", "created": 200, "priority": 1},
    )

    assert updated is False
    item = table.get_item(Key={"email": "user@example.com"}).get("Item")
    assert item["payment_status"] == "paid"
    assert item["stripe_subscription_id"] == "sub_new"


def test_checkout_put_race_preserves_bounce_suppression(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    original_put = table.put_item
    error_type = table.meta.client.exceptions.ConditionalCheckFailedException
    calls = 0

    def put_bounce_record_then_fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            original_put(
                Item={
                    "email": "raced@example.com",
                    "status": "unsubscribed",
                    "unsubscribed_reason": "bounce",
                    "registered_at": 1,
                }
            )
            raise error_type({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        return original_put(**kwargs)

    with mock.patch.object(stripe_webhook.dynamodb, "Table", return_value=table), mock.patch.object(
        table, "put_item", side_effect=put_bounce_record_then_fail
    ), mock.patch.object(stripe_webhook, "_notify_owner") as m_notify:
        resp = stripe_webhook.lambda_handler(
            checkout_completed_event("raced@example.com", event_id="evt_race", event_created=200),
            None,
        )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "raced@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "bounce"
    assert m_notify.call_count == 1


def test_checkout_update_race_preserves_new_bounce_suppression(stripe_webhook):
    table = stripe_webhook.dynamodb.Table("test-waitlist")
    table.put_item(
        Item={
            "email": "raced@example.com",
            "status": "pending",
            "registered_at": 1,
        }
    )
    original_update = table.update_item
    error_type = table.meta.client.exceptions.ConditionalCheckFailedException
    calls = 0

    def add_bounce_then_fail(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            original_update(
                Key={"email": "raced@example.com"},
                UpdateExpression="SET #status = :status, unsubscribed_reason = :reason",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "unsubscribed", ":reason": "bounce"},
            )
            raise error_type({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
        return original_update(**kwargs)

    with mock.patch.object(stripe_webhook.dynamodb, "Table", return_value=table), mock.patch.object(
        table, "update_item", side_effect=add_bounce_then_fail
    ), mock.patch.object(stripe_webhook, "_notify_owner") as m_notify:
        resp = stripe_webhook.lambda_handler(
            checkout_completed_event("raced@example.com", event_id="evt_race", event_created=200),
            None,
        )

    assert resp["statusCode"] == 200
    item = table.get_item(Key={"email": "raced@example.com"}).get("Item")
    assert item["status"] == "unsubscribed"
    assert item["unsubscribed_reason"] == "bounce"
    assert "payment_status" not in item
    assert m_notify.call_count == 1


def test_unhandled_event_type_returns_200(stripe_webhook):
    event = make_event({"type": "customer.created", "data": {"object": {}}})
    resp = stripe_webhook.lambda_handler(event, None)
    assert resp["statusCode"] == 200

