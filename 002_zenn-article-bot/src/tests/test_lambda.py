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
    assert "{DIAGRAM_1}" not in result
    assert "{DIAGRAM_2}" not in result


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


def test_embed_no_heading_does_not_raise():
    """見出しが1つも無くても例外を出さずそのまま返すこと（画像はBot側で生成しない）"""
    article = "見出しのない本文だけのテキスト"
    out = lambda_function._embed_image_placeholders(article, [], "Amazon S3")
    assert out == article


def test_embed_strips_marker_without_embedding_image():
    """{DIAGRAM_N}マーカーは画像に置換せず除去だけすること（画像はGPTに依頼する運用のため）"""
    article = "## はじめに\n本文\n\n{DIAGRAM_1}\n\n## まとめ\n"
    out = lambda_function._embed_image_placeholders(article, [], "Amazon S3")
    assert "{DIAGRAM_1}" not in out
    assert ".png" not in out


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


def test_validate_article_flags_too_short():
    """1,200文字未満（内容不足・生成異常の兆候）を検出すること"""
    article = "## はじめに\n\n## まとめ\n"
    issues = lambda_function.validate_article(article, 1000)
    assert any("文字数" in i for i in issues)


def test_validate_article_flags_too_long():
    """目安(2,000文字程度)を大きく超える記事（2,800文字超）を警告すること（2026-11-05〜）"""
    article = "## はじめに\n\n## まとめ\n"
    issues = lambda_function.validate_article(article, 3000)
    assert any("超えています" in i for i in issues)


def test_validate_article_accepts_target_length_without_cli():
    """ハンズオン廃止によりAWS CLIコマンドが無くても、目安文字数内なら問題なしとすること"""
    article = "## はじめに\n\n## ポイント\n\n## まとめ\n"
    issues = lambda_function.validate_article(article, 1900)
    assert issues == []


def test_auto_fix_replaces_old_runtime():
    """古いLambdaランタイム表記を最新版に自動置換すること"""
    article = "```bash\naws lambda create-function --runtime python3.12\n```"
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert "python3.12" not in fixed
    assert "python3.14" in fixed
    assert any("python3.12" in f for f in fixes)


def test_auto_fix_replaces_previous_latest_runtime():
    """1つ前の最新版（python3.13 / nodejs22.x）も最新版に置換すること"""
    article = "```bash\naws lambda create-function --runtime python3.13\naws lambda create-function --runtime nodejs22.x\n```"
    fixed, _ = lambda_function._auto_fix_article(article)
    assert "python3.13" not in fixed and "nodejs22.x" not in fixed
    assert "python3.14" in fixed and "nodejs24.x" in fixed


def test_auto_fix_promotes_h1_outside_code_block():
    """コードブロック外のh1見出しは##に格上げし、コードブロック内の# コメントは触らないこと"""
    article = (
        "# タイトル\n## はじめに\n本文\n\n"
        "```bash:例\n# 変数定義\nBUCKET_NAME=example\n```\n"
    )
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert "## タイトル" in fixed
    assert "# 変数定義" in fixed  # コードブロック内はそのまま
    assert any("h1見出し" in f for f in fixes)


def test_auto_fix_adds_language_to_bare_code_block():
    """言語指定のないコードブロックに text を補完すること"""
    article = "## はじめに\n```\nsome output\n```\n## まとめ\n"
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert "```text" in fixed
    assert any("text" in f for f in fixes)


def test_auto_fix_appends_region_when_missing_everywhere():
    """記事全体に--regionが一つも無い場合、単一行の aws コマンドに補完すること"""
    article = "## はじめに\n```bash\naws s3 ls\n```\n## まとめ\n"
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert "aws s3 ls --region ap-northeast-1" in fixed
    assert any("region" in f for f in fixes)


def test_auto_fix_skips_multiline_command_for_region():
    """行末が\\の複数行コマンドには--regionを補完しない（誤修正防止）こと"""
    article = "## はじめに\n```bash\naws s3 ls \\\n  --bucket example\n```\n## まとめ\n"
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert fixed == article
    assert fixes == []


