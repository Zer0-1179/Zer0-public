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
        diagram_section="",
        angle="コスト最適化の観点",
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


def test_select_topic_excludes_recent():
    """除外済みIDのトピックが選ばれないこと"""
    excluded = [t["id"] for t in lambda_function.AWS_TOPICS if t["id"] != "s3"]
    topic = lambda_function.select_topic(excluded_ids=excluded)
    assert topic["id"] == "s3"


def test_select_topic_resets_when_all_excluded():
    """全トピックが除外済みでも例外を出さず選択できること（リセット挙動）"""
    all_ids = [t["id"] for t in lambda_function.AWS_TOPICS]
    topic = lambda_function.select_topic(excluded_ids=all_ids)
    assert topic["id"] in all_ids


def test_select_angle_excludes_recent():
    """除外済みの切り口が選ばれないこと"""
    excluded = lambda_function._DEFAULT_ANGLES[:-1]
    angle = lambda_function.select_angle(excluded_angles=excluded)
    assert angle == lambda_function._DEFAULT_ANGLES[-1]


def test_recent_angles_limit_smaller_than_total():
    """RECENT_ANGLES_LIMITが_DEFAULT_ANGLES総数より小さいこと（全消化後の恒久ロックバグ再発防止）"""
    assert lambda_function.RECENT_ANGLES_LIMIT < len(lambda_function._DEFAULT_ANGLES)


def test_validate_article_ignores_shell_comments_in_code_block():
    """コードブロック内のシェルコメント（# ...）をh1見出し混入と誤検出しないこと"""
    article = (
        "## はじめに\n本文\n\n"
        "```bash:例\n# 変数定義\nBUCKET_NAME=example\n```\n\n"
        "## まとめ\n次のアクション\n"
    )
    issues = lambda_function.validate_article(article, len(article))
    assert not any("h1見出し" in i for i in issues)


def test_validate_article_detects_real_h1_heading():
    """コードブロック外のh1見出し（# ）は検出すること"""
    article = "# タイトル\n## はじめに\n本文\n\n## まとめ\n次のアクション\n"
    issues = lambda_function.validate_article(article, len(article))
    assert any("h1見出し" in i for i in issues)


def test_validate_article_flags_char_count_out_of_range():
    """想定文字数レンジ外の記事を検出すること"""
    article = "## はじめに\naws s3 ls --region ap-northeast-1\n\n## まとめ\n"
    issues = lambda_function.validate_article(article, 200)
    assert any("文字数" in i for i in issues)
