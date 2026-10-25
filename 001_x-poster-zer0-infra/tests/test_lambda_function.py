from datetime import datetime, timedelta, timezone

import lambda_function as lf


# ── x_weighted_length ──────────────────────────────────────────────
def test_weighted_length_ascii_is_plain_len():
    assert lf.x_weighted_length("hello world") == len("hello world")


def test_weighted_length_japanese_is_doubled():
    text = "こんにちは"
    assert lf.x_weighted_length(text) == len(text) * 2


def test_weighted_length_mixed():
    # "AWS" (weight 1 each) + "です" (weight 2 each)
    assert lf.x_weighted_length("AWSです") == 3 + 2 * 2


# ── clamp_tweet ─────────────────────────────────────────────────────
def test_clamp_tweet_under_limit_unchanged():
    text = "短い文章。"
    assert lf.clamp_tweet(text, max_len=280) == text


def test_clamp_tweet_cuts_at_sentence_boundary():
    text = "これは最初の文。" + "あ" * 200 + "これは最後の文。"
    clamped = lf.clamp_tweet(text, max_len=30)
    assert lf.x_weighted_length(clamped) <= 30
    assert clamped.endswith("。")


def test_clamp_tweet_no_boundary_appends_ellipsis_within_budget():
    # 句読点が無い長文。省略記号を付けても max_len を超えないことを確認する
    # （v2.1で修正した「省略記号の加重分を差し引かず超過していた」バグの回帰テスト）
    text = "あ" * 300
    clamped = lf.clamp_tweet(text, max_len=50)
    assert lf.x_weighted_length(clamped) <= 50
    assert clamped.endswith("…")


def test_clamp_tweet_exact_boundary_not_truncated():
    text = "あ" * 10  # weighted length = 20
    assert lf.clamp_tweet(text, max_len=20) == text


# ── pick_post_type ──────────────────────────────────────────────────
def test_pick_post_type_prefers_unused():
    types = ["a", "b", "c"]
    used = ["a", "a", "a"]
    for _ in range(20):
        picked = lf.pick_post_type(types, used)
        assert picked in ("b", "c")


def test_pick_post_type_falls_back_to_oldest_when_all_recent():
    types = ["a", "b"]
    used = ["b", "a"]  # 直近使用済み。古い順なので b が先
    assert lf.pick_post_type(types, used) == "b"


def test_pick_post_type_picks_least_recently_used():
    # 先頭の "a" は末尾でも使われているため、最後の使用が最も古い "b" を選ぶ
    assert lf.pick_post_type(["a", "b", "c", "d"], ["a", "b", "c", "d", "c", "a"]) == "b"


def test_pick_post_type_rotates_evenly_from_legacy_history():
    # 本番の凍結履歴（旧タイプ名）から始めて、4回ごとに全タイプが1回ずつ出て連続しないこと
    types = lf.SLOTS["evening"]["types"]
    used = ["news_intro", "classmethod_reaction", "aws_failure", "aws_failure", "news_comparison", "thread_tips"]
    picked = []
    for _ in range(12):
        t = lf.pick_post_type(types, used)
        picked.append(t)
        used = (used + [t])[-lf.MAX_USED_TYPES:]
    for i in range(0, 12, 4):
        assert sorted(picked[i:i + 4]) == sorted(types)
    assert all(a != b for a, b in zip(picked, picked[1:]))


# ── build_hashtags ──────────────────────────────────────────────────
def test_build_hashtags_returns_empty_when_random_below_threshold(monkeypatch):
    monkeypatch.setattr(lf.random, "random", lambda: 0.1)  # < 0.35 → タグなし
    article = {"title": "Amazon EC2 の新機能", "desc": ""}
    assert lf.build_hashtags(article) == ""


