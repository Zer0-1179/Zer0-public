"""X auto-post bot @Zer0_0326 — AI lifestyle content via Bedrock (Mon/Thu 20:00, Sun 10:00 JST)."""

import json, os, random, re, time, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
import hmac, hashlib, base64
from datetime import datetime, timezone, timedelta

import boto3

# ---- AWS クライアント ----
bedrock    = boto3.client("bedrock-runtime", region_name="ap-northeast-1")
ssm_client = boto3.client("ssm",             region_name="ap-northeast-1")

# ---- 定数 ----
BEDROCK_MODEL_ID     = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
SSM_PREFIX           = os.environ.get("SSM_PREFIX", "/ai_bot")
DRY_RUN              = os.environ.get("DRY_RUN", "false").lower() == "true"
JST                  = timezone(timedelta(hours=9))

CATEGORIES           = ["recipe", "jissoku", "hikaku", "shippai", "fukugyo", "question"]
MAX_CATEGORY_HISTORY = 4   # 6カテゴリ中、直近4件を避けて選択
MAX_USED_URLS        = 28
URL_HISTORY_DAYS     = 90   # 使用済みURLの保持期間（日）
NO_HASHTAG_RATE      = 0.35 # Bot感軽減: この確率でハッシュタグなし投稿にする
URL_REACTION_RATE    = 0.5  # 月曜にurl_reactionを選ぶ確率（残りはローテーション）
URL_REACTION_LIMIT   = 100  # url_reaction本文の文字数上限（URLはリプライにぶら下げる）
BODY_LIMIT           = 140  # 通常カテゴリ本文の文字数上限（ハッシュタグ・URL除く）
TWEET_MAX_LEN        = 280  # X実際の投稿上限（weighted length）

# カテゴリ別ハッシュタグ（リストの場合は投稿ごとにランダム選択）
HASHTAGS = {
    "recipe":       ["#AI活用", "#ChatGPT", "#仕事術"],
    "jissoku":      ["#AI活用", "#仕事術", "#生成AI"],
    "hikaku":       ["#生成AI", "#AI活用"],
    "shippai":      ["#生成AI", "#AI活用", "#ChatGPT"],
    "fukugyo":      "#副業",
    "question":     ["#AI活用", "#生成AI"],
    "trend":        "#AI活用",
    "url_reaction": "#AI活用",
}

# url_reaction 用ハッシュタグプール（文章に合うものをピック）
HASHTAG_POOL = [
    {"tag": "#AI活用",      "keywords": ["AI", "ChatGPT", "Claude", "Gemini", "Copilot", "生成AI", "LLM", "プロンプト", "自動化", "人工知能"]},
    {"tag": "#生成AI",      "keywords": ["生成AI", "LLM", "大規模言語モデル", "画像生成", "テキスト生成"]},
    {"tag": "#ChatGPT",     "keywords": ["ChatGPT", "GPT", "OpenAI"]},
    {"tag": "#副業",        "keywords": ["副業", "収益", "案件", "フリーランス", "稼ぎ", "収入", "note"]},
    {"tag": "#時短",        "keywords": ["時短", "効率", "早く", "速く", "短縮", "削減", "節約"]},
    {"tag": "#仕事術",      "keywords": ["仕事", "業務", "作業", "タスク", "報告書", "プレゼン", "会議", "メール", "議事録"]},
    {"tag": "#エンジニア",  "keywords": ["エンジニア", "プログラミング", "コード", "開発", "システム", "ツール"]},
    {"tag": "#働き方",      "keywords": ["働き方", "リモート", "テレワーク", "定時", "残業", "ワークライフ"]},
    {"tag": "#プロンプト",  "keywords": ["プロンプト", "プロンプトエンジニアリング", "指示", "質問の仕方"]},
    {"tag": "#AI副業",      "keywords": ["AI", "副業", "自動化", "収益", "案件"]},
]

