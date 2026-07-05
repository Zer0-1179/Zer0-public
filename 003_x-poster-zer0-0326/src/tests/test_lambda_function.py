import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import lambda_function as lf


# ─────────────────────────────────────────────────────
# x_weighted_length / トリム安全弁
# ─────────────────────────────────────────────────────

def test_weighted_length_ascii_is_single_weight():
    assert lf.x_weighted_length("abc") == 3


def test_weighted_length_japanese_is_double_weight():
    """ひらがな・カタカナ・漢字はweighted 2として計算されること"""
    assert lf.x_weighted_length("あいう") == 6


def test_trim_body_keeps_short_text_untouched():
    text = "普通の短いツイート\n#AI活用"
    assert lf.trim_body_excluding_hashtags(text) == text


def test_trim_body_truncates_over_body_limit():
    body = "あ" * 200  # BODY_LIMIT(140)を超える全角文字列
    result = lf.trim_body_excluding_hashtags(f"{body}\n#AI活用")
    body_part = result.split("\n")[0]
    assert len(body_part) <= lf.BODY_LIMIT


def test_trim_body_safety_valve_enforces_weighted_280():
    """本文がBODY_LIMIT(140)以内でも、weighted lengthが280を超える場合は追加で削られること
    （2026-07-03発見: 全角文字はweighted 2のため140文字ちょうどでも280を超えうる）"""
    body = "あ" * 139  # 140以内だが weighted で278
    text = f"{body}\n#AI活用サミット2026特別編"  # 長いタグでweighted 280超を誘発
    result = lf.trim_body_excluding_hashtags(text)
    assert lf.x_weighted_length(result) <= lf.TWEET_MAX_LEN


def test_fit_weighted_budget_shared_by_url_reaction_path():
    """_fit_weighted_budgetがtrim_body_excluding_hashtagsとurl_reaction分岐の
    共通ヘルパーとして正しく機能すること（v2.7でのロジック重複解消の回帰防止）"""
    body = "あ" * 139
    tag  = "#AI活用サミット2026特別編"
    result = lf._fit_weighted_budget(body, tag)
    assert lf.x_weighted_length(result) <= lf.TWEET_MAX_LEN
    assert result.endswith(tag)


# ─────────────────────────────────────────────────────
# strip_model_hashtag_lines
# ─────────────────────────────────────────────────────

def test_strip_hashtag_lines_removes_trailing_single_tag():
    text = "本文だよ\n#AI活用"
    assert lf.strip_model_hashtag_lines(text) == "本文だよ"


def test_strip_hashtag_lines_removes_multi_tag_single_line():
    """1行に複数タグが並ぶケースも除去できること（re.sub単純置換では取りこぼしていた）"""
    text = "本文だよ\n#AI活用 #生成AI #ChatGPT"
    assert lf.strip_model_hashtag_lines(text) == "本文だよ"


def test_strip_hashtag_lines_keeps_body_only_text():
    text = "タグが一切無い本文"
    assert lf.strip_model_hashtag_lines(text) == text


# ─────────────────────────────────────────────────────
# pick_hashtag / pick_category
# ─────────────────────────────────────────────────────

def test_pick_hashtag_matches_keyword():
    assert lf.pick_hashtag("フリーランスとして働く") == "#副業"


def test_pick_hashtag_fallback_when_no_match():
    assert lf.pick_hashtag("特に何も関係ない文章です") == "#会社員あるある"


def test_pick_category_excludes_recent():
    recent = list(lf.CATEGORIES)[:lf.MAX_CATEGORY_HISTORY]
    assert lf.pick_category(recent) not in recent


def test_pick_category_falls_back_when_all_recent():
    result = lf.pick_category(list(lf.CATEGORIES))
    assert result in lf.CATEGORIES


# ─────────────────────────────────────────────────────
# extract_keywords
# ─────────────────────────────────────────────────────

def test_extract_keywords_returns_fallback_when_empty():
    assert lf.extract_keywords("特に固有名詞のない普通の文章") == ["会社員"]


def test_extract_keywords_finds_topic_words():
    keywords = lf.extract_keywords("議事録の作成が副業でも役立った")
    assert "議事録" in keywords
    assert "副業" in keywords


# ─────────────────────────────────────────────────────
# pick_recipe_task / pick_question_theme（v2.7で追加した重複回避）
# ─────────────────────────────────────────────────────

def test_pick_recipe_task_excludes_recent():
    recent = lf.RECIPE_TASKS[:lf.MAX_RECIPE_TASK_HISTORY]
    assert lf.pick_recipe_task(recent) not in recent


def test_pick_recipe_task_falls_back_when_all_recent():
    result = lf.pick_recipe_task(list(lf.RECIPE_TASKS))
    assert result in lf.RECIPE_TASKS


def test_max_recipe_task_history_smaller_than_total():
    """恒久ロックバグ（002で発見）の再発防止: 保持件数は総数より必ず小さいこと"""
    assert lf.MAX_RECIPE_TASK_HISTORY < len(lf.RECIPE_TASKS)


