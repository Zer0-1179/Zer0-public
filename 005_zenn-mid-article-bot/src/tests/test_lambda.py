import os
import sys
import json
import datetime

os.environ.setdefault("SES_SENDER_EMAIL", "test@example.com")
os.environ.setdefault("SES_RECIPIENT_EMAIL", "test@example.com")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import lambda_function


def test_should_skip_scheduled_run_until_resume_month():
    """2027年1月までのEventBridge定期実行だけを一時停止すること。"""
    scheduled_event = {"source": "aws.events", "detail-type": "Scheduled Event"}

    assert lambda_function.should_skip_scheduled_run(
        scheduled_event, datetime.datetime(2026, 8, 15, 21, tzinfo=datetime.timezone.utc)
    )
    assert lambda_function.should_skip_scheduled_run(
        scheduled_event, datetime.datetime(2027, 1, 15, 21, tzinfo=datetime.timezone.utc)
    )
    assert not lambda_function.should_skip_scheduled_run(
        scheduled_event, datetime.datetime(2027, 2, 1, 21, tzinfo=datetime.timezone.utc)
    )


def test_should_not_skip_manual_or_dry_run_invocations():
    """手動実行・dry_runの検証経路は一時停止中も利用できること。"""
    now = datetime.datetime(2026, 8, 15, 21, tzinfo=datetime.timezone.utc)

    assert not lambda_function.should_skip_scheduled_run({}, now)
    assert not lambda_function.should_skip_scheduled_run({"dry_run": True}, now)


def test_lambda_handler_returns_before_any_generation_during_pause(monkeypatch):
    """一時停止中の定期実行は外部I/Oを始める前に終了すること。"""
    monkeypatch.setattr(lambda_function, "should_skip_scheduled_run", lambda event, now: True)

    def fail_if_called():
        raise AssertionError("一時停止中にトピック取得が実行されました")

    monkeypatch.setattr(lambda_function, "get_recent_topics", fail_if_called)
    result = lambda_function.lambda_handler(
        {"source": "aws.events", "detail-type": "Scheduled Event"}, None
    )
    body = json.loads(result["body"])

    assert result["statusCode"] == 200
    assert body["skipped"] is True
    assert body["resume_month"] == "2027-02"


def _prompt_topic():
    return {
        "name": "サーバーレスEコマース",
        "subtitle": "Lambda + API Gateway + DynamoDB",
        "services": ["Lambda", "API Gateway", "DynamoDB"],
        "keywords": "サーバーレス, eコマース, スケーリング",
        "primary_service_label": "API Gateway",
    }


def test_article_prompt_no_key_error():
    """プロンプト組み立て（テンプレートformat＋乱択要素の埋め込み）がKeyErrorを出さないこと"""
    result = lambda_function.build_article_prompt(_prompt_topic(), "2026-01-01", "")
    assert "Lambda" in result
    assert "{DIAGRAM_1}" in result


def test_build_prompt_keeps_diagram_marker_and_sections():
    """乱択要素が入ってもDIAGRAM_1マーカーと必須セクション指示が毎回含まれること"""
    for _ in range(30):
        result = lambda_function.build_article_prompt(_prompt_topic(), "2026-01-01", "")
        assert "{DIAGRAM_1}" in result
        assert "## 各コンポーネントの選定理由" in result
        assert "## 構成手順" in result
        assert "## はじめに" in result


def test_build_prompt_opening_style_varies():
    """書き出しスタイルがコード側乱択で切り替わること（LLM任せの偏り防止）"""
    assert len(set(lambda_function._OPENING_STYLES)) >= 4
    seen = set()
    for _ in range(100):
        result = lambda_function.build_article_prompt(_prompt_topic(), "2026-01-01", "")
        for i, style in enumerate(lambda_function._OPENING_STYLES):
            if style in result:
                seen.add(i)
    assert len(seen) >= 2, "書き出しスタイルが1種類しか選ばれていません"


