"""008 入札情報通知Bot 全体のpytest共通フィクスチャ。

collector/lp_waitlist/bounce_handlerはどれもファイル名がlambda_function.pyで衝突するため、
sys.path経由のimportではなくimportlib.utilで明示的な別名を付けてロードする(006と同じ手法)。
DynamoDB/SESはmoto(mock_aws)でモックし、テストセッション全体で1つのモックAWS環境を共有する。
"""
import importlib.util
import os
import sys

import boto3
import pytest
from moto import mock_aws

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "ap-northeast-1"

os.environ.setdefault("PROCESSED_TABLE_NAME", "test-processed")
os.environ.setdefault("WAITLIST_TABLE_NAME", "test-waitlist")
os.environ.setdefault("WEEKLY_STATS_TABLE_NAME", "test-weekly-stats")
os.environ.setdefault("MATCH_HISTORY_TABLE_NAME", "test-match-history")
os.environ.setdefault("KEYWORDS_PARAM_NAME", "/test/keywords")
os.environ.setdefault("NOTIFY_EMAIL_PARAM_NAME", "/test/notify-email")
os.environ.setdefault("SES_SENDER_PARAM_NAME", "/test/sender")
os.environ.setdefault("HMAC_SECRET_PARAM_NAME", "/test/hmac-secret")
os.environ.setdefault("UNSUBSCRIBE_BASE_URL_PARAM_NAME", "/test/unsubscribe-base-url")
os.environ.setdefault("SES_CONFIGURATION_SET_NAME", "test-config-set")
os.environ.setdefault("FORWARD_FROM_ADDRESS", "relay@example.com")


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_mock = mock_aws()
_mock.start()

_ddb = boto3.client("dynamodb", region_name=REGION)
_ddb.create_table(
    TableName="test-processed",
    KeySchema=[{"AttributeName": "kokoku_no", "KeyType": "HASH"}],
    AttributeDefinitions=[{"AttributeName": "kokoku_no", "AttributeType": "N"}],
    BillingMode="PAY_PER_REQUEST",
)
_ddb.create_table(
    TableName="test-waitlist",
    KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
    AttributeDefinitions=[{"AttributeName": "email", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)
_ddb.create_table(
    TableName="test-weekly-stats",
    KeySchema=[{"AttributeName": "stats_id", "KeyType": "HASH"}],
    AttributeDefinitions=[{"AttributeName": "stats_id", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)
_ddb.create_table(
    TableName="test-match-history",
    KeySchema=[
        {"AttributeName": "kokoku_no", "KeyType": "HASH"},
        {"AttributeName": "detail_no", "KeyType": "RANGE"},
    ],
    AttributeDefinitions=[
        {"AttributeName": "kokoku_no", "AttributeType": "N"},
        {"AttributeName": "detail_no", "AttributeType": "S"},
    ],
    BillingMode="PAY_PER_REQUEST",
)

_ssm = boto3.client("ssm", region_name=REGION)
_ssm.put_parameter(Name="/test/hmac-secret", Value="test-secret-value", Type="SecureString")
_ssm.put_parameter(Name="/test/sender", Value="sender@example.com", Type="String")
_ssm.put_parameter(Name="/test/notify-email", Value="owner@example.com", Type="String")
_ssm.put_parameter(Name="/test/unsubscribe-base-url", Value="https://example.com", Type="String")
_ssm.put_parameter(Name="/test/keywords", Value="清掃,美化", Type="String")

_collector = _load_module(
    "collector_lambda_function", os.path.join(ROOT, "lambda", "collector", "lambda_function.py")
)
_lp_waitlist = _load_module(
    "lp_waitlist_lambda_function", os.path.join(ROOT, "lambda", "lp_waitlist", "lambda_function.py")
)
_bounce_handler = _load_module(
    "bounce_handler_lambda_function", os.path.join(ROOT, "lambda", "bounce_handler", "lambda_function.py")
)
_mail_forwarder = _load_module(
    "mail_forwarder_lambda_function", os.path.join(ROOT, "lambda", "mail_forwarder", "lambda_function.py")
)

_TABLE_KEYS = {
    "test-waitlist": ["email"],
    "test-processed": ["kokoku_no"],
    "test-weekly-stats": ["stats_id"],
    "test-match-history": ["kokoku_no", "detail_no"],
}


def pytest_sessionfinish(session, exitstatus):
    _mock.stop()


@pytest.fixture
def collector():
    return _collector


@pytest.fixture
def lp_waitlist():
    return _lp_waitlist


@pytest.fixture
def bounce_handler():
    return _bounce_handler


@pytest.fixture
def mail_forwarder():
    return _mail_forwarder


@pytest.fixture(autouse=True)
def _clean_tables():
    """テスト間でDynamoDBの内容を持ち越さないよう、各テスト終了後に全テーブルを空にする。"""
    yield
    ddb = boto3.resource("dynamodb", region_name=REGION)
    for table_name, key_names in _TABLE_KEYS.items():
        table = ddb.Table(table_name)
        for item in table.scan().get("Items", []):
            table.delete_item(Key={k: item[k] for k in key_names})


class _FakeContext:
    """Lambdaのcontext.get_remaining_time_in_millis()を模したテスト用スタブ。
    残り時間の系列(sequence)を渡すと呼び出しごとに1つずつ消費し、尽きたら最後の値を返し続ける。"""

    def __init__(self, remaining_ms_sequence):
        self._seq = list(remaining_ms_sequence)
        self._last = self._seq[-1] if self._seq else 300000

    def get_remaining_time_in_millis(self):
        if self._seq:
            return self._seq.pop(0)
        return self._last


@pytest.fixture
def make_context():
    def _make(remaining_ms=300000):
        seq = remaining_ms if isinstance(remaining_ms, (list, tuple)) else [remaining_ms]
        return _FakeContext(seq)
    return _make


def fake_event(path, method, body=None, query=None):
    """API Gateway(HTTP API v2)形式の疑似イベントを組み立てるヘルパー。"""
    import json as _json
    return {
        "requestContext": {
            "http": {"method": method, "sourceIp": "1.2.3.4", "path": path},
            "domainName": "example.com",
        },
        "rawPath": path,
        "queryStringParameters": query or {},
        "body": _json.dumps(body) if body is not None else None,
    }
