import json
import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["WAITLIST_TABLE_NAME"]


def mark_unsubscribed(email: str, reason: str) -> None:
    """reason: "bounce" または "complaint"。handle_registerがこの理由を見て、
    バウンス・苦情による停止済みアドレスの再登録(=再送)を拒否する
    (送信健全性保護、lp_waitlist Lambda参照)。"""
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.update_item(
            Key={"email": email.strip().lower()},
            UpdateExpression="SET #s = :u, unsubscribed_at = :t, unsubscribed_reason = :r",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":u": "unsubscribed", ":t": int(time.time()), ":r": reason},
            ConditionExpression="attribute_exists(email)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # waitlist未登録アドレス(例: SSMのオーナー通知先)のバウンス・苦情。
        # update_itemはアップサートのため、条件なしだと不完全な幽霊レコードが
        # 新規作成されてしまう。登録されていないので何もしない。
        logger.info("%s for unregistered address %s, ignoring", reason, email)


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        # Configuration Set Event Destination経由の通知は"eventType"、
        # 旧来のIdentity Notification経由は"notificationType"を使う。
        # このLambdaはConfiguration Set経由(eventType)を主に使うが、
        # 念のため両方を見る。
        notification_type = message.get("eventType") or message.get("notificationType")

        if notification_type == "Complaint":
            # 苦情(迷惑メール報告)は即座に配信停止する。SESアカウントの送信健全性を守るため、
            # 一時的な不着かどうかの判定は行わない。
            recipients = message.get("complaint", {}).get("complainedRecipients", [])
            for r in recipients:
                email = r.get("emailAddress", "")
                if email:
                    logger.warning("complaint received, unsubscribing %s", email)
                    mark_unsubscribed(email, reason="complaint")

        elif notification_type == "Bounce":
            bounce = message.get("bounce", {})
            # Permanentバウンス(アドレス不存在等)のみ配信停止する。Transient
            # (メールボックス満杯等の一時的な不着)は次回配信でも再送されうるため対象外。
            if bounce.get("bounceType") == "Permanent":
                for r in bounce.get("bouncedRecipients", []):
                    email = r.get("emailAddress", "")
                    if email:
                        logger.warning("permanent bounce, unsubscribing %s", email)
                        mark_unsubscribed(email, reason="bounce")

    return {"statusCode": 200, "body": "processed"}
