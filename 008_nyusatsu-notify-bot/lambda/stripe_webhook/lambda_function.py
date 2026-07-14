import base64
import hashlib
import hmac
import html
import json
import logging
import os
import time

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
ses = boto3.client("ses")

TABLE_NAME = os.environ["WAITLIST_TABLE_NAME"]
STRIPE_WEBHOOK_SECRET_PARAM_NAME = os.environ["STRIPE_WEBHOOK_SECRET_PARAM_NAME"]
NOTIFY_EMAIL_PARAM_NAME = os.environ["NOTIFY_EMAIL_PARAM_NAME"]
SES_SENDER_PARAM_NAME = os.environ["SES_SENDER_PARAM_NAME"]
SES_CONFIGURATION_SET_NAME = os.environ["SES_CONFIGURATION_SET_NAME"]

# 通知メール件名等に使うサービス名。collector/lp_waitlist Lambdaと合わせること(v0.14で改称)。
SERVICE_NAME = "入札情報ウォッチ"

# Stripeの署名タイムスタンプ許容誤差(秒)。公式SDKのデフォルトと同じ5分。
SIGNATURE_TOLERANCE_SEC = 300

_param_cache: dict[str, str] = {}


def _get_param(name: str, decrypt: bool = False) -> str:
    if name not in _param_cache:
        _param_cache[name] = ssm.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]
    return _param_cache[name]


def verify_signature(payload: str, sig_header: str, secret: str) -> bool:
    """StripeのWebhook署名をSDK不使用で検証する(公式アルゴリズムと同一:
    signed_payload = "{timestamp}.{payload}" のHMAC-SHA256を、ヘッダー内のv1値と比較)。
    タイムスタンプが許容誤差を超えている場合はリプレイとみなし拒否する。"""
    if not sig_header:
        return False
    timestamp = None
    v1_signatures = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)
    if timestamp is None or not v1_signatures:
        return False
    try:
        if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SEC:
            return False
    except ValueError:
        return False
    signed_payload = f"{timestamp}.{payload}"
    expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in v1_signatures)