def test_auto_fix_noop_when_no_issues():
    """修正対象が無ければテキストは変更されず、修正リストも空であること"""
    article = "## はじめに\n```bash:例\naws s3 ls --region ap-northeast-1\n```\n## まとめ\n"
    fixed, fixes = lambda_function._auto_fix_article(article)
    assert fixed == article
    assert fixes == []


def test_all_diagram_functions_render_without_error(tmp_path):
    """全構成図生成関数がエラーなくPNGを出力すること（回帰防止）"""
    import diagram_generator as dg

    fns = [
        (name, obj) for name, obj in vars(dg).items()
        if name.startswith("_diagram_") and callable(obj)
    ]
    assert len(fns) > 0, "構成図関数が1つも見つかりません"
    for name, fn in fns:
        out = str(tmp_path / f"{name}.png")
        fn(out)
        assert os.path.exists(out), f"{name}: PNGが出力されませんでした"


def test_diagram_vpc_1_cluster_not_clipped_by_xlim(tmp_path):
    """VPCトピック図1で、クラスター重なり解消により押し出された枠がxlim内に収まること
    （2026-07-16に発覚した右端クリップバグの回帰防止。過去はxlimが固定(0,13)で
    プライベートサブネット枠の右端がちょうど境界に達し画像端でクリップされていた）"""
    import diagram_generator as dg
    from unittest.mock import patch

    captured = {}
    orig_subplots = dg.plt.subplots

    def spy_subplots(*args, **kwargs):
        captured["figsize"] = kwargs.get("figsize", args[0] if args else None)
        return orig_subplots(*args, **kwargs)

    with patch.object(dg.plt, "subplots", side_effect=spy_subplots):
        dg._diagram_vpc_1(str(tmp_path / "vpc_1.png"))

    # 修正前は常に (13, 6) 固定だった。押し出された枠を収めるため幅が拡張されていること
    assert captured["figsize"][0] > 13.0, (
        "xlim自動拡張が発動していません。クラスター枠がクリップされる可能性があります"
    )


# ─── 新機能記事モード（2026-11-05〜） ───────────────────────────────────────────

