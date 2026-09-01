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
import urllib.request
from datetime import datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage

import boto3
from boto3.dynamodb.conditions import Attr
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
MATCH_HISTORY_TABLE_NAME = os.environ["MATCH_HISTORY_TABLE_NAME"]
# LINE通知(v0.28)。チャネルアクセストークン/シークレットは実際にはType: String
# (AWS::SSM::ParameterはネイティブでSecureStringをサポートしないため、
# cfn-lp-backend.yaml参照)のリテラルプレースホルダー。ユーザーがLINE Developers
# コンソールでチャネル作成後にCLIで上書きするまでは未設定状態。
LINE_CHANNEL_ACCESS_TOKEN_PARAM_NAME = os.environ["LINE_CHANNEL_ACCESS_TOKEN_PARAM_NAME"]
LINE_CHANNEL_SECRET_PARAM_NAME = os.environ["LINE_CHANNEL_SECRET_PARAM_NAME"]
LINE_LIFF_ID_PARAM_NAME = os.environ["LINE_LIFF_ID_PARAM_NAME"]
LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 利用者向けメールの差出人表示名・件名プレフィックスに使うサービス名。
# collector Lambda側のSERVICE_NAMEと合わせること(v0.14で「Bot」を含む旧名称から改称)。
SERVICE_NAME = "入札情報ウォッチ"
INQUIRY_EMAIL = "nyusatsu@zer0-infra.com"

# 横浜市電子調達システムのURL(collector LambdaのBASE_URLと同じ値)。バックフィル
# ウェルカムメールで案件ページへのリンクを組み立てるために使う。
YOKOHAMA_BASE_URL = "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p"


def _from_address(sender: str) -> Address:
    """差出人に日本語のサービス名を表示名として付ける(Addressを使うことで
    policy.defaultがRFC 2047エンコードを正しく行う)。SESのSource(エンベロープ)は
    従来どおり素のアドレスのまま。"""
    local_part, _, domain = sender.partition("@")
    return Address(display_name=SERVICE_NAME, username=local_part, domain=domain)

# 確認メール(登録・再登録時)の再送は最短でもこの秒数を空ける。
# 第三者が停止済み/未確認アドレスへ繰り返しPOSTして確認メールを送りつけさせる
# (メール爆撃)ことの抑止。
CONFIRMATION_RESEND_COOLDOWN_SEC = 300

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


def verify_line_signature(body: str, signature: str, secret: str) -> bool:
    """LINE Messaging APIのWebhook署名(X-Line-Signature)を検証する。
    LINEの仕様はStripeと異なりHMAC-SHA256のbase64エンコードそのものを1個だけ
    比較する(Stripeのようなタイムスタンプ付きの複数署名リストではない)。"""
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature or "")