def _notify_owner(subject: str, body: str) -> None:
    try:
        notify_email = _get_param(NOTIFY_EMAIL_PARAM_NAME)
        sender_email = _get_param(SES_SENDER_PARAM_NAME)
        # オーナー宛の内部通知。スマホでの視認性のため最小限のHTML版も付ける。
        body_html = (
            "<!doctype html><html lang=\"ja\"><body style=\"font-family:sans-serif;"
            "font-size:14px;line-height:1.7;color:#222222;\">"
            f"<div>{html.escape(body).replace(chr(10), '<br>')}</div></body></html>"
        )
        ses.send_email(
            Source=sender_email,
            Destination={"ToAddresses": [notify_email]},
            Message={
                "Subject": {"Data": f"【{SERVICE_NAME}】{subject}", "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
            ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
        )
    except Exception:
        logger.warning("owner notification failed", exc_info=True)


def _extract_email(session_obj: dict) -> str:
    details = session_obj.get("customer_details") or {}
    email = details.get("email") or session_obj.get("customer_email") or ""
    return email.strip().lower()


def handle_checkout_completed(session_obj: dict) -> None:
    email = _extract_email(session_obj)
    if not email:
        logger.warning("checkout.session.completed with no email, skipping")
        return
    customer_id = session_obj.get("customer") or ""
    subscription_id = session_obj.get("subscription") or ""
    now_ts = int(time.time())
    table = dynamodb.Table(TABLE_NAME)

    existing = table.get_item(Key={"email": email}).get("Item")
    if existing and existing.get("unsubscribed_reason") in ("bounce", "complaint"):
        # バウンス・苦情による送信健全性保護の抑制は、支払いがあっても上書きしない
        # (lp_waitlist Lambdaのhandle_registerと同じガード)。オーナーに手動対応を促す。
        logger.warning("payment received for suppressed address %s, not activating", email)
        _notify_owner(
            "支払い済みだが配信停止済みのアドレスです",
            f"アドレス: {email}\n配信停止理由: {existing.get('unsubscribed_reason')}\n"
            "自動では有効化していません。手動でのご確認をお願いします。",
        )
        return

    if existing:
        # 支払い完了は本人確認相当のハードルを超えているため、二重オプトイン
        # (登録確認メールのクリック)を省略してactive化する(ユーザー決定事項)。
        table.update_item(
            Key={"email": email},
            UpdateExpression=(
                "SET #s = :active, payment_status = :paid, stripe_customer_id = :cust, "
                "stripe_subscription_id = :sub, paid_at = :t "
                "REMOVE unsubscribed_at, unsubscribed_reason"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":active": "active",
                ":paid": "paid",
                ":cust": customer_id,
                ":sub": subscription_id,
                ":t": now_ts,
            },
        )
        logger.info("activated existing subscriber %s via Stripe payment", email)
    else:
        # LP未登録/メール不一致でも、支払いを最優先の意思表示とみなし自動登録する
        # (ユーザー決定事項)。オーナーには参考情報として通知する。
        table.put_item(
            Item={
                "email": email,
                "registered_at": now_ts,
                "status": "active",
                "payment_status": "paid",
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "paid_at": now_ts,
                "source": "stripe",
            }
        )
        logger.info("auto-registered new paying subscriber %s via Stripe", email)
        _notify_owner(
            "LP未登録アドレスからの支払いを検知しました",
            f"アドレス: {email}\n事前登録(LP)にはなかったメールアドレスですが、"
            "Stripeでの支払いを確認したため購読者として自動登録しました。",
        )


def _find_email_by_customer_id(customer_id: str) -> str | None:
    if not customer_id:
        return None
    table = dynamodb.Table(TABLE_NAME)
    scan_kwargs = {
        "FilterExpression": Attr("stripe_customer_id").eq(customer_id),
        "ProjectionExpression": "email",
    }
    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        if items:
            return items[0]["email"]
        if "LastEvaluatedKey" not in resp:
            return None
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _set_payment_status(email: str, payment_status: str) -> None:
    table = dynamodb.Table(TABLE_NAME)
    table.update_item(
        Key={"email": email},
        UpdateExpression="SET payment_status = :s",
        ExpressionAttributeValues={":s": payment_status},
    )


def handle_subscription_deleted(subscription_obj: dict) -> None:
    email = _find_email_by_customer_id(subscription_obj.get("customer") or "")
    if not email:
        logger.warning("subscription.deleted for unknown customer %s", subscription_obj.get("customer"))
        return
    _set_payment_status(email, "canceled")
    logger.info("subscription canceled for %s", email)


def handle_payment_failed(invoice_obj: dict) -> None:
    if invoice_obj.get("next_payment_attempt") is not None:
        # Stripeがまだリトライ中(Smart Retries)。最終失敗ではないため何もしない。
        logger.info("payment retry still pending for customer %s, ignoring", invoice_obj.get("customer"))
        return
    email = _find_email_by_customer_id(invoice_obj.get("customer") or "")
    if not email:
        logger.warning("invoice.payment_failed for unknown customer %s", invoice_obj.get("customer"))
        return
    _set_payment_status(email, "past_due")
    logger.info("payment failed (retries exhausted) for %s", email)


def handle_invoice_paid(invoice_obj: dict) -> None:
    """定期支払い(更新分含む)の成功を検知しpayment_status="paid"に戻す。
    invoice.payment_failedでpast_dueにした後、顧客がカード更新して支払いが
    成功しても復帰させる経路がなく、payment-requiredフラグ運用開始後は支払済み
    顧客に配信されない事故になりうる問題を解消(Fable指摘、2026-07-14)。"""
    email = _find_email_by_customer_id(invoice_obj.get("customer") or "")
    if not email:
        logger.warning("invoice.paid for unknown customer %s", invoice_obj.get("customer"))
        return
    _set_payment_status(email, "paid")
    logger.info("payment recovered/confirmed for %s", email)


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("stripe-signature", "")
    payload = event.get("body") or ""
    if event.get("isBase64Encoded"):
        payload = base64.b64decode(payload).decode("utf-8")

    secret = _get_param(STRIPE_WEBHOOK_SECRET_PARAM_NAME, decrypt=True)
    if not verify_signature(payload, sig_header, secret):
        logger.warning("signature verification failed")
        return {"statusCode": 400, "body": "invalid signature"}

    try:
        stripe_event = json.loads(payload)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "invalid json"}

    event_type = stripe_event.get("type", "")
    data_object = (stripe_event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(data_object)
    elif event_type == "invoice.payment_failed":
        handle_payment_failed(data_object)
    elif event_type == "invoice.paid":
        handle_invoice_paid(data_object)
    else:
        logger.info("ignoring unhandled event type %s", event_type)

    return {"statusCode": 200, "body": "ok"}