# 月曜のURL反応投稿用RSSフィード
URL_REACTION_FEEDS = [
    {"url": "https://zenn.dev/topics/ai/feed",          "source": "zenn",  "label": "Zenn"},
    {"url": "https://zenn.dev/topics/chatgpt/feed",     "source": "zenn",  "label": "Zenn"},
    {"url": "https://zenn.dev/topics/llm/feed",         "source": "zenn",  "label": "Zenn"},
    {"url": "https://qiita.com/tags/ai/feed.atom",      "source": "qiita", "label": "Qiita"},
    {"url": "https://qiita.com/tags/chatgpt/feed.atom", "source": "qiita", "label": "Qiita"},
    {"url": "https://qiita.com/tags/生成ai/feed.atom",  "source": "qiita", "label": "Qiita"},
]

# url_reaction フィルタ用キーワード
URL_REACTION_KEYWORDS = [
    "AI", "ChatGPT", "Claude", "Gemini", "生成AI", "LLM",
    "プロンプト", "Copilot", "自動化", "機械学習",
]

# Google Trendsキーワードの優先度別マッチリスト
AI_TIER1 = [
    "AI", "人工知能", "ChatGPT", "Claude", "Gemini", "Copilot",
    "生成AI", "LLM", "テクノロジー", "Tech", "IT", "AWS", "クラウド",
    "デジタル", "プログラミング", "エンジニア",
]
AI_TIER2 = [
    "副業", "ビジネス", "働き方", "転職", "起業", "スタートアップ",
    "スキル", "学習", "教育", "資格", "ツール", "自動", "データ",
    "アプリ", "スマホ", "SNS", "動画", "ゲーム",
    "ショッピング", "EC", "通販",
]

# キーワード抽出用のトピックリスト
TOPIC_WORDS = [
    "AI", "ChatGPT", "Claude", "副業", "自動化", "時短", "収益",
    "議事録", "プロンプト", "ツール", "作業", "仕事", "会社",
    "業務", "SNS", "ブログ", "記事", "生産性", "時間", "案件",
    "残業", "転職", "給料", "評価", "定時", "note",
]

# recipe / jissoku 用の業務お題（投稿ごとにローテーション）
RECIPE_TASKS = [
    "会議の議事録・文字起こしの整理",
    "催促・リマインドなど気まずいメールの作成",
    "企画書・提案資料のたたき台づくり",
    "Excelの関数・データ整理",
    "長い資料・PDFの要約",
    "週報・報告書の作成",
    "プレゼンの構成・スライド骨子",
    "クレーム対応・謝罪文",
    "リサーチ・下調べ",
    "タスクの優先順位整理",
    "自分の資料の弱点チェック（セルフレビュー）",
    "上司への相談・報告の言い回し",
]

# ---- 全カテゴリ共通ルール ----
ABSOLUTE_RULES = """【絶対ルール】
- 140文字以内（ハッシュタグ・URL含まず）。上限まで書こうとせず短くてもいい
- ハッシュタグは指定したもの1個のみ（それ以外は付けない）
- 絵文字は最大1個
- 「〜です」「〜ます」禁止
- 「AIに任せたら全部解決した」で終わる抽象的な感想は禁止
- 結論・教訓・まとめで締めない
- 「…」は1投稿に最大1回まで
- 「なんか」「ちょっと」「わりと」などのフィラーは1投稿に合計2回まで

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
キャラ：AIに頼りながらなんとか生きてる普通の会社員

【1行目が命】
スクロールを止める書き出しを必ず作る。以下のどれかで始める：
  ・告白型：「実は〜」「正直〜」「こっそり〜」「言えてなかったけど〜」
  ・対比型：「〜なのに〜」「〜したら〜だった」
  ・問いかけ型：「〜ってある？」「〜だけ？」「〜どうしてる？」
  ・数字型：「2時間かけてた〜を」「3回失敗して〜」

【語感】
語尾→「…」「〜」「笑」「かも」「気がする」「だけど」「かな」「っていう」
文中→「なんか」「ちょっと」「わりと」「けっこう」「なんとなく」「よくわかんないけど」
反応→「え、待って」「まじか」「あ、そういうことか」「うーん」
その他→独り言調・失敗談・試行錯誤・雑な数字（「もう2時間経ってた笑」等）

【人間らしさの核心】
文章は完成させなくていい。途中で迷いや脱線が出てもいい。
「よくわかんないけど」「なんかうまく言えない」があってもいい。
毎回同じ構成にしない（バラバラな方がリアル）。
オチを決めようとしない。思ったことをそのまま垂れ流す感じで。

【終わり方】
結論を出さない。疑問・余韻・皮肉・「でも〜」で終わらせる。
読んだ人が「わかる」「自分も〜」と口に出したくなる終わり方を選ぶ。
ただし毎回「自虐オチ」「皮肉オチ」にしない。何も落とさず終わる日があっていい。"""

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
    val = HASHTAGS.get(category, "#AI活用")
    return random.choice(val) if isinstance(val, list) else val


