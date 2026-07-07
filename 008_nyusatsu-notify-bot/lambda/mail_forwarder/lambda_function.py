import email
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

import boto3

s3 = boto3.client("s3")
ses = boto3.client("ses")
ssm = boto3.client("ssm")

NOTIFY_EMAIL_PARAM_NAME = os.environ["NOTIFY_EMAIL_PARAM_NAME"]
FORWARD_FROM_ADDRESS = os.environ["FORWARD_FROM_ADDRESS"]


def lambda_handler(event, context):
    to_address = ssm.get_parameter(Name=NOTIFY_EMAIL_PARAM_NAME)["Parameter"]["Value"]

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        original = email.message_from_bytes(raw)

        original_from = original.get("From", "unknown")
        original_subject = original.get("Subject", "(件名なし)")
        _, reply_to_address = parseaddr(original_from)

        forwarded = MIMEMultipart()
        forwarded["From"] = FORWARD_FROM_ADDRESS
        forwarded["To"] = to_address
        if reply_to_address:
            forwarded["Reply-To"] = reply_to_address
        forwarded["Subject"] = f"[入札Bot問合せ転送] {original_subject}"

        forwarded.attach(
            MIMEText(
                f"入札情報通知Bot(nyusatsu@zer0-infra.com)宛に届いたメールです。\n"
                f"差出人: {original_from}\n\n"
                f"---- 以下、元のメール(添付) ----\n",
                "plain",
                "utf-8",
            )
        )
        attachment = MIMEApplication(raw, _subtype="rfc822")
        attachment.add_header(
            "Content-Disposition", "attachment", filename="original.eml"
        )
        forwarded.attach(attachment)

        ses.send_raw_email(
            Source=FORWARD_FROM_ADDRESS,
            Destinations=[to_address],
            RawMessage={"Data": forwarded.as_bytes()},
        )

        s3.delete_object(Bucket=bucket, Key=key)