_FEED = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Amazon SageMaker AI で SOCI インデックス付きイメージがサポート</title>
<link>https://aws.amazon.com/about-aws/whats-new/2026/10/a/</link>
<description>&lt;p&gt;{body}&lt;/p&gt;</description><pubDate>Wed, 29 Oct 2026 20:00:00 GMT</pubDate>
<category>general:products/amazon-ecr,general:products/amazon-sagemaker</category></item>
<item><title>Amazon EC2 Auto Scaling が終了前の起動をサポート</title>
<link>https://aws.amazon.com/about-aws/whats-new/2026/10/b/</link>
<description>{body}</description><pubDate>Mon, 26 Oct 2026 01:00:00 GMT</pubDate>
<category>general:products/amazon-ec2,general:products/amazon-ec2-auto-scaling</category></item>
<item><title>AWS GovCloud (米国) の Amazon Bedrock で新モデル</title>
<link>https://aws.amazon.com/about-aws/whats-new/2026/10/c/</link>
<description>{body}</description><pubDate>Mon, 26 Oct 2026 01:00:00 GMT</pubDate>
<category>general:products/amazon-bedrock</category></item>
<item><title>Amazon Connect で新機能</title>
<link>https://aws.amazon.com/about-aws/whats-new/2026/10/d/</link>
<description>{body}</description><pubDate>Mon, 26 Oct 2026 01:00:00 GMT</pubDate>
<category>general:products/amazon-connect</category></item>
</channel></rss>""".replace("{body}", "発表本文。" * 60)


def _fetch_from(tmp_path, monkeypatch):
    f = tmp_path / "feed.xml"
    f.write_text(_FEED, encoding="utf-8")
    monkeypatch.setattr(lambda_function, "NEWS_FEED_URL", f.as_uri())
    return lambda_function.fetch_news_items()


def test_fetch_news_uses_title_service_and_filters_noise(tmp_path, monkeypatch):
    """製品タグのうちタイトルに出るサービスを主役にし、GovCloud・対象外サービスを除くこと"""
    items = _fetch_from(tmp_path, monkeypatch)
    got = {i["url"].rsplit("/", 2)[-2]: i["topic_id"] for i in items}
    assert got == {"a": "sagemaker", "b": "auto_scaling"}
    a = next(i for i in items if i["topic_id"] == "sagemaker")
    assert a["date"] == "2026-10-30"  # GMT 20:00 → JST翌日
    assert "<p>" not in a["body"]


def test_select_news_skips_used_urls_and_prefers_new_services():
    items = [
        {"url": "u1", "topic_id": "ec2", "body": "x" * 300},
        {"url": "u2", "topic_id": "s3", "body": "x" * 300},
        {"url": "u3", "topic_id": "rds", "body": "x" * 100},  # 本文が短すぎる
    ]
    for _ in range(20):
        assert lambda_function.select_news(items, ["u1"], [])["url"] == "u2"
    # 直近に扱ったサービスは避ける（他に候補がある場合）
    items.append({"url": "u4", "topic_id": "vpc", "body": "x" * 300})
    for _ in range(20):
        assert lambda_function.select_news(items, [], ["ec2", "s3"])["url"] == "u4"
    # 全サービスが直近でも、未使用URLがあれば選ぶ
    assert lambda_function.select_news(items[:1], [], ["ec2"])["url"] == "u1"
    assert lambda_function.select_news(items[:1], ["u1"], []) is None


def test_news_prompt_formats_without_key_error():
    result = lambda_function.NEWS_ARTICLE_PROMPT_TEMPLATE.format(
        service_name="Amazon EKS", news_title="T", news_date="2026-10-29",
        news_body="本文", docs_section="", today="2026-11-05",
    )
    assert "Amazon EKS" in result and "本文" in result
    assert "切り口" not in result


def test_all_news_services_have_zenn_meta():
    ids = {v[0] for v in lambda_function.NEWS_PRODUCT_MAP.values()}
    assert ids <= set(lambda_function._ZENN_META)


def test_generate_article_news_appends_source(monkeypatch):
    """新機能記事では出典リンクをコード側で末尾に付けること"""
    from unittest.mock import MagicMock
    body = MagicMock()
    body.read.return_value = json.dumps({
        "content": [{"text": "TITLE: タイトル\n\n## はじめに\n本文\n\n## まとめ\n次へ"}],
        "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "end_turn",
    }).encode()
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {"body": body}
    monkeypatch.setattr(lambda_function, "bedrock", mock_bedrock)
    monkeypatch.setattr(lambda_function, "fetch_aws_docs", lambda *a, **k: "")
    news = {"title": "発表", "url": "https://example.com/n", "date": "2026-10-29", "body": "本文"}
    topic = {"id": "eks", "name": "Amazon EKS", "subtitle": "発表", "keywords": ""}
    text, title, _, _ = lambda_function.generate_article(topic, "2026-11-05", "", news=news)
    assert title == "タイトル"
    assert text.rstrip().endswith("**出典**: [発表](https://example.com/n)（AWS 最新情報、2026-10-29）")
    sent = json.loads(mock_bedrock.invoke_model.call_args.kwargs["body"])["messages"][0]["content"]
    assert "発表内容（根拠情報）" in sent


def test_run_falls_back_to_evergreen_when_no_news(monkeypatch):
    """新機能の候補が無いときは定番解説で生成を続けること"""
    calls = {}
    monkeypatch.setattr(lambda_function, "_pick_news", lambda recent: None)
    monkeypatch.setattr(lambda_function, "get_recent_topics", lambda: [])
    monkeypatch.setattr(lambda_function, "get_recent_angles", lambda: [])
    monkeypatch.setattr(lambda_function, "_save_recent_id", lambda *a, **k: None)
    monkeypatch.setattr(lambda_function, "_prepare_article_paths", lambda *a, **k: ("/tmp/x.md", "/tmp/x"))
    monkeypatch.setattr(lambda_function, "save_to_local", lambda *a, **k: None)

    def fake_generate(topic, today, angle, news=None):
        calls["news"] = news
        calls["angle"] = angle
        return "## はじめに\n本文\n## まとめ\n", "t", False, {}
    monkeypatch.setattr(lambda_function, "generate_article", fake_generate)
    lambda_function.run(dry_run=True, mode="news")
    assert calls["news"] is None
    assert calls["angle"].startswith("【新機能の候補なしのため定番解説】")
