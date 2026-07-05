"""X auto-post bot @Zer0_0326 — 普通の会社員のあるある系バズ狙いコンテンツをBedrockで生成（Mon/Thu 20:00, Sun 10:00 JST）。"""

import json, os, random, re, time, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
import hmac, hashlib, base64
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config

# ---- AWS クライアント ----
# ツイート生成は max_tokens=512 と小さいため read_timeout は短めでよい。
# 一過性のスロットリング・5xxで即失敗しないようリトライを設定（002と同じ方針）。
bedrock    = boto3.client(
    "bedrock-runtime", region_name="ap-northeast-1",
    config=Config(connect_timeout=10, read_timeout=30,
                  retries={"max_attempts": 3, "mode": "adaptive"}),
)
ssm_client = boto3.client("ssm",             region_name="ap-northeast-1")

# ---- 定数 ----
BEDROCK_MODEL_ID     = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
SSM_PREFIX           = os.environ.get("SSM_PREFIX", "/ai_bot")
DRY_RUN              = os.environ.get("DRY_RUN", "false").lower() == "true"
JST                  = timezone(timedelta(hours=9))

CATEGORIES           = ["recipe", "jissoku", "hikaku", "shippai", "fukugyo", "question"]
MAX_CATEGORY_HISTORY = 4   # 6カテゴリ中、直近4件を避けて選択
# RECIPE_TASKS（12件）と同値にすると、全消化後に除外リストが恒久的に「全お題」を
# 含んだまま固定化するバグ（002で2026-07-03に発見・修正済み）が再発するため、
# 総数より必ず小さい値にすること
MAX_RECIPE_TASK_HISTORY = 5
MAX_USED_URLS        = 28
URL_HISTORY_DAYS     = 90   # 使用済みURLの保持期間（日）
NO_HASHTAG_RATE      = 0.9  # 2026-07-05: Fable評価で「現在のXではハッシュタグはリーチを生まずBot感のシグナルになる」
                            # と指摘され0.35→0.9に引き上げ。原則タグなし・稀にタグありにする
URL_REACTION_RATE    = 0.5  # 月曜にurl_reactionを選ぶ確率（残りはローテーション）
URL_REACTION_LIMIT   = 100  # url_reaction本文の文字数上限（URLはリプライにぶら下げる）
BODY_LIMIT           = 140  # 通常カテゴリ本文の文字数上限（ハッシュタグ・URL除く）
TWEET_MAX_LEN        = 280  # X実際の投稿上限（weighted length）

# カテゴリ別ハッシュタグ（リストの場合は投稿ごとにランダム選択）
HASHTAGS = {
    "recipe":       ["#会社員あるある", "#仕事術", "#社会人"],
    "jissoku":      ["#会社員あるある", "#仕事術", "#暮らし"],
    "hikaku":       ["#会社員あるある", "#働き方"],
    "shippai":      ["#会社員あるある", "#仕事術", "#やらかし"],
    "fukugyo":      "#副業",
    "question":     ["#会社員あるある", "#働き方"],
    "trend":        "#会社員あるある",
    "url_reaction": "#会社員あるある",
}

# url_reaction 用ハッシュタグプール（文章に合うものをピック）
HASHTAG_POOL = [
    {"tag": "#会社員あるある", "keywords": ["会社員", "社会人", "サラリーマン", "同僚", "上司", "職場"]},
    {"tag": "#副業",          "keywords": ["副業", "収益", "案件", "フリーランス", "稼ぎ", "収入", "note"]},
    {"tag": "#時短",          "keywords": ["時短", "効率", "早く", "速く", "短縮", "削減", "節約"]},
    {"tag": "#仕事術",        "keywords": ["仕事", "業務", "作業", "タスク", "報告書", "プレゼン", "会議", "メール", "議事録"]},
    {"tag": "#お金の話",      "keywords": ["貯金", "投資", "節約", "家計", "給料", "ボーナス", "税金", "保険"]},
    {"tag": "#働き方",        "keywords": ["働き方", "リモート", "テレワーク", "定時", "残業", "ワークライフ"]},
    {"tag": "#転職",          "keywords": ["転職", "退職", "面接", "履歴書", "キャリア"]},
    {"tag": "#人間関係",      "keywords": ["人間関係", "同僚", "上司", "部下", "距離感", "苦手"]},
    {"tag": "#暮らし",        "keywords": ["暮らし", "生活", "習慣", "片付け", "家事"]},
    {"tag": "#雑談",          "keywords": ["雑談", "つぶやき", "モヤモヤ", "本音"]},
]

# 月曜のURL反応投稿用RSSフィード（AIコンセプト撤廃に伴いYahoo!ニュースの一般トピックに変更。
# 会社員が反応しやすい経済・国内・エンタメの3ジャンルで話題の幅を確保）
URL_REACTION_FEEDS = [
    {"url": "https://news.yahoo.co.jp/rss/topics/business.xml",      "source": "yahoo", "label": "Yahoo!ニュース"},
    {"url": "https://news.yahoo.co.jp/rss/topics/domestic.xml",      "source": "yahoo", "label": "Yahoo!ニュース"},
    {"url": "https://news.yahoo.co.jp/rss/topics/entertainment.xml", "source": "yahoo", "label": "Yahoo!ニュース"},
]

# url_reaction フィルタ用キーワード（会社員・キャリア・お金・生活まわりの関心事）
URL_REACTION_KEYWORDS = [
    "仕事", "会社", "職場", "転職", "副業", "働き方",
    "お金", "貯金", "人間関係", "上司", "同僚", "生活",
]

# Google Trendsキーワードの優先度別マッチリスト（会社員が反応しやすい話題を優先。
# 見つからなければTier3で任意のキーワードにフォールバックするため、AIに縛らず何でも拾える）
TIER1_KEYWORDS = [
    "仕事", "会社", "転職", "副業", "残業", "給料", "ボーナス",
    "働き方", "リモート", "出社", "上司", "職場",
]
TIER2_KEYWORDS = [
    "お金", "貯金", "投資", "節約", "税金", "保険", "住宅",
    "スキル", "学習", "資格", "ビジネス", "起業", "スタートアップ",
    "アプリ", "スマホ", "SNS", "動画", "ゲーム", "ショッピング",
]

# trendカテゴリの炎上防止用NGワード。訃報・事件・災害・政治等を会社員あるあるネタと
# 絡めて投稿すると不謹慎に見えアカウントの信頼を損なうため、Tier1〜3すべてから除外する。
TREND_NG_WORDS = [
    "死去", "訃報", "逝去", "追悼", "逮捕", "事故", "事件", "地震", "台風", "水害",
    "火災", "殺", "自殺", "戦争", "ミサイル", "紛争", "選挙", "議員", "内閣", "首相",
    "炎上", "不倫", "引退", "容疑", "被害", "噴火", "遭難", "訴訟", "賠償",
]

# キーワード抽出用のトピックリスト
TOPIC_WORDS = [
    "副業", "時短", "収益", "貯金", "投資", "節約", "税金",
    "議事録", "ツール", "作業", "仕事", "会社", "職場", "同僚", "上司",
    "業務", "SNS", "ブログ", "記事", "生産性", "時間", "案件",
    "残業", "転職", "給料", "ボーナス", "評価", "定時", "note",
]

# question 用のテーマ軸（木曜固定＋ローテーションで最頻出カテゴリのため、
# few-shot例とtemperatureだけでは数週間スパンで似た問いが再来しやすい対策）
QUESTION_THEMES = [
    "給料・ボーナスへの本音（妥当だと思う？不満？）",
    "転職を考えるタイミング（何がきっかけになる？）",
    "職場での本音の隠し方（言えてる？隠してる？）",
    "将来のキャリア不安（今の仕事このままで大丈夫？）",
    "頑張りの空回り（頑張った分、報われてる？）",
    "スキルの身につけ方（どう学んでる？）",
    "上司・同僚との温度差（周りと自分、ズレてない？）",
    "自分の仕事への自信（できてる、とできてる気がしてるだけ、の差）",
    "副業の始め方・きっかけ",
    "定時・働き方への複雑な気持ち",
]
MAX_QUESTION_THEME_HISTORY = 4   # QUESTION_THEMES（10件）より必ず小さい値にすること

# recipe / jissoku 用の業務・生活お題（投稿ごとにローテーション）
RECIPE_TASKS = [
    "気まずい誘いを角が立たないように断る",
    "催促・リマインドなど気まずいメールの言い回し",
    "値上げ・値引き交渉の切り出し方",
    "クレーム対応の最初の一言",
    "謝罪メール・謝罪の言い回し",
    "飲み会・誘いを早めに切り上げる理由づけ",
    "苦手な同僚・上司との距離の取り方",
    "家計簿・固定費の見直し方",
    "転職活動の最初の一歩",
    "部屋・デスク周りの片付けが続くコツ",
    "会議を早く終わらせる一言",
    "上司への相談・報告の切り出し方",
]

