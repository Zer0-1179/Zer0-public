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

# Stripe はイベントの配信順を保証しない。同じsubscriptionに対する遅延・再送を
# 過去の状態で上書きしないため、発生時刻と同時刻時の状態優先度を記録する。
# canceled は即時キャンセル後の終端状態として最優先にする。
EVENT_PRIORITIES = {
    "invoice.payment_failed": 1,
    "checkout.session.completed": 2,
    "invoice.paid": 2,
    "customer.subscription.deleted": 3,
}

_param_cache: dict[str, str] = {}


def _get_param(name: str, decrypt: bool = False) -> str:
    # Stripe endpoint secrets are rotated when switching Stripe environments.
    # A warm Lambda must never keep accepting an old endpoint secret after that
    # switch, so SecureString reads deliberately bypass the module cache.
    if decrypt:
        _param_cache.pop(name, None)
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
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
        # SES/SSM例外には宛先やリクエスト情報が含まれ得るため、例外全体は記録しない。
        logger.warning("owner notification failed")


def _extract_email(session_obj: dict) -> str:
    details = session_obj.get("customer_details") or {}
    email = details.get("email") or session_obj.get("customer_email") or ""
    return email.strip().lower()


def _event_metadata(stripe_event: dict) -> dict | None:
    """状態更新に必要なStripeイベントの順序情報だけを安全に取り出す。"""
    event_id = stripe_event.get("id")
    created = stripe_event.get("created")
    event_type = stripe_event.get("type")
    if (
        not isinstance(event_id, str)
        or not event_id
        or not isinstance(created, int)
        or isinstance(created, bool)
        or created < 0
        or event_type not in EVENT_PRIORITIES
    ):
        return None
    return {
        "id": event_id,
        "created": created,
        "priority": EVENT_PRIORITIES[event_type],
    }


def _fresh_event_condition() -> str:
    """既知の状態より新しいStripeイベントだけを受け入れるDynamoDB条件式。"""
    return (
        "attribute_not_exists(#last_created) OR #last_created < :event_created OR "
        "(#last_created = :event_created AND "
        "(attribute_not_exists(#last_priority) OR #last_priority < :event_priority)) OR "
        "(#last_created = :event_created AND #last_priority = :event_priority AND "
        "(attribute_not_exists(#last_id) OR #last_id <> :event_id))"
    )


def _event_attribute_names() -> dict[str, str]:
    return {
        "#last_created": "stripe_last_event_created",
        "#last_priority": "stripe_last_event_priority",
        "#last_id": "stripe_last_event_id",
    }


def _event_attribute_values(event_metadata: dict) -> dict:
    return {
        ":event_created": event_metadata["created"],
        ":event_priority": event_metadata["priority"],
        ":event_id": event_metadata["id"],
    }


def _is_delivery_suppressed(subscriber: dict | None) -> bool:
    return bool(subscriber and subscriber.get("unsubscribed_reason") in ("bounce", "complaint"))


def _notify_suppressed_payment(subscriber: dict) -> None:
    """バウンス・苦情で抑制中の支払いを自動再有効化せず運営者へ通知する。"""
    logger.warning("payment received for a suppressed address; not activating")
    _notify_owner(
        "支払い済みだが配信停止済みのアドレスです",
        f"アドレス: {subscriber['email']}\n配信停止理由: {subscriber.get('unsubscribed_reason')}\n"
        "自動では有効化していません。手動でのご確認をお願いします。",
    )


