import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import time
import urllib.parse
from email.message import EmailMessage

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
ses = boto3.client("ses")

TABLE_NAME = os.environ["WAITLIST_TABLE_NAME"]
NOTIFY_EMAIL_PARAM_NAME = os.environ["NOTIFY_EMAIL_PARAM_NAME"]
SES_SENDER_PARAM_NAME = os.environ["SES_SENDER_PARAM_NAME"]
HMAC_SECRET_PARAM_NAME = os.environ["HMAC_SECRET_PARAM_NAME"]
SES_CONFIGURATION_SET_NAME = os.environ["SES_CONFIGURATION_SET_NAME"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

_secret_cache = None
_param_cache = {}


def _get_param(name: str, decrypt: bool = False) -> str:
    if name not in _param_cache:
        _param_cache[name] = ssm.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]
    return _param_cache[name]


def _get_secret() -> str:
    global _secret_cache
    if _secret_cache is None:
        _secret_cache = _get_param(HMAC_SECRET_PARAM_NAME)
    return _secret_cache


def make_token(email: str, purpose: str) -> str:
    """メールアドレス+用途(confirm/unsubscribe)から検証用トークンを生成する。
    DynamoDBにトークンを保存しないステートレス方式(HMAC-SHA256)。"""
    digest = hmac.new(_get_secret().encode(), f"{email}:{purpose}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_token(email: str, purpose: str, token: str) -> bool:
    return hmac.compare_digest(make_token(email, purpose), token or "")


def _json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _html_response(status_code, body_html):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": body_html,
    }


def _page(title: str, message: str) -> str:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        f"<title>{safe_title}</title>"
        "<style>body{font-family:sans-serif;background:#14181a;color:#e8e8e8;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
        ".box{max-width:480px;padding:2rem;text-align:center}"
        "a{color:#7ec9a1}</style>"
        f"</head><body><div class=\"box\"><h1>{safe_title}</h1><p>{safe_message}</p>"
        "</div></body></html>"
    )


def _get_query(event, key: str) -> str:
    return (event.get("queryStringParameters") or {}).get(key, "") or ""


def _base_url(event) -> str:
    domain = event.get("requestContext", {}).get("domainName", "")
    return f"https://{domain}"


def send_confirmation_email(email: str, confirm_url: str, sender: str) -> None:
    """確認メールをHTML(「登録を確定する」をクリック可能なリンクとして埋め込む)+
    プレーンテキスト(URLそのまま、フォールバック)のmultipart/alternativeで送る。
    生URLをメール本文に長く表示しないための対応。"""
    text_body = (
        "入札情報通知Bot（横浜市パイロット版）への事前登録を受け付けました。\n\n"
        f"登録メールアドレス: {email}\n\n"
        "以下のリンクをクリックして登録を確定してください。クリックするまで登録は完了せず、"
        "通知メールも配信されません。\n\n"
        f"{confirm_url}\n\n"
        "----\n"
        "本サービスは、横浜市が公開する入札公告のうち清掃・ビルメンテナンス関連案件を"
        "毎朝自動収集し、メールでお知らせするサービスです（現在無料テスト運用中）。\n\n"
        "心当たりのない場合は、上記リンクをクリックせずこのメールを破棄してください。"
        "その場合、登録情報は自動的に有効化されません。"
    )
    html_body = (
        "<!doctype html><html lang=\"ja\"><body style=\"font-family:sans-serif;"
        "line-height:1.7;color:#222\">"
        "<p>入札情報通知Bot（横浜市パイロット版）への事前登録を受け付けました。</p>"
        f"<p>登録メールアドレス: {html.escape(email)}</p>"
        f"<p><a href=\"{html.escape(confirm_url)}\">登録を確定する</a><br>"
        "クリックするまで登録は完了せず、通知メールも配信されません。</p>"
        "<hr style=\"margin:24px 0;border:none;border-top:1px solid #ddd\">"
        "<p style=\"font-size:13px;color:#666\">"
        "本サービスは、横浜市が公開する入札公告のうち清掃・ビルメンテナンス関連案件を"
        "毎朝自動収集し、メールでお知らせするサービスです（現在無料テスト運用中）。<br><br>"
        "心当たりのない場合は、上記リンクをクリックせずこのメールを破棄してください。"
        "その場合、登録情報は自動的に有効化されません。</p></body></html>"
    )
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = email
    msg["Subject"] = "【入札情報通知Bot】登録確認のお願い"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    ses.send_raw_email(
        Source=sender,
        Destinations=[email],
        RawMessage={"Data": msg.as_bytes()},
        ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
    )