# ---- 全カテゴリ共通ルール ----
ABSOLUTE_RULES = """【絶対ルール】
- 140文字以内（ハッシュタグ・URL含まず）。上限まで書こうとせず短くてもいい
- ハッシュタグは指定したもの1個のみ（それ以外は付けない）
- 絵文字は最大1個
- 「〜です」「〜ます」禁止
- 「〜したら全部解決した」で終わる抽象的な感想は禁止
- 「きれいな教訓」でまとめない（ただし賛否が分かれる強い意見・断定で終わるのはOK）
- 「…」は1投稿に最大1回まで
- 「なんか」「ちょっと」「わりと」などのフィラーは1投稿に合計2回まで

【バズを狙う強い意見（2026-07-05追加・強化）】
- 「〜な気がする」「〜かもしれない」で逃げない。最後の一文は原則、断定で言い切る（ヘッジ表現で終わらせない）
- 賛否が分かれてもいい。反発されるくらい踏み込んだ方が伸びる。両論併記で毒を抜かない
- ただし特定の個人・企業への攻撃、差別的表現、誤情報の断定はしない（あくまで働き方・お金・人間関係についての私見の範囲）

【AIっぽい口調・厳禁】
- 綺麗な起承転結でオチがピタッと決まる構成
- 「複雑な気持ち」「なんか申し訳ない」などの感情まとめフレーズ
- 毎回同じ「状況→結果→一言」の3段パターン
- 均等な行の長さ・左右対称な対比表現
- 文全体がきれいに収束して終わる

【禁止パターン】
- 「〜するようになった」で終わる感想文
- 「生産性が上がる」「効率化できる」などビジネス書的な表現
- 綺麗すぎる名言調
- 絵文字の多用"""

STYLE_GUIDE = """【文体ルール】
キャラ：なんとか生きてる普通の会社員

【1行目が命】
スクロールを止める書き出しを必ず作る。以下のどれかで始める：
  ・告白型：「実は〜」「正直〜」「こっそり〜」「言えてなかったけど〜」
  ・対比型：「〜なのに〜」「〜したら〜だった」
  ・問いかけ型：「〜ってある？」「〜だけ？」「〜どうしてる？」
  ・数字型：「2時間かけてた〜を」「3回失敗して〜」
  ・挑発型：「〜はもう終わってる」「〜してない人、正直やばいと思ってる」「〜だと思ってる人、たぶんズレてる」

【語感】
語尾→「…」「〜」「笑」「かも」「気がする」「だけど」「かな」「っていう」
文中→「なんか」「ちょっと」「わりと」「けっこう」「なんとなく」「よくわかんないけど」
反応→「え、待って」「まじか」「あ、そういうことか」「うーん」
その他→独り言調・失敗談・試行錯誤・雑な数字（「もう2時間経ってた笑」等）

【1投稿1メッセージ（2026-07-05改訂）】
言いたいことを1つに絞り、余計な一文を入れない。情報密度を最大にする。
「垂れ流す」のは文の構成ではなく語尾・言い回しで出す（【語感】参照）。本筋をぼかす脱線・言い訳の連鎖は入れない。
毎回同じ構成にしない（バラバラな方がリアル）が、どの構成でも最後は1つの強いメッセージに収束させる。

【終わり方】
疑問・皮肉・断定の強い一言、のどれかで終わらせる。「きれいな教訓」としてまとめない。
最後の一文はヘッジ（「〜な気がする」「〜かもしれない」）で終わらせず、原則として言い切る。
読んだ人が「わかる」でも「いや違うだろ」でもいいので、反応せずにいられない終わり方を選ぶ。"""

# 投稿ごとに1つ抽選する文章フォーマット（毎回同じポエム調になるのを防ぐ）
FORMAT_STYLES = [
    "短い行を改行・空行で区切るスタイル（3〜6行）。ただし1文をぶつ切りにしすぎない",
    "改行を使わず、普通の文章2〜3文でつぶやく（句読点も普通に使う）",
    "改行1回まで・60文字以内の短いひとこと投稿",
    "1〜2文目は普通につながった文章で書き、最後だけ改行して一言ぼそっと付け足す",
]


def style_guide() -> str:
    """STYLE_GUIDEに今回の文章フォーマット指定を付けて返す。"""
    fmt = random.choice(FORMAT_STYLES)
    return (f"{STYLE_GUIDE}\n\n【今回の形式（必ずこの形式で書く）】\n{fmt}\n"
            "※ 上の良い例の改行の仕方はコピーせず、この形式指定を優先する")


# ─────────────────────────────────────────────────────
# SSM 履歴管理
# ─────────────────────────────────────────────────────

def load_history(category: str) -> list:
    """SSMからカテゴリ履歴を読み込む。7日以上古いエントリは除外する。"""
    param = f"{SSM_PREFIX}/history/{category}"
    try:
        val     = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        entries = json.loads(val)
        cutoff  = datetime.now(JST) - timedelta(days=7)
        return [e for e in entries if datetime.fromisoformat(e["posted_at"]) > cutoff]
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[History] 読み込みエラー ({category}): {e}")
        return []


def save_history(category: str, current: list, new_keywords: list):
    """SSMにカテゴリ履歴を保存する。7日以上古いエントリを自動削除。"""
    new_entry = {"keywords": new_keywords, "posted_at": datetime.now(JST).isoformat()}
    cutoff    = datetime.now(JST) - timedelta(days=7)
    updated   = [e for e in current if datetime.fromisoformat(e["posted_at"]) > cutoff]
    updated.append(new_entry)
    param = f"{SSM_PREFIX}/history/{category}"
    try:
        ssm_client.put_parameter(
            Name=param,
            Value=json.dumps(updated, ensure_ascii=False),
            Type="String",
            Overwrite=True,
        )
        print(f"[History] 保存完了 ({category}): {new_keywords}")
    except Exception as e:
        print(f"[History] 保存エラー ({category}): {e}")


def load_used_categories() -> list:
    """SSMからカテゴリ使用履歴を読み込む。"""
    param = f"{SSM_PREFIX}/history/used_categories"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        return json.loads(val)
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[History] カテゴリ履歴読み込みエラー: {e}")
        return []


def save_used_categories(used: list, new_category: str):
    """SSMにカテゴリ使用履歴を保存する。直近MAX_CATEGORY_HISTORY件を保持。"""
    updated = (used + [new_category])[-MAX_CATEGORY_HISTORY:]
    try:
        ssm_client.put_parameter(
            Name=f"{SSM_PREFIX}/history/used_categories",
            Value=json.dumps(updated),
            Type="String",
            Overwrite=True,
        )
        print(f"[History] カテゴリ履歴保存: {updated}")
    except Exception as e:
        print(f"[History] カテゴリ履歴保存エラー: {e}")


def load_recipe_task_history() -> list:
    """SSMからrecipe/jissoku共通のお題使用履歴を読み込む。"""
    param = f"{SSM_PREFIX}/history/recipe_tasks"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        return json.loads(val)
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[History] お題履歴読み込みエラー: {e}")
        return []


def save_recipe_task_history(used: list, new_task: str):
    """SSMにお題使用履歴を保存する。直近MAX_RECIPE_TASK_HISTORY件を保持。"""
    updated = (used + [new_task])[-MAX_RECIPE_TASK_HISTORY:]
    try:
        ssm_client.put_parameter(
            Name=f"{SSM_PREFIX}/history/recipe_tasks",
            Value=json.dumps(updated, ensure_ascii=False),
            Type="String",
            Overwrite=True,
        )
        print(f"[History] お題履歴保存: {updated}")
    except Exception as e:
        print(f"[History] お題履歴保存エラー: {e}")


def pick_recipe_task(used_tasks: list) -> str:
    """直近MAX_RECIPE_TASK_HISTORY件に含まれないお題からランダム選択。
    全お題が直近に含まれる場合は完全ランダム選択にフォールバックする。"""
    recent = used_tasks[-MAX_RECIPE_TASK_HISTORY:]
    unused = [t for t in RECIPE_TASKS if t not in recent]
    return random.choice(unused) if unused else random.choice(RECIPE_TASKS)


def load_question_theme_history() -> list:
    """SSMからquestionのテーマ使用履歴を読み込む。"""
    param = f"{SSM_PREFIX}/history/question_themes"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        return json.loads(val)
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[History] テーマ履歴読み込みエラー: {e}")
        return []


def save_question_theme_history(used: list, new_theme: str):
    """SSMにquestionのテーマ使用履歴を保存する。直近MAX_QUESTION_THEME_HISTORY件を保持。"""
    updated = (used + [new_theme])[-MAX_QUESTION_THEME_HISTORY:]
    try:
        ssm_client.put_parameter(
            Name=f"{SSM_PREFIX}/history/question_themes",
            Value=json.dumps(updated, ensure_ascii=False),
            Type="String",
            Overwrite=True,
        )
        print(f"[History] テーマ履歴保存: {updated}")
    except Exception as e:
        print(f"[History] テーマ履歴保存エラー: {e}")


