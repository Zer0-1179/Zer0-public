import html
import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_URL = "https://keiyaku.city.yokohama.lg.jp/epco/servlet/p"
USER_AGENT = "Zer0-NyusatsuNotifyBot/1.0 (+contact via SES sender address)"
REQUEST_INTERVAL_SEC = 3

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")
ses = boto3.client("ses")

SECTION_RE = re.compile(
    r'<table border="0" align="center" width="93%">\s*<tr>\s*<td>\s*(工事|物品|委託)\s*</td>\s*</tr>\s*</table>'
)
ROW_RE = re.compile(
    r'<tr>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<contract_no>[^<]*?)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>\s*<a href="javascript:detail2?\(\'(?P<detail_no>[^\']+)\'\);">(?P<title>[^<]+)</a>\s*<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<category>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<method>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<responsible>[^<]*)<br\s*/?>\s*</td>\s*'
    r'<td class="inputAreaG[12]"[^>]*>(?P<dept>[^<]*)<br\s*/?>\s*</td>\s*'
    r'</tr>',
    re.DOTALL,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
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
                }
            )
    return cases


def filter_by_keywords(cases: list[dict], keywords: list[str]) -> list[dict]:
    return [c for c in cases if any(kw in c["title"] for kw in keywords)]


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


def send_notification(kokoku_no: int, matches: list[dict]) -> None:
    sender = get_param(os.environ["SES_SENDER_PARAM_NAME"])
    recipient = get_param(os.environ["NOTIFY_EMAIL_PARAM_NAME"])
    detail_url = f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}"

    lines = [f"横浜市 公告第{kokoku_no}号 で清掃関連案件が{len(matches)}件見つかりました。\n"]
    for c in matches:
        lines.append(
            f"・{c['title']}\n"
            f"  契約番号: {c['contract_no']} / 入札方式: {c['method']} / 担当: {c['dept']}\n"
        )
    lines.append(f"\n詳細一覧: {detail_url}")
    body = "\n".join(lines)

    ses.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": f"【入札通知】横浜市 第{kokoku_no}号 清掃関連案件{len(matches)}件", "Charset": "UTF-8"},
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
                import time

                time.sleep(REQUEST_INTERVAL_SEC)

            anken_html = fetch(f"{BASE_URL}?job=KokokuAnkenList&kokoku_no={kokoku_no}")
            cases = extract_itaku_cases(anken_html)
            matches = filter_by_keywords(cases, keywords)
            if matches:
                send_notification(kokoku_no, matches)
                total_matches += len(matches)

        mark_processed(kokoku_no)

    logger.info("done: new_numbers=%d total_matches=%d bootstrap=%s", len(new_numbers), total_matches, bootstrap)
    return {
        "statusCode": 200,
        "body": json.dumps(
            {"new_numbers": len(new_numbers), "matches": total_matches, "bootstrap": bootstrap},
            ensure_ascii=False,
        ),
    }
