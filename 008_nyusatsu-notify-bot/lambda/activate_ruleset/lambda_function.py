# 参照用コピー。正はcfn-mail-relay.yaml内のActivateRuleSetFunctionのZipFile
# （CFnがスタック作成中に同期呼び出しするため、インラインコードを正としている）。
# 変更する場合は両方を更新すること。

import json
import urllib.request

import boto3

ses = boto3.client("ses")


def send_response(event, context, status, reason=None):
    body = json.dumps(
        {
            "Status": status,
            "Reason": reason or f"See CloudWatch Logs: {context.log_stream_name}",
            "PhysicalResourceId": event.get("PhysicalResourceId")
            or event["LogicalResourceId"],
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url=event["ResponseURL"],
        data=body,
        method="PUT",
        headers={"Content-Type": ""},
    )
    urllib.request.urlopen(req, timeout=10)


def lambda_handler(event, context):
    request_type = event["RequestType"]
    rule_set_name = event["ResourceProperties"]["RuleSetName"]

    try:
        if request_type in ("Create", "Update"):
            ses.set_active_receipt_rule_set(RuleSetName=rule_set_name)
        elif request_type == "Delete":
            try:
                active = ses.describe_active_receipt_rule_set()
                active_name = (active.get("Metadata") or {}).get("Name")
                if active_name == rule_set_name:
                    ses.set_active_receipt_rule_set()
            except Exception:
                pass
        send_response(event, context, "SUCCESS")
    except Exception as e:
        send_response(event, context, "FAILED", str(e))