def pick_question_theme(used_themes: list) -> str:
    """直近MAX_QUESTION_THEME_HISTORY件に含まれないテーマからランダム選択。
    全テーマが直近に含まれる場合は完全ランダム選択にフォールバックする。"""
    recent = used_themes[-MAX_QUESTION_THEME_HISTORY:]
    unused = [t for t in QUESTION_THEMES if t not in recent]
    return random.choice(unused) if unused else random.choice(QUESTION_THEMES)


def load_url_history() -> list:
    """SSMから使用済みURL履歴を読み込み、URL文字列のリストを返す。
    URL_HISTORY_DAYS日以上古いエントリは自動除外する。"""
    param = f"{SSM_PREFIX}/history/url_reaction_urls"
    try:
        val     = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        entries = json.loads(val)
        if not entries:
            return []
        # 旧形式（文字列リスト）との後方互換
        if isinstance(entries[0], str):
            return entries
        cutoff  = datetime.now(JST) - timedelta(days=URL_HISTORY_DAYS)
        active  = [e for e in entries if datetime.fromisoformat(e["posted_at"]) > cutoff]
        expired = len(entries) - len(active)
        if expired:
            print(f"[History] URL履歴: {expired}件の期限切れエントリを除外（{URL_HISTORY_DAYS}日超）")
        print(f"[History] URL履歴: 有効{len(active)}件")
        return [e["url"] for e in active]
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[History] URL履歴読み込みエラー: {e}")
        return []


def save_url_history(new_url: str):
    """SSMに使用済みURL履歴をタイムスタンプ付きで保存する。
    タイムスタンプを保つため、load_url_history が返す整形済みリストではなく
    SSMから生データを再取得してから追記する。
    MAX_USED_URLS件を超えた場合は古い方から削除する。"""
    param = f"{SSM_PREFIX}/history/url_reaction_urls"
    # タイムスタンプを保持するため、SSMから生データを再取得
    try:
        raw     = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        entries = json.loads(raw)
        if not entries:
            entries = []
        elif isinstance(entries[0], str):
            # 旧形式（文字列リスト）を新形式に一括変換
            entries = [{"url": u, "posted_at": datetime.now(JST).isoformat()} for u in entries]
    except ssm_client.exceptions.ParameterNotFound:
        entries = []
    except Exception as e:
        print(f"[History] URL履歴読み込みエラー: {e}")
        entries = []

    entries.append({"url": new_url, "posted_at": datetime.now(JST).isoformat()})
    entries = entries[-MAX_USED_URLS:]  # 古い方から削除
    try:
        ssm_client.put_parameter(
            Name=param,
            Value=json.dumps(entries, ensure_ascii=False),
            Type="String",
            Overwrite=True,
        )
        print(f"[History] URL履歴保存: {len(entries)}件（新規: {new_url[:60]}）")
    except Exception as e:
        print(f"[History] URL履歴保存エラー: {e}")


def pick_category(used_categories: list) -> str:
    """直近MAX_CATEGORY_HISTORY件に含まれないカテゴリからランダム選択。
    全カテゴリが直近に含まれる場合は最も古いものを選ぶ。"""
    recent = used_categories[-MAX_CATEGORY_HISTORY:]
    unused = [c for c in CATEGORIES if c not in recent]
    if unused:
        return random.choice(unused)
    for c in recent:
        if c in CATEGORIES:
            return c
    return random.choice(CATEGORIES)


def pick_category_hashtag(category: str) -> str:
    """カテゴリのハッシュタグを返す。リストの場合はランダム選択。"""
    val = HASHTAGS.get(category, "#会社員あるある")
    return random.choice(val) if isinstance(val, list) else val


def pick_hashtag(body: str) -> str:
    """本文・記事タイトルの内容に合わせてHASHTAG_POOLから最適なハッシュタグを選ぶ。
    スコアが同点の場合はランダム選択。マッチなしは '#会社員あるある' を返す。"""
    body_lower = body.lower()
    scores = {}
    for item in HASHTAG_POOL:
        score = sum(1 for kw in item["keywords"] if kw.lower() in body_lower)
        if score > 0:
            scores[item["tag"]] = score
    if not scores:
        return "#会社員あるある"
    max_score = max(scores.values())
    candidates = [tag for tag, s in scores.items() if s == max_score]
    return random.choice(candidates)


def extract_keywords(body_text: str) -> list:
    """本文（ハッシュタグ除く）からキーワードを3〜5個抽出する。Bedrock不使用。"""
    clean    = re.sub(r'#\S+', '', body_text).strip()
    katakana = re.findall(r'[ァ-ヶー]{2,}', clean)
    numbers  = re.findall(r'\d+[時間万円本個分%倍]', clean)
    matched  = [kw for kw in TOPIC_WORDS if kw in clean]
    all_kws  = list(dict.fromkeys(katakana + matched + numbers))
    return all_kws[:5] if len(all_kws) >= 3 else (all_kws or ["会社員"])


def _past_keywords_hint(history: list) -> str:
    """履歴から過去キーワードをプロンプト用テキストに変換する。"""
    all_kws = [kw for e in history for kw in e.get("keywords", [])]
    if not all_kws:
        return ""
    unique = list(dict.fromkeys(all_kws))
    return f"\n【過去7日間に使ったキーワード（繰り返し禁止）】\n{', '.join(unique[:20])}\n"


# ─────────────────────────────────────────────────────
# Google Trends RSS
# ─────────────────────────────────────────────────────

def fetch_google_trends_jp() -> list:
    """Google Trends RSS（日本）からトレンドキーワードを最大20件取得する。"""
    url = "https://trends.google.co.jp/trending/rss?geo=JP"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())
        return [
            item.findtext("title", "").strip()
            for item in root.findall(".//item")
            if item.findtext("title", "").strip()
        ][:20]
    except Exception as e:
        print(f"[Trends] 取得エラー: {e}")
        return []


def pick_relatable_trend(keywords: list) -> str | None:
    """トレンドキーワードを優先度順に1つ選ぶ（AIコンセプト撤廃により内容は問わない）。
    Tier1: 仕事・お金まわりの直球ワード、Tier2: 幅広い生活・ビジネス系、
    Tier3: 日本語の任意キーワードにフォールバックするため、実質どんな話題でも拾える。
    訃報・事件・災害・政治等のNGワードを含むキーワードは炎上防止のため事前に除外する。"""
    before = len(keywords)
    keywords = [kw for kw in keywords if not any(ng in kw for ng in TREND_NG_WORDS)]
    if len(keywords) != before:
        print(f"[Trends] NGワードにより{before - len(keywords)}件除外")

    tier1 = [kw for kw in keywords if any(t in kw for t in TIER1_KEYWORDS)]
    if tier1:
        print(f"[Trends] Tier1マッチ: {tier1}")
        return random.choice(tier1)

    tier2 = [kw for kw in keywords if any(t in kw for t in TIER2_KEYWORDS)]
    if tier2:
        print(f"[Trends] Tier2マッチ: {tier2}")
        return random.choice(tier2)

    tier3 = [kw for kw in keywords
             if re.search(r'[\u3040-\u30FF\u4E00-\u9FFF]{2,}', kw) and len(kw) <= 15]
    if tier3:
        print(f"[Trends] Tier3マッチ: {tier3}")
        return random.choice(tier3)

    return None


# ─────────────────────────────────────────────────────
# プロンプトビルダー
# ─────────────────────────────────────────────────────

def fetch_url_reaction_article(used_urls: list) -> dict | None:
    """URL_REACTION_FEEDSからニュース記事を取得し未使用のものを1件返す。
    未使用がなければused_urls無視でランダム選択。取得失敗時はNoneを返す。"""
    articles = []
    for feed in URL_REACTION_FEEDS:
        try:
            # 非ASCII文字を含むURLをパーセントエンコード
            encoded_url = urllib.parse.quote(feed["url"], safe=":/?=&%#+@")
            req = urllib.request.Request(encoded_url, headers={"User-Agent": "Mozilla/5.0"})
            # 6フィード直列取得のため timeout は短めに（Lambda Timeout=60秒との兼ね合い）
            with urllib.request.urlopen(req, timeout=5) as r:
                tree = ET.parse(r)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            # RSS形式
            for item in tree.findall(".//item")[:5]:
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                desc  = item.findtext("description", "").strip()[:300]
                if title and link:
                    articles.append({"source": feed["source"], "label": feed["label"],
                                     "title": title, "url": link, "desc": desc})
            # Atom形式（Qiita）
            for entry in tree.findall(".//{http://www.w3.org/2005/Atom}entry")[:5]:
                title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link  = ""
                for l in entry.findall("{http://www.w3.org/2005/Atom}link"):
                    if l.get("rel") in (None, "alternate"):
                        link = l.get("href", "")
                        break
                desc  = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")[:300]
                if title and link:
                    articles.append({"source": feed["source"], "label": feed["label"],
                                     "title": title, "url": link, "desc": desc})
        except Exception as e:
            print(f"[URL RSS] {feed['label']} error: {e}")

    if not articles:
        return None

    # 会社員の関心キーワードでスコアリング
    def score(a):
        text = (a["title"] + " " + a["desc"]).upper()
        return sum(1 for kw in URL_REACTION_KEYWORDS if kw.upper() in text)

    # 未使用URLを優先
    unused = [a for a in articles if a["url"] not in used_urls]
    pool   = unused if unused else articles
    # スコア上位から絞り込み
    scored = sorted(pool, key=score, reverse=True)
    top    = [a for a in scored if score(a) >= 1] or scored
    chosen = random.choice(top[:5])
    print(f"[URL RSS] 取得:{len(articles)}件 未使用:{len(unused)}件 選択:「{chosen['title'][:50]}」")
    return chosen