def send_line_push(line_user_id: str, text: str) -> None:
    """LINE Messaging APIでプッシュメッセージを1件送信する(v0.28)。
    メール送信(SES)と違いLambda標準ライブラリのみで完結させるため、requestsは
    使わずurllib.requestで直接HTTP POSTする(プロジェクト共通方針)。"""
    token = _get_param(LINE_CHANNEL_ACCESS_TOKEN_PARAM_NAME, decrypt=True)
    payload = json.dumps({
        "to": line_user_id,
        # LINEのテキストメッセージは1通5000文字までのため安全側で切り詰める。
        "messages": [{"type": "text", "text": text[:4900]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        LINE_PUSH_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"LINE push failed: status={resp.status}")


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


LP_TOP_URL = "https://nyusatsu.zer0-infra.com/"


def _page(title: str, message: str, link_html: str = "") -> str:
    """確認・配信停止結果ページの共通レイアウト。LP・メールと同じ白背景+青系アクセント
    (#2b6cb0)のトーンに統一する(v0.20でメールをカード型に刷新した際、このページだけ
    旧来のダーク基調が残っていたためユーザー指摘で統一)。link_htmlは次のアクションへの
    導線(次に進むリンク等)を任意で追加する場合に使う(Fable指摘、2026-07-13。以前は
    確認完了ページに次の導線が一切無かった)。"""
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>{safe_title}</title>"
        "<style>body{font-family:sans-serif;background:#f4f5f7;color:#222222;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
        ".box{max-width:480px;padding:2rem;text-align:center;background:#ffffff;"
        "border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08)}"
        "h1{font-size:1.25rem;color:#1a3550}"
        "a{color:#2b6cb0}</style>"
        f"</head><body><div class=\"box\"><h1>{safe_title}</h1><p>{safe_message}</p>"
        f"{link_html}"
        "</div></body></html>"
    )


def _get_query(event, key: str) -> str:
    return (event.get("queryStringParameters") or {}).get(key, "") or ""


def _base_url(event) -> str:
    domain = event.get("requestContext", {}).get("domainName", "")
    return f"https://{domain}"


def _wrap_html_email(content_html: str, footer_html: str) -> str:
    """本文HTMLを、スマホでも読みやすい共通レイアウト(白背景カード+サービス名見出し+
    フッター)で包む。メールクライアントはCSSサポートが限定的なため、テーブルレイアウト+
    インラインスタイルのみを使う(collector Lambdaのbuild_html_bodyと同じデザイン)。"""
    return (
        "<!doctype html><html lang=\"ja\"><body style=\"margin:0;padding:0;background-color:#f4f5f7;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"background-color:#f4f5f7;\">"
        "<tr><td align=\"center\" style=\"padding:16px 8px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"max-width:600px;background-color:#ffffff;border-radius:8px;\">"
        "<tr><td style=\"padding:20px 16px;font-family:sans-serif;font-size:14px;"
        "color:#222222;line-height:1.7;\">"
        "<div style=\"font-size:13px;font-weight:bold;color:#2b6cb0;"
        "border-bottom:2px solid #2b6cb0;padding-bottom:8px;margin-bottom:16px;\">"
        f"{SERVICE_NAME}（横浜市パイロット版）</div>"
        f"{content_html}"
        "</td></tr></table>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"max-width:600px;\">"
        "<tr><td style=\"padding:14px 16px;font-family:sans-serif;font-size:12px;"
        "color:#888888;line-height:1.8;\">"
        f"{footer_html}"
        "</td></tr></table>"
        "</td></tr></table></body></html>"
    )


def send_confirmation_email(email: str, confirm_url: str, sender: str) -> None:
    """確認メールをHTML(「登録を確定する」をクリック可能なボタンとして埋め込む)+
    プレーンテキスト(URLそのまま、フォールバック)のmultipart/alternativeで送る。
    生URLをメール本文に長く表示しないための対応。"""
    text_body = (
        f"「{SERVICE_NAME}」（横浜市パイロット版）への事前登録を受け付けました。\n\n"
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
    content_html = (
        f"<p style=\"margin:0 0 16px;\">「{SERVICE_NAME}」（横浜市パイロット版）への"
        "事前登録を受け付けました。</p>"
        f"<p style=\"margin:0 0 20px;\">登録メールアドレス: {html.escape(email)}</p>"
        "<div style=\"margin:0 0 12px;\">"
        f"<a href=\"{html.escape(confirm_url)}\" style=\"display:inline-block;"
        "padding:12px 28px;background-color:#2b6cb0;color:#ffffff;font-size:15px;"
        "font-weight:bold;text-decoration:none;border-radius:6px;\">登録を確定する</a></div>"
        "<p style=\"margin:0;font-size:13px;color:#666666;\">"
        "上のボタンをクリックするまで登録は完了せず、通知メールも配信されません。</p>"
    )
    footer_html = (
        "本サービスは、横浜市が公開する入札公告のうち清掃・ビルメンテナンス関連案件を"
        "毎朝自動収集し、メールでお知らせするサービスです（現在無料テスト運用中）。<br><br>"
        "心当たりのない場合は、上記ボタンをクリックせずこのメールを破棄してください。"
        "その場合、登録情報は自動的に有効化されません。"
    )
    html_body = _wrap_html_email(content_html, footer_html)
    msg = EmailMessage()
    msg["From"] = _from_address(sender)
    msg["To"] = email
    msg["Subject"] = f"【{SERVICE_NAME}】登録確認のお願い"
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
    body_text = f"確認済みメールアドレス: {email}"
    # オーナー宛の内部通知。スマホでの視認性のため最小限のHTML版も付ける。
    body_html = (
        "<!doctype html><html lang=\"ja\"><body style=\"font-family:sans-serif;"
        "font-size:14px;line-height:1.7;color:#222222;\">"
        f"<div>{html.escape(body_text)}</div></body></html>"
    )
    ses.send_email(
        Source=sender_email,
        Destination={"ToAddresses": [notify_email]},
        Message={
            "Subject": {"Data": f"【{SERVICE_NAME}】事前登録が確認されました", "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"},
            },
        },
        ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
    )


def get_recent_matches(days: int = 30) -> list[dict]:
    """直近days日以内にマッチした案件履歴を新しい順で取得する。
    登録確認時のバックフィルウェルカムメールで「実際に届く案件のイメージ」を
    示すために使う(Fable指摘: 最初の実メールまで数週間無音になりうる問題への対応、v0.11)。"""
    table = dynamodb.Table(MATCH_HISTORY_TABLE_NAME)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    items: list[dict] = []
    scan_kwargs = {"FilterExpression": Attr("matched_at").gte(cutoff)}
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    items.sort(key=lambda i: i.get("matched_at", ""), reverse=True)
    return items


def history_detail_url(item: dict) -> str:
    """履歴itemから案件ページのURLを返す。collector側が保存したdetail_url(個別案件の
    詳細ページ、GETで直接開けることを実測確認済み)を優先し、detail_urlを持たない
    旧レコードは公告の案件一覧ページにフォールバックする。"""
    if item.get("detail_url"):
        return item["detail_url"]
    return f"{YOKOHAMA_BASE_URL}?job=KokokuAnkenList&kokoku_no={int(item['kokoku_no'])}"


def format_history_line(item: dict) -> str:
    line = (
        f"・{item.get('title', '')}\n"
        f"  契約番号: {item.get('contract_no', '')} / 入札方式: {item.get('method', '')} / 担当: {item.get('dept', '')}\n"
    )
    if item.get("category_detail"):
        line += f"  種目: {item['category_detail']}\n"
    qualification = [p for p in (item.get("area_rank"), item.get("company_size")) if p]
    if qualification:
        line += f"  参加資格: {' / '.join(qualification)}\n"
    if item.get("location"):
        line += f"  履行場所: {item['location']}\n"
    if item.get("period"):
        line += f"  履行期間: {item['period']}\n"
    line += f"  案件詳細: {history_detail_url(item)}\n"
    return line


def case_card_html(info: dict, url: str | None) -> str:
    """1案件をカード状(枠+ラベル/値の2列テーブル+詳細ページへのリンクボタン)の
    HTMLにする。collector Lambdaの同名関数と同じデザイン(スマホのメールクライアント
    でも崩れないテーブルレイアウト+インラインスタイルのみ)。"""
    rows = [
        ("契約番号", info.get("contract_no", "")),
        ("入札方式", info.get("method", "")),
        ("担当", info.get("dept", "")),
    ]
    if info.get("category_detail"):
        rows.append(("種目", info["category_detail"]))
    qualification = [p for p in (info.get("area_rank"), info.get("company_size")) if p]
    if qualification:
        rows.append(("参加資格", " / ".join(qualification)))
    if info.get("location"):
        rows.append(("履行場所", info["location"]))
    if info.get("period"):
        rows.append(("履行期間", info["period"]))
    if info.get("bid_opening"):
        rows.append(("開札予定", info["bid_opening"]))
    rows_html = "".join(
        "<tr>"
        f"<td style=\"padding:2px 10px 2px 0;font-size:12px;color:#888888;"
        f"white-space:nowrap;vertical-align:top;\">{html.escape(label)}</td>"
        f"<td style=\"padding:2px 0;font-size:13px;color:#333333;\">{html.escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )
    link_html = ""
    if url:
        link_html = (
            "<div style=\"margin-top:10px;\">"
            f"<a href=\"{html.escape(url)}\" style=\"display:inline-block;padding:8px 16px;"
            "background-color:#2b6cb0;color:#ffffff;font-size:13px;text-decoration:none;"
            "border-radius:4px;\">案件詳細を開く</a></div>"
        )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"margin:0 0 12px;border:1px solid #dde3ea;border-radius:6px;background-color:#fbfcfd;\">"
        "<tr><td style=\"padding:12px 14px;\">"
        f"<div style=\"font-size:15px;font-weight:bold;color:#1a3550;line-height:1.5;\">{html.escape(info.get('title', ''))}</div>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"margin-top:8px;line-height:1.6;\">{rows_html}</table>"
        f"{link_html}"
        "</td></tr></table>"
    )


def send_welcome_email(email: str, sender: str, unsubscribe_url: str) -> None:
    """登録確認完了時に、直近1ヶ月の該当案件（あれば）をまとめて送るバックフィル
    ウェルカムメール。案件がない場合も「システムは正常に稼働している」ことを伝え、
    登録後の沈黙による不安を解消する(Fable指摘、v0.11)。

    collector Lambdaの通知メールと同じくList-Unsubscribeヘッダー+本文フッターの
    配信停止リンクを付ける(以前はこのメールだけ配信停止導線が無かった、
    Fable指摘、レビュー2026-07-11)。"""
    recent = get_recent_matches(days=30)

    if recent:
        intro = (
            f"ご登録ありがとうございます。過去1ヶ月に対象の案件が{len(recent)}件ありました。"
            "参考までにご案内します（すでに締切を過ぎている案件も含みます。今後は新着があり次第、随時お届けします）。"
        )
        lines = [intro + "\n"]
        card_htmls = []
        for item in recent[:10]:
            lines.append(format_history_line(item))
            card_htmls.append(case_card_html(item, history_detail_url(item)))
        body = "\n".join(lines)
        content_html = f"<p style=\"margin:0 0 16px;\">{html.escape(intro)}</p>" + "".join(card_htmls)
        subject = f"【{SERVICE_NAME}】直近1ヶ月の該当案件（参考）"
    else:
        body = (
            "ご登録ありがとうございます。\n\n"
            "横浜市の入札公告は原則毎週火曜日に発行されます。過去1ヶ月は該当する案件が"
            "ありませんでしたが、システムは毎朝正常に稼働し、公告をチェックしています。\n\n"
            "該当案件が見つかり次第、すぐにメールでお知らせします。"
        )
        content_html = (
            "<p style=\"margin:0 0 16px;\">ご登録ありがとうございます。</p>"
            "<p style=\"margin:0 0 16px;\">横浜市の入札公告は原則毎週火曜日に発行されます。"
            "過去1ヶ月は該当する案件がありませんでしたが、システムは毎朝正常に稼働し、"
            "公告をチェックしています。</p>"
            "<p style=\"margin:0;\">該当案件が見つかり次第、すぐにメールでお知らせします。</p>"
        )
        subject = f"【{SERVICE_NAME}】ご登録ありがとうございます"

    footer_text = (
        "\n\n---\n"
        f"本メールは「{SERVICE_NAME}」（横浜市パイロット版）から自動配信しています。\n"
        f"配信停止はこちら: {unsubscribe_url}\n"
        f"お問い合わせは {INQUIRY_EMAIL} までご連絡ください。"
    )
    footer_html = (
        f"本メールは「{SERVICE_NAME}」（横浜市パイロット版）から自動配信しています。<br>"
        f"<a href=\"{html.escape(unsubscribe_url)}\" style=\"color:#2b6cb0;\">配信停止はこちら</a><br>"
        f"お問い合わせは {INQUIRY_EMAIL} までご連絡ください。"
    )
    html_body = _wrap_html_email(content_html, footer_html)

    msg = EmailMessage()
    msg["From"] = _from_address(sender)
    msg["To"] = email
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body + footer_text)
    msg.add_alternative(html_body, subtype="html")
    ses.send_raw_email(
        Source=sender,
        Destinations=[email],
        RawMessage={"Data": msg.as_bytes()},
        ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
    )


def send_line_link_email(email: str, liff_url: str, sender: str) -> None:
    """既存の登録済みメールアドレスへ、LINE連携用のLIFF URLをメールで送る。
    第三者が対象アドレスを知っているだけでLINEチャネルへ勝手に切り替えられない
    よう、URLをAPIレスポンスで直接返さずメール本文でのみ届ける(メール所有の
    確認を挟む。実機レビューで発覚した乗っ取り脆弱性の修正、2026-07-14)。"""
    text_body = (
        f"「{SERVICE_NAME}」のLINE通知への切り替えリクエストを受け付けました。\n\n"
        f"対象メールアドレス: {email}\n\n"
        "以下のリンクをLINEアプリで開くと連携が完了します。開くまで切り替えは反映されず、"
        "現在の通知方法のまま届きます。\n\n"
        f"{liff_url}\n\n"
        "----\n"
        "心当たりのない場合は、このメールを破棄してください。リンクを開かない限り、"
        "通知方法は変更されません。"
    )
    content_html = (
        f"<p style=\"margin:0 0 16px;\">「{SERVICE_NAME}」のLINE通知への切り替え"
        "リクエストを受け付けました。</p>"
        f"<p style=\"margin:0 0 20px;\">対象メールアドレス: {html.escape(email)}</p>"
        "<div style=\"margin:0 0 12px;\">"
        f"<a href=\"{html.escape(liff_url)}\" style=\"display:inline-block;"
        "padding:12px 28px;background-color:#06c755;color:#ffffff;font-size:15px;"
        "font-weight:bold;text-decoration:none;border-radius:6px;\">LINEで連携する</a></div>"
        "<p style=\"margin:0;font-size:13px;color:#666666;\">"
        "リンクを開くまで通知方法は変更されません。心当たりのない場合は破棄してください。</p>"
    )
    footer_html = (
        "心当たりのない場合は、このメールを破棄してください。リンクを開かない限り、"
        "通知方法は変更されません。"
    )
    html_body = _wrap_html_email(content_html, footer_html)
    msg = EmailMessage()
    msg["From"] = _from_address(sender)
    msg["To"] = email
    msg["Subject"] = f"【{SERVICE_NAME}】LINE通知への切り替えについて"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    ses.send_raw_email(
        Source=sender,
        Destinations=[email],
        RawMessage={"Data": msg.as_bytes()},
        ConfigurationSetName=SES_CONFIGURATION_SET_NAME,
    )


def _line_pending_response(email: str, via_email: bool = False) -> dict:
    """channel="line"登録に対して返すレスポンスを組み立てる。
    新規登録(via_email=False)はLIFF連携URLをレスポンスに含めて即座に案内する
    (メール所有の検証は不要、乗っ取れる既存の購読が存在しないため)。
    既存アドレス(via_email=True、active/pending/unsubscribed)へのチャネル切替は
    URLをレスポンスに含めず登録済みメールアドレス宛に送る。第三者が対象アドレスを
    知っているだけで無断でLINEチャネルに切り替えられる乗っ取りを防ぐため
    (handle_registerの複数の分岐から呼ばれる、2026-07-14修正)。"""
    token = make_token(email, "line_link")
    liff_id = _get_param(LINE_LIFF_ID_PARAM_NAME)
    liff_url = f"https://liff.line.me/{liff_id}?token={urllib.parse.quote(token)}&email={urllib.parse.quote(email)}"
    if via_email:
        try:
            sender_email = _get_param(SES_SENDER_PARAM_NAME)
            send_line_link_email(email, liff_url, sender_email)
        except Exception as exc:
            logger.warning("line link email failed; error_type=%s", type(exc).__name__)
        return _json_response(200, {"status": "line_pending"})
    return _json_response(200, {"status": "line_pending", "liff_url": liff_url})


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

    # 通知チャネル(v0.28)。"line"以外は全て"email"扱い(後方互換: 旧フロントエンドは
    # channelを送らないため、そのまま従来通りメール確認フローに乗る)。
    channel = str(payload.get("channel", "email")).strip().lower()
    if channel != "line":
        channel = "email"

    source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp", "")
    table = dynamodb.Table(TABLE_NAME)
    now_ts = int(time.time())
    # 既存レコードが見つかった(=真に新規登録ではない)かどうか。channel="line"の
    # レスポンス方式(URLを直接返すか、メール経由にするか)の判断に使う
    # (乗っ取り脆弱性の修正、2026-07-14)。
    record_existed = False
    try:
        table.put_item(
            Item={
                "email": email,
                "registered_at": now_ts,
                "status": "pending",
                "channel": channel,
                "source_ip": source_ip,
                "last_confirm_sent_at": now_ts,
            },
            ConditionExpression="attribute_not_exists(email)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        record_existed = True
        existing = table.get_item(Key={"email": email}).get("Item", {})
        status = existing.get("status")

        if status == "active":
            # 第三者が任意のメールアドレスの購読状態(activeか否か)を判別できて
            # しまうため、他のケースと同じ"registered"を返す
            # (Fable指摘、レビュー2026-07-11)。channel="line"の場合も、新規登録時と
            # 同じ形のline_pending+liff_urlを返すことで判別不能性を維持しつつ、
            # 既にメールでactive済みの利用者がLINEへ切り替えられるようにする
            # (v0.28で発覚したバグの修正: 以前はここで一律"registered"を返して
            # おり、既存購読者がLINEへの切替をリクエストしてもliff_urlが発行
            # されず何も起きなかった)。
            if channel == "line":
                return _line_pending_response(email, via_email=True)
            return _json_response(200, {"status": "registered"})

        if status == "unsubscribed" and existing.get("unsubscribed_reason") in ("bounce", "complaint"):
            # バウンス・苦情による配信停止は送信健全性保護のための抑制なので、
            # 本人以外でも叩けるこのエンドポイントでは再登録による復活を許さない。
            # channel="line"でも同じ形のレスポンスを返し判別不能性を保つ
            # (handle_line_link側でunsubscribed状態は理由を問わず復活させない
            # ガードが既にあるため、liff_urlを発行しても実害はない、v0.28)。
            logger.info(
                "registration blocked for a suppressed address (reason=%s)",
                existing.get("unsubscribed_reason"),
            )
            if channel == "line":
                return _line_pending_response(email, via_email=True)
            return _json_response(200, {"status": "registered"})

        # status は "pending"(確認メール未クリック) または "unsubscribed"(reason="user"
        # ないし旧レコードでreason未設定)。どちらも再登録は許すが、確認メールの
        # 連続再送はクールダウンで抑止する(第三者によるメール爆撃対策)。LINE切替の
        # 再登録はメール送信を伴わないためクールダウン対象外(下のchannel分岐後に処理)。
        last_sent = int(existing.get("last_confirm_sent_at", 0))
        if channel == "email" and now_ts - last_sent < CONFIRMATION_RESEND_COOLDOWN_SEC:
            logger.info("confirmation resend suppressed by cooldown")
            return _json_response(200, {"status": "registered"})

        update_expr = "SET #s = :pending, last_confirm_sent_at = :t, channel = :channel"
        expr_values = {":pending": "pending", ":t": now_ts, ":channel": channel}
        if status == "unsubscribed":
            update_expr += ", registered_at = :t REMOVE unsubscribed_at, unsubscribed_reason"
        table.update_item(
            Key={"email": email},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=expr_values,
        )

    if channel == "line":
        # LINEは友だち追加(LIFF連携)そのものが本人確認になるため、真に新規の
        # アドレス(record_existed=False)はメールでの二重オプトインを行わずLIFF連携
        # URLを直接返す。既存レコード(pending/unsubscribed(user)からの再登録)は
        # 第三者が対象アドレスを知っているだけで乗っ取れないよう、メール経由に
        # する(2026-07-14修正)。実際の紐付けはhandle_line_linkで行う(v0.28)。
        return _line_pending_response(email, via_email=record_existed)

    # 登録(DynamoDB書き込み)は既に成功しているため、確認メール送信が失敗しても
    # 利用者にはエラーを返さない(再送すればよいだけで実害はない)。
    try:
        sender_email = _get_param(SES_SENDER_PARAM_NAME)
        token = make_token(email, "confirm")
        confirm_url = f"{_base_url(event)}/confirm?email={urllib.parse.quote(email)}&token={token}"
        send_confirmation_email(email, confirm_url, sender_email)
    except Exception as exc:
        logger.warning("confirmation email failed; error_type=%s", type(exc).__name__)

    return _json_response(200, {"status": "registered"})


def handle_line_link(event):
    """LIFFページ(line-link.html)からのPOSTを受け、line_link用トークンを検証した上で
    line_user_idを紐付けactive化する(v0.28)。メールの二重オプトイン(handle_confirm)に
    相当するLINE版のエンドポイント。"""
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json_response(400, {"error": "invalid_json"})

    email = str(payload.get("email", "")).strip().lower()
    token = str(payload.get("token", ""))
    line_user_id = str(payload.get("line_user_id", "")).strip()
    if not email or not verify_token(email, "line_link", token) or not line_user_id:
        return _json_response(400, {"error": "invalid_token"})

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"email": email}).get("Item")
    if not item:
        return _json_response(404, {"error": "not_found"})

    status = item.get("status")
    if status == "unsubscribed":
        # handle_confirmと同じ方針: 配信停止済みアドレスへのトークンは無期限の
        # ステートレスHMACのため、本人の停止意思を尊重し無条件には復活させない。
        return _json_response(200, {"status": "unsubscribed"})

    if status != "active" or item.get("line_user_id") != line_user_id:
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :active, channel = :line, line_user_id = :uid, confirmed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":active": "active", ":line": "line", ":uid": line_user_id, ":t": int(time.time()),
            },
        )
        try:
            notify_owner_confirmed(email)
        except Exception as exc:
            logger.warning("owner confirm notification failed (line); error_type=%s", type(exc).__name__)
        try:
            send_line_push(
                line_user_id,
                f"「{SERVICE_NAME}」のご登録が完了しました。\n"
                "横浜市の入札公告に対象案件があれば、このアカウントからお知らせします。\n"
                f"配信停止はこのアカウントをブロックするか、{INQUIRY_EMAIL} までご連絡ください。",
            )
        except Exception as exc:
            logger.warning("line welcome push failed; error_type=%s", type(exc).__name__)

    return _json_response(200, {"status": "linked"})


