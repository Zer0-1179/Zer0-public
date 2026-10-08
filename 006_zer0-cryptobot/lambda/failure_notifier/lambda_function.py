"""
Zer0-CryptoBot FailureNotifier Lambda
Executor の非同期起動が失敗した際に SES でアラートメールを送信する。
EventInvokeConfig の OnFailure destination として ExecutorFunction に紐づけられる。
MaximumRetryAttempts は 0 固定（v3.6〜。4時間毎の定期実行が実質的なリトライとして
機能するため、自動リトライによる二重発注を避ける設計）。そのためこのLambdaは
リトライ待ちなしに最初の失敗で即座に起動する（approximateInvokeCount は常に1）。
"""

import os
import json
import boto3

import alert_mail

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
        f"Executor Lambda の非同期起動が失敗しました（リトライは無効設定のため即時通知）。\n"
        f"ポジションが管理されていない可能性があります。\n\n"
        f"失敗Function  : {func_name}\n"
        f"失敗条件      : {condition}\n"
        f"試行回数      : {invoke_count} 回（MaximumRetryAttempts=0のため通常は1回）\n"
        f"エラー種別    : {func_error}\n"
        f"ステータス    : {status_code}\n"
        f"シグナル数    : {len(signals)} 件\n\n"
        f"対応: CloudWatch Logs で {func_name} のエラーを確認し、\n"
        f"必要に応じて手動実行してください。\n\n"
        f"手動実行コマンド:\n"
        f"aws lambda invoke --function-name Zer0-CryptoBot-Executor \\\n"
        f"  --payload '{{\"signals\":[]}}' /tmp/exec.json --region {AWS_REGION}"
    )
    subject = alert_mail.decorate_subject("【Zer0-CryptoBot】🚨Executor 起動失敗", "critical")
    action = ("Executor が動いていないため、保有中ポジションの管理（TP1/SL/トレーリング）が止まっている可能性があります。"
              "bitbank の管理画面でポジションとSL注文が残っているかを確認し、上のコマンドで手動実行してください。")
    try:
        mail_body = {
            "Text": {"Data": alert_mail.render_text(subject, body, level="critical", action=action), "Charset": "UTF-8"},
            "Html": {"Data": alert_mail.render_html(subject, body, service="Zer0-CryptoBot", source="FailureNotifier",
                                                    level="critical", action=action), "Charset": "UTF-8"},
        }
    except Exception as e:
        # 装飾の不具合で通知そのものが失われないよう、素のテキストで送る
        print(f"[FailureNotifier] メール整形失敗（テキストのみで送信）: {e}")
        mail_body = {"Text": {"Data": body, "Charset": "UTF-8"}}

    ses = boto3.client("ses", region_name=AWS_REGION)
    ses.send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [SES_RECIPIENT]},
        Message={
            "Subject": {
                "Data": subject,
                "Charset": "UTF-8",
            },
            "Body": mail_body,
        },
    )
    print(f"[FailureNotifier] アラートメール送信完了: {func_name} ({condition})")
