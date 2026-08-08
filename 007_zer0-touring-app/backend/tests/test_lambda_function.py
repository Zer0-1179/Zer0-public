"""lambda_function.py の主要ロジックに対するユニットテスト。
実際のAWS/外部APIには接続せず、boto3クライアントとurllib呼び出しをモックする。
第2巡Fableレビュー(2026-07-03)で見つかった各バグの再発防止テストを含む。
"""
import json
from unittest.mock import MagicMock, patch


# ── X-Forwarded-For / レートリミット回避対策 ──────────────────────────────

def test_get_client_ip_trusts_last_hop_not_first(module):
    """XFFの先頭ではなく末尾（CloudFrontが付与する実IP）を信頼すること。
    先頭を信頼するとクライアントが偽装してレートリミットを回避できてしまう。"""
    event = {"headers": {"x-forwarded-for": "1.2.3.4, 203.0.113.9"}}
    assert module._get_client_ip(event) == "203.0.113.9"


def test_get_client_ip_falls_back_to_source_ip(module):
    event = {"headers": {}, "requestContext": {"http": {"sourceIp": "198.51.100.1"}}}
    assert module._get_client_ip(event) == "198.51.100.1"


# ── execute-api 直接アクセス遮断（X-Origin-Verify） ───────────────────────

def test_edge_secret_rejects_missing_header(module, monkeypatch):
    monkeypatch.setattr(module, "EDGE_SECRET", "correct-secret")
    event = {"requestContext": {"http": {"method": "GET", "path": "/api/status"}}, "headers": {}}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 403


def test_edge_secret_rejects_wrong_value(module, monkeypatch):
    monkeypatch.setattr(module, "EDGE_SECRET", "correct-secret")
    event = {"requestContext": {"http": {"method": "GET", "path": "/api/status"}},
             "headers": {"x-origin-verify": "wrong"}}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 403


def test_edge_secret_allows_correct_value(module, monkeypatch):
    monkeypatch.setattr(module, "EDGE_SECRET", "correct-secret")
    monkeypatch.setattr(module, "get_usage", MagicMock(return_value=0))
    event = {"requestContext": {"http": {"method": "GET", "path": "/api/status"}},
             "headers": {"x-origin-verify": "correct-secret"}}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200


def test_edge_secret_bypassed_for_options_preflight(module, monkeypatch):
    monkeypatch.setattr(module, "EDGE_SECRET", "correct-secret")
    event = {"requestContext": {"http": {"method": "OPTIONS", "path": "/api/suggest"}}, "headers": {}}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200


# ── ジオコーディングキャッシュ ────────────────────────────────────────────

def test_geocode_cache_key_buckets_by_origin_degree(module):
    key_a = module._geocode_cache_key("テスト", 35.6, 139.6)
    key_near = module._geocode_cache_key("テスト", 35.65, 139.55)
    key_far = module._geocode_cache_key("テスト", 34.6, 135.5)
    assert key_a == key_near, "1度以内の近いoriginは同じキャッシュバケットになるべき"
    assert key_a != key_far, "大きく離れたoriginは別バケットになるべき"


