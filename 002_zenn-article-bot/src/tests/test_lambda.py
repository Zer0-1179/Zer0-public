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
        topic_name="Amazon S3",
        topic_subtitle="オブジェクトストレージの基本",
        keywords="s3, バケット, オブジェクト",
        today="2026-01-01",
        docs_section="",
    )
    assert "Amazon S3" in result
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
        "Parameter": {"Value": json.dumps(["ec2", "s3", "lambda"])}
    }
    monkeypatch.setattr(lambda_function, "ssm", mock_ssm)

    result = lambda_function.get_recent_topics()
    assert result == ["ec2", "s3", "lambda"]


def test_get_recent_topics_invalid_json(monkeypatch):
    """SSMの値が不正なJSONでも空リストを返すこと"""
    from unittest.mock import MagicMock
    mock_ssm = MagicMock()
    mock_ssm.exceptions.ParameterNotFound = type("ParameterNotFound", (Exception,), {})
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": "not-json"}
    }
    monkeypatch.setattr(lambda_function, "ssm", mock_ssm)

    result = lambda_function.get_recent_topics()
    assert result == []


def test_embed_cleanup_removes_single_brace_markers():
    """PNG未生成時、単一波括弧 {DIAGRAM_N} マーカーが記事に残らないこと"""
    article = "## はじめに\n本文\n\n{DIAGRAM_1}\n\n## 次\n{DIAGRAM_2}\n"
    out = lambda_function._embed_image_placeholders(article, [], "Amazon S3")
    assert "{DIAGRAM_1}" not in out
    assert "{DIAGRAM_2}" not in out


def test_embed_fallback_no_heading_does_not_raise():
    """見出しが1つも無くてもIndexErrorを出さず画像を末尾に追記すること"""
    article = "見出しのない本文だけのテキスト"
    out = lambda_function._embed_image_placeholders(article, ["/tmp/x_1.png"], "Amazon S3")
    assert "x_1.png" in out


def test_embed_replaces_marker_with_placeholder():
    """マーカーが画像プレースホルダーに置換されること"""
    article = "## はじめに\n本文\n\n{DIAGRAM_1}\n\n## まとめ\n"
    out = lambda_function._embed_image_placeholders(article, ["/tmp/diagram_1.png"], "Amazon S3")
    assert "{DIAGRAM_1}" not in out
    assert "diagram_1.png" in out