def pick_hashtag(body: str) -> str:
    """本文・記事タイトルの内容に合わせてHASHTAG_POOLから最適なハッシュタグを選ぶ。
    スコアが同点の場合はランダム選択。マッチなしは '#AI活用' を返す。"""
    body_lower = body.lower()
    scores = {}
    for item in HASHTAG_POOL:
        score = sum(1 for kw in item["keywords"] if kw.lower() in body_lower)
        if score > 0:
            scores[item["tag"]] = score
    if not scores:
        return "#AI活用"
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
    return all_kws[:5] if len(all_kws) >= 3 else (all_kws or ["AI"])


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


def pick_ai_relatable_trend(keywords: list) -> str | None:
    """AIと絡められるトレンドキーワードを優先度順に1つ選ぶ。"""
    tier1 = [kw for kw in keywords if any(t in kw for t in AI_TIER1)]
    if tier1:
        print(f"[Trends] Tier1マッチ: {tier1}")
        return random.choice(tier1)

    tier2 = [kw for kw in keywords if any(t in kw for t in AI_TIER2)]
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
    """URL_REACTION_FEEDSからAI記事を取得し未使用のものを1件返す。
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

    # AI関連キーワードでスコアリング
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
    return f"""AIを仕事で使っている会社員が、X（旧Twitter）にAI記事を読んだ感想を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIに興味ある会社員。「この記事読みたい」「保存しよ」と思わせる内容
{avoid}
【今日の記事】
タイトル：{title}
概要：{desc}

【良い例（記事からの「持ち帰り」を1つ＋正直な反応）】
---
この記事、一番の持ち帰りはここだった
「指示に役割を入れるだけで出力が変わる」

知ってたつもりだったけど
例を見たら自分全然やれてなかった
---
---
読む前「またこの話か」
読んだ後「明日からこれやる」

タイトルで損してるタイプの記事だと思う
中身は具体的だった
---
---
これ読んで自分のやり方を見返したら
「やりがち」って書かれてるやつ、ほぼ全部やってた

直す場所が明確になっただけでも読んだ価値あった
---
---
半分くらいは知ってる内容だったけど
後半の具体例だけでも読む価値あった

こういうのは知識の差じゃなくて
「実際やってみたか」の差なんだよな
---

【今回の形式（必ずこの形式で書く）】
{random.choice(FORMAT_STYLES)}
※ 上の良い例の改行の仕方はコピーせず、この形式指定を優先する

【ルール】
- 記事から得た学び・持ち帰りを1つだけ挙げる。ただし記事タイトル・概要に実際に書かれている範囲の表現にとどめ、書かれていないことを記事の内容として書かない
- 記事の要約・紹介はしない（自分の変化・気づきを書く）
- 1行目で読者を止めるフックを作る
- 「です・ます」禁止
- 100文字以内でコンパクトに
- 絵文字は最大1個
- 「…」は1投稿に最大1回まで
- 綺麗に締めない・余白を残す
- URLは含めない（自動で付加される）

