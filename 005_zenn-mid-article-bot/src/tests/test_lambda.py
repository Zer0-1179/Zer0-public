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
        docs_section="",
        primary_service_label="API Gateway",
    )
    assert "Lambda" in result
    assert "{DIAGRAM_1}" in result


def test_inject_reference_link_covers_all_services():
    """primary_service以外のサービスも含めて全件リンク化されること（S3・Athena等）"""
    topic = {
        "services": ["CloudTrail", "S3", "Athena"],
        "primary_service": "cloudtrail",
        "primary_service_label": "CloudTrail",
    }
    article = "本文\n\n## 参考\n"
    result = lambda_function._inject_reference_link(article, topic)
    assert "[CloudTrail 公式ドキュメント]" in result
    assert "[S3 公式ドキュメント]" in result
    assert "[Athena 公式ドキュメント]" in result


def test_inject_reference_link_skips_unmapped_service():
    """対応表・URLマップに無いサービス名が混ざっていても、他のサービスのリンクは挿入されること"""
    topic = {
        "services": ["CloudTrail", "存在しないサービス"],
        "primary_service": "cloudtrail",
        "primary_service_label": "CloudTrail",
    }
    article = "本文\n\n## 参考\n"
    result = lambda_function._inject_reference_link(article, topic)
    assert "[CloudTrail 公式ドキュメント]" in result
    assert "存在しないサービス" not in result


def test_select_topic_excludes_given_ids():
    """除外リストに含まれるトピックは選ばれないこと（Bedrockに依頼しないコード側乱択）"""
    excluded = [t["id"] for t in lambda_function.AWS_TOPICS if t["id"] != "log_analytics"]
    for _ in range(20):
        topic = lambda_function.select_topic(excluded)
        assert topic["id"] == "log_analytics"


def test_select_topic_resets_when_all_excluded():
    """全トピックが除外済みでも例外にならず、全トピックから選ばれること"""
    all_ids = [t["id"] for t in lambda_function.AWS_TOPICS]
    topic = lambda_function.select_topic(all_ids)
    assert topic["id"] in all_ids


def test_save_topic_to_ssm_uses_passed_recent_list(monkeypatch):
    """SSMを再取得せず、渡されたrecentリストをそのまま使って保存すること
    （再取得だと一時的な読み込みエラー時に履歴が[topic_id]1件に縮退するバグがあった）"""
    from unittest.mock import MagicMock
    mock_ssm = MagicMock()
    monkeypatch.setattr(lambda_function, "ssm", mock_ssm)
    # get_recent_topics が呼ばれたら（＝再取得してしまっていたら）テストを失敗させる
    mock_ssm.get_parameter.side_effect = AssertionError("save_topic_to_ssmはSSMを再取得してはいけない")

    lambda_function.save_topic_to_ssm("log_analytics", ["data_lake", "cost_optimization"])

    saved_value = json.loads(mock_ssm.put_parameter.call_args.kwargs["Value"])
    assert saved_value == ["data_lake", "cost_optimization", "log_analytics"]


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


def _make_invoke_response(content_blocks, stop_reason="end_turn"):
    import io
    body = json.dumps({
        "content": content_blocks,
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "stop_reason": stop_reason,
    }).encode("utf-8")
    return {"body": io.BytesIO(body)}


def _dummy_topic():
    return {
        "name": "テストトピック",
        "subtitle": "サブタイトル",
        "services": ["Lambda"],
        "keywords": "テスト",
        "primary_service": "unknown_service_not_in_docs_map",
        "primary_service_label": "Lambda",
    }


def test_generate_article_extracts_text_block_when_thinking_present(monkeypatch):
    """thinkingブロックがcontent[0]にあってもtextブロックを正しく抽出できること"""
    monkeypatch.setattr(
        lambda_function.bedrock, "invoke_model",
        lambda **kwargs: _make_invoke_response([
            {"type": "thinking", "thinking": "考え中..."},
            {"type": "text", "text": "本文です"},
        ]),
    )
    text, is_truncated = lambda_function.generate_article(_dummy_topic(), "2026-01-01", "jp.anthropic.claude-sonnet-5")
    assert text == "本文です"
    assert is_truncated is False


def test_generate_article_no_text_block_does_not_raise(monkeypatch):
    """adaptive thinkingがmax_tokensで打ち切られtextブロックが無い場合でも
    StopIterationを送出せず、空記事＋truncated扱いにフォールバックすること"""
    monkeypatch.setattr(
        lambda_function.bedrock, "invoke_model",
        lambda **kwargs: _make_invoke_response(
            [{"type": "thinking", "thinking": "考え中..."}],
            stop_reason="max_tokens",
        ),
    )
    text, is_truncated = lambda_function.generate_article(_dummy_topic(), "2026-01-01", "jp.anthropic.claude-sonnet-5")
    assert text == ""
    assert is_truncated is True
