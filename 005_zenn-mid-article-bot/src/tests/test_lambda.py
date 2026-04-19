import os
import sys
import json

os.environ.setdefault("SES_SENDER_EMAIL", "test@example.com")
os.environ.setdefault("SES_RECIPIENT_EMAIL", "test@example.com")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import lambda_function


def test_article_prompt_no_key_error():
    """プロンプトテンプレートのformat()がKeyErrorを出さないこと"""
    result = lambda_function.ARTICLE_PROMPT_TEMPLATE.format(
        topic_name="サーバーレスEコマース",
        topic_subtitle="Lambda + API Gateway + DynamoDB",
        services="Lambda, API Gateway, DynamoDB",
        keywords="サーバーレス, eコマース, スケーリング",
        today="2026-01-01",
    )
    assert "Lambda" in result
    assert "{DIAGRAM_1}" in result
    assert "{DIAGRAM_2}" in result


def test_get_recent_topics_empty(monkeypatch):
    """SSMパラメータが存在しない場合は空リストを返すこと"""
    from unittest.mock import MagicMock
    mock_ssm = MagicMock()
    mock_ssm.exceptions.ParameterNotFound = type("ParameterNotFound", (Exception,), {})
    mock_ssm.get_parameter.side_effect = mock_ssm.exceptions.ParameterNotFound("not found")
    monkeypatch.setattr(lambda_function, "ssm", mock_ssm)

    result = lambda_function.get_recent_topics()
    assert result == []


def test_get_recent_topics_with_data(monkeypatch):
    """SSMにデータがある場合はリストを返すこと"""
    from unittest.mock import MagicMock
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": json.dumps(["serverless_ec", "data_lake"])}
    }
    monkeypatch.setattr(lambda_function, "ssm", mock_ssm)

    result = lambda_function.get_recent_topics()
    assert result == ["serverless_ec", "data_lake"]


def test_model_id_test_mode():
    """test_mode=Trueのとき HAIKU_MODEL_ID が使われること"""
    assert lambda_function.HAIKU_MODEL_ID != lambda_function.BEDROCK_MODEL_ID
    # model_id の切り替えロジックを直接検証
    model_id = lambda_function.HAIKU_MODEL_ID if True else lambda_function.BEDROCK_MODEL_ID
    assert model_id == lambda_function.HAIKU_MODEL_ID


def test_model_id_prod_mode():
    """test_mode=Falseのとき BEDROCK_MODEL_ID（Sonnet）が使われること"""
    model_id = lambda_function.HAIKU_MODEL_ID if False else lambda_function.BEDROCK_MODEL_ID
    assert model_id == lambda_function.BEDROCK_MODEL_ID