ツイート本文のみ出力。"""

def build_recipe_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    task  = random.choice(RECIPE_TASKS)
    return f"""AIを仕事で使っている普通の会社員が、X（旧Twitter）に「コピペで使えるプロンプトのレシピ」を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員。ただしやり方は具体的
ターゲット：AIを仕事で使い始めた会社員。読んだ人が「保存しよ」と思うのがゴール
{avoid}
【今回のお題（この業務シーンのレシピを書く）】
{task}

【良い例（プロンプトは「」で示す。構成はバラバラでOK）】
---
議事録まとめ、結局これだけで足りてる

「この文字起こしから、決定事項・宿題・担当・期限だけ表にして」

要約させるより、欲しい形を先に指定する方が早い
気づくまで3ヶ月かかった
{hashtag}
---
---
催促メールが苦手すぎてたどり着いたやつ

「急かさずに期限を思い出してもらうメール、トーン違いで3パターン」

3つ出させて混ぜるのがコツ
1個だけ使うとAIっぽさが残る
{hashtag}
---
---
資料できたら送る前にこれやってる

「この資料の弱点を、意地悪な役員になりきって5個指摘して」

先に詰められておくと本番のレビューが軽い
自分ではもう気づけない部分が出てくる
{hashtag}
---
---
週報、メモ書き3行から作ってる

「この箇条書きを週報にして。頑張ってる感は出しすぎず事実ベースで」

「頑張ってる感出しすぎず」を入れてから
上司の反応がむしろ良くなった笑
{hashtag}
---

【ルール】
- お題の業務シーンに合った、実際にコピペで使えるプロンプトを「」で1つ入れる（1行・汎用的に・誰の環境でも使える内容）
- なぜそれが効くのか・気づいたきっかけ・実際どうなったかを一言そえる
- 数字や具体的な変化があると強い（盛らない・現実的な範囲で）
- プロンプトの中身が今回のお題とズレないこと

【文体】
- 上の例のような常体・口語。「です・ます」禁止
- 完璧にまとめない。一言の余韻や本音で終わる

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_fukugyo_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIに頼りながら副業もしている会社員がX（旧Twitter）に投稿する「副業の現実・やり方・本音」のつぶやきを1件生成してください。
ターゲット：副業に興味ある会社員。「現実が知れた」「自分もやってみようかな」と思わせる内容
{avoid}
【良い例】
---
副業のリサーチ、AIに下調べさせて自分で裏取りする流れにしたら
1案件2時間→40分

単価は同じだから実質時給が上がった
これに気づいてから続けられてる
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

AIに作業の半分を任せてから
なんとか続けられてる
これがなかったら続いてなかった
#副業
---
---
副業の納品前、AIに「クライアント目線で不安になる点を指摘して」って投げてる

これやるようになってから修正依頼が減った
先回りが一番の時短かもしれない
#副業
---
---
副業の確定申告
去年はパニックだったのに
今年はAIに聞きながらやったらなんとかなった

毎年怖いのは変わらないけど
#副業
---

【ルール】
- 数字（金額・時間・件数）か具体的なやり方を、どれか1つは入れる（盛らない・現実的に）
- 夢を売らない。「楽して稼げる」系の表現は禁止
- 良いことだけで終わらせず、現実・本音を残す

{style_guide()}

{ABSOLUTE_RULES}