def test_pick_question_theme_excludes_recent():
    recent = lf.QUESTION_THEMES[:lf.MAX_QUESTION_THEME_HISTORY]
    assert lf.pick_question_theme(recent) not in recent


def test_max_question_theme_history_smaller_than_total():
    assert lf.MAX_QUESTION_THEME_HISTORY < len(lf.QUESTION_THEMES)


# ─────────────────────────────────────────────────────
# pick_relatable_trend / TREND_NG_WORDS（炎上防止フィルタ）
# ─────────────────────────────────────────────────────

def test_trend_ng_words_excluded_from_tier1():
    keywords = ["仕事速報 訃報", "転職ブーム"]
    result = lf.pick_relatable_trend(keywords)
    assert result == "転職ブーム"


def test_trend_ng_words_excluded_entirely_falls_back_to_none():
    keywords = ["有名人 死去", "議員 逮捕"]
    assert lf.pick_relatable_trend(keywords) is None


def test_trend_normal_tier1_keyword_still_matches():
    assert lf.pick_relatable_trend(["転職ブーム到来"]) == "転職ブーム到来"


def test_trend_generic_keyword_matches_via_tier3():
    """AIコンセプト撤廃により、Tier1/2に一致しない一般的な話題もTier3で拾えること"""
    assert lf.pick_relatable_trend(["謎の新現象"]) == "謎の新現象"


# ─────────────────────────────────────────────────────
# _score_tweet / pick_best_tweet（2026-07-05追加: バズ狙いの自己採点パイプライン）
# ─────────────────────────────────────────────────────

def test_score_tweet_penalizes_hedge_ending():
    hedge   = "在宅の方が楽な気がする"
    assert lf._score_tweet(hedge) < lf._score_tweet("在宅の方が楽だと思ってる")


def test_score_tweet_rewards_numbers():
    with_num    = "残業月60時間でも給料変わらん"
    without_num = "残業しても給料変わらん"
    assert lf._score_tweet(with_num) > lf._score_tweet(without_num)


def test_score_tweet_penalizes_empty_text():
    assert lf._score_tweet("") < 0
    assert lf._score_tweet("#タグだけ") < 0


def test_pick_best_tweet_selects_highest_score():
    candidates = [
        "在宅の方が楽な気がする",           # ヘッジ終わり・数字なし
        "残業60時間でも給料変わらんと思ってる",  # 断定・数字あり
    ]
    assert lf.pick_best_tweet(candidates) == candidates[1]


def test_pick_best_tweet_handles_single_candidate():
    assert lf.pick_best_tweet(["これだけしかない"]) == "これだけしかない"


# ─────────────────────────────────────────────────────
# リプライ営業（2026-07-05追加: ユーザー承認済みアカウントのみ対象）
# ─────────────────────────────────────────────────────

def test_default_reply_target_accounts_are_user_approved_list():
    """デフォルト対象は必ずユーザーが明示承認した10アカウントのみで、自動追加されないこと
    （diamond_online/PRESIDENT_Onlineは誤ったハンドルと判明しdol_editors/PRE_ONLINEに訂正済み）"""
    assert set(lf.DEFAULT_REPLY_TARGET_ACCOUNTS) == {
        "nikkei", "toyokeizai", "dol_editors", "PRE_ONLINE",
        "itmedia_news", "itmedia",
        "livedoornews", "asahi", "sankei_news", "mainichi",
    }


def test_reply_target_history_limit_smaller_than_total():
    """恒久ロックバグ再発防止: 保持件数は対象アカウント総数より必ず小さいこと（対象数が変わっても成立）"""
    accounts = lf.DEFAULT_REPLY_TARGET_ACCOUNTS
    assert lf._reply_target_history_limit(accounts) < len(accounts)


def test_reply_target_history_limit_scales_with_small_account_list():
    """対象数を減らしても除外件数が対象数以上にならず、必ず1件以上候補が残ること"""
    assert lf._reply_target_history_limit(["a", "b"]) == 1


def test_pick_reply_target_excludes_recent():
    accounts = lf.DEFAULT_REPLY_TARGET_ACCOUNTS
    limit = lf._reply_target_history_limit(accounts)
    recent = accounts[:limit]
    assert lf.pick_reply_target(recent, accounts) not in recent


def test_is_sensitive_for_reply_detects_ng_words():
    assert lf._is_sensitive_for_reply("〇〇容疑者を逮捕") is True
    assert lf._is_sensitive_for_reply("今期の決算は増収増益でした") is False


def test_pick_reply_candidate_tweet_skips_replied_and_sensitive():
    tweets = [
        {"id": "1", "text": "議員が逮捕された件について"},   # センシティブ
        {"id": "2", "text": "返信済みのツイート"},           # 返信済み
        {"id": "3", "text": "今期の決算について発表しました"},  # 選ばれるべき
    ]
    chosen = lf.pick_reply_candidate_tweet(tweets, replied_ids=["2"])
    assert chosen["id"] == "3"


def test_pick_reply_candidate_tweet_returns_none_when_all_unsuitable():
    tweets = [{"id": "1", "text": "地震速報が入りました"}]
    assert lf.pick_reply_candidate_tweet(tweets, replied_ids=[]) is None