def build_url_reaction_prompt(article: dict, history: list) -> str:
    avoid = _past_keywords_hint(history)
    title = article["title"]
    desc  = article.get("desc", "")
    return f"""普通の会社員が、X（旧Twitter）にニュース記事を読んだ感想・反応を投稿します。
キャラ：なんとか生きてる普通の会社員
ターゲット：同じニュースが気になってる人。「わかる」「そう思う」「言われてみれば」と思わせる内容
{avoid}
【今日の記事】
タイトル：{title}
概要：{desc}

【良い例（記事への率直な反応・意見を1つ＋正直な感想）】
---
このニュース、一番の引っかかりはここだった
「〇〇が当たり前になってきてる」ってやつ

知ってたつもりだったけど
改めて言われると地味に来るものがある
---
---
読む前「またこの話か」
読んだ後「これは正直それな」

タイトルで損してるタイプの記事だと思う
中身は思ったより刺さった
---
---
これ読んで自分の状況を見返したら
「あるある」って書かれてるやつ、ほぼ全部当てはまってた

自覚しただけでも読んだ価値あった
---
---
半分くらいは知ってる内容だったけど
後半のコメント欄だけでも読む価値あった

こういうのは知識の差じゃなくて
「自分ごとにできるか」の差なんだよな
---
---
正直この意見には賛同できない部分もあるけど
言いたいことは分かる気がする

叩かれそうだけど自分もこっち側だと思う
---

【今回の形式（必ずこの形式で書く）】
{random.choice(FORMAT_STYLES)}
※ 上の良い例の改行の仕方はコピーせず、この形式指定を優先する

【ルール】
- 記事から得た気づき・意見を1つだけ挙げる。ただし記事タイトル・概要に実際に書かれている範囲の表現にとどめ、書かれていないことを記事の内容として書かない
- 記事の要約・紹介はしない（自分の意見・気づきを書く）
- 賛否が分かれてもいいので率直な意見を断定で書く（両論併記でヘッジしない。誹謗中傷・断定的な誤情報は書かない）
- 1行目で読者を止めるフックを作る
- 「です・ます」禁止
- 100文字以内でコンパクトに
- 絵文字は最大1個
- 「…」は1投稿に最大1回まで
- 綺麗に締めない・余白を残す
- URLは含めない（自動で付加される）

ツイート本文のみ出力。"""

