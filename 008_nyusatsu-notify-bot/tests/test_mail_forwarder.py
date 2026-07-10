"""mail_forwarder Lambda のユニットテスト。
S3・SES・SSMはmoto(mock_aws)でモックする。
2026-07-11のFableレビューで見つかった「S3イベント重複配信でオブジェクトが
既に削除されている場合の異常終了」の回帰テストを兼ねる。
"""
import email as email_lib

import boto3
import pytest


@pytest.fixture
def s3_bucket():
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    try:
        s3.create_bucket(
            Bucket="test-mail-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    yield s3
    for obj in s3.list_objects_v2(Bucket="test-mail-bucket").get("Contents", []):
        s3.delete_object(Bucket="test-mail-bucket", Key=obj["Key"])


def _s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


def _put_raw_email(s3, bucket, key, subject="テストメール", body="本文"):
    msg = email_lib.message.EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "nyusatsu@zer0-infra.com"
    msg["Subject"] = subject
    msg.set_content(body)
    s3.put_object(Bucket=bucket, Key=key, Body=msg.as_bytes())


@pytest.fixture(autouse=True)
def _notify_email_param():
    ssm = boto3.client("ssm", region_name="ap-northeast-1")
    ssm.put_parameter(Name="/test/notify-email", Value="owner@example.com", Type="String", Overwrite=True)
    ses = boto3.client("ses", region_name="ap-northeast-1")
    ses.verify_email_identity(EmailAddress="relay@example.com")


def test_forwards_email_and_deletes_object(mail_forwarder, s3_bucket):
    _put_raw_email(s3_bucket, "test-mail-bucket", "incoming/msg1")
    mail_forwarder.lambda_handler(_s3_event("test-mail-bucket", "incoming/msg1"), None)

    with pytest.raises(s3_bucket.exceptions.NoSuchKey):
        s3_bucket.get_object(Bucket="test-mail-bucket", Key="incoming/msg1")


def test_duplicate_delivery_on_already_deleted_object_does_not_raise(mail_forwarder, s3_bucket):
    """回帰テスト: S3の重複イベント配信で、既に処理・削除済みのオブジェクトに対する
    2回目の呼び出しが例外を送出せず正常にスキップされること。"""
    # オブジェクトを作らず、最初から存在しない状態で呼び出す(=既に他方の呼び出しが削除済み)
    event = _s3_event("test-mail-bucket", "incoming/already-gone")
    mail_forwarder.lambda_handler(event, None)  # 例外を送出しないことを確認