def handle_line_webhook(event):
    """LINE Messaging APIからのWebhookイベント(follow/unfollow)を受信する(v0.28)。
    自動修復はせず、unfollow(ブロック)されたユーザーをunsubscribed化するのみ。
    紐付け自体はLIFF経由のhandle_line_linkで完結しており、followイベント単体では
    登録メールアドレスとの対応が取れないため何もしない。"""
    signature = (event.get("headers") or {}).get("x-line-signature", "")
    body = event.get("body") or ""
    secret = _get_param(LINE_CHANNEL_SECRET_PARAM_NAME, decrypt=True)
    if not verify_line_signature(body, signature, secret):
        return _json_response(400, {"error": "invalid_signature"})

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _json_response(400, {"error": "invalid_json"})

    unfollowed_ids = [
        e.get("source", {}).get("userId")
        for e in payload.get("events", [])
        if e.get("type") == "unfollow" and e.get("source", {}).get("userId")
    ]
    if unfollowed_ids:
        table = dynamodb.Table(TABLE_NAME)
        # line_user_idはハッシュキーではないため、テーブル規模が小さいことを前提に
        # Scanで逆引きする(stripe_customer_idの逆引きと同じ方式)。
        scan_kwargs = {"FilterExpression": Attr("line_user_id").is_in(unfollowed_ids)}
        while True:
            resp = table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                table.update_item(
                    Key={"email": item["email"]},
                    UpdateExpression="SET #s = :u, unsubscribed_at = :t, unsubscribed_reason = :r",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":u": "unsubscribed", ":t": int(time.time()), ":r": "line_block"},
                )
                logger.info("unsubscribed a recipient due to LINE unfollow")
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    return _json_response(200, {})


