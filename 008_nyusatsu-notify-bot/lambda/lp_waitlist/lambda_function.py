import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
ses = boto3.client("ses")

TABLE_NAME = os.environ["WAITLIST_TABLE_NAME"]
NOTIFY_EMAIL_PARAM_NAME = os.environ["NOTIFY_EMAIL_PARAM_NAME"]
SES_SENDER_PARAM_NAME = os.environ["SES_SENDER_PARAM_NAME"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _get_param(name):
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]


def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _response(200, {})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json"})

    email = str(payload.get("email", "")).strip().lower()
    if not EMAIL_RE.match(email):
        return _response(400, {"error": "invalid_email"})

    table = dynamodb.Table(TABLE_NAME)
    try:
        table.put_item(
            Item={"email": email, "registered_at": int(time.time())},
            ConditionExpression="attribute_not_exists(email)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(200, {"status": "already_registered"})
        raise

    notify_email = _get_param(NOTIFY_EMAIL_PARAM_NAME)
    sender_email = _get_param(SES_SENDER_PARAM_NAME)
    ses.send_email(
        Source=sender_email,
        Destination={"ToAddresses": [notify_email]},
        Message={
            "Subject": {"Data": "[Nyusatsu LP] 事前登録がありました", "Charset": "UTF-8"},
            "Body": {
                "Text": {
                    "Data": f"事前登録メールアドレス: {email}",
                    "Charset": "UTF-8",
                }
            },
        },
    )

    return _response(200, {"status": "registered"})