def handle_checkout_completed(
    session_obj: dict, event_metadata: dict, allow_put_retry: bool = True
) -> None:
    email = _extract_email(session_obj)
    if not email:
        logger.warning("checkout.session.completed with no email, skipping")
        return
    customer_id = session_obj.get("customer") or ""
    subscription_id = session_obj.get("subscription") or ""
    now_ts = int(time.time())
    table = dynamodb.Table(TABLE_NAME)

    existing = table.get_item(Key={"email": email}).get("Item")
    if _is_delivery_suppressed(existing):
        # バウンス・苦情による送信健全性保護の抑制は、支払いがあっても上書きしない
        # (lp_waitlist Lambdaのhandle_registerと同じガード)。オーナーに手動対応を促す。
        _notify_suppressed_payment(existing)
        return

    if existing:
        # 支払い完了は本人確認相当のハードルを超えているため、二重オプトイン
        # (登録確認メールのクリック)を省略してactive化する(ユーザー決定事項)。
        try:
            table.update_item(
                Key={"email": email},
                UpdateExpression=(
                    "SET #s = :active, payment_status = :paid, stripe_customer_id = :cust, "
                    "stripe_subscription_id = :sub, paid_at = :t, "
                    "#last_created = :event_created, #last_priority = :event_priority, "
                    "#last_id = :event_id "
                    "REMOVE unsubscribed_at, unsubscribed_reason"
                ),
                ConditionExpression=(
                    f"({_fresh_event_condition()}) AND "
                    "(attribute_not_exists(#unsubscribed_reason) OR "
                    "(#unsubscribed_reason <> :bounce AND #unsubscribed_reason <> :complaint))"
                ),
                ExpressionAttributeNames={
                    "#s": "status",
                    "#unsubscribed_reason": "unsubscribed_reason",
                    **_event_attribute_names(),
                },
                ExpressionAttributeValues={
                    ":active": "active",
                    ":paid": "paid",
                    ":cust": customer_id,
                    ":sub": subscription_id,
                    ":t": now_ts,
                    ":bounce": "bounce",
                    ":complaint": "complaint",
                    **_event_attribute_values(event_metadata),
                },
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # 読み取り後にbounce/complaintが記録された場合は、通知して終了する。
            # それ以外はイベント鮮度による安全な拒否として扱う。
            current = table.get_item(Key={"email": email}).get("Item")
            if _is_delivery_suppressed(current):
                _notify_suppressed_payment(current)
            else:
                logger.info("ignored a stale checkout event")
            return
        logger.info("activated an existing subscriber via Stripe payment")
    else:
        # LP未登録/メール不一致でも、支払いを最優先の意思表示とみなし自動登録する
        # (ユーザー決定事項)。オーナーには参考情報として通知する。
        try:
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
                    "stripe_last_event_created": event_metadata["created"],
                    "stripe_last_event_priority": event_metadata["priority"],
                    "stripe_last_event_id": event_metadata["id"],
                },
                # get_item後にバウンス/苦情抑制レコードが作られても上書きしない。
                ConditionExpression="attribute_not_exists(email)",
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            if allow_put_retry:
                logger.info("checkout raced with an existing subscriber; retrying safely")
                handle_checkout_completed(session_obj, event_metadata, allow_put_retry=False)
            else:
                logger.warning("checkout record changed during safe retry")
            return
        logger.info("auto-registered a new paying subscriber via Stripe")
        _notify_owner(
            "LP未登録アドレスからの支払いを検知しました",
            f"アドレス: {email}\n事前登録(LP)にはなかったメールアドレスですが、"
            "Stripeでの支払いを確認したため購読者として自動登録しました。",
        )


def _find_subscriber(customer_id: str, subscription_id: str) -> dict | None:
    if not customer_id or not subscription_id:
        return None
    table = dynamodb.Table(TABLE_NAME)
    scan_kwargs = {
        "FilterExpression": Attr("stripe_customer_id").eq(customer_id)
        & Attr("stripe_subscription_id").eq(subscription_id),
        # 直近に書き込まれた購読情報を支払いイベントで見落とさないよう、
        # subscription照合は常に強整合読み取りにする。
        "ConsistentRead": True,
        "ProjectionExpression": (
            "email, stripe_customer_id, stripe_subscription_id, payment_status"
        ),
    }
    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        if items:
            return items[0]
        if "LastEvaluatedKey" not in resp:
            return None
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _set_payment_status(subscriber: dict, payment_status: str, event_metadata: dict) -> bool:
    """対象subscriptionの新しいイベントだけで支払い状態を更新する。"""
    table = dynamodb.Table(TABLE_NAME)
    attribute_names = {
        "#payment_status": "payment_status",
        "#stripe_customer": "stripe_customer_id",
        "#stripe_subscription": "stripe_subscription_id",
        **_event_attribute_names(),
    }
    attribute_values = {
        ":payment_status": payment_status,
        ":stripe_customer": subscriber["stripe_customer_id"],
        ":stripe_subscription": subscriber["stripe_subscription_id"],
        **_event_attribute_values(event_metadata),
    }
    # Scan直後に新しいCheckoutが同じemailのsubscriptionを差し替えた場合も、
    # 古いイベントが新しい購読の状態を更新しないよう識別子を再確認する。
    condition = (
        f"({_fresh_event_condition()}) AND #stripe_customer = :stripe_customer "
        "AND #stripe_subscription = :stripe_subscription"
    )
    if payment_status != "canceled":
        # 同一subscriptionのキャンセル後に遅れて届く請求イベントで復帰させない。
        condition = f"({condition}) AND (attribute_not_exists(#payment_status) OR #payment_status <> :canceled)"
        attribute_values[":canceled"] = "canceled"
    try:
        table.update_item(
            Key={"email": subscriber["email"]},
            UpdateExpression=(
                "SET #payment_status = :payment_status, #last_created = :event_created, "
                "#last_priority = :event_priority, #last_id = :event_id"
            ),
            ConditionExpression=condition,
            ExpressionAttributeNames=attribute_names,
            ExpressionAttributeValues=attribute_values,
        )
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info("ignored a stale or terminal Stripe event")
        return False


