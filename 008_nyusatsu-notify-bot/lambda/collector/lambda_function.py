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
from datetime import date, datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_URL = "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p"
USER_AGENT = "Zer0-NyusatsuNotifyBot/1.0 (+contact: nyusatsu@zer0-infra.com)"
# 利用者向けメールの差出人表示名・件名プレフィックスに使うサービス名。
# 「Bot」を含む旧名称は受信箱での印象が悪いため改称した(v0.14)。
SERVICE_NAME = "入札情報ウォッチ"
REQUEST_INTERVAL_SEC = 3
JST = timezone(timedelta(hours=9))
INQUIRY_EMAIL = "nyusatsu@zer0-infra.com"
# Lambdaの残り実行時間がこの値を下回ったら、未処理の号を翌日の実行に持ち越す
# (mark_processed前に打ち切ることで、送信済みメールの重複送信を防ぐ)
TIME_BUDGET_MARGIN_MS = 60000

# 詳細ページ取得時のjavascript関数名→job値の対応（一覧ページのリンク文字列から実測して判明）
DETAIL_JOB_MAP = {
    "detail": "HacchuJohoKojiDetail",
    "detail2": "HacchuJohoBuppinDetail",
}

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
ses = boto3.client("ses")

SECTION_RE = re.compile(
    r'<table border="0" align="center" width="93%">\s*<tr>\s*<td>\s*(工事|物品|委託)\s*</td>\s*</tr>\s*</table>'
)
ROW_RE = re.compile(
    r'<tr>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<contract_no>[^<]*?)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>\s*<a href="javascript:(?P<fn>detail2?)\(\'(?P<detail_no>[^\']+)\'\);">(?P<title>[^<]+)</a>\s*<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<category>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<method>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<responsible>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<dept>[^<]*)<br\s*/?>\s*</td>\s*'
    r'</tr>',
    re.DOTALL,
)
BID_PERIOD_RE = re.compile(r"入札期間.*?<td[^>]*>(.*?)</td>", re.DOTALL)
ERA_DATE_RE = re.compile(r"令和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日")
_ZENKAKU_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

