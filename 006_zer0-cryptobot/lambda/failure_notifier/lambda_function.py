"""
Zer0-CryptoBot FailureNotifier Lambda
Executor の非同期起動がリトライ上限（3回）に達した際に SES でアラートメールを送信する。
EventInvokeConfig の OnFailure destination として ExecutorFunction に紐づけられる。
"""

import os
import json
import boto3

SES_SENDER    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT = os.environ["SES_RECIPIENT_EMAIL"]
AWS_REGION    = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


def lambda_handler(event, context):
    req_ctx      = event.get("requestContext", {})
    func_arn     = req_ctx.get("functionArn", "")
    func_name    = func_arn.split(":")[-1] if func_arn else "不明"
    condition    = req_ctx.get("condition", "不明")
    invoke_count = req_ctx.get("approximateInvokeCount", "不明")

    resp_ctx    = event.get("responseContext", {})
    func_error  = resp_ctx.get("functionError", "（なし）")
    status_code = resp_ctx.get("statusCode", "不明")

    signals = event.get("requestPayload", {}).get("signals", [])

    body = (
        f"Executor Lambda の非同期起動が全リトライ失敗しました。\n"
        f"ポジションが管理されていない可能性があります。\n\n"
        f"失敗Function  : {func_name}\n"
        f"失敗条件      : {condition}\n"
        f"試行回数      : {invoke_count} 回\n"
        f"エラー種別    : {func_error}\n"
        f"ステータス    : {status_code}\n"
        f"シグナル数    : {len(signals)} 件\n\n"
        f"対応: CloudWatch Logs で {func_name} のエラーを確認し、\n"
        f"必要に応じて手動実行してください。\n\n"
        f"手動実行コマンド:\n"
        f"aws lambda invoke --function-name Zer0-CryptoBot-Executor \\\n"
        f"  --payload '{{\"signals\":[]}}' /tmp/exec.json --region {AWS_REGION}"
    )
    html_body = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="font-family:sans-serif;font-size:14px;line-height:1.8;">'
        + body.replace("\n", "<br>")
        + "</body></html>"
    )

    ses = boto3.client("ses", region_name=AWS_REGION)
    ses.send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [SES_RECIPIENT]},
        Message={
            "Subject": {
                "Data": "【Zer0-CryptoBot】🚨Executor 起動失敗（リトライ上限）",
                "Charset": "UTF-8",
            },
            "Body": {
                "Text": {"Data": body,      "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    )
    print(f"[FailureNotifier] アラートメール送信完了: {func_name} ({condition})")
