import email
import logging
import os
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

        try:
            raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                # S3イベントの重複配信(at-least-once)で同一オブジェクトに対し
                # 複数回起動した場合、先に処理した側が既に削除済みのことがある。
                # 転送は完了済みとみなしてこのレコードはスキップする。
                logger.info("object already processed/deleted, skipping: %s/%s", bucket, key)
                continue
            raise
        # policy=default(モダンAPI)でパースすると、RFC 2047エンコード済みの
        # From/Subjectヘッダーが自動でデコードされた文字列として取得できる。
        # 従来のcompat32(デフォルト)だとエンコード済みの生文字列
        # (=?utf-8?B?...?=)がそのまま返り、転送メールの件名に混入して
        # Gmail上で文字化けする不具合があったため修正(v0.11)。
        original = email.message_from_bytes(raw, policy=policy.default)

        original_from = str(original.get("From", "unknown"))
        original_subject = str(original.get("Subject", "(件名なし)"))
        _, reply_to_address = parseaddr(original_from)

        forwarded = EmailMessage()
        forwarded["From"] = FORWARD_FROM_ADDRESS
        forwarded["To"] = to_address
        if reply_to_address:
            forwarded["Reply-To"] = reply_to_address
        forwarded["Subject"] = f"[入札情報ウォッチ問合せ転送] {original_subject}"
        forwarded.set_content(
            f"入札情報ウォッチ(nyusatsu@zer0-infra.com)宛に届いたメールです。\n"
            f"差出人: {original_from}\n\n"
            f"---- 以下、元のメール(添付) ----\n"
        )
        forwarded.add_attachment(
            raw, maintype="message", subtype="rfc822", filename="original.eml"
        )

        ses.send_raw_email(
            Source=FORWARD_FROM_ADDRESS,
            Destinations=[to_address],
            RawMessage={"Data": forwarded.as_bytes()},
        )

        s3.delete_object(Bucket=bucket, Key=key)