末尾に「#副業」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_jissoku_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    task  = random.choice(RECIPE_TASKS)
    return f"""AIを仕事で使っている普通の会社員が、X（旧Twitter）に「AIで仕事がどれだけ変わったかのbefore/after実録」を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AI活用に興味ある会社員。「そんなに変わるのか、自分もやってみよう」と思わせる
{avoid}
【今回のお題（この業務の実録を書く）】
{task}

【良い例】
---
週報にかけてた時間、測ったら毎週50分だった

今は箇条書きメモをAIに渡して5分
浮いた45分で何してるかというと…別の仕事なんだけど笑
それでも気持ちが全然違う
{hashtag}
---
---
会議の議事録、前は翌日の午前までかかってた
今は会議終了10分後に共有してる

「仕事早いね」って言われるようになったけど
早くなったのは自分じゃないんだよな
{hashtag}
---
---
プレゼン資料の構成決め
1人でうんうん唸ってた2時間が
AIと壁打ちして20分になった

質が上がったかは正直わからない
でも「始められない」がなくなったのがでかい
{hashtag}
---
---
リサーチ仕事、丸1日かかってたのが半日になった

AIの調べた内容そのままは怖いから裏取りはする
それ込みでも半分
裏取りスキルの方が大事になってきてる気がする
{hashtag}
---

【ルール】
- 具体的な時間・回数などの数字をbefore/afterで1組入れる（盛らない・現実的に）
- どうやったかを一言だけ入れる（「箇条書きを渡して」など）
- 良いことだけで終わらせない。本音・引っかかり・余韻を残す
- お題の業務からズレないこと

【文体】
- 常体・口語。「です・ます」禁止
- 綺麗にまとめない

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_question_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIを使いながら働く会社員がX（旧Twitter）に投稿する「問いかけ・議論を呼ぶ質問系」のつぶやきを1件生成してください。
ターゲット：AI・副業・仕事に興味ある会社員・思わず返信したくなる・自分の答えを言いたくなる問いかけ
{avoid}
【良い例】
---
AIで仕事が早くなった分
業務量が増えただけだった

これって効率化できてる？
同じ現象の人いる？
{hashtag}
---
---
ChatGPTとClaude
みんな使い分けてる？

なんとなく使ってるけど
正直違いがよくわかってない笑
{hashtag}
---
---
AI使ってること
職場の人に言える環境？

自分は言いづらくて
こっそり使ってる笑
{hashtag}
---
---
AIを使いこなせてる自信ある？

「使ってる」と「使いこなせてる」って
全然別物な気がしてる
{hashtag}
---
---
月いくらAI系ツールに課金してる？

無料で十分派と
有料一択派に分かれる気がしてて
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
AIで一番「これは使えた」
ってなった使い方ってある？

自分はメール返信と議事録が多いけど
他にどんな使い方してるか気になってる
{hashtag}
---
---
仕事できる人って
何が違うんだろうって観察してる

なんかAIの使い方が上手いだけな気がしてきた
そういう時代なのかな
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

{style_guide()}

{ABSOLUTE_RULES}

ハッシュタグは「{hashtag}」「#副業」のどちらか内容に合う方を1つ、または付けない。URLは含めない。ツイート本文のみ出力。"""