def build_recipe_prompt(history: list, hashtag: str, task: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""なんとか生きてる普通の会社員が、X（旧Twitter）に「コピペで使える言い回し・テンプレのレシピ」を投稿します。
キャラ：要領は良くないが、生き延びるための言い回しは具体的
ターゲット：似た場面で困っている会社員。読んだ人が「保存しよ」と思うのがゴール
{avoid}
【今回のお題（このシーンで使えるレシピを書く）】
{task}

【良い例（テンプレ・言い回しは「」で示す。構成はバラバラでOK）】
---
気まずい誘いの断り方、これで乗り切ってる

「その日ちょっと予定あって〜また誘って！」

理由を細かく言わないのがコツ
言い訳を盛ると逆に怪しまれる
{hashtag}
---
---
値上げ交渉、苦手すぎてたどり着いたやつ

「他社さんの見積もりも見てるんですが、〇〇円だと即決できます」

即決をちらつかせるのがコツ
これ使うようになってから8割くらい通る
{hashtag}
---
---
クレーム対応、最初の一言だけ決めてる

「ご不便おかけしてすみません、状況教えてもらえますか」

謝罪と質問を同じ文に入れると
相手のトーンが下がる
{hashtag}
---
---
週報、メモ書き3行からこれで作ってる

「事実だけ淡々と、頑張ってる感は出しすぎない」

このスタンスにしてから
むしろ上司の反応が良くなった笑
{hashtag}
---

【ルール】
- お題のシーンに合った、実際にコピペで使える言い回し・テンプレを「」で1つ入れる（1行・汎用的に・誰でも使える内容）
- なぜそれが効くのか・気づいたきっかけ・実際どうなったかを一言そえる
- 効果は「7〜9割」「ほぼ毎回」レベルの強い数字で言い切る（誇張しすぎない範囲で、弱く見積もらない）
- テンプレの中身が今回のお題とズレないこと

【文体】
- 上の例のような常体・口語。「です・ます」禁止
- 完璧にまとめない。一言の余韻や本音で終わる

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_fukugyo_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""副業もしている普通の会社員がX（旧Twitter）に投稿する「副業の現実・やり方・本音」のつぶやきを1件生成してください。
ターゲット：副業に興味ある会社員。「現実が知れた」「自分もやってみようかな」と思わせる内容
{avoid}
【良い例】
---
副業のリサーチ、下調べのやり方を変えたら
1案件2時間→40分

単価は同じだから実質時給が上がった
これに気づくのに半年かかった
#副業
---
---
クラウドソーシングで初案件とれた
金額は3,000円だったけど

本業の給料が振り込まれた日より
なんか嬉しかった笑
#副業
---
---
本業終わってから副業しようとしたら
体力が全然残ってない

作業を朝に前倒ししてから
なんとか続けられてる
これがなかったら続いてなかった
#副業
---
---
副業の納品前、必ず一晩寝かせてから見返すようにしてる

これやるようになってから修正依頼が減った
急いで出すのが一番損だった
#副業
---
---
副業の確定申告
去年はパニックだったのに
今年は早めに準備したらなんとかなった

毎年怖いのは変わらないけど
#副業
---
---
副業で月5万稼いでる人の投稿見るたびに
自分は本業でいいやってなる

無理に手広げなくてもいいと思ってる
反対意見も分かるけど
#副業
---

【ルール】
- 数字（金額・時間・件数）か具体的なやり方を、どれか1つは入れる（盛らない・現実的に）
- 夢を売らない。「楽して稼げる」系の表現は禁止
- 良いことだけで終わらせず、現実・本音を残す
- たまには「副業なんてやらなくていい」のような逆張りの本音もOK

{style_guide()}

{ABSOLUTE_RULES}

末尾に「#副業」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_jissoku_prompt(history: list, hashtag: str, task: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""普通の会社員が、X（旧Twitter）に「やり方を変えたらどれだけ変わったかのbefore/after実録」を投稿します。
キャラ：なんとか生きてる普通の会社員
ターゲット：似た悩みを持つ会社員。「そんなに変わるのか、自分もやってみよう」と思わせる
{avoid}
【今回のお題（このシーンの実録を書く）】
{task}

【良い例】
---
週報にかけてた時間、測ったら毎週50分だった

今はメモ3行から書くようにして5分
浮いた45分で何してるかというと…別の仕事なんだけど笑
それでも気持ちが全然違う
{hashtag}
---
---
会議の議事録、前は翌日の午前までかかってた
今は会議終了10分後に共有してる

「仕事早いね」って言われるようになったけど
中身は前とそんなに変わってない
{hashtag}
---
---
資料の構成決め
1人でうんうん唸ってた2時間が
先に骨組みだけ決める方式にして20分になった

質が上がったかは正直わからない
でも「始められない」がなくなったのがでかい
{hashtag}
---
---
リサーチ仕事、丸1日かかってたのが半日になった

情報源を3つに絞ってから深掘りする方式にした
それでも半分
絞り込むスキルの方が調べるスキルより大事になってきてる
{hashtag}
---

【ルール】
- 具体的な時間・回数などの数字をbefore/afterで1組入れる（盛らない・現実的に）
- どうやったかを一言だけ入れる（「メモ3行から書く」など）
- 良いことだけで終わらせない。本音・引っかかり・余韻を残す
- お題からズレないこと

【文体】
- 常体・口語。「です・ます」禁止
- 綺麗にまとめない

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_question_prompt(history: list, hashtag: str, theme: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""普通の会社員がX（旧Twitter）に投稿する「問いかけ・議論を呼ぶ質問系」のつぶやきを1件生成してください。
ターゲット：仕事・お金・人間関係に興味ある会社員・思わず返信したくなる・自分の答えを言いたくなる問いかけ
{avoid}
【今回のテーマ（この軸で問いかけを作る）】
{theme}

【良い例】
---
頑張って早く仕事終わらせた分
新しい仕事が増えただけだった

これって評価される？
同じ現象の人いる？
{hashtag}
---
---
ボーナス、みんな額面で満足してる？

なんとなく妥当な気がしてるけど
正直基準がよくわかってない笑
{hashtag}
---
---
給料の話
職場の人とできる環境？

自分は言いづらくて
誰にも話したことない笑
{hashtag}
---
---
今の仕事、向いてる自信ある？

「向いてる」と「慣れただけ」って
全然別物な気がしてる
{hashtag}
---
---
毎月いくら貯金してる？

無理してでも貯める派と
使う派に分かれる気がしてて
{hashtag}
---
---
副業ってどこから始めた？

始めたいけど何からやればいいか
わからないままでいる人
けっこういそう
#副業
---
---
今の職場で一番「これはよかった」
って思える待遇や制度ってある？

自分は有給が取りやすいことくらいだけど
他にどんなのがあるか気になってる
{hashtag}
---
---
仕事できる人って
何が違うのかずっと観察してる

結論、要領がいいだけだと思ってる
実力とは別の話
{hashtag}
---
---
副業と本業
どっちがやりがいある？

副業始めてから
本業のモチベの保ち方がわからなくなってきた
#副業
---
---
定時に帰れてる？

「定時で帰るの申し訳ない」
って思ってた時期がある
今思うとなんでだったんだろ
---
---
正直、転職エージェントの言うこと
半分くらい話盛ってると思ってる

それでも使う価値はあると思ってるけど
どう思う？
{hashtag}
---

{style_guide()}

{ABSOLUTE_RULES}

ハッシュタグは「{hashtag}」「#副業」のどちらか内容に合う方を1つ、または付けない。URLは含めない。ツイート本文のみ出力。"""


def build_trend_prompt(trend_kw: str, history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""「{trend_kw}」というトレンドに対する、会社員としての率直な意見・持論をX（旧Twitter）用に1件生成してください。
キャラ：なんとか生きてる普通の会社員
ターゲット：同じトレンドを見ている人・「それな」「いや違うだろ」のどちらかの反応をせずにいられない内容
{avoid}
【良い例（{trend_kw}の部分は実際のキーワードに変わる）】
---
「{trend_kw}」を見て思ったんだけど

これで得するのは結局、時間がある人だけだと思ってる
仕事してる身からするとその感覚にはついていけない
---
---
「{trend_kw}」に賛否あるみたいだけど
自分は完全に否定派

会社員の生活には正直関係ない話だと思ってる
---
---
「{trend_kw}」がトレンド入りしてるけど

これ数年後には誰も覚えてないやつだと思ってる
毎回こういうのに反応してたら疲れる
---
---
「{trend_kw}」の件、みんな盛り上がってるけど

自分は正直どうでもいいと思ってる派
仕事の方がよっぽど大事な話が山積みなんだよな
---
---
「{trend_kw}」を仕事の合間に知って

これが話題になる世の中で
自分たちの働き方だけ変わってない気がしてる
---

【ルール】
- トレンドに対して賛成・反対・どうでもいい、のいずれかの立場を明確に取る（両論併記で終わらせない）
- 「知らなかった」「初めて知った」型の反応は避ける（意見・持論を書く）
- 会社員の仕事・お金・生活の視点から一言つなげる

{style_guide()}

{ABSOLUTE_RULES}

末尾に「#会社員あるある」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_hikaku_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""普通の会社員が、X（旧Twitter）に「働き方・お金・生活の比較と自分なりの結論」を投稿します。
キャラ：なんとか生きてる普通の会社員
ターゲット：同じことで迷っている会社員。「自分はこうしてる」と返信したくなる内容
{avoid}
【良い例】
---
在宅勤務と出社
どっちが生産性高いか問題

自分は在宅の方が集中できるけど
評価されるのは出社の日ばかり

正直者が損する仕組みになってると思ってる
{hashtag}
---
---
貯金派と投資派いるけど
自分は完全に投資派

元本割れが怖くて始められなかった頃より
少額でも動かす方が結局増えてる

貯金だけしてる人、正直もったいないと思ってる
{hashtag}
---
---
転職するか今の会社で我慢するか問題

自分は我慢を選んだけど
給料は上がらないままで3年経った

我慢が正解だったとは正直思ってない
{hashtag}
---
---
飲み会、行く派と行かない派いるけど
自分は完全に行かない派

人間関係で損してる自覚はあるけど
それでも行かない方が得だと思ってる
{hashtag}
---

【ルール】
- 比較対象を2つ明確に出して、自分の結論を断定で言い切る（「人によるけど」で逃げない）
- 反発されてもいい。読んだ人が「自分はこう」と返信したくなる余地を残す
- 架空の数字・誇張しすぎた比較は作らない（現実的な範囲で）

【文体】
- 常体・口語。「です・ます」禁止

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_shippai_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""普通の会社員が、X（旧Twitter）に「仕事・お金・人間関係のやらかし話」を投稿します。
キャラ：なんとか生きてる普通の会社員
ターゲット：似た失敗をしたことがある会社員。「あるある」「それは恥ずかしい」と思わせる、恥の解像度が高い内容
{avoid}
【良い例（「きれいな教訓」で締めず、具体的な恥のディテールで終わるものも混ぜる）】
---
確認してない数字をそのまま会議資料に入れて
「出典は？」って聞かれて時が止まった

隣の席の後輩が資料の裏まで持ってて
それを見た瞬間さらに顔が赤くなった
{hashtag}
---
---
謝罪メール、丁寧に書きすぎて
逆に嫌味っぽく伝わってたことがある

「誠に遺憾ながら」とか普段使わないのに
なんであの時だけ背伸びしたのか自分でもわからない
{hashtag}
---
---
社内資料を個人チャットにそのまま転送しそうになって手が止まった
固有名詞めっちゃ入ってるやつ

送信ボタンの手前で気づいた自分を
褒めていいのか怖がっていいのかわからない
{hashtag}
---
---
噂話を信じて上司に確認なしで報告したら間違ってた

「聞いた話ですが」を最初につけただけで
自分は逃げたつもりになってた
{hashtag}
---
---
会議中に寝落ちして
指名されて頓珍漢な返事をした話

隣の人が助け船出してくれたの
未だにお礼言えてない
{hashtag}
---

【ルール】
- 恥ずかしさ・気まずさの具体的なディテール（時刻・場所・周りの反応など）を1つ入れる
- 回避法や教訓で必ず締めなくていい。恥の余韻を残したまま終わってもいい
- 機密情報・思い込み・トーンのズレ・居眠りなど、現実的にありそうな失敗のみ
- 大事故すぎる話にしない（クビ・訴訟レベルはNG。ヒヤッとした程度）

【文体】
- 常体・口語。「です・ます」禁止
- 自虐で終わってもいいが毎回同じオチにしない

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

# ─────────────────────────────────────────────────────
# ツイート処理
# ─────────────────────────────────────────────────────

_HASHTAG_LINE_RE = re.compile(r'^(#\S+(\s+#\S+)*)$')


def x_weighted_length(text: str) -> int:
    """X（Twitter）の weighted length を算出する。
    ひらがな・カタカナ・漢字等ほぼ全ての日本語文字は加重2の範囲に入るため、
    Python の len()（=文字数）だけで判定すると、本文がBODY_LIMIT(140)文字以内でも
    ハッシュタグ込みの実際の重みが280を超えてX APIに投稿を拒否されることがある。
    参考: https://developer.x.com/en/docs/counting-characters"""
    total = 0
    for ch in text:
        cp = ord(ch)
        if (0 <= cp <= 4351) or (8192 <= cp <= 8205) or (8208 <= cp <= 8223) or (8242 <= cp <= 8247):
            total += 1
        else:
            total += 2
    return total


def strip_model_hashtag_lines(text: str) -> str:
    """末尾のハッシュタグ行（1行に複数タグでも可）をモデル出力から取り除く。
    単純な r'\\n#\\S+' 部分置換は「1行に複数タグ」「先頭行がタグ」のケースで
    タグの一部が本文に残留するため、行単位で判定して除去する。"""
    lines = text.rstrip().split('\n')
    while lines and (not lines[-1].strip() or _HASHTAG_LINE_RE.match(lines[-1].strip())):
        lines.pop()
    return '\n'.join(lines).rstrip()


def _fit_weighted_budget(body: str, tags: str) -> str:
    """本文+タグ全体のXの weighted length が TWEET_MAX_LEN を超える場合、
    タグ分の重みを差し引いた予算まで本文を1文字ずつ削って収める安全弁。
    trim_body_excluding_hashtags と url_reaction 分岐の両方から使う共通ヘルパー
    （以前は同じロジックが2箇所に重複していたため、片方だけ修正漏れする事故があった）。"""
    combined = f"{body}\n{tags}" if tags else body
    if x_weighted_length(combined) <= TWEET_MAX_LEN:
        return combined
    tag_weighted = x_weighted_length(f"\n{tags}") if tags else 0
    budget = TWEET_MAX_LEN - tag_weighted
    while body and x_weighted_length(body) > budget:
        body = body[:-1]
    body = body.rstrip()
    return f"{body}\n{tags}" if tags else body


def trim_body_excluding_hashtags(text: str, limit: int = BODY_LIMIT) -> str:
    """末尾ハッシュタグ行を分離し、本文を limit 文字以内に収めて再結合する。
    さらに本文+タグ全体のXの weighted length が280を超える場合は、
    タグ分の重みを差し引いた予算まで本文を追加で削る（安全弁）。"""
    lines      = text.strip().split('\n')
    hashtag_re = _HASHTAG_LINE_RE

    tag_lines = []
    for line in reversed(lines):
        s = line.strip()
        if not s or hashtag_re.match(s):
            tag_lines.insert(0, line)
        else:
            break

    body_end = len(lines) - len(tag_lines)
    body     = '\n'.join(lines[:body_end]).rstrip()
    tags     = '\n'.join(l for l in tag_lines if l.strip())

    if len(body) > limit:
        # 文の途中でぶった切れないよう、直近の文末（改行・句点等）まで戻って切る
        cut = body[:limit]
        idx = max(cut.rfind(s) for s in "\n。！？!?…〜笑")
        body = (cut[:idx + 1] if idx >= limit // 2 else cut[:limit - 1] + "…").rstrip()

    return _fit_weighted_budget(body, tags)


# ─────────────────────────────────────────────────────
# Bedrock 呼び出し
# ─────────────────────────────────────────────────────

_BEDROCK_SYSTEM = (
    "あなたは普通の会社員。仕事・お金・人間関係のリアルを、やり方・数字は具体的に話す。"
    "賛否が分かれる強い意見も断定で言い切る。ヘッジ表現（〜な気がする等）で終わらせない。"
    "ツイート本文だけ出力。前置き・説明・「ツイート：」などは付けない。"
    "1投稿1メッセージに絞り、情報密度を最大にする。文体は崩しても構成は締まった文章にする。"
)

_CANDIDATE_COUNT = 3  # 生成してスコアで選ぶ候補数（1回のBedrock呼び出しで生成、コスト増は誤差）

_HEDGE_ENDINGS = (
    "気がする", "気もする", "気がしてる", "かもしれない", "かもな", "かも",
    "んだろうか", "のかな", "なんだろう", "んだろう", "だろうか",
)


def _score_tweet(text: str) -> int:
    """ツイート案のバズりやすさを簡易採点する（高いほど良い）。Bedrock再呼び出しなしの機械採点。"""
    body = re.sub(r'#\S+', '', text).strip()
    if not body:
        return -100
    lines = [l for l in body.splitlines() if l.strip()]
    last_line = lines[-1].strip() if lines else body
    score = 0
    if not any(last_line.endswith(h) for h in _HEDGE_ENDINGS):
        score += 3  # ヘッジで終わっていない＝断定で言い切れている
    if re.search(r'\d', body):
        score += 2  # 具体的な数字がある
    if 30 <= len(body) <= 130:
        score += 2  # 短すぎず長すぎない情報密度
    if any(w in body for w in ("正直", "だと思ってる", "思ってる")):
        score += 1  # 意見表明のシグナル
    return score


def pick_best_tweet(candidates: list[str]) -> str:
    """スコア最上位の案を返す（同点はリスト先頭優先）。"""
    return max(candidates, key=_score_tweet)


def invoke_bedrock(prompt: str, n: int = _CANDIDATE_COUNT) -> str:
    """Bedrockで1投稿につきn案のツイート候補を1回の呼び出しで生成し、
    ヘッジ表現の有無・数字の有無・情報密度で機械採点して最良の1案を返す。
    （2026-07-05追加: 一発生成では上振れを引けないというFable評価を受けて導入）"""
    resp = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512 * n,
            "system": _BEDROCK_SYSTEM,
            "temperature": 0.95,
            "messages": [{"role": "user", "content": (
                f"{prompt}\n\n"
                f"上記の条件で、切り口や具体例が違う案を{n}つ生成してください。"
                f"各案の間は \"===\" のみの行で区切ってください（前置き・番号付けなし。各案はツイート本文のみ）。"
            )}],
        }),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    usage = result.get("usage", {})
    print(f"[Bedrock] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")
    text = result["content"][0]["text"].strip()
    candidates = [c.strip() for c in re.split(r'\n?={3,}\n?', text) if c.strip()]
    if not candidates:
        candidates = [text]
    best = pick_best_tweet(candidates)
    if len(candidates) > 1:
        print(f"[Bedrock] {len(candidates)}案からスコア{_score_tweet(best)}点の案を採用")
    return best


# ─────────────────────────────────────────────────────
# X API v2 投稿（OAuth 1.0a）
# ─────────────────────────────────────────────────────

def _percent_encode(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def get_x_credentials() -> dict:
    param_names = [
        f"{SSM_PREFIX}/twitter_api_key",
        f"{SSM_PREFIX}/twitter_api_secret",
        f"{SSM_PREFIX}/twitter_access_token",
        f"{SSM_PREFIX}/twitter_access_token_secret",
    ]
    response = ssm_client.get_parameters(Names=param_names, WithDecryption=True)
    creds    = {p["Name"].split("/")[-1]: p["Value"] for p in response["Parameters"]}
    if len(creds) != 4:
        missing = set(n.split("/")[-1] for n in param_names) - set(creds.keys())
        raise ValueError(f"SSMパラメータが不足: {missing}")
    return creds


def _build_oauth_header(method: str, url: str, creds: dict, extra_params: dict | None = None) -> str:
    """OAuth 1.0aの署名付きAuthorizationヘッダーを生成する（GET/POST共通）。"""
    ts    = str(int(time.time()))
    nonce = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    oauth = {
        "oauth_consumer_key":     creds["twitter_api_key"],
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        ts,
        "oauth_token":            creds["twitter_access_token"],
        "oauth_version":          "1.0",
    }
    all_params = {**oauth, **(extra_params or {})}
    params_str = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}"
                          for k, v in sorted(all_params.items()))
    base_str   = "&".join([method, _percent_encode(url), _percent_encode(params_str)])
    sign_key   = (_percent_encode(creds["twitter_api_secret"]) + "&"
                  + _percent_encode(creds["twitter_access_token_secret"]))
    sig        = base64.b64encode(
        hmac.new(sign_key.encode(), base_str.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"' for k, v in sorted(oauth.items())
    )


def post_to_x(tweet_text: str, creds: dict, reply_to: str | None = None) -> dict:
    url = "https://api.twitter.com/2/tweets"
    auth_header = _build_oauth_header("POST", url, creds)
    payload_dict = {"text": tweet_text}
    if reply_to:
        payload_dict["reply"] = {"in_reply_to_tweet_id": reply_to}
    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
        headers={"Authorization": auth_header, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            tweet_id = result["data"]["id"]
            print(f"[X] 投稿成功: tweet_id={tweet_id}")
            print(f"[X] https://x.com/i/web/status/{tweet_id}")
            return result
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"X API エラー {e.code}: {e.read().decode()}") from e


def get_x(url_path: str, creds: dict, params: dict | None = None) -> dict:
    """X API v2 のGETエンドポイント（読み取り専用）をOAuth 1.0aで署名して呼び出す。
    2026-07-05: リプライ営業機能のためのユーザー検索・タイムライン取得に使用。実地テストで
    Read権限が現行プランで利用可能なことを確認済み（追加料金なし）。"""
    url = f"https://api.twitter.com{url_path}"
    auth_header = _build_oauth_header("GET", url, creds, extra_params=params)
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(url + query, headers={"Authorization": auth_header})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"X API エラー {e.code}: {e.read().decode()}") from e


# ─────────────────────────────────────────────────────
# リプライ営業（大手アカウントへの返信、2026-07-05追加）
# ─────────────────────────────────────────────────────
# ユーザーが実在確認・明示承認した返信先のみを対象とする（対象選定を自動化・AI判断に
# 委ねることはしない）。頻度は既存スケジュール（週3回）に相乗りさせ、新たな
# EventBridge実行は追加しない（1回の実行につき最大1件）。

# 初回起動時のデフォルト値（SSMパラメータが未設定の場合のみ使用・自動書き込みされる）。
# 運用中にリプ先を変更したい場合は、このデフォルト値を書き換えて再デプロイする必要はなく、
# 以下のコマンドでSSMパラメータを直接更新するだけでよい（コード変更・再デプロイ不要）:
#   aws ssm put-parameter --name /ai_bot/reply_target_accounts \
#     --value '["nikkei","toyokeizai","dol_editors","PRE_ONLINE","itmedia_news","itmedia",
#                "livedoornews","asahi","sankei_news","mainichi"]' \
#     --type String --overwrite --region ap-northeast-1
# 2026-07-05: 当初の候補"diamond_online"はフォロワー15人の無関係な個人アカウントに、
# "PRESIDENT_Online"はXのユーザー名文字数上限(15文字)違反で無効だったことが
# GET /2/users/by/username の実地確認で判明。正しい公式ハンドル（dol_editors・
# PRE_ONLINE、いずれもprofile descriptionで公式アカウントと確認済み）に差し替え。
# nikkeibp（日経BP）は凍結済みアカウントのため不採用。
DEFAULT_REPLY_TARGET_ACCOUNTS = [
    "nikkei", "toyokeizai", "dol_editors", "PRE_ONLINE",
    "itmedia_news", "itmedia",
    "livedoornews", "asahi", "sankei_news", "mainichi",
]
MAX_REPLY_TARGET_HISTORY_CAP = 5   # 除外履歴の上限（対象数が増えても際限なく増やさない）
MAX_REPLIED_TWEET_HISTORY    = 50  # 同一ツイートへの二重返信を防ぐための履歴保持件数


def load_reply_target_accounts() -> list:
    """リプ先アカウント一覧をSSMから読み込む。未設定時はデフォルト値をSSMに書き込んでから返す。
    運用中の変更はコード修正・再デプロイ不要で、SSMパラメータの直接更新だけで反映される。"""
    param = f"{SSM_PREFIX}/reply_target_accounts"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        accounts = json.loads(val)
        if isinstance(accounts, list) and accounts:
            return accounts
    except ssm_client.exceptions.ParameterNotFound:
        pass
    except Exception as e:
        print(f"[Reply] 対象アカウント読み込みエラー（デフォルトを使用）: {e}")
    try:
        ssm_client.put_parameter(
            Name=param, Value=json.dumps(DEFAULT_REPLY_TARGET_ACCOUNTS),
            Type="String", Overwrite=True,
        )
    except Exception as e:
        print(f"[Reply] デフォルト対象アカウントのSSM書き込みエラー: {e}")
    return DEFAULT_REPLY_TARGET_ACCOUNTS


def _reply_target_history_limit(accounts: list) -> int:
    """除外履歴の保持件数を対象アカウント数に応じて動的に決める。
    アカウント数-1件をMAX_REPLY_TARGET_HISTORY_CAPまでに収め、候補が必ず1件以上残るようにする
    （対象数を変更しても恒久ロックしない設計）。"""
    return max(1, min(MAX_REPLY_TARGET_HISTORY_CAP, len(accounts) - 1))


def load_reply_target_history() -> list:
    param = f"{SSM_PREFIX}/history/reply_targets"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        return json.loads(val)
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[Reply] リプ先履歴読み込みエラー: {e}")
        return []


def save_reply_target_history(used: list, new_target: str, accounts: list):
    limit = _reply_target_history_limit(accounts)
    updated = (used + [new_target])[-limit:]
    try:
        ssm_client.put_parameter(
            Name=f"{SSM_PREFIX}/history/reply_targets",
            Value=json.dumps(updated), Type="String", Overwrite=True,
        )
        print(f"[Reply] リプ先履歴保存: {updated}")
    except Exception as e:
        print(f"[Reply] リプ先履歴保存エラー: {e}")


def pick_reply_target(used_targets: list, accounts: list) -> str:
    """直近履歴（アカウント数に応じて動的に決まる件数）に含まれないアカウントから
    ランダム選択し、毎回同じ相手にリプ営業が偏らないようにする。"""
    limit = _reply_target_history_limit(accounts)
    recent = used_targets[-limit:]
    unused = [a for a in accounts if a not in recent]
    return random.choice(unused) if unused else random.choice(accounts)


def load_replied_tweet_ids() -> list:
    param = f"{SSM_PREFIX}/history/replied_tweets"
    try:
        val = ssm_client.get_parameter(Name=param)["Parameter"]["Value"]
        return json.loads(val)
    except ssm_client.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[Reply] 返信済みツイート履歴読み込みエラー: {e}")
        return []


def save_replied_tweet_id(current: list, new_id: str):
    updated = (current + [new_id])[-MAX_REPLIED_TWEET_HISTORY:]
    try:
        ssm_client.put_parameter(
            Name=f"{SSM_PREFIX}/history/replied_tweets",
            Value=json.dumps(updated), Type="String", Overwrite=True,
        )
    except Exception as e:
        print(f"[Reply] 返信済みツイート履歴保存エラー: {e}")


def resolve_user_id(username: str, creds: dict) -> str | None:
    """ユーザー名からユーザーIDを取得する。失敗時はNoneを返し呼び出し元でスキップさせる。"""
    try:
        result = get_x(f"/2/users/by/username/{username}", creds)
        return result.get("data", {}).get("id")
    except Exception as e:
        print(f"[Reply] ユーザーID解決エラー (@{username}): {e}")
        return None


def fetch_recent_tweets(user_id: str, creds: dict, max_results: int = 5) -> list:
    """指定ユーザーの最新ツイートを取得する（RT・リプライは除外）。失敗時は空リスト。"""
    try:
        result = get_x(f"/2/users/{user_id}/tweets", creds,
                       params={"max_results": str(max_results), "exclude": "retweets,replies"})
        return result.get("data", []) or []
    except Exception as e:
        print(f"[Reply] タイムライン取得エラー: {e}")
        return []


# リプ営業はニュースメディアの投稿を対象にするため政治・国際情勢の話題に触れやすい
# （実地テストでトランプ大統領関連の投稿が候補に上がった）。TREND_NG_WORDSに加えて
# 大統領・政権・外交等も除外し、政治的な話題への反応を避ける。
REPLY_NG_WORDS = TREND_NG_WORDS + [
    "大統領", "首相官邸", "政権", "外交", "与党", "野党", "国会", "トランプ",
    # 2026-07-05: 朝日新聞の実タイムラインに「線状降水帯直前予測」等の進行中の災害警報が
    # 含まれ、TREND_NG_WORDS（台風・水害等の一般語）だけでは検知できなかったため追加
    "警報", "線状降水帯", "洪水", "土砂災害", "避難指示", "避難勧告", "津波",
]


def _is_sensitive_for_reply(text: str) -> bool:
    """訃報・事件・災害・政治・国際情勢等、リプ営業には不適切な内容かどうかを判定する。"""
    return any(ng in text for ng in REPLY_NG_WORDS)


def pick_reply_candidate_tweet(tweets: list, replied_ids: list) -> dict | None:
    """返信対象として適切なツイートを1つ選ぶ。返信済み・センシティブ内容は除外。"""
    for t in tweets:
        if t.get("id") in replied_ids:
            continue
        if _is_sensitive_for_reply(t.get("text", "")):
            continue
        return t
    return None


def build_reply_prompt(tweet_text: str, target_label: str) -> str:
    return f"""なんとか生きてる普通の会社員が、X（旧Twitter）で「{target_label}」の以下の投稿に返信します。

【相手の投稿】
{tweet_text}

【良い例（投稿の具体的な内容に触れた上で、会社員目線の本音や関連する体験を一言添える）】
---
これ見て思ったけど、給料からの天引き額を明細で改めて見ると毎回めまいがする
使い道が納得できないとなおさら
---
---
正直この手のニュース、自分の手取りとは別世界の話に感じる
生活してる側からするとリアリティがない
---
---
記事の内容はわかるけど、結局自分の給料には反映されない話だよなと思ってしまう
---

【ルール】
- 相手の投稿の具体的な内容（数字・固有名詞・論点）に触れること。「わかります」「そうですね」のような当たり障りのない相槌は禁止
- 会社員としての本音・実感を1つ添える（仕事・お金・生活の視点）。税金・手取りへの不満などの切り口もOK
- 特定の個人・政党・企業への攻撃、差別的表現、誤情報の断定はしない（あくまで会社員としての実感・本音の範囲）
- 「です・ます」禁止。常体・口語
- 80文字以内
- 絵文字は使わない
- ハッシュタグ・URLは含めない
- 宣伝・営業目的だとわかる文面にしない（「フォローお願いします」等は厳禁）

返信本文のみ出力。"""


def attempt_reply_outreach(creds: dict, dry_run: bool) -> None:
    """大手アカウントの最新投稿に1件だけ返信する。
    どのステップで失敗してもログに残すだけでメインの投稿処理には影響させない
    （リプ営業はあくまで付随機能であり、これが原因でメイン投稿が止まってはならない）。"""
    try:
        accounts = load_reply_target_accounts()
        used_targets = load_reply_target_history()
        target = pick_reply_target(used_targets, accounts)
        limit = _reply_target_history_limit(accounts)
        print(f"[Reply] リプ先候補: @{target} (対象{len(accounts)}件中・直近使用: {used_targets[-limit:]})")

        user_id = resolve_user_id(target, creds)
        if not user_id:
            print("[Reply] ユーザーID解決失敗のためスキップ")
            return

        tweets = fetch_recent_tweets(user_id, creds)
        if not tweets:
            print("[Reply] 取得できるツイートがないためスキップ")
            return

        replied_ids = load_replied_tweet_ids()
        chosen = pick_reply_candidate_tweet(tweets, replied_ids)
        if not chosen:
            print("[Reply] 返信可能なツイートがない（センシティブ or 返信済み）ためスキップ")
            return

        prompt = build_reply_prompt(chosen["text"], target)
        reply_text = invoke_bedrock(prompt, n=2)
        reply_text = trim_body_excluding_hashtags(reply_text, limit=80)
        reply_text = strip_model_hashtag_lines(reply_text)

        if not reply_text or len(reply_text) < 5:
            print("[Reply] 生成結果が短すぎる/空のためスキップ")
            return

        print(f"[Reply] @{target} の投稿「{chosen['text'][:40]}...」に返信予定:\n{reply_text}")

        if dry_run:
            print("[Reply] [DRY_RUN] 返信投稿・履歴更新をスキップ")
            return

        post_to_x(reply_text, creds, reply_to=chosen["id"])
        save_reply_target_history(used_targets, target, accounts)
        save_replied_tweet_id(replied_ids, chosen["id"])
    except Exception as e:
        print(f"[Reply] リプ営業処理でエラー（無視して続行）: {e}")


# ─────────────────────────────────────────────────────
# Lambda エントリーポイント
# ─────────────────────────────────────────────────────

def lambda_handler(event, context):
    event = event or {}
    now      = datetime.now(JST)
    mode     = event.get("mode", "random")
    # event側のdry_runを優先しつつ環境変数DRY_RUNも後方互換で見る（test_invoke.shの
    # 「本番環境変数を書き換えて戻す」運用は事故りやすいため、ペイロード指定に一本化する）
    dry_run  = bool(event.get("dry_run", DRY_RUN))
    weekday  = now.weekday()  # 0=月 1=火 2=水 3=木 4=金 5=土 6=日
    print(f"[Start] {now.strftime('%Y-%m-%d %H:%M JST')} / mode={mode} / weekday={weekday} / dry_run={dry_run}")

    # ── カテゴリ決定 ──────────────────────────────────
    used_categories = load_used_categories()
    trend_kw    = None
    url_article = None
    used_urls   = None

    if mode == "trend":
        trends   = fetch_google_trends_jp()
        trend_kw = pick_relatable_trend(trends) if trends else None
        if trend_kw:
            category = "trend"
            print(f"[Trend] 使用キーワード: {trend_kw}")
        else:
            print("[Trend] 絡められるキーワードなし → ローテーションカテゴリにフォールバック")
            category = pick_category(used_categories)
    elif weekday == 0:  # 月曜=0: 50%でurl_reaction、50%でローテーション（固定化による予測可能性を下げる）
        if random.random() < URL_REACTION_RATE:
            used_urls   = load_url_history()
            url_article = fetch_url_reaction_article(used_urls)
            if url_article:
                category = "url_reaction"
                print(f"[URL Reaction] 記事取得成功: 「{url_article['title'][:50]}」")
            else:
                print("[URL Reaction] 記事取得失敗 → ローテーションカテゴリにフォールバック")
                category = pick_category(used_categories)
        else:
            category = pick_category(used_categories)
            print(f"[Category] 月曜ローテーション選択: {category}")
    elif weekday == 3:  # 木曜=3: question固定（エンゲージメント最大化。インプレッションが高い曜日に合わせる）
        category = "question"
        print("[Category] 木曜固定: question")
    else:
        category = pick_category(used_categories)

    # テスト用: FORCE_CATEGORY 環境変数でカテゴリを強制
    force_cat = os.environ.get("FORCE_CATEGORY")
    if force_cat:
        if force_cat in CATEGORIES:
            category = force_cat
            print(f"[Force] FORCE_CATEGORY={force_cat}")
        elif force_cat == "url_reaction":
            used_urls   = load_url_history()
            url_article = fetch_url_reaction_article(used_urls)
            if url_article:
                category = "url_reaction"
                print("[Force] FORCE_CATEGORY=url_reaction")
            else:
                print("[Warning] FORCE_CATEGORY=url_reaction 記事取得失敗（ローテーションで続行）")
                category = pick_category(used_categories)
        else:
            print(f"[Warning] 無効なFORCE_CATEGORY: '{force_cat}'（無視）")
    print(f"[Category] {category} (直近使用: {used_categories[-MAX_CATEGORY_HISTORY:]})")

    # ── 履歴読み込み ──────────────────────────────────
    history  = load_history(category)
    past_kws = [kw for e in history for kw in e.get("keywords", [])]
    print(f"[History] 過去キーワード数: {len(past_kws)}")

    # ── プロンプト構築 ────────────────────────────────
    cat_hashtag = pick_category_hashtag(category)
    # recipe/jissokuは共通の12お題からお題を選ぶ。直近MAX_RECIPE_TASK_HISTORY件は
    # 除外し、確率1/12での連続同一お題を防ぐ（002のrecent-angles方式を横展開）
    recipe_task_history = None
    recipe_task = None
    if category in ("recipe", "jissoku"):
        recipe_task_history = load_recipe_task_history()
        recipe_task = pick_recipe_task(recipe_task_history)
        print(f"[Task] {recipe_task} (直近使用: {recipe_task_history[-MAX_RECIPE_TASK_HISTORY:]})")

    # questionは木曜固定＋ローテーションで最頻出のため、テーマ軸をSSM履歴除外つきで選ぶ
    question_theme_history = None
    question_theme = None
    if category == "question":
        question_theme_history = load_question_theme_history()
        question_theme = pick_question_theme(question_theme_history)
        print(f"[Theme] {question_theme} (直近使用: {question_theme_history[-MAX_QUESTION_THEME_HISTORY:]})")

    builders = {
        "recipe":   lambda h: build_recipe_prompt(h, cat_hashtag, recipe_task),
        "jissoku":  lambda h: build_jissoku_prompt(h, cat_hashtag, recipe_task),
        "hikaku":   lambda h: build_hikaku_prompt(h, cat_hashtag),
        "shippai":  lambda h: build_shippai_prompt(h, cat_hashtag),
        "fukugyo":  lambda h: build_fukugyo_prompt(h),
        "question": lambda h: build_question_prompt(h, cat_hashtag, question_theme),
    }
    if category == "trend":
        prompt = build_trend_prompt(trend_kw, history)
    elif category == "url_reaction":
        prompt = build_url_reaction_prompt(url_article, history)
    else:
        prompt = builders[category](history)

    # ── ツイート生成 ──────────────────────────────────
    raw = invoke_bedrock(prompt)

    if category == "url_reaction":
        # 本文は100文字以内。URLは本文に入れるとリーチが抑制されるため、投稿後にリプライへぶら下げる
        body  = trim_body_excluding_hashtags(raw, limit=URL_REACTION_LIMIT)
        body  = strip_model_hashtag_lines(body)  # drop model-inserted hashtag lines
        htag  = pick_hashtag(body + " " + url_article["title"])
        # ハッシュタグ再付加後にXのweighted lengthで最終チェック（安全弁）
        tweet = _fit_weighted_budget(body, htag)
    else:
        tweet = trim_body_excluding_hashtags(raw)

    # Bot感軽減: 約35%はハッシュタグなしで投稿する（url_reaction は除く）
    if category != "url_reaction" and random.random() < NO_HASHTAG_RATE:
        stripped = re.sub(r'[ \t]*#\S+', '', tweet).rstrip()
        if stripped:
            tweet = stripped
            print("[Hashtag] 今回はタグなしで投稿")
    print(f"[Tweet]\n{tweet}\n[文字数] len={len(tweet)} weighted={x_weighted_length(tweet)}/{TWEET_MAX_LEN}")

    # X認証情報はdry_runでもリプ営業のプレビューに使うため、DRY RUN判定より先に取得する
    creds = get_x_credentials()

    # ── リプライ営業（大手アカウントへの返信。既存の週3回スケジュールに相乗り） ──
    print("[Reply] リプ営業を試行中...")
    attempt_reply_outreach(creds, dry_run)

    # ── DRY RUN ───────────────────────────────────────
    if dry_run:
        print("[DRY RUN] 投稿スキップ（SSM履歴は更新しません）")
        return {"statusCode": 200, "category": category, "tweet": tweet, "dry_run": True}

    # ── X投稿 ─────────────────────────────────────────
    result = post_to_x(tweet, creds)

    # url_reaction: 記事URLをリプライにぶら下げる（本文に入れるとリーチが抑制されるため）
    if category == "url_reaction":
        try:
            post_to_x(url_article["url"], creds, reply_to=result["data"]["id"])
        except Exception as e:
            print(f"[X] URLリプライ投稿失敗（本文投稿は成功済みのため続行）: {e}")

    # ── 履歴更新 ──────────────────────────────────────
    body_only = re.sub(r'#\S+', '', tweet).strip()
    keywords  = extract_keywords(body_only)
    save_history(category, history, keywords)
    if category == "url_reaction":
        save_url_history(url_article["url"])
    elif category in CATEGORIES:
        # trend / url_reaction は固定スロットでありローテーション対象外。
        # used_categories に書き込むと dedup ウィンドウ（直近MAX_CATEGORY_HISTORY件）を
        # ローテーション外カテゴリで圧迫してしまうため、CATEGORIES のものだけ記録する。
        save_used_categories(used_categories, category)
    if recipe_task is not None:
        save_recipe_task_history(recipe_task_history, recipe_task)
    if question_theme is not None:
        save_question_theme_history(question_theme_history, question_theme)

    tweet_id = result.get("data", {}).get("id")
    return {
        "statusCode": 200,
        "category":   category,
        "tweet_id":   tweet_id,
        "tweet_url":  f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None,
        "keywords":   keywords,
        "timestamp":  now.isoformat(),
    }
