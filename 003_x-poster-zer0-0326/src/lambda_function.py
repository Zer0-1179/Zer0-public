"""
X AI Bot - Lambda Function
@Zer0_0326 — AIに頼りながらなんとか生きてる普通の会社員
4カテゴリ 共感・あるある系エンタメ 自動投稿Bot

スケジュール:
- 22:00 JST: ランダムカテゴリ (shigoto/fukugyo/jitsuwa/question) 1日1回
- 日曜10:00 JST: Google Trendsトレンド投稿（AIと絡められる場合のみ）

EventBridge Input:
  {"mode": "random"}  -- ランダムカテゴリ
  {"mode": "trend"}   -- Google Trendsトレンド（フォールバックあり）
"""

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

CATEGORIES           = ["shigoto", "fukugyo", "jitsuwa", "question", "suji"]
MAX_CATEGORY_HISTORY = 7
MAX_USED_URLS        = 28
URL_HISTORY_DAYS     = 90   # 使用済みURLの保持期間（日）

# カテゴリ別ハッシュタグ（リストの場合は投稿ごとにランダム選択）
HASHTAGS = {
    "shigoto":      ["#AI活用", "#生成AI", "#ChatGPT"],
    "fukugyo":      "#副業",
    "jitsuwa":      ["#生成AI", "#AI活用", "#ChatGPT"],
    "question":     ["#AI活用", "#生成AI"],
    "suji":         ["#生成AI", "#AI活用", "#ChatGPT"],
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

# 火曜・金曜のURL反応投稿用RSSフィード
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

# ---- 全カテゴリ共通ルール ----
ABSOLUTE_RULES = """【絶対ルール】
- 140文字以内（ハッシュタグ・URL含まず）
- ハッシュタグは指定したもの1個のみ（それ以外は付けない）
- 絵文字は最大1個
- 「〜です」「〜ます」禁止
- 「AIに任せたら全部解決した」で終わる抽象的な感想は禁止
- 結論・教訓・まとめで締めない

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
語尾→「…」「〜」「笑」「かも」「気がする」「だけど」「かな」
文中→「なんか」「ちょっと」「わりと」「けっこう」
反応→「え、待って」「まじか」「あ、そういうことか」
その他→独り言調・失敗談・試行錯誤・雑な数字（「もう2時間経ってた笑」等）

【終わり方】
結論を出さない。疑問・余韻・皮肉・「でも〜」で終わらせる。
読んだ人が「わかる」「自分も〜」と口に出したくなる終わり方を選ぶ。"""


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


def save_url_history(used_urls: list, new_url: str):
    """SSMに使用済みURL履歴をタイムスタンプ付きで保存する。
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
            with urllib.request.urlopen(req, timeout=10) as r:
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
    return f"""AIに関心のある会社員がX（旧Twitter）にAI記事を読んだ感想を投稿します。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AI・副業に興味ある会社員・「これ読みたい」「わかる」と思わせる内容
{avoid}
【今日の記事】
タイトル：{title}
概要：{desc}

【良い例（1行目でフックを作り、記事を読んだ後の具体的な感情を書く）】
---
これ読んで
「自分、全然使えてないじゃん」ってなった

一番ショックだったのはタイトルじゃなくて
最後の一文
---
---
タイトルだけで「知ってる」とスルーしかけた
読んだら全然違う話だった

ちゃんと読んでよかった笑
---
---
これ職場の人に共有したいやつ
でも「AI使ってるの？」ってなるのが面倒で

結局自分だけ知ってる状態がずっと続いてる
---
---
え、こんな使い方できるの
今まで全部手でやってた

しかも前から使えた機能だったらしい
知らなかっただけだった
---
---
読んでて「あ、これ自分がなんとなくやってたやつだ」ってなった

ちゃんと言語化されると
なるほどな〜ってなる
---
---
タイトル見た時は「またこの話か」と思ったけど
読んだら角度が全然違った

食わず嫌いしてた
---
---
これ読んで
試してみたくなった

仕事終わりにすぐやってみるやつ
---
---
AIって追いかけるだけで精一杯になってくる
でも追いかけないと置いていかれそうで

こういう記事がいちばん刺さる
---

【ルール】
- 記事タイトルや内容を直接紹介・要約しない（感想・感情を書く）
- 1行目で読者を止めるフックを作る
- 「です・ます」禁止
- 100文字以内でコンパクトに
- 絵文字は最大1個
- 綺麗に締めない・余白を残す
- URLは含めない（自動で付加される）

ツイート本文のみ出力。"""


def build_shigoto_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIに頼りながらなんとか生きてる普通の会社員がX（旧Twitter）に投稿する「仕事×AIのあるある・本音」を1件生成してください。
ターゲット：AIを使ってる・使い始めた会社員・「わかる〜」「自分も〜」と思わせる内容
{avoid}
【良い例】
---
上司に頼まれた資料
こっそりChatGPTに作らせたら

「いつもより良かった」って褒められた
言えるわけない笑
{hashtag}
---
---
AIで仕事が早くなった
その分仕事量が増えた

え、これって
効率化できてる？
{hashtag}
---
---
2時間悩んでた件
試しにAIに投げてみたら30秒で答え出てきた

さっきの2時間…
何してたんだろ
{hashtag}
---
---
AIのおかげで定時に帰れた
久しぶりすぎて何していいかわからなかった

自由な時間ってこんな感じだったっけ
{hashtag}
---
---
プレゼン前日に気づいた
資料ほぼ作ってない

慌ててAIに全部投げたら
なんか形になった

こういう使い方でいいのかとは思う
{hashtag}
---
---
会社でAIツールの使用が制限された
便利さを知ってしまった後だから

これはきつい
知らなければよかったまである
{hashtag}
---
---
今日あった嫌なことをAIに話してみた

「それは大変でしたね」って返ってきた
なんか少し楽になった

AIでいいのかとは思うけど
{hashtag}
---
---
入社1年目の子
AIの使い方が自分より全然上手くて

複雑な気持ちになった
素直にすごいとは思う笑
{hashtag}
---
---
会議の議事録
ずっと自分でまとめてたのをAIに任せたら

自分より読みやすくてちょっとへこんだ
…でも楽だからまあいいか
{hashtag}
---
---
上司への感情的な返信メール
AIに書き直させたら

丁寧すぎて自分っぽくなかった
まあでも送った
{hashtag}
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_fukugyo_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIに頼りながら副業もしている会社員がX（旧Twitter）に投稿する「副業の現実・本音」のつぶやきを1件生成してください。
ターゲット：副業に興味ある会社員・「わかる」「自分もやってみようかな」と思わせる内容
{avoid}
【良い例】
---
副業収入が初めて本業の1日分を超えた

翌朝、普通に出社しながら
心の中ではニヤニヤしてた
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
副業の月収が本業の日給を超えた日

「これいけるんじゃないか」って思ったら
翌月また下がった

副業ってそういうものらしい
#副業
---
---
副業をAIで効率化したら
余った時間でさらに別の副業を始めた

正しいのかどうかはわからない笑
でも止まれない
#副業
---
---
副業で失敗した
納期に間に合わなくてクライアントに怒られた

AIで作業してたのに
見積もりが甘かっただけだった

反省…
#副業
---
---
副業始めて一番変わったのは
本業で嫌なことがあっても

「まあ副業あるし」
ってなれること

心の余裕が全然違う
#副業
---
---
副業の確定申告
去年はパニックだったのに

今年はAIに聞きながらやったら
なんとかなった

毎年怖いのは変わらないけど
#副業
---
---
副業の作業をAIに手伝ってもらってる

自分でやる部分と任せる部分のバランスが難しい
全部任せたらそれは自分の副業なのかって
たまに思う
#副業
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「#副業」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_jitsuwa_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIを使いながら働く会社員が「実は〜してる」という告白・白状系のつぶやきをX（旧Twitter）用に1件生成してください。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIに興味ある会社員・「え、自分も〜」「言えてなかったけどわかる」と思わせる内容
{avoid}
【良い例】
---
実は会議中にAIに指示してた

返信文の下書きを作らせながら
うなずいてた

集中してるふりは完璧だったと思う
{hashtag}
---
---
正直に言うと
メールの7割はAIに書いてもらってる

でも「文章うまいね」って言われる
複雑な気持ち
{hashtag}
---
---
こっそり言うと
上司への報告書
もう1年以上AIに叩き台作らせてる

「最近しっかりしてきたね」って言われた
{hashtag}
---
---
実は仕事でわからないことがあっても
もう上司に聞いてない

ChatGPTに聞いた方が
早くて正確だから
{hashtag}
---
---
正直、今の職場の人に言えてないけど
仕事の半分くらいAIに任せてる

「仕事できる人」だと思われてるのが
なんか申し訳ない笑
{hashtag}
---
---
実はずっと黙ってたけど
嫌いな人からのメール

AIに返信させると
感情が入らなくてちょうどいい
{hashtag}
---
---
言えてなかったけど
プレゼンの質疑応答対策

全部AIと事前にシミュレーションしてた
「準備が完璧だったね」って言われた
{hashtag}
---
---
こっそり言うと
昨日の「自分で考えた提案」

AIと1時間かけて作ったやつ
「発想がユニークだね」って言われた
{hashtag}
---
---
実はもう
「自分でゼロから考えた」ことが
ほとんどない気がしてる

AIとの協働なのか
依存なのか
正直わからなくなってきた
{hashtag}
---
---
言えてないけど
転職活動の志望動機も
全部AIに添削してもらってた

面接で「熱意が伝わりました」って言われた
{hashtag}
---

{STYLE_GUIDE}

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

{STYLE_GUIDE}

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

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「#AI活用」または「#生成AI」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_suji_prompt(history: list, hashtag: str) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIを使いながら働く会社員がX（旧Twitter）に投稿する「数字・リスト型」のつぶやきを1件生成してください。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIに興味ある会社員・思わず保存・引用したくなる具体的な内容
{avoid}
【フォーマット】
「〇〇して変わった3つのこと」「AIで削れた業務3選」「〇〇してわかったこと」など
数字（3〜5個）を使ったリスト形式で書く。最後に一言オチを入れる。

【良い例】
---
AIを半年使って変わったこと3つ

・議事録：30分→5分
・メール返信：考える時間がほぼゼロ
・報告書：叩き台をAIに作らせるようになった

でも一番変わったのは「まず試す」癖がついたこと
{hashtag}
---
---
ChatGPTに課金して気づいたこと3つ

・無料版との差が思ったより大きい
・使いこなせてるかよくわからないまま1年経った
・でも解約できない

何かに依存してる感がある笑
{hashtag}
---
---
AIで「やめた仕事」3選

・メールの文章を自分で考えること
・議事録を手でまとめること
・資料の構成を0から考えること

やめて困ったことは今のところない
{hashtag}
---
---
仕事でAIを使い始めて変わったこと3つ

・残業が月20時間→5時間くらいになった
・「どうすればいいか」で詰まらなくなった
・上司より先に答えが出るようになった

でも給料は変わってない
{hashtag}
---
---
AIに慣れてきた人がよくやる失敗3つ

・プロンプトを長くしすぎる
・答えをそのまま使う
・できないことまで頼む

自分は全部やった笑
{hashtag}
---
---
副業でAI使い始めてよかったこと3つ

・作業時間が半分以下になった
・クオリティのムラが減った
・「これで合ってるかな」って迷う時間がなくなった

問題は副業が増えたこと
{hashtag}
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「{hashtag}」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


# ─────────────────────────────────────────────────────
# ツイート処理
# ─────────────────────────────────────────────────────

def trim_body_excluding_hashtags(text: str, limit: int = 140) -> str:
    """本文（ハッシュタグ除く）を140文字以内に収め、ハッシュタグと再結合する。"""
    lines      = text.strip().split('\n')
    hashtag_re = re.compile(r'^(#\S+(\s+#\S+)*)$')

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
        body = body[:limit - 1] + "…"

    return f"{body}\n{tags}" if tags else body


# ─────────────────────────────────────────────────────
# Bedrock 呼び出し
# ─────────────────────────────────────────────────────

_BEDROCK_SYSTEM = (
    "あなたはAIに頼りながらなんとか生きてる普通の会社員です。"
    "X（旧Twitter）に本音の短文を投稿します。"
    "指示されたフォーマットとルールを必ず守り、ツイート本文のみを出力してください。"
    "説明・前置き・「ツイート：」などの余計な文字は一切付けないでください。"
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


def post_to_x(tweet_text: str, creds: dict) -> dict:
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
    payload = json.dumps({"text": tweet_text}).encode()
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
    elif weekday in (1, 4):  # 火曜=1, 金曜=4
        used_urls   = load_url_history()
        url_article = fetch_url_reaction_article(used_urls)
        if url_article:
            category = "url_reaction"
            print(f"[URL Reaction] 記事取得成功: 「{url_article['title'][:50]}」")
        else:
            print("[URL Reaction] 記事取得失敗 → ローテーションカテゴリにフォールバック")
            category = pick_category(used_categories)
    elif weekday == 2:  # 水曜=2: question固定（エンゲージメント最大化）
        category = "question"
        print("[Category] 水曜固定: question")
    else:
        category = pick_category(used_categories)
    print(f"[Category] {category} (直近使用: {used_categories[-MAX_CATEGORY_HISTORY:]})")

    # ── 履歴読み込み ──────────────────────────────────
    history  = load_history(category)
    past_kws = [kw for e in history for kw in e.get("keywords", [])]
    print(f"[History] 過去キーワード数: {len(past_kws)}")

    # ── プロンプト構築 ────────────────────────────────
    cat_hashtag = pick_category_hashtag(category)
    builders = {
        "shigoto":  lambda h: build_shigoto_prompt(h, cat_hashtag),
        "fukugyo":  lambda h: build_fukugyo_prompt(h),
        "jitsuwa":  lambda h: build_jitsuwa_prompt(h, cat_hashtag),
        "question": lambda h: build_question_prompt(h, cat_hashtag),
        "suji":     lambda h: build_suji_prompt(h, cat_hashtag),
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
        # 本文は100文字以内、URL+ハッシュタグをlambda_handler側で付加
        body  = trim_body_excluding_hashtags(raw, limit=100)
        htag  = pick_hashtag(body + " " + url_article["title"])
        tweet = f"{body}\n{url_article['url']}\n{htag}"
    else:
        tweet = trim_body_excluding_hashtags(raw)
    print(f"[Tweet]\n{tweet}\n[文字数] {len(tweet)}")

    # ── DRY RUN ───────────────────────────────────────
    if DRY_RUN:
        print("[DRY RUN] 投稿スキップ（SSM履歴は更新しません）")
        return {"statusCode": 200, "category": category, "tweet": tweet}

    # ── X投稿 ─────────────────────────────────────────
    creds  = get_x_credentials()
    result = post_to_x(tweet, creds)

    # ── 履歴更新 ──────────────────────────────────────
    body_only = re.sub(r'#\S+', '', tweet).strip()
    keywords  = extract_keywords(body_only)
    save_history(category, history, keywords)
    if category == "url_reaction":
        save_url_history(used_urls, url_article["url"])
    else:
        save_used_categories(used_categories, category)

    return {
        "statusCode": 200,
        "category":   category,
        "tweet_id":   result.get("data", {}).get("id"),
        "keywords":   keywords,
        "timestamp":  now.isoformat(),
    }