def build_trend_prompt(trend_kw: str, history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""「{trend_kw}」というトレンドと仕事・AIを絡めた会社員のつぶやきをX（旧Twitter）用に1件生成してください。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIに興味ある会社員・「そう来るか」「わかる」と思わせる内容
{avoid}
【良い例（{trend_kw}の部分は実際のキーワードに変わる）】
---
「{trend_kw}」がトレンドになってるの見て

これAIと組み合わせたら
どう変わるんだろってついつい考えてしまった
#AI活用
---
---
「{trend_kw}」か〜
自分これ全然知らなかった

最近こういう流行りに疎くなったの
AIに情報収集任せすぎてるせいかも笑
#生成AI
---
---
「{trend_kw}」ってトレンドに入るくらいの話なんだ

AIで仕事してると
世の中の流れとズレてくるのを感じることがある
#AI活用
---
---
「{trend_kw}」で盛り上がってるの見て

なんかAIを使いこなせてる人と
そうじゃない人で見えてる景色が違う気がした
#生成AI
---
---
「{trend_kw}」って言葉
今日初めて知った

知らないまま仕事してたけど
AIに聞いたら30秒で全部わかった

これが便利なのか怖いのかよくわからない
#AI活用
---

{style_guide()}

{ABSOLUTE_RULES}

末尾に「#AI活用」または「#生成AI」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_hikaku_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIツールを複数使っている普通の会社員が、X（旧Twitter）に「ツール・使い方の比較と自分なりの結論」を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：どのAIをどう使えばいいか迷っている会社員。「自分はこうしてる」と返信したくなる内容
{avoid}
【良い例】
---
メールの下書きはChatGPT
長い資料の要約はClaude
調べものはGemini

って使い分けに落ち着いたけど
正直メールはどれでもいい気がしてる

みんな使い分けてる？1個で全部？
{hashtag}
---
---
AIへの指示、最初に長く書く派と短く何回も直す派いるけど
自分は完全に後者

最初から完璧な指示を書こうとしてた頃より
雑に投げて3回直す方が結局早い
{hashtag}
---
---
無料版で粘るか課金するか問題

自分は月3,000円課金してるけど
回収できてるかは計算したことない
「多分得してる」で思考停止してる

ちゃんと計算したことある人いる？
{hashtag}
---
---
音声入力でAIに指示するの試したけど
オフィスだと無理だった笑

家だと最高なんだけどな
結局場所で入力方法変えてる
{hashtag}
---

【ルール】
- 比較対象を2〜3個明確に出して、自分の結論をまず言い切る（そのあと揺れてもいい）
- 読んだ人が「自分はこう」と返信したくなる余地を残す
- 実在するツール名・現実的な使い方のみ。架空の機能・架空の料金を作らない

【文体】
- 常体・口語。「です・ます」禁止

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""

def build_shippai_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIを仕事で使っている普通の会社員が、X（旧Twitter）に「AI活用の失敗談と、そこから学んだ回避法」を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIを使う会社員。「あるある」かつ「気をつけよう」と思わせる
{avoid}
【良い例】
---
AIが出した数字をそのまま会議資料に入れて
「出典は？」って聞かれて凍った話

それ以来「その数字の根拠は？」って
AI自身に聞き返すのを癖にしてる
1回やらかすと忘れない
{hashtag}
---
---
謝罪メールをAIに書かせたら
丁寧すぎて逆に煽ってるみたいになった

「誠に遺憾ながら」とか普段使わないし
結局、要点だけ作らせて自分の言葉に直すのが正解だった
{hashtag}
---
---
社内資料をそのままAIに貼りそうになって手が止まった
固有名詞めっちゃ入ってるやつ

今は社名と人名を置き換えてから投げるルールにしてる
面倒だけど事故るよりまし
{hashtag}
---
---
AIの回答を信じて上司に即レスしたら間違ってた

調べる時間は10分の1になったけど
確認まで全部すっ飛ばしていいわけじゃなかった
当たり前のことに金曜の夜気づいた
{hashtag}
---

【ルール】
- 失敗→どう回避するようにしたか、を1セットで書く（説教くさくしない）
- 機密情報・間違った回答・トーンのズレなど、現実的にありそうな失敗のみ
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

    combined = f"{body}\n{tags}" if tags else body

    if x_weighted_length(combined) > TWEET_MAX_LEN:
        tag_weighted = x_weighted_length(f"\n{tags}") if tags else 0
        budget = TWEET_MAX_LEN - tag_weighted
        while body and x_weighted_length(body) > budget:
            body = body[:-1]
        body = body.rstrip()
        combined = f"{body}\n{tags}" if tags else body

    return combined


# ─────────────────────────────────────────────────────
# Bedrock 呼び出し
# ─────────────────────────────────────────────────────

_BEDROCK_SYSTEM = (
    "あなたは普通の会社員。AIを仕事で毎日使っていて、やり方・数字は具体的に話す。"
    "ツイート本文だけ出力。前置き・説明・「ツイート：」などは付けない。"
    "綺麗にまとめない。オチを決めようとしない。思ったことをそのまま書くような文体で。"
)

def invoke_bedrock(prompt: str) -> str:
    """Bedrockでツイートテキストを生成する。"""
    resp = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "system": _BEDROCK_SYSTEM,
            "temperature": 0.95,
            "messages": [{"role": "user", "content": prompt}],
        }),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    usage = result.get("usage", {})
    print(f"[Bedrock] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")
    return result["content"][0]["text"].strip()


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