def test_nominatim_geocode_cache_hit_skips_network_call(module):
    module.dynamodb.get_item = MagicMock(
        return_value={"Item": {"lat": {"N": "35.3"}, "lon": {"N": "139.48"}}}
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        lat, lon = module.nominatim_geocode("江の島", 35.6, 139.6)
    assert (lat, lon) == (35.3, 139.48)
    assert not mock_urlopen.called


def test_nominatim_geocode_cache_miss_calls_network_and_populates_cache(module):
    module.dynamodb.get_item = MagicMock(return_value={})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'[{"lat":"35.3","lon":"139.48"}]'
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        lat, lon = module.nominatim_geocode("江の島", 35.6, 139.6)
    assert (lat, lon) == (35.3, 139.48)
    assert mock_urlopen.called
    assert module.dynamodb.put_item.called


def test_nominatim_geocode_retry_recovers_from_transient_error(module):
    """目的地ジオコーディングが接続エラーで失敗すると天気取得も道連れでフロントが
    「取得中...」のまま固まるバグがあったため、retry=Trueで1回だけ再試行できること。"""
    module.dynamodb.get_item = MagicMock(return_value={})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'[{"lat":"35.3","lon":"139.48"}]'
        mock_urlopen.side_effect = [TimeoutError("timed out"), MagicMock(__enter__=lambda s: mock_resp, __exit__=lambda *a: None)]
        lat, lon = module.nominatim_geocode("江の島", 35.6, 139.6, retry=True)
    assert (lat, lon) == (35.3, 139.48)
    assert mock_urlopen.call_count == 2


def test_nominatim_geocode_no_retry_by_default(module):
    """retry=False（デフォルト）では従来通り1回失敗したら即諦めること
    （スポット側geocode_and_filter_filterの時間予算を圧迫しないため）。"""
    module.dynamodb.get_item = MagicMock(return_value={})
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")) as mock_urlopen:
        lat, lon = module.nominatim_geocode("江の島", 35.6, 139.6)
    assert (lat, lon) == (None, None)
    assert mock_urlopen.call_count == 1


def test_nominatim_geocode_empty_result_not_retried(module):
    """0件ヒットはネットワークエラーではないため、retry=Trueでも再試行しないこと
    （再試行しても結果は変わらず無駄なNominatim呼び出しになるため）。"""
    module.dynamodb.get_item = MagicMock(return_value={})
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        lat, lon = module.nominatim_geocode("存在しない地名", 35.6, 139.6, retry=True)
    assert (lat, lon) == (None, None)
    assert mock_urlopen.call_count == 1


# ── コース履歴保存機能 ────────────────────────────────────────────────────

def test_history_post_rejects_invalid_device_id(module):
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/history"}},
             "headers": {"x-device-id": "x"}, "body": json.dumps({"course": {"name": "test"}})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 400


def test_history_post_saves_with_correct_partition_key(module):
    device_id = "a" * 32
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/history"}},
             "headers": {"x-device-id": device_id},
             "body": json.dumps({"course": {"name": "テストコース", "destination": "箱根", "duration_hours": 2}})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    assert module.dynamodb.put_item.call_args.kwargs["Item"]["pk"]["S"] == device_id


def test_history_get_returns_items_newest_first(module):
    device_id = "a" * 32
    module.dynamodb.query = MagicMock(return_value={"Items": [
        {"name": {"S": "コースA"}, "destination": {"S": "箱根"}, "duration": {"S": "2"},
         "course_b64": {"S": "xxx"}, "sk": {"S": "2026-07-03T00:00:00#ab12"}},
    ]})
    event = {"requestContext": {"http": {"method": "GET", "path": "/api/history"}},
             "headers": {"x-device-id": device_id}}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    items = json.loads(resp["body"])["items"]
    assert len(items) == 1
    assert items[0]["name"] == "コースA"
    assert items[0]["created_at"] == "2026-07-03T00:00:00"  # sk末尾のsuffixは含まない
    assert module.dynamodb.query.call_args.kwargs["ScanIndexForward"] is False


# ── 二段階レスポンス（/api/suggest 高速化 + /api/enrich） ─────────────────

def test_suggest_returns_without_calling_enrich(module, monkeypatch):
    """/api/suggest はBedrock結果をそのまま返し、enrich_courseを呼ばないこと
    （呼ぶと3コース分のNominatim直列ジオコーディングでLambda Timeoutに近づく）。"""
    monkeypatch.setattr(module, "check_rate_limit", MagicMock(return_value=True))
    mock_enrich = MagicMock()
    monkeypatch.setattr(module, "enrich_course", mock_enrich)
    monkeypatch.setattr(module.bedrock, "invoke_model", MagicMock(return_value={"body": MagicMock(read=lambda: json.dumps({
        "content": [{"text": '{"courses":[{"name":"テストコース","destination":"箱根","distance_km":50,"duration_hours":1.0}]}'}]
    }).encode())}))
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/suggest"}},
             "headers": {"x-forwarded-for": "1.2.3.4"},
             "body": json.dumps({"latitude": 35.6, "longitude": 139.6, "temperature": 20, "weather_condition": "晴れ"})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    assert not mock_enrich.called
    data = json.loads(resp["body"])
    assert data["courses"][0]["name"] == "テストコース"

    # 成功時のみ利用実績カスタムメトリクスを発火すること（stats_handler集計対象）
    _, kwargs = module.cloudwatch.put_metric_data.call_args
    assert kwargs["Namespace"] == module.STATS_METRIC_NAMESPACE
    assert kwargs["MetricData"][0]["MetricName"] == module.STATS_METRIC_NAME


def test_enrich_post_updates_course_and_returns_it(module, monkeypatch):
    monkeypatch.setattr(module, "check_and_reserve_gmaps", MagicMock(return_value=False))

    def fake_enrich(course, lat, lon, ctx, use_gmaps=True):
        course["distance_km"] = 55
        course["dest_lat"] = 35.2

    monkeypatch.setattr(module, "enrich_course", MagicMock(side_effect=fake_enrich))
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/enrich"}}, "headers": {},
             "body": json.dumps({"course": {"name": "テストコース", "destination": "箱根"},
                                  "latitude": 35.6, "longitude": 139.6})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    course = json.loads(resp["body"])["course"]
    assert course["distance_km"] == 55
    assert course["dest_lat"] == 35.2


def test_enrich_post_returns_200_with_original_course_on_internal_error(module, monkeypatch):
    """enrich_courseが例外を投げても、AI推定値のままcourseを200で返し続けること
    （失敗してもフロントの表示が壊れないようにするための設計）。"""
    monkeypatch.setattr(module, "check_and_reserve_gmaps", MagicMock(return_value=False))
    monkeypatch.setattr(module, "enrich_course", MagicMock(side_effect=Exception("boom")))
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/enrich"}}, "headers": {},
             "body": json.dumps({"course": {"name": "テスト2"}, "latitude": 35.6, "longitude": 139.6})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["course"]["name"] == "テスト2"


def test_enrich_post_emits_metric_when_geocode_fails(module, monkeypatch):
    """目的地ジオコーディング失敗（dest_lat無し）の発生率を追跡できるよう、
    その場合のみカスタムメトリクスを発火すること（フロントの「取得中...」固着バグの
    再発検知用、2026-08-09追加）。"""
    monkeypatch.setattr(module, "check_and_reserve_gmaps", MagicMock(return_value=False))
    monkeypatch.setattr(module, "enrich_course", MagicMock())  # course.dest_latを付けない=失敗を模擬
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/enrich"}}, "headers": {},
             "body": json.dumps({"course": {"name": "テスト3", "destination": "箱根"},
                                  "latitude": 35.6, "longitude": 139.6})}
    resp = module.lambda_handler(event, MagicMock())
    assert resp["statusCode"] == 200
    _, kwargs = module.cloudwatch.put_metric_data.call_args
    assert kwargs["MetricData"][0]["MetricName"] == "EnrichGeocodeFailed"