def test_build_hashtags_falls_back_to_aws_when_no_keyword_match(monkeypatch):
    monkeypatch.setattr(lf.random, "random", lambda: 0.9)  # >= 0.35 → タグ判定に進む
    article = {"title": "何か関係ないニュース", "desc": ""}
    assert lf.build_hashtags(article) == "#AWS"


def test_build_hashtags_ignores_partial_word_match(monkeypatch):
    monkeypatch.setattr(lf.random, "random", lambda: 0.9)
    article = {"title": "AgentCore Runtime が WebSocket をサポート", "desc": ""}
    assert lf.build_hashtags(article) == "#AWS"


def test_build_hashtags_matches_keyword(monkeypatch):
    monkeypatch.setattr(lf.random, "random", lambda: 0.9)
    monkeypatch.setattr(lf.random, "choice", lambda seq: seq[0])
    article = {"title": "Amazon S3 のアップデート", "desc": ""}
    assert lf.build_hashtags(article) == "#S3"


# ── is_too_old ────────────────────────────────────────────────────────
def test_is_too_old_true_for_old_article():
    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert lf.is_too_old({"pub_date": old_date}) is True


def test_is_too_old_false_for_recent_article():
    recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert lf.is_too_old({"pub_date": recent_date}) is False


def test_is_too_old_false_when_missing():
    assert lf.is_too_old({}) is False


def test_is_too_old_false_when_unparseable():
    assert lf.is_too_old({"pub_date": "not-a-date"}) is False


# ── extract_topic_keywords / is_topic_duplicate ────────────────────────
def test_extract_topic_keywords_matches_infra_services():
    keywords = lf.extract_topic_keywords("Amazon S3 と Amazon EC2 の連携")
    assert "S3" in keywords
    assert "EC2" in keywords


def test_extract_topic_keywords_requires_word_boundary():
    assert lf.extract_topic_keywords("OpenSearch Dashboards の assessment 機能") == []


def test_extract_topic_keywords_matches_full_load_balancer_name():
    assert "LOAD BALANCER" in lf.extract_topic_keywords("Application Load Balancer がヘッダー変換をサポート")


def test_extract_topic_keywords_matches_container_and_serverless():
    keywords = lf.extract_topic_keywords("Amazon ECS が LiveTaskCount を追加、AWS Lambda の再帰ループ検出が EventBridge に対応")
    assert {"ECS", "LAMBDA", "EVENTBRIDGE"} <= set(keywords)


def test_extract_topic_keywords_ignores_non_infra_services():
    assert lf.extract_topic_keywords("Amazon Polly に新しい音声が追加") == []


def test_is_topic_duplicate_true_on_overlap():
    article = {"title": "Amazon S3 の新機能"}
    assert lf.is_topic_duplicate(article, used_keywords=["S3"]) is True


def test_is_topic_duplicate_false_without_overlap():
    article = {"title": "Amazon S3 の新機能"}
    assert lf.is_topic_duplicate(article, used_keywords=["EC2"]) is False


# ── is_service_in_cooldown ────────────────────────────────────────────
def test_is_service_in_cooldown_true_within_window():
    today = datetime.now(lf.JST).date().isoformat()
    article = {"title": "Amazon S3 の話"}
    assert lf.is_service_in_cooldown(article, {"S3": today}) is True


def test_is_service_in_cooldown_false_after_window():
    old = (datetime.now(lf.JST).date() - timedelta(days=lf.SERVICE_COOLDOWN_DAYS + 1)).isoformat()
    article = {"title": "Amazon S3 の話"}
    assert lf.is_service_in_cooldown(article, {"S3": old}) is False


# ── pick_infra_article ─────────────────────────────────────────────────
def test_pick_infra_article_raises_on_empty():
    try:
        lf.pick_infra_article([])
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_pick_infra_article_prefers_higher_keyword_score():
    articles = [
        {"source": "aws_news", "title": "Amazon EC2 の新機能", "desc": ""},
        {"source": "aws_news", "title": "Amazon EC2 と Amazon EBS の統合", "desc": ""},
    ]
    picked = lf.pick_infra_article(articles)
    assert "EBS" in picked["title"]


