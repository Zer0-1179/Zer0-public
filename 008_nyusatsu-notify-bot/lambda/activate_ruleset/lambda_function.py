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
    urllib.request.urlopen(req)


def lambda_handler(event, context):
    request_type = event["RequestType"]
    rule_set_name = event["ResourceProperties"]["RuleSetName"]

    try:
        if request_type in ("Create", "Update"):
            ses.set_active_receipt_rule_set(RuleSetName=rule_set_name)
        elif request_type == "Delete":
            try:
                ses.set_active_receipt_rule_set()
            except Exception:
                pass
        send_response(event, context, "SUCCESS")
    except Exception as e:
        send_response(event, context, "FAILED", str(e))
