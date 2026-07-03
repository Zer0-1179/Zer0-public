"""006 CryptoBot 全体のpytest共通フィクスチャ。

analyzer/executor はどちらもファイル名が lambda_function.py で衝突するため、
sys.path 経由の import ではなく importlib.util で明示的な別名を付けてロードする。
このディレクトリは lambda/*/ の外（プロジェクトルート直下）に置くこと。
deploy.sh は analyzer は "*.py"（非再帰）、executor は requirements.txt が空の限り
lambda_function.py 単体のみをzip化するため、lambda/配下にtests/を置くと
将来requirements.txtに依存が追加された際に誤って本番ZIPへ同梱されるリスクがある。
"""
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("SES_SENDER_EMAIL", "test@example.com")
os.environ.setdefault("SES_RECIPIENT_EMAIL", "test@example.com")
os.environ.setdefault("EXECUTOR_FUNCTION_NAME", "test-executor")
os.environ.setdefault("TRADES_BUCKET", "test-bucket")

sys.path.insert(0, os.path.join(ROOT, "backtest"))


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


with patch("boto3.client", return_value=MagicMock()):
    _analyzer = _load_module("analyzer_lambda_function", os.path.join(ROOT, "lambda", "analyzer", "lambda_function.py"))
    _executor = _load_module("executor_lambda_function", os.path.join(ROOT, "lambda", "executor", "lambda_function.py"))


@pytest.fixture
def analyzer():
    return _analyzer


@pytest.fixture
def executor():
    """executor_lambda_function モジュールを返す。DynamoDBは使わずSSM/bitbank/SESを
    テスト間で毎回リセットする（副作用の持ち越し防止）。"""
    _executor.send_email = MagicMock()
    return _executor


@pytest.fixture
def mock_bb():
    """BitbankClient相当のMagicMock。get_margin_positions等はテスト毎に個別設定する。"""
    return MagicMock()