def test_pick_infra_article_skips_non_infra():
    articles = [
        {"source": "aws_news", "title": "Amazon Bedrock で構造化出力が利用可能に", "desc": ""},
        {"source": "aws_news", "title": "AWS CloudFormation がロールバック操作を簡素化", "desc": ""},
    ]
    assert "CloudFormation" in lf.pick_infra_article(articles)["title"]


def test_pick_infra_article_raises_when_no_infra():
    articles = [{"source": "aws_news", "title": "Amazon Polly の新しい音声", "desc": ""}]
    try:
        lf.pick_infra_article(articles)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_pick_infra_article_skips_other_region_expansion():
    articles = [
        {"source": "aws_news", "title": "Amazon S3 サーバーアクセスログが 5 つの追加リージョンで利用可能に", "desc": "Amazon S3 Amazon S3"},
        {"source": "aws_news", "title": "Amazon CloudWatch アラームがタグをサポート", "desc": ""},
    ]
    assert "CloudWatch" in lf.pick_infra_article(articles)["title"]


# ── is_noise_article ───────────────────────────────────────────────────
def test_is_noise_article_true_for_govcloud():
    assert lf.is_noise_article({"title": "Amazon Cognito が GovCloud (US) リージョンに拡張"}) is True


def test_is_noise_article_false_when_tokyo_included():
    assert lf.is_noise_article({"title": "Amazon EC2 T8i が東京リージョンで利用可能に"}) is False


def test_is_noise_article_false_for_feature_update():
    assert lf.is_noise_article({"title": "AWS Transit Gateway が 1:1 NAT をサポート"}) is False


def test_is_noise_article_true_for_parenthesized_region():
    assert lf.is_noise_article({"title": "Amazon EC2 T8i インスタンスが南米 (サンパウロ) で利用可能に"}) is True


def test_is_noise_article_true_for_region_expansion_wording():
    assert lf.is_noise_article({"title": "Amazon EC2 R8gd インスタンスを利用可能なリージョンが拡大"}) is True


def test_is_noise_article_false_for_non_region_parentheses():
    assert lf.is_noise_article({"title": "Amazon EC2 Auto Scaling (ASG) でウォームプールをサポート"}) is False


def test_is_noise_article_false_for_generic_expansion_including_tokyo():
    article = {"title": "Amazon CloudWatch Omni がいくつかの AWS リージョンで新たに提供開始",
               "body": "アジアパシフィック (東京) などで利用できるようになりました"}
    assert lf.is_noise_article(article) is False


def test_is_noise_article_true_for_generic_expansion_without_tokyo():
    article = {"title": "Amazon S3 Metadata が 6 つの AWS リージョンで新たに利用可能に",
               "body": "欧州 (ミラノ) などで利用できるようになりました"}
    assert lf.is_noise_article(article) is True


def test_is_noise_article_service_noise_wins_over_tokyo_exemption():
    article = {"title": "AWS Transform が Aurora PostgreSQL のクロスリージョンデプロイをさらに 7 つのリージョンでサポート",
               "body": "アジアパシフィック (東京) を含む"}
    assert lf.is_noise_article(article) is True


def test_is_noise_article_false_for_cross_region_feature():
    assert lf.is_noise_article({"title": "Amazon Aurora がクロスリージョンのスナップショットコピーを高速化"}) is False


def test_infra_score_ignores_desc_only_match():
    assert lf.infra_score({"title": "Amazon Polly の新機能", "desc": "Amazon VPC で動作"}) == 0


def test_is_noise_article_true_for_healthomics_even_with_health_keyword():
    assert lf.is_noise_article({"title": "AWS HealthOmics が共有 VPC のサポートを開始"}) is True