def test_enrich_post_does_not_emit_metric_when_geocode_succeeds(module, monkeypatch):
    monkeypatch.setattr(module, "check_and_reserve_gmaps", MagicMock(return_value=False))

    def fake_enrich(course, lat, lon, ctx, use_gmaps=True):
        course["dest_lat"] = 35.2

    monkeypatch.setattr(module, "enrich_course", MagicMock(side_effect=fake_enrich))
    module.cloudwatch.put_metric_data.reset_mock()
    event = {"requestContext": {"http": {"method": "POST", "path": "/api/enrich"}}, "headers": {},
             "body": json.dumps({"course": {"name": "テスト4", "destination": "箱根"},
                                  "latitude": 35.6, "longitude": 139.6})}
    module.lambda_handler(event, MagicMock())
    assert not module.cloudwatch.put_metric_data.called


# ── 外部API呼び出しの時間予算管理（enrich_course の残り時間ガード） ────────

def test_enrich_course_skips_weather_when_time_is_low(module, mock_context, monkeypatch):
    """残り時間が不足したら天気取得だけスキップし、距離は既に取れていれば維持する。"""
    monkeypatch.setattr(module, "nominatim_geocode", MagicMock(return_value=(35.0, 139.0)))
    monkeypatch.setattr(module, "osrm_route", MagicMock(return_value=(100, None)))
    monkeypatch.setattr(module, "google_maps_route", MagicMock(return_value=(None, None)))
    mock_weather = MagicMock(return_value=(20, 0))
    monkeypatch.setattr(module, "fetch_dest_weather", mock_weather)

    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.side_effect = [20000, 20000, 2000]
    course = {"destination": "テスト目的地", "outbound_spots": [], "return_spots": []}
    module.enrich_course(course, 35.0, 139.0, ctx, use_gmaps=False)

    assert not mock_weather.called
    assert course.get("distance_km") == 100