def _invoice_subscription_id(invoice_obj: dict) -> str:
    """旧・Basil形式の請求書からsubscriptionを取得し、one-offは空文字列で返す。"""
    parent = invoice_obj.get("parent")
    if isinstance(parent, dict) and parent.get("type") == "subscription_details":
        details = parent.get("subscription_details")
        if isinstance(details, dict):
            subscription_id = details.get("subscription")
            if isinstance(subscription_id, str) and subscription_id:
                return subscription_id

    # Basilではparentが正規の参照先。旧形式だけのイベントとの互換性のために、
    # parentに有効なsubscriptionがない場合だけトップレベル値へフォールバックする。
    subscription_id = invoice_obj.get("subscription")
    if isinstance(subscription_id, str) and subscription_id:
        return subscription_id
    return ""


def handle_subscription_deleted(subscription_obj: dict, event_metadata: dict) -> None:
    customer_id = subscription_obj.get("customer") or ""
    subscription_id = subscription_obj.get("id") or ""
    subscriber = _find_subscriber(customer_id, subscription_id)
    if not subscriber:
        logger.warning("subscription.deleted for an unknown customer")
        return
    if _set_payment_status(subscriber, "canceled", event_metadata):
        logger.info("subscription canceled")


def handle_payment_failed(invoice_obj: dict, event_metadata: dict) -> None:
    """対象subscriptionの支払い失敗をpast_dueとして記録する。

    Stripe Billing Automations使用時はnext_payment_attemptがinvoice.payment_failedに
    含まれないため、その有無を終局判定に使わない。支払い成功時はinvoice.paidで
    paidへ復帰し、canceledは_set_payment_statusの条件式で終端状態として保持する。
    """
    subscriber = _find_subscriber(
        invoice_obj.get("customer") or "", _invoice_subscription_id(invoice_obj)
    )
    if not subscriber:
        logger.warning("invoice.payment_failed for an unknown subscription")
        return
    if _set_payment_status(subscriber, "past_due", event_metadata):
        logger.info("subscription payment requires attention")


def handle_invoice_paid(invoice_obj: dict, event_metadata: dict) -> None:
    """定期支払い(更新分含む)の成功を検知しpayment_status="paid"に戻す。
    invoice.payment_failedでpast_dueにした後、顧客がカード更新して支払いが
    成功しても復帰させる経路がなく、payment-requiredフラグ運用開始後は支払済み
    顧客に配信されない事故になりうる問題を解消(Fable指摘、2026-07-14)。"""
    subscriber = _find_subscriber(
        invoice_obj.get("customer") or "", _invoice_subscription_id(invoice_obj)
    )
    if not subscriber:
        logger.warning("invoice.paid for an unknown subscription")
        return
    if _set_payment_status(subscriber, "paid", event_metadata):
        logger.info("payment recovered or confirmed")


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

    if event_type not in EVENT_PRIORITIES:
        logger.info("ignoring unhandled event type %s", event_type)
        return {"statusCode": 200, "body": "ok"}

    event_metadata = _event_metadata(stripe_event)
    if event_metadata is None:
        logger.warning("Stripe event metadata is invalid")
        return {"statusCode": 400, "body": "invalid event metadata"}

    if event_type == "checkout.session.completed":
        handle_checkout_completed(data_object, event_metadata)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(data_object, event_metadata)
    elif event_type == "invoice.payment_failed":
        handle_payment_failed(data_object, event_metadata)
    elif event_type == "invoice.paid":
        handle_invoice_paid(data_object, event_metadata)

    return {"statusCode": 200, "body": "ok"}