# 詳細ページの「入札参加資格」テーブル等、ラベル付き行(<th>ラベル</th><td>値</td>)から
# 抽出する項目。通知メールに「受注判断に必要な情報」を追加するため(Fable指摘、v0.11)。
DETAIL_FIELD_LABELS = [
    ("種目", "category_detail"),
    ("所在地区分・順位", "area_rank"),
    ("企業規模", "company_size"),
    ("納入／履行場所", "location"),
    ("納入／履行期間等", "period"),
    ("開札予定日時", "bid_opening"),
]
DETAIL_FIELD_RE = re.compile(
    r'<th class="header pcak4000-header"[^>]*>\s*(?P<label>[^<]+?)\s*</th>\s*'
    r'<td[^>]*>(?P<value>.*?)</td>',
    re.DOTALL,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as res:
        raw = res.read()
    return raw.decode("cp932", errors="replace")


def post(url: str, params: dict) -> str:
    data = urllib.parse.urlencode(params).encode("cp932")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        raw = res.read()
    return raw.decode("cp932", errors="replace")


def extract_kokoku_numbers(list_html: str) -> list[int]:
    numbers = {int(n) for n in re.findall(r"kokoku_no=(\d+)", list_html)}
    return sorted(numbers)


def extract_itaku_cases(anken_html: str) -> list[dict]:
    """公告案件一覧ページから「委託」セクションの案件だけを抽出する"""
    sections = list(SECTION_RE.finditer(anken_html))
    cases = []
    for i, sec_match in enumerate(sections):
        section_name = sec_match.group(1)
        if section_name != "委託":
            continue
        start = sec_match.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(anken_html)
        segment = anken_html[start:end]
        for row in ROW_RE.finditer(segment):
            cases.append(
                {
                    "contract_no": html.unescape(row.group("contract_no")).strip(),
                    "title": html.unescape(row.group("title")).strip(),
                    "category": html.unescape(row.group("category")).strip(),
                    "method": html.unescape(row.group("method")).strip(),
                    "dept": html.unescape(row.group("dept")).strip(),
                    "detail_fn": row.group("fn"),
                    "detail_no": row.group("detail_no"),
                }
            )
    return cases


def filter_by_keywords(cases: list[dict], keywords: list[str]) -> list[dict]:
    """案件名(title)だけでなく工種等区分(category)にもキーワードを当てる。
    案件名に「清掃」等を含まないが区分が「建物管理」等の案件を取りこぼさないため
    (Fable指摘、レビュー2026-07-11)。"""
    return [c for c in cases if any(kw in c["title"] or kw in c["category"] for kw in keywords)]


def _clean_field_text(raw: str) -> str:
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_detail_fields(detail_html: str) -> dict:
    """詳細ページのラベル付きテーブル行(<th>ラベル</th><td>値</td>)を全て抽出する。"""
    fields = {}
    for m in DETAIL_FIELD_RE.finditer(detail_html):
        label = m.group("label").strip()
        value = _clean_field_text(m.group("value"))
        if value and value != "-":
            fields[label] = value
    return fields


def fetch_case_detail(case: dict) -> dict:
    """案件詳細ページを一度だけ取得し、締切表示・入札参加資格情報（種目・所在地区分・
    企業規模・履行場所・履行期間・開札予定日時）をまとめて返す。取得・解析に失敗した
    場合は空dict（または取得できた分のみ）を返し、通知自体は継続させる
    （受注判断に必要な情報を追加、Fable指摘v0.11。既存の締切取得と同じ1回のPOSTで完結し、
    追加リクエストは発生しない）。"""
    job = DETAIL_JOB_MAP.get(case["detail_fn"])
    if not job:
        return {}
    try:
        detail_html = post(
            BASE_URL,
            {"job": job, "page": "", "keiyakuBango": case["detail_no"]},
        )
    except Exception:
        logger.warning("detail fetch failed for detail_no=%s", case.get("detail_no"), exc_info=True)
        return {}

    info: dict = {}
    try:
        period_match = BID_PERIOD_RE.search(detail_html)
        if period_match:
            dates = ERA_DATE_RE.findall(period_match.group(1))
            if dates:
                # 「開始日～終了日」の並びのため、最後にマッチした日付が締切
                reiwa_year, month, day = dates[-1]
                greg_year = int(reiwa_year.translate(_ZENKAKU_DIGITS)) + 2018
                deadline = date(
                    greg_year, int(month.translate(_ZENKAKU_DIGITS)), int(day.translate(_ZENKAKU_DIGITS))
                )
                days_left = (deadline - datetime.now(JST).date()).days
                info["days_left"] = days_left  # 通知メール内の締切昇順ソートに使う
                if days_left >= 0:
                    info["deadline_display"] = (
                        f"入札期間終了: {deadline.year}/{deadline.month}/{deadline.day}（あと{days_left}日）"
                    )
                else:
                    info["deadline_display"] = f"入札期間終了: {deadline.year}/{deadline.month}/{deadline.day}（終了済）"
    except Exception:
        logger.warning("deadline parse failed for detail_no=%s", case.get("detail_no"), exc_info=True)

    raw_fields = extract_detail_fields(detail_html)
    for label, key in DETAIL_FIELD_LABELS:
        if label in raw_fields:
            info[key] = raw_fields[label]

    return info


def case_detail_url(case: dict) -> str | None:
    """個別案件の詳細ページを直接開けるGET URL。サイト上はjavascript:detail()による
    POST遷移だが、同じパラメータのGETでも同一の詳細ページが返ることを実測確認済み
    (工事・物品/委託とも、2026-07-12)。メール本文から案件へ直接飛べるようにする。"""
    job = DETAIL_JOB_MAP.get(case.get("detail_fn", ""))
    detail_no = case.get("detail_no")
    if not job or not detail_no:
        return None
    return f"{BASE_URL}?job={job}&page=&keiyakuBango={urllib.parse.quote(detail_no)}"


def format_case_line(c: dict, detail: dict) -> str:
    line = (
        f"・{c['title']}\n"
        f"  契約番号: {c['contract_no']} / 入札方式: {c['method']} / 担当: {c['dept']}\n"
    )
    if detail.get("category_detail"):
        line += f"  種目: {detail['category_detail']}\n"
    qualification = [p for p in (detail.get("area_rank"), detail.get("company_size")) if p]
    if qualification:
        line += f"  参加資格: {' / '.join(qualification)}\n"
    if detail.get("location"):
        line += f"  履行場所: {detail['location']}\n"
    if detail.get("period"):
        line += f"  履行期間: {detail['period']}\n"
    if detail.get("deadline_display"):
        line += f"  {detail['deadline_display']}\n"
    if detail.get("bid_opening"):
        line += f"  開札予定: {detail['bid_opening']}\n"
    url = case_detail_url(c)
    if url:
        line += f"  案件詳細: {url}\n"
    return line


def case_card_html(info: dict, url: str | None) -> str:
    """1案件をカード状(枠+ラベル/値の2列テーブル+詳細ページへのリンクボタン)の
    HTMLにする。スマホのメールクライアントでも「テキストの壁」にならないよう、
    メールで安定して効くテーブルレイアウト+インラインスタイルのみを使う。"""
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
    deadline_html = ""
    if info.get("deadline_display"):
        deadline_html = (
            "<div style=\"margin-top:8px;font-size:13px;font-weight:bold;color:#b7472a;\">"
            f"{html.escape(info['deadline_display'])}</div>"
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
        f"{deadline_html}{link_html}"
        "</td></tr></table>"
    )


def record_match_history(kokoku_no: int, case: dict, detail: dict) -> None:
    """マッチ案件を履歴テーブルに記録する。登録確認時のバックフィルウェルカムメール
    (lp_waitlist Lambda)が直近のマッチ実績を参照するために使う。60日でTTL失効する。"""
    table = dynamodb.Table(os.environ["MATCH_HISTORY_TABLE_NAME"])
    now = datetime.now(timezone.utc)
    item = {
        "kokoku_no": kokoku_no,
        "detail_no": case["detail_no"],
        "title": case["title"],
        "contract_no": case["contract_no"],
        "method": case["method"],
        "dept": case["dept"],
        "matched_at": now.isoformat(),
        "ttl": int((now + timedelta(days=60)).timestamp()),
    }
    for key in ("category_detail", "area_rank", "company_size", "location", "period", "deadline_display", "bid_opening"):
        if detail.get(key):
            item[key] = detail[key]
    # バックフィルウェルカムメール(lp_waitlist)が案件詳細ページへ直接リンクできる
    # よう、GETで開ける詳細URLも保存する。
    url = case_detail_url(case)
    if url:
        item["detail_url"] = url
    table.put_item(Item=item)


def is_processed(kokoku_no: int) -> bool:
    table = dynamodb.Table(os.environ["PROCESSED_TABLE_NAME"])
    resp = table.get_item(Key={"kokoku_no": kokoku_no})
    return "Item" in resp


def mark_processed(kokoku_no: int) -> None:
    table = dynamodb.Table(os.environ["PROCESSED_TABLE_NAME"])
    table.put_item(
        Item={
            "kokoku_no": kokoku_no,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    )


_param_cache: dict[str, str] = {}


def get_param(name: str) -> str:
    """1回のLambda実行内で同じパラメータを繰り返し取得しないようキャッシュする
    (購読者数×号数に比例してSSM呼び出しが線形増加していたため、レビュー2026-07-11)。
    lp_waitlist Lambdaの_param_cacheと同じ方式。"""
    if name not in _param_cache:
        _param_cache[name] = ssm.get_parameter(Name=name)["Parameter"]["Value"]
    return _param_cache[name]


def make_unsubscribe_token(email: str) -> str:
    """lp_waitlist Lambdaのmake_token(email, "unsubscribe")と同一アルゴリズム。
    両Lambdaが同じSSM秘密鍵(HMAC_SECRET_PARAM_NAME)を参照するため、ここで生成した
    トークンはlp_waitlist側の/unsubscribeエンドポイントでそのまま検証できる。"""
    secret = get_param(os.environ["HMAC_SECRET_PARAM_NAME"])
    digest = hmac.new(secret.encode(), f"{email}:unsubscribe".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_unsubscribe_url(email: str) -> str:
    # lp_waitlist側のverify_tokenはemailをstrip().lower()してから検証するため、
    # ここで正規化しないと大文字を含むアドレス(SSMのオーナー通知先等)の
    # 配信停止リンクが常に無効になる。
    base_url = get_param(os.environ["UNSUBSCRIBE_BASE_URL_PARAM_NAME"])
    normalized_email = email.strip().lower()
    token = make_unsubscribe_token(normalized_email)
    return f"{base_url}/unsubscribe?email={urllib.parse.quote(normalized_email)}&token={token}"


def get_active_subscriber_emails() -> list[str]:
    """zer0-nyusatsu-lp-waitlistからstatus=active(二重オプトイン確認済み)の
    購読者メールアドレスを全件取得する。SSMパラメータPAYMENT_REQUIRED_PARAM_NAMEが
    "true"の場合のみ、payment_status=paid(Stripe決済済み)も条件に加える。デフォルトの
    "false"では従来通りstatus=activeのみで配信し、既存の無料テスト購読者への配信は
    変えない(課金必須化はユーザーがこのSSM値を切り替えたタイミングで発効する)。"""
    payment_required = get_param(os.environ["PAYMENT_REQUIRED_PARAM_NAME"]).strip().lower() == "true"
    table = dynamodb.Table(os.environ["WAITLIST_TABLE_NAME"])
    emails: list[str] = []
    filter_expr = Attr("status").eq("active")
    if payment_required:
        filter_expr &= Attr("payment_status").eq("paid")
    scan_kwargs = {"FilterExpression": filter_expr, "ProjectionExpression": "email"}
    while True:
        resp = table.scan(**scan_kwargs)
        emails.extend(item["email"] for item in resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return emails


def get_all_recipients(owner_email: str) -> list[str]:
    """運用監視用のオーナー宛+実際にactiveな購読者宛を、重複なく返す。"""
    recipients = [owner_email]
    seen = {owner_email}
    for email in get_active_subscriber_emails():
        if email not in seen:
            seen.add(email)
            recipients.append(email)
    return recipients


def notification_footer_text(unsubscribe_url: str) -> str:
    """プレーンテキスト版フッター。URLをそのまま記載する
    (HTML非対応メーラー向けのフォールバック)。"""
    return (
        "\n\n---\n"
        f"本メールは「{SERVICE_NAME}」（横浜市パイロット版）から自動配信しています。\n"
        f"配信停止はこちら: {unsubscribe_url}\n"
        f"お問い合わせは {INQUIRY_EMAIL} までご連絡ください。"
    )


def build_html_body(content_html: str, unsubscribe_url: str) -> str:
    """本文HTMLを、スマホでも読みやすい共通レイアウト(白背景カード+サービス名見出し+
    配信停止リンク付きフッター)で包む。メールクライアントはCSSサポートが限定的なため、
    テーブルレイアウト+インラインスタイルのみを使う(Flexbox/Grid等は使わない)。"""
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
        f"本メールは「{SERVICE_NAME}」（横浜市パイロット版）から自動配信しています。<br>"
        f"<a href=\"{html.escape(unsubscribe_url)}\" style=\"color:#2b6cb0;\">配信停止はこちら</a><br>"
        f"お問い合わせは {INQUIRY_EMAIL} までご連絡ください。"
        "</td></tr></table>"
        "</td></tr></table></body></html>"
    )


def send_email_with_unsubscribe(sender: str, recipient: str, subject: str, body: str, html_content: str | None = None) -> None:
    """List-Unsubscribeヘッダー(RFC 8058のOne-Click Unsubscribe含む)を付与し、
    HTML版(「配信停止」をクリック可能なリンクとして埋め込む)+プレーンテキスト版
    (URLそのまま、フォールバック)のmultipart/alternativeでSES送信する。
    SES Configuration Set(バウンス・苦情をSNS経由で検知、B-3)を付与する。

    html_contentに構造化済みの本文HTML(案件カード等)を渡すとそれを使い、
    省略時(週次サマリー等)はプレーンテキストを改行変換して使う。"""
    unsubscribe_url = build_unsubscribe_url(recipient)
    if html_content is None:
        html_content = html.escape(body).replace("\n", "<br>")
    msg = EmailMessage()
    # 差出人に日本語のサービス名を表示名として付ける(Addressを使うことで
    # policy.defaultがRFC 2047エンコードを正しく行う)。SESのSource(エンベロープ)は
    # 従来どおり素のアドレスのまま。
    local_part, _, domain = sender.partition("@")
    msg["From"] = Address(display_name=SERVICE_NAME, username=local_part, domain=domain)
    msg["To"] = recipient
    msg["Subject"] = subject
    # mailto:を併記しない: mailto経由の停止依頼はmail_forwarderが個人メールへ転送する
    # だけでDynamoDBのstatusを更新するコードがなく、メーラーがmailto側を選んで送信
    # すると利用者は「停止済み」のつもりで実際は配信が継続してしまうため。
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body + notification_footer_text(unsubscribe_url))
    msg.add_alternative(build_html_body(html_content, unsubscribe_url), subtype="html")
    ses.send_raw_email(
        Source=sender,
        Destinations=[recipient],
        RawMessage={"Data": msg.as_bytes()},
        ConfigurationSetName=os.environ["SES_CONFIGURATION_SET_NAME"],
    )


def send_notification(kokoku_no: int, matches: list[dict], context) -> tuple[bool, bool]:
    """通知メールを組み立てて全宛先に送信する。

    戻り値: (fully_sent, had_failure)
      fully_sent: Falseなら時間切れ、または宛先の一部/全部への送信失敗で完了して
        いない。呼び出し元はこの号をmark_processedせず、次回実行に持ち越す。
      had_failure: Trueなら時間切れではなく実際の送信失敗(SESエラー等)が発生して
        おり、呼び出し元はLambda呼び出し全体を失敗させてDLQ/アラームに繋げる必要
        がある(時間切れによる持ち越しは正常な自己回復動作のため区別する)。
    """
    sender = get_param(os.environ["SES_SENDER_PARAM_NAME"])
    owner_email = get_param(os.environ["NOTIFY_EMAIL_PARAM_NAME"])
    detail_url = f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}"

    case_details: list[tuple[dict, dict]] = []
    for idx, c in enumerate(matches):
        if idx > 0:
            time.sleep(REQUEST_INTERVAL_SEC)
        # 号ループ先頭だけでなくここでもチェックする。マッチ件数が多い号は
        # 詳細取得(sleep+POST)の累積時間だけでLambdaがタイムアウトしうるため。
        if context.get_remaining_time_in_millis() < TIME_BUDGET_MARGIN_MS:
            logger.warning(
                "time budget exhausted while fetching case details for kokoku_no=%s (idx=%d/%d), deferring to next run",
                kokoku_no, idx, len(matches),
            )
            return False, False
        detail = fetch_case_detail(c)
        case_details.append((c, detail))
        try:
            record_match_history(kokoku_no, c, detail)
        except Exception:
            logger.warning("match history record failed for detail_no=%s", c.get("detail_no"), exc_info=True)

    # 締切が近い案件を先頭に表示する(締切が取れない案件は末尾)。忙しい受信者が
    # 「今すぐ動くべき案件」を最初に見られるようにするため(Fable指摘、レビュー2026-07-11)。
    case_details.sort(key=lambda cd: cd[1].get("days_left", 10**9))

    intro = f"横浜市 公告第{kokoku_no}号 で対象案件が{len(matches)}件見つかりました。"
    lines = [intro + "\n"]
    card_htmls = []
    for c, detail in case_details:
        lines.append(format_case_line(c, detail))
        card_htmls.append(case_card_html({**c, **detail}, case_detail_url(c)))
    lines.append(f"\n公告の全案件一覧: {detail_url}")
    body = "\n".join(lines)
    html_content = (
        f"<p style=\"margin:0 0 16px;\">{html.escape(intro)}</p>"
        + "".join(card_htmls)
        + "<p style=\"margin:16px 0 0;font-size:13px;\">"
        f"<a href=\"{html.escape(detail_url)}\" style=\"color:#2b6cb0;\">"
        f"公告第{kokoku_no}号の全案件一覧を見る</a></p>"
    )
    subject = f"【{SERVICE_NAME}】横浜市 第{kokoku_no}号 対象案件{len(matches)}件"

    # 運用監視用のオーナー宛+実際にactiveな購読者宛の両方に個別送信する(B-1)。
    # BCC一斉送信は使わない(宛先ごとに異なる配信停止トークンを埋め込む必要があるため)。
    had_failure = False
    for recipient in get_all_recipients(owner_email):
        if context.get_remaining_time_in_millis() < TIME_BUDGET_MARGIN_MS:
            logger.warning(
                "time budget exhausted while sending kokoku_no=%s, remaining recipients deferred to next run",
                kokoku_no,
            )
            return False, had_failure
        try:
            send_email_with_unsubscribe(sender, recipient, subject, body, html_content=html_content)
        except Exception:
            # v0.8まではses.send_email失敗がLambda全体を失敗させDLQ/アラームに
            # 繋がっていたが、v0.10の宛先ごとの個別送信でこの安全網が消失していた。
            # ここでは握りつぶさずhad_failureを立て、呼び出し元でLambda呼び出し
            # 自体を失敗させることでリトライ・DLQ・アラームに再度繋げる。
            logger.error("notification email failed for %s, kokoku_no=%s", recipient, kokoku_no, exc_info=True)
            had_failure = True

    return not had_failure, had_failure


def update_weekly_stats(matches_today: int, cases_today: int) -> tuple[int, int, int]:
    """週次集計(シングルトン項目)に今回の実行結果を加算し、更新後の値を返す。
    cases_today(委託案件の総チェック数)は「0件でも怠けていない」ことを購読者に
    伝えるために追加した(v0.11、Fable指摘: チェックした母数を書くのがポイント)。"""
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    resp = table.update_item(
        Key={"stats_id": "current"},
        UpdateExpression="ADD total_matches :m, total_cases_checked :c, days_run :d SET last_run_at = :t",
        ExpressionAttributeValues={
            ":m": matches_today,
            ":c": cases_today,
            ":d": 1,
            ":t": datetime.now(timezone.utc).isoformat(),
        },
        ReturnValues="UPDATED_NEW",
    )
    attrs = resp["Attributes"]
    return int(attrs["total_matches"]), int(attrs.get("total_cases_checked", 0)), int(attrs["days_run"])


def reset_weekly_stats() -> None:
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    table.put_item(
        Item={
            "stats_id": "current",
            "total_matches": 0,
            "total_cases_checked": 0,
            "days_run": 0,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    # put_itemによる全置換のため、digest_pendingフラグもここで自動的にクリアされる。


def get_digest_pending() -> bool:
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    resp = table.get_item(Key={"stats_id": "current"})
    return bool(resp.get("Item", {}).get("digest_pending", False))


def set_digest_pending(pending: bool) -> None:
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    table.update_item(
        Key={"stats_id": "current"},
        UpdateExpression="SET digest_pending = :p",
        ExpressionAttributeValues={":p": pending},
    )


def send_weekly_digest(total_matches: int, total_cases_checked: int, days_run: int, pending: bool = False) -> None:
    sender = get_param(os.environ["SES_SENDER_PARAM_NAME"])
    owner_email = get_param(os.environ["NOTIFY_EMAIL_PARAM_NAME"])

    # 月曜に持ち越しが発生し週次サマリーを見送った場合、解消後の実行でこの関数が
    # pending=Trueで呼ばれる。「先週は」だと対象期間が不正確になるため文言を変える
    # (Fable指摘、レビュー2026-07-11)。
    period_label = "直近の集計期間" if pending else "先週"
    if total_matches > 0:
        body = (
            f"{period_label}は{days_run}回の巡回で委託案件を{total_cases_checked}件チェックし、"
            f"対象案件を合計{total_matches}件通知しました。\nシステムは正常に稼働しています。"
        )
    else:
        body = (
            f"{period_label}は{days_run}回の巡回で委託案件を{total_cases_checked}件チェックしましたが、"
            f"該当する案件はありませんでした。\nシステムは正常に稼働しています。"
        )

    # v0.11: 運用監視用のオーナーだけでなく、実際の購読者にも週次サマリーを届ける。
    # 横浜市の入札公告は原則毎週火曜発行のため案件ゼロの週が実測で約半数あり、
    # 「本当に動いているか」という不安を解消するハートビートとして重要(Fable指摘)。
    for recipient in get_all_recipients(owner_email):
        try:
            send_email_with_unsubscribe(sender, recipient, f"【{SERVICE_NAME}】週次稼働レポート", body)
        except Exception:
            logger.warning("weekly digest failed for %s", recipient, exc_info=True)


def lambda_handler(event, context):
    keywords = [k.strip() for k in get_param(os.environ["KEYWORDS_PARAM_NAME"]).split(",") if k.strip()]

    list_html = fetch(f"{BASE_URL}?job=KokokuList")
    all_numbers = extract_kokoku_numbers(list_html)

    bootstrap = all(not is_processed(n) for n in all_numbers) if all_numbers else False

    new_numbers = [n for n in all_numbers if not is_processed(n)]
    logger.info("kokoku_no total=%d new=%d bootstrap=%s", len(all_numbers), len(new_numbers), bootstrap)

    total_matches = 0
    total_cases_checked = 0
    deferred = False
    had_send_failure = False
    for idx, kokoku_no in enumerate(new_numbers):
        if not bootstrap:
            # 詳細ページPOST+3秒sleepが号ごとに累積するため、残り時間が不足したら
            # ここで打ち切る。未処理のままなので翌日の実行が自動的に引き継ぐ
            # (mark_processed前に抜けるため、この号自体の重複送信は起きない。
            # ただしここより細かい粒度のチェックはsend_notification内で行う)。
            if context.get_remaining_time_in_millis() < TIME_BUDGET_MARGIN_MS:
                logger.warning(
                    "time budget exhausted at idx=%d, deferring remaining %d kokoku_no to next run",
                    idx,
                    len(new_numbers) - idx,
                )
                deferred = True
                break

            if idx > 0:
                time.sleep(REQUEST_INTERVAL_SEC)

            anken_html = fetch(f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}")
            if not SECTION_RE.search(anken_html):
                # 「工事/物品/委託」のセクション見出しが1つも見つからない場合、
                # 横浜市サイトのHTML構造が変わり解析が壊れている可能性が高い。
                # このケースはエラーにならず通知0件のまま進んでしまうため、
                # サイレント故障を防ぐために明示的にログを残す(Fable指摘、レビュー2026-07-11)。
                logger.error(
                    "kokoku_no=%d: no section markers found in anken_html; "
                    "Yokohama city site structure may have changed, parser needs review",
                    kokoku_no,
                )
            cases = extract_itaku_cases(anken_html)
            total_cases_checked += len(cases)
            matches = filter_by_keywords(cases, keywords)
            unmatched = [c["title"] for c in cases if c not in matches]
            if unmatched:
                # マッチしなかった案件名を記録し、キーワードのチューニングを
                # 実データ駆動で行えるようにする(Fable指摘、レビュー2026-07-11)。
                logger.info("kokoku_no=%d unmatched titles: %s", kokoku_no, unmatched)
            if matches:
                fully_sent, had_failure = send_notification(kokoku_no, matches, context)
                if had_failure:
                    had_send_failure = True
                if not fully_sent:
                    logger.warning(
                        "kokoku_no=%d notification incomplete, not marking processed; will retry",
                        kokoku_no,
                    )
                    deferred = True
                    break
                total_matches += len(matches)

        mark_processed(kokoku_no)

    if not bootstrap:
        weekly_total, weekly_cases, weekly_days = update_weekly_stats(total_matches, total_cases_checked)
        pending = get_digest_pending()
        if datetime.now(JST).weekday() == 0 or pending:
            if deferred:
                # 持ち越し号が残ったまま週次サマリーを送ると、その分の集計が
                # 反映されないまま送信・リセットされ過少報告になる。持ち越しが
                # 解消するまで送信・リセットを見送り、digest_pendingフラグを立てて
                # 持ち越し解消後の実行(月曜とは限らない)で必ず送る
                # (Fable指摘、レビュー2026-07-11。以前はweekday()==0のときしか
                # 再送されず、フラグが無いままだと持ち越しが長引くと欠落週が発生していた)。
                if not pending:
                    set_digest_pending(True)
                logger.warning("weekly digest deferred: carryover kokoku_no pending")
            else:
                send_weekly_digest(weekly_total, weekly_cases, weekly_days, pending=pending)
                reset_weekly_stats()

    logger.info("done: new_numbers=%d total_matches=%d bootstrap=%s", len(new_numbers), total_matches, bootstrap)

    if had_send_failure:
        # 時間切れによる持ち越し(deferred)は正常な自己回復動作なので例外にしないが、
        # 実際の送信失敗はLambda呼び出し自体を失敗させ、非同期呼び出しのリトライ→
        # DLQ→アラームという既存の安全網に確実に繋げる。
        raise RuntimeError(
            f"one or more notification emails failed to send for kokoku_no processed in this run "
            f"(new_numbers={len(new_numbers)}); invocation marked as failed to trigger retry/DLQ/alarm"
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"new_numbers": len(new_numbers), "matches": total_matches, "bootstrap": bootstrap},
            ensure_ascii=False,
        ),
    }