def test_enrich_course_skips_everything_when_time_is_critically_low(module, monkeypatch):
    monkeypatch.setattr(module, "nominatim_geocode", MagicMock(return_value=(35.0, 139.0)))
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = 1000
    course = {"destination": "テスト目的地3", "outbound_spots": [{"name": "A", "type": "道の駅"}], "return_spots": []}
    module.enrich_course(course, 35.0, 139.0, ctx, use_gmaps=False)

    assert "dest_lat" in course  # 目的地ジオコーディングだけは無条件で行う
    assert course["outbound_spots"] == [{"name": "A", "type": "道の駅"}]  # 以降はAI原文のまま


# ── stats_handler（利用統計集計バッチ） ────────────────────────────────

def _mock_metric_data(module, points):
    """[(datetime, value), ...] からGetMetricDataのレスポンス形状を組み立てる。"""
    module.cloudwatch.get_metric_data.return_value = {
        "MetricDataResults": [
            {
                "Id": "suggest_calls",
                "Timestamps": [p[0] for p in points],
                "Values": [p[1] for p in points],
            }
        ]
    }


def test_stats_handler_zero_fills_days_without_invocations(module):
    """CloudWatchはデータがない日はDatapointを返さないため、間引かず0件として埋めること。
    間引くとグラフのx軸間隔が実際のカレンダー日とずれ、利用頻度が実態より高く見えてしまう。
    日付はJSTの暦日で判定すること（UTC日境界のままだと深夜0〜9時JSTの呼び出しが
    前日扱いになりグラフの日付がずれるバグが過去にあった）。"""
    today_jst = module.datetime.now(module.JST).replace(hour=0, minute=0, second=0, microsecond=0)

    def jst_hour(days_ago, hour):
        return (today_jst - module.timedelta(days=days_ago)).replace(hour=hour).astimezone(module.timezone.utc)

    _mock_metric_data(module, [
        (jst_hour(1, 20), 5.0),
        (jst_hour(3, 2), 2.0),  # JST深夜2時 = 前日UTCだが集計はJST暦日で3日前扱い
    ])

    result = module.stats_handler({}, None)
    assert result["statusCode"] == 200

    _, kwargs = module.s3.put_object.call_args
    payload = json.loads(kwargs["Body"])

    assert payload["total"] == 7
    assert len(payload["history"]) == module.STATS_HISTORY_DAYS
    by_date = {d["date"]: d["count"] for d in payload["history"]}
    assert by_date[(today_jst - module.timedelta(days=1)).strftime("%Y-%m-%d")] == 5
    assert by_date[(today_jst - module.timedelta(days=3)).strftime("%Y-%m-%d")] == 2
    assert by_date[(today_jst - module.timedelta(days=2)).strftime("%Y-%m-%d")] == 0


def test_stats_handler_queries_custom_metric_only(module):
    """関数全体(AWS/Lambda Invocations)ではなく、/api/suggest成功時のみ発火する
    カスタムメトリクスだけを集計対象にすること（他ルート呼び出しの誤集計防止）。
    GetMetricStatisticsは90日×1時間=2,160点で1,440点上限を超えるため、
    上限がはるかに大きいGetMetricDataを使うこと（実機invokeで発覚したバグの回帰防止）。"""
    _mock_metric_data(module, [])
    module.stats_handler({}, None)

    _, kwargs = module.cloudwatch.get_metric_data.call_args
    query = kwargs["MetricDataQueries"][0]
    assert query["MetricStat"]["Metric"]["Namespace"] == module.STATS_METRIC_NAMESPACE
    assert query["MetricStat"]["Metric"]["MetricName"] == module.STATS_METRIC_NAME
    assert query["MetricStat"]["Period"] == 3600
    assert "Dimensions" not in query["MetricStat"]["Metric"]


def test_stats_handler_writes_to_configured_bucket_and_key(module):
    _mock_metric_data(module, [])
    module.stats_handler({}, None)

    args, kwargs = module.s3.put_object.call_args
    assert kwargs["Bucket"] == module.STATS_BUCKET
    assert kwargs["Key"] == module.STATS_KEY
    assert kwargs["ContentType"] == "application/json"
