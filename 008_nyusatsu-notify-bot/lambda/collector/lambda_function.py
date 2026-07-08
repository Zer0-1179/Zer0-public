import html
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_URL = "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p"
USER_AGENT = "Zer0-NyusatsuNotifyBot/1.0 (+contact via SES sender address)"
REQUEST_INTERVAL_SEC = 3
JST = timezone(timedelta(hours=9))
INQUIRY_EMAIL = "nyusatsu@zer0-infra.com"

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
    return [c for c in cases if any(kw in c["title"] for kw in keywords)]


def fetch_deadline_display(case: dict) -> str | None:
    """案件詳細ページの「入札期間」終了日を取得し、残り日数を含む表示文字列を返す。
    取得・解析に失敗した場合はNoneを返し、通知自体は継続させる。"""
    job = DETAIL_JOB_MAP.get(case["detail_fn"])
    if not job:
        return None
    try:
        detail_html = post(
            BASE_URL,
            {"job": job, "page": "", "keiyakuBango": case["detail_no"]},
        )
        period_match = BID_PERIOD_RE.search(detail_html)
        if not period_match:
            return None
        dates = ERA_DATE_RE.findall(period_match.group(1))
        if not dates:
            return None
        # 「開始日～終了日」の並びのため、最後にマッチした日付が締切
        reiwa_year, month, day = dates[-1]
        greg_year = int(reiwa_year.translate(_ZENKAKU_DIGITS)) + 2018
        deadline = date(greg_year, int(month.translate(_ZENKAKU_DIGITS)), int(day.translate(_ZENKAKU_DIGITS)))
        days_left = (deadline - datetime.now(JST).date()).days
        if days_left >= 0:
            return f"入札期間終了: {deadline.month}/{deadline.day}（あと{days_left}日）"
        return f"入札期間終了: {deadline.month}/{deadline.day}（終了済）"
    except Exception:
        logger.warning("deadline fetch/parse failed for detail_no=%s", case.get("detail_no"), exc_info=True)
        return None


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


def get_param(name: str) -> str:
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]


def notification_footer() -> str:
    return (
        "\n\n---\n"
        "本メールは入札情報通知Bot（横浜市パイロット版）が自動送信しています。\n"
        f"お問い合わせ・配信停止をご希望の場合は {INQUIRY_EMAIL} までご連絡ください。"
    )


def send_notification(kokoku_no: int, matches: list[dict]) -> None:
    sender = get_param(os.environ["SES_SENDER_PARAM_NAME"])
    recipient = get_param(os.environ["NOTIFY_EMAIL_PARAM_NAME"])
    detail_url = f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}"

    lines = [f"横浜市 公告第{kokoku_no}号 で清掃関連案件が{len(matches)}件見つかりました。\n"]
    for idx, c in enumerate(matches):
        if idx > 0:
            time.sleep(REQUEST_INTERVAL_SEC)
        deadline_display = fetch_deadline_display(c)
        line = (
            f"・{c['title']}\n"
            f"  契約番号: {c['contract_no']} / 入札方式: {c['method']} / 担当: {c['dept']}\n"
        )
        if deadline_display:
            line += f"  {deadline_display}\n"
        lines.append(line)
    lines.append(f"\n詳細一覧: {detail_url}")
    lines.append(notification_footer())
    body = "\n".join(lines)

    ses.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": f"【入札通知】横浜市 第{kokoku_no}号 清掃関連案件{len(matches)}件", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )


def update_weekly_stats(matches_today: int) -> tuple[int, int]:
    """週次集計(シングルトン項目)に今回の実行結果を加算し、更新後の値を返す。"""
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    resp = table.update_item(
        Key={"stats_id": "current"},
        UpdateExpression="ADD total_matches :m, days_run :d SET last_run_at = :t",
        ExpressionAttributeValues={
            ":m": matches_today,
            ":d": 1,
            ":t": datetime.now(timezone.utc).isoformat(),
        },
        ReturnValues="UPDATED_NEW",
    )
    attrs = resp["Attributes"]
    return int(attrs["total_matches"]), int(attrs["days_run"])


def reset_weekly_stats() -> None:
    table = dynamodb.Table(os.environ["WEEKLY_STATS_TABLE_NAME"])
    table.put_item(
        Item={
            "stats_id": "current",
            "total_matches": 0,
            "days_run": 0,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def send_weekly_digest(total_matches: int, days_run: int) -> None:
    sender = get_param(os.environ["SES_SENDER_PARAM_NAME"])
    recipient = get_param(os.environ["NOTIFY_EMAIL_PARAM_NAME"])

    if total_matches > 0:
        body = f"先週は{days_run}回の巡回で、清掃関連案件を合計{total_matches}件通知しました。\nBotは正常に稼働しています。"
    else:
        body = f"先週は{days_run}回の巡回を行いましたが、該当する案件はありませんでした。\nBotは正常に稼働しています。"
    body += notification_footer()

    ses.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": "【入札情報通知Bot】週次稼働レポート", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )


def lambda_handler(event, context):
    keywords = [k.strip() for k in get_param(os.environ["KEYWORDS_PARAM_NAME"]).split(",") if k.strip()]

    list_html = fetch(f"{BASE_URL}?job=KokokuList")
    all_numbers = extract_kokoku_numbers(list_html)

    bootstrap = all(not is_processed(n) for n in all_numbers) if all_numbers else False

    new_numbers = [n for n in all_numbers if not is_processed(n)]
    logger.info("kokoku_no total=%d new=%d bootstrap=%s", len(all_numbers), len(new_numbers), bootstrap)

    total_matches = 0
    for idx, kokoku_no in enumerate(new_numbers):
        if not bootstrap:
            if idx > 0:
                time.sleep(REQUEST_INTERVAL_SEC)

            anken_html = fetch(f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}")
            cases = extract_itaku_cases(anken_html)
            matches = filter_by_keywords(cases, keywords)
            if matches:
                send_notification(kokoku_no, matches)
                total_matches += len(matches)

        mark_processed(kokoku_no)

    if not bootstrap:
        weekly_total, weekly_days = update_weekly_stats(total_matches)
        if datetime.now(JST).weekday() == 0:
            send_weekly_digest(weekly_total, weekly_days)
            reset_weekly_stats()

    logger.info("done: new_numbers=%d total_matches=%d bootstrap=%s", len(new_numbers), total_matches, bootstrap)
    return {
        "statusCode": 200,
        "body": json.dumps(
            {"new_numbers": len(new_numbers), "matches": total_matches, "bootstrap": bootstrap},
            ensure_ascii=False,
        ),
    }
