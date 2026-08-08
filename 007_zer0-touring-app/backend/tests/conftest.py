import os
import sys
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("SES_SENDER_EMAIL", "test@example.com")
os.environ.setdefault("SES_RECIPIENT_EMAIL", "test@example.com")
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with patch("boto3.client", return_value=MagicMock()):
    import lambda_function as lf


@pytest.fixture
def module():
    """lambda_function モジュール（boto3クライアントはモック済み）を返す。
    テスト間の副作用を避けるため、DynamoDB/外部APIコール系のモックを都度リセットする。"""
    lf.dynamodb.get_item = MagicMock(return_value={})
    lf.dynamodb.put_item = MagicMock()
    lf.dynamodb.query = MagicMock(return_value={"Items": []})
    lf.dynamodb.update_item = MagicMock()
    lf.cloudwatch.get_metric_data = MagicMock(return_value={
        "MetricDataResults": [{"Id": "suggest_calls", "Timestamps": [], "Values": []}]
    })
    lf.cloudwatch.put_metric_data = MagicMock()
    lf.s3.put_object = MagicMock()
    return lf


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = 20000
    return ctx