# ── fit_history ────────────────────────────────────────────────────────
def _big_history():
    return {
        "used_urls": [f"https://aws.amazon.com/jp/about-aws/whats-new/2026/10/item-{i:03d}/" for i in range(28)],
        "used_types": ["infra_update", "ops_benefit", "ops_caution", "thread_tips"],
        "used_keywords": ["EC2"] * 40,
        "used_services": {"EC2": "2026-10-22"},
        "post_log": [{"date": "2026-10-22", "post_type": "infra_update", "tweet_id": "2113223952919310669"}] * 20,
        "last_updated": "2026-10-22T20:00:30.925744+09:00",
    }


def test_fit_history_shrinks_under_limit():
    import json
    h = lf.fit_history(_big_history(), max_bytes=2000)
    assert len(json.dumps(h, ensure_ascii=False).encode("utf-8")) <= 2000
    assert h["used_types"] == ["infra_update", "ops_benefit", "ops_caution", "thread_tips"]


def test_fit_history_drops_urls_before_post_log():
    import json
    h = _big_history()
    limit = len(json.dumps(h, ensure_ascii=False).encode("utf-8")) - 100
    lf.fit_history(h, max_bytes=limit)
    assert len(h["used_urls"]) < 28
    assert len(h["post_log"]) == 20


def test_fit_history_keeps_minimums():
    h = lf.fit_history(_big_history(), max_bytes=1200)
    assert len(h["used_urls"]) >= 6
    assert len(h["post_log"]) >= 5
    assert h["used_urls"][-1].endswith("item-027/")


def test_fit_history_handles_none_lists():
    h = lf.fit_history({"used_urls": None, "used_types": [], "post_log": None})
    assert h["used_urls"] == [] and h["post_log"] == []


def test_fit_history_steady_state_keeps_post_log():
    # 実運用相当（実フィードの平均URL長≒100文字・キーワード12件・30日内のサービス12件・post_log20件）で
    # 上限内に収まり、post_logが削られないこと
    import json
    h = {
        "used_urls": ["https://aws.amazon.com/jp/about-aws/whats-new/2026/10/" + "x" * 45 + f"{i}/" for i in range(lf.MAX_USED_URLS)],
        "used_types": ["infra_update"] * lf.MAX_USED_TYPES,
        "used_keywords": ["CLOUDWATCH"] * lf.MAX_USED_KEYWORDS,
        "used_services": {f"SERVICE{i}": "2026-10-22" for i in range(12)},
        "post_log": [{"date": "2026-10-22", "post_type": "ops_caution", "tweet_id": "2113223952919310669"}] * lf.MAX_POST_LOG,
        "last_updated": "2026-10-22T20:00:30.925744+09:00",
    }
    before = json.dumps(h)
    lf.fit_history(h)
    assert json.dumps(h) == before


def test_fit_history_unchanged_when_small():
    h = {"used_urls": ["u"], "used_types": ["a"], "used_keywords": [], "post_log": []}
    assert lf.fit_history(dict(h)) == h


# ── html_to_text / fetch_article_text ──────────────────────────────────
def test_html_to_text_unescapes_entities():
    assert lf.html_to_text("<p>A&nbsp;&amp;&nbsp;B</p>") == "A & B"


class _Resp:
    def __init__(self, body):
        self.body = body.encode("utf-8")
    def read(self):
        return self.body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_fetch_article_text_prefers_article_tag(monkeypatch):
    page = "<nav>メニュー" + "x" * 3000 + "</nav><article><p>本文です</p></article>"
    monkeypatch.setattr(lf.urllib.request, "urlopen", lambda req, timeout: _Resp(page))
    assert lf.fetch_article_text("https://example.com") == "本文です"


def test_fetch_article_text_without_article_uses_whole_page(monkeypatch):
    monkeypatch.setattr(lf.urllib.request, "urlopen", lambda req, timeout: _Resp("<p>全体</p>"))
    assert lf.fetch_article_text("https://example.com") == "全体"