def post_to_x(tweet_text: str, creds: dict, reply_to: str | None = None) -> dict:
    url   = "https://api.twitter.com/2/tweets"
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
    params_str = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}"
                          for k, v in sorted(oauth.items()))
    base_str   = "&".join(["POST", _percent_encode(url), _percent_encode(params_str)])
    sign_key   = (_percent_encode(creds["twitter_api_secret"]) + "&"
                  + _percent_encode(creds["twitter_access_token_secret"]))
    sig        = base64.b64encode(
        hmac.new(sign_key.encode(), base_str.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    auth_header = "OAuth " + ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"' for k, v in sorted(oauth.items())
    )
    payload_dict = {"text": tweet_text}
    if reply_to:
        payload_dict["reply"] = {"in_reply_to_tweet_id": reply_to}
    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
        headers={"Authorization": auth_header, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            print(f"[X] 投稿成功: tweet_id={result['data']['id']}")
            return result
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"X API エラー {e.code}: {e.read().decode()}") from e


# ─────────────────────────────────────────────────────
# Lambda エントリーポイント
# ─────────────────────────────────────────────────────

def lambda_handler(event, context):
    now     = datetime.now(JST)
    mode    = event.get("mode", "random")
    weekday = now.weekday()  # 0=月 1=火 2=水 3=木 4=金 5=土 6=日
    print(f"[Start] {now.strftime('%Y-%m-%d %H:%M JST')} / mode={mode} / weekday={weekday} / DRY_RUN={DRY_RUN}")

    # ── カテゴリ決定 ──────────────────────────────────
    used_categories = load_used_categories()
    trend_kw    = None
    url_article = None
    used_urls   = None

    if mode == "trend":
        trends   = fetch_google_trends_jp()
        trend_kw = pick_ai_relatable_trend(trends) if trends else None
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
    builders = {
        "recipe":   lambda h: build_recipe_prompt(h, cat_hashtag),
        "jissoku":  lambda h: build_jissoku_prompt(h, cat_hashtag),
        "hikaku":   lambda h: build_hikaku_prompt(h, cat_hashtag),
        "shippai":  lambda h: build_shippai_prompt(h, cat_hashtag),
        "fukugyo":  lambda h: build_fukugyo_prompt(h),
        "question": lambda h: build_question_prompt(h, cat_hashtag),
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
        tweet = f"{body}\n{htag}"
        # ハッシュタグ再付加後にXのweighted lengthで最終チェック（安全弁）
        if x_weighted_length(tweet) > TWEET_MAX_LEN:
            tag_weighted = x_weighted_length(f"\n{htag}")
            budget = TWEET_MAX_LEN - tag_weighted
            while body and x_weighted_length(body) > budget:
                body = body[:-1]
            tweet = f"{body.rstrip()}\n{htag}"
    else:
        tweet = trim_body_excluding_hashtags(raw)

    # Bot感軽減: 約35%はハッシュタグなしで投稿する（url_reaction は除く）
    if category != "url_reaction" and random.random() < NO_HASHTAG_RATE:
        stripped = re.sub(r'[ \t]*#\S+', '', tweet).rstrip()
        if stripped:
            tweet = stripped
            print("[Hashtag] 今回はタグなしで投稿")
    print(f"[Tweet]\n{tweet}\n[文字数] {len(tweet)}")

    # ── DRY RUN ───────────────────────────────────────
    if DRY_RUN:
        print("[DRY RUN] 投稿スキップ（SSM履歴は更新しません）")
        return {"statusCode": 200, "category": category, "tweet": tweet}

    # ── X投稿 ─────────────────────────────────────────
    creds  = get_x_credentials()
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

    return {
        "statusCode": 200,
        "category":   category,
        "tweet_id":   result.get("data", {}).get("id"),
        "keywords":   keywords,
        "timestamp":  now.isoformat(),
    }