def handle_confirm(event):
    email = _get_query(event, "email").strip().lower()
    token = _get_query(event, "token")
    if not email or not verify_token(email, "confirm", token):
        return _html_response(400, _page("確認できませんでした", "リンクが無効です。お手数ですが再度登録をお試しください。"))

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"email": email}).get("Item")
    if not item:
        return _html_response(404, _page("確認できませんでした", "登録情報が見つかりませんでした。"))

    status = item.get("status")
    if status == "unsubscribed":
        # 確認トークンは無期限のステートレスHMACのため、配信停止済みアドレスに
        # 対しては(本人が停止した後にメールボックスへ残る古いリンクを開いた
        # 場合でも)無条件に復活させない。本人の停止意思を尊重するため、
        # 受け取りたい場合は改めて登録し直してもらう。
        return _html_response(
            200,
            _page("既に配信停止済みです", "このメールアドレスは配信停止済みです。再度受け取りたい場合は、お手数ですが改めてご登録ください。"),
        )

    if status != "active":
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :active, confirmed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":active": "active", ":t": int(time.time())},
        )
        try:
            notify_owner_confirmed(email)
        except Exception as exc:
            logger.warning("owner confirm notification failed; error_type=%s", type(exc).__name__)
        try:
            sender_email = _get_param(SES_SENDER_PARAM_NAME)
            unsubscribe_token = make_token(email, "unsubscribe")
            unsubscribe_url = f"{_base_url(event)}/unsubscribe?email={urllib.parse.quote(email)}&token={unsubscribe_token}"
            send_welcome_email(email, sender_email, unsubscribe_url)
        except Exception as exc:
            logger.warning("welcome email failed; error_type=%s", type(exc).__name__)

    return _html_response(
        200,
        _page(
            "登録を確認しました",
            "ご登録ありがとうございます。対象の入札情報が見つかり次第、メールでお知らせします。",
            link_html=(
                "<p style=\"margin-top:1.5rem;font-size:0.9rem;\">"
                f"<a href=\"{html.escape(LP_TOP_URL)}\">サービストップに戻る</a></p>"
            ),
        ),
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
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>配信停止の確認</title>"
            "<style>body{font-family:sans-serif;background:#f4f5f7;color:#222222;"
            "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
            ".box{max-width:480px;padding:2rem;text-align:center;background:#ffffff;"
            "border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08)}"
            "h1{font-size:1.25rem;color:#1a3550}"
            "button{background:#2b6cb0;color:#ffffff;border:none;padding:0.75rem 1.5rem;"
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
    try:
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :u, unsubscribed_at = :t, unsubscribed_reason = :r",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":u": "unsubscribed", ":t": int(time.time()), ":r": "user"},
            ConditionExpression="attribute_exists(email)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # 未登録アドレス(トークンはHMAC検証済みだがwaitlistに存在しない)。
        # update_itemはアップサートのため、条件なしだと不完全な幽霊レコードが
        # 新規作成されてしまう。既に「登録なし」なので何もせず成功扱いにする。
        logger.info("unsubscribe requested for an unregistered address; ignoring")
    return _html_response(200, _page("配信を停止しました", "ご利用ありがとうございました。配信を停止しました。"))


def lambda_handler(event, context):
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", "")
    path = http_ctx.get("path", "") or event.get("rawPath", "")

    if method == "OPTIONS":
        return _json_response(200, {})
    if path == "/favicon.ico" and method == "GET":
        # execute-apiドメインへ直接アクセスした場合にブラウザが自動要求する
        # favicon.icoが生の404になるのを防ぐ(Fable指摘、低優先度)。
        return {"statusCode": 204, "headers": {}, "body": ""}
    if path == "/register" and method == "POST":
        return handle_register(event)
    if path == "/confirm" and method == "GET":
        return handle_confirm(event)
    if path == "/unsubscribe" and method in ("GET", "POST"):
        return handle_unsubscribe(event, method)
    if path == "/line/link" and method == "POST":
        return handle_line_link(event)
    if path == "/line/webhook" and method == "POST":
        return handle_line_webhook(event)

    return _json_response(404, {"error": "not_found"})