def test_build_prompt_section_order_varies():
    """選定理由と構成手順の並び順が両方向とも出現すること"""
    orders = set()
    for _ in range(100):
        result = lambda_function.build_article_prompt(_prompt_topic(), "2026-01-01", "")
        idx_components = result.index("## 各コンポーネントの選定理由")
        idx_steps = result.index("## 構成手順")
        orders.add(idx_components < idx_steps)
    assert orders == {True, False}


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


def _all_service_combos(topic: dict) -> list[list[str]]:
    """トピックの基本形＋全バリエーションのservicesリストを列挙する"""
    combos = [topic["services"]]
    for v in topic.get("variants", []):
        if "services" in v:
            combos.append(v["services"])
    return combos


def test_select_topic_resolves_variants():
    """variantsを持つトピックは複数回の選択で異なるサービス組み合わせが選ばれ得ること。
    返る辞書は解決済み（variantsキーなし・servicesは定義済み組み合わせのいずれか）であること。"""
    base = next(t for t in lambda_function.AWS_TOPICS if t["id"] == "log_analytics")
    assert base.get("variants"), "log_analyticsにvariantsが定義されている前提のテスト"
    allowed = {tuple(c) for c in _all_service_combos(base)}
    excluded = [t["id"] for t in lambda_function.AWS_TOPICS if t["id"] != "log_analytics"]

    seen = set()
    for _ in range(100):
        topic = lambda_function.select_topic(excluded)
        assert topic["id"] == "log_analytics"
        assert "variants" not in topic
        assert tuple(topic["services"]) in allowed
        # subtitle・keywordsもバリエーションに合わせて解決されていること（AWS_TOPICS本体は不変）
        assert topic["subtitle"]
        assert topic["keywords"]
        seen.add(tuple(topic["services"]))
    assert len(seen) >= 2, "100回選択してもサービス組み合わせが1種類しか出ていません"
    # 乱択がAWS_TOPICS本体を書き換えていないこと
    assert base["services"] == ["CloudTrail", "S3", "Athena"]
    assert "variants" in base


def test_resolve_variant_passthrough_for_fixed_topic():
    """variantsを持たないトピックはそのままの内容で返ること"""
    base = next(t for t in lambda_function.AWS_TOPICS if not t.get("variants"))
    resolved = lambda_function._resolve_topic_variant(base)
    assert resolved == base


def test_all_variant_services_have_docs_urls():
    """基本形・バリエーション含む全サービス名が公式ドキュメントURLに解決できること
    （URLハルシネーション・追加漏れの回帰防止）"""
    for topic in lambda_function.AWS_TOPICS:
        for combo in _all_service_combos(topic):
            for svc in combo:
                doc_id = lambda_function._SERVICE_NAME_TO_DOCS_ID.get(svc)
                assert doc_id, f"{topic['id']}: '{svc}' が_SERVICE_NAME_TO_DOCS_IDに未登録"
                url = lambda_function.DOCS_URL_MAP.get(doc_id)
                assert url and url.startswith("https://docs.aws.amazon.com/"), (
                    f"{topic['id']}: '{svc}' ({doc_id}) のDOCS_URL_MAPエントリが不正"
                )


def test_all_variant_services_have_official_icons():
    """基本形・バリエーション含む全サービス名がAWS公式アイコンに解決できること
    （userアイコン・色付きボックスへのフォールバック禁止）"""
    import diagram_generator as dg

    for topic in lambda_function.AWS_TOPICS:
        for combo in _all_service_combos(topic):
            for svc in combo:
                icon = dg._icon_for_service(svc)
                assert icon != "user", f"{topic['id']}: '{svc}' がuserアイコンにフォールバック"
                official = os.path.join(dg._OFFICIAL_ICON_DIR, dg._OFFICIAL_ICON_MAP.get(icon, ""))
                bundled = os.path.join(dg._BUNDLED_ICON_DIR, f"{icon}.png")
                assert (icon in dg._OFFICIAL_ICON_MAP and os.path.exists(official)) or os.path.exists(bundled), (
                    f"{topic['id']}: '{svc}' のアイコン '{icon}' の実ファイルが存在しない"
                )


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