def notify_owner_confirmed(email: str) -> None:
    notify_email = _get_param(NOTIFY_EMAIL_PARAM_NAME)
    sender_email = _get_param(SES_SENDER_PARAM_NAME)
    ses.send_email(
        Source=sender_email,
        Destination={"ToAddresses": [notify_email]},
        Message={
            "Subject": {"Data": "[Nyusatsu LP] 事前登録が確認されました", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": f"確認済みメールアドレス: {email}", "Charset": "UTF-8"}},
        },
        ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
    )


def handle_register(event):
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json_response(400, {"error": "invalid_json"})

    # honeypot: フォームの非表示フィールド(website)が埋まっていればbotとみなし、
    # 正常登録したかのように振る舞って早期リターンする(botに気づかせない)。
    if str(payload.get("website", "")).strip():
        logger.info("honeypot triggered, ignoring submission")
        return _json_response(200, {"status": "registered"})

    email = str(payload.get("email", "")).strip().lower()
    if not EMAIL_RE.match(email):
        return _json_response(400, {"error": "invalid_email"})

    source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp", "")
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.put_item(
            Item={
                "email": email,
                "registered_at": int(time.time()),
                "status": "pending",
                "source_ip": source_ip,
            },
            ConditionExpression="attribute_not_exists(email)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = table.get_item(Key={"email": email}).get("Item", {})
        if existing.get("status") == "unsubscribed":
            # 配信停止済みアドレスからの再登録: pendingに戻し確認メールを再送する
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET #s = :pending, registered_at = :t REMOVE unsubscribed_at",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": "pending", ":t": int(time.time())},
            )
        else:
            return _json_response(200, {"status": "already_registered"})

    # 登録(DynamoDB書き込み)は既に成功しているため、確認メール送信が失敗しても
    # 利用者にはエラーを返さない(再送すればよいだけで実害はない)。
    try:
        sender_email = _get_param(SES_SENDER_PARAM_NAME)
        token = make_token(email, "confirm")
        confirm_url = f"{_base_url(event)}/confirm?email={urllib.parse.quote(email)}&token={token}"
        send_confirmation_email(email, confirm_url, sender_email)
    except Exception:
        logger.warning("confirmation email failed for %s", email, exc_info=True)

    return _json_response(200, {"status": "registered"})


def handle_confirm(event):
    email = _get_query(event, "email").strip().lower()
    token = _get_query(event, "token")
    if not email or not verify_token(email, "confirm", token):
        return _html_response(400, _page("確認できませんでした", "リンクが無効です。お手数ですが再度登録をお試しください。"))

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"email": email}).get("Item")
    if not item:
        return _html_response(404, _page("確認できませんでした", "登録情報が見つかりませんでした。"))

    if item.get("status") != "active":
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :active, confirmed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":active": "active", ":t": int(time.time())},
        )
        try:
            notify_owner_confirmed(email)
        except Exception:
            logger.warning("owner confirm notification failed for %s", email, exc_info=True)

    return _html_response(
        200,
        _page("登録を確認しました", "ご登録ありがとうございます。清掃関連の入札情報が見つかり次第、メールでお知らせします。"),
    )


def handle_unsubscribe(event, method: str):
    email = _get_query(event, "email").strip().lower()
    token = _get_query(event, "token")
    if not email or not verify_token(email, "unsubscribe", token):
        return _html_response(400, _page("手続きできませんでした", "リンクが無効です。"))

    if method == "GET":
        action_url = f"?email={urllib.parse.quote(email)}&token={urllib.parse.quote(token)}"
        form_html = (
            "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
            "<title>配信停止の確認</title>"
            "<style>body{font-family:sans-serif;background:#14181a;color:#e8e8e8;"
            "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
            ".box{max-width:480px;padding:2rem;text-align:center}"
            "button{background:#e08a8a;color:#14181a;border:none;padding:0.75rem 1.5rem;"
            "border-radius:6px;font-size:1rem;cursor:pointer}</style></head><body>"
            "<div class=\"box\"><h1>配信を停止しますか？</h1>"
            f"<p>{html.escape(email)} 宛の通知メール配信を停止します。</p>"
            f"<form method=\"POST\" action=\"{html.escape(action_url)}\">"
            "<button type=\"submit\">配信を停止する</button></form></div></body></html>"
        )
        return _html_response(200, form_html)

    # POST: 上記フォーム送信、またはメールクライアントによる
    # One-Click Unsubscribe(RFC 8058, List-Unsubscribe-Post)からの直接リクエスト。
    table = dynamodb.Table(TABLE_NAME)
    table.update_item(
        Key={"email": email},
        UpdateExpression="SET #s = :u, unsubscribed_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":u": "unsubscribed", ":t": int(time.time())},
    )
    return _html_response(200, _page("配信を停止しました", "ご利用ありがとうございました。配信を停止しました。"))


def lambda_handler(event, context):
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", "")
    path = http_ctx.get("path", "") or event.get("rawPath", "")

    if method == "OPTIONS":
        return _json_response(200, {})
    if path == "/register" and method == "POST":
        return handle_register(event)
    if path == "/confirm" and method == "GET":
        return handle_confirm(event)
    if path == "/unsubscribe" and method in ("GET", "POST"):
        return handle_unsubscribe(event, method)

    return _json_response(404, {"error": "not_found"})
