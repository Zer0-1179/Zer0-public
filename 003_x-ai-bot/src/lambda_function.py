"""
X AI Bot - Lambda Function
@Zer0_0326 — AIに頼りながらなんとか生きてる普通の会社員
4カテゴリ 共感・あるある系エンタメ 自動投稿Bot

スケジュール:
- 21:00 JST: ランダムカテゴリ (shigoto/fukugyo/kyokan/question) 1日1回
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

CATEGORIES           = ["shigoto", "fukugyo", "kyokan", "question"]
MAX_CATEGORY_HISTORY = 7
MAX_USED_URLS        = 28
URL_HISTORY_DAYS     = 90   # 使用済みURLの保持期間（日）

# カテゴリ別ハッシュタグ（既存カテゴリ用）
HASHTAGS = {
    "shigoto":      "#AI活用",
    "fukugyo":      "#副業",
    "kyokan":       "",
    "question":     "#AI活用",
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
- 140文字以内（ハッシュタグ含まず）
- ハッシュタグは指定したもの1個のみ（それ以外は付けない）
- 絵文字は最大1個
- 「〜です」「〜ます」禁止
- 綺麗に締めない・余白を残す
- オチをあえてつけない
- 技術用語（Lambda・API・AWS・クラウド等）禁止
- 【起】誰でも共感できる状況 → 【転】展開・AIが絡む → 【結】本音の反応
- 「AIに任せたら全部解決した」だけで終わる抽象的な感想は禁止

【禁止パターン】
- 「〜するようになった」で終わる感想文
- 「生産性が上がる」「効率化できる」などビジネス書的な表現
- 綺麗すぎる名言調
- 技術用語が入った内容
- 教訓・結論で締める投稿
- 絵文字の多用"""

STYLE_GUIDE = """【文体ルール】
キャラ：AIに頼りながらなんとか生きてる普通の会社員
以下の表現を自然に混ぜる：
語尾→「…」「〜」「笑」「かも」「気がする」「だけど」「かな」
文中→「なんか」「ちょっと」「わりと」「けっこう」
反応→「え、待って」「まじか」「あ、そういうことか」「なるほどな〜」
その他→独り言っぽく終わる、失敗談・試行錯誤を入れる、
       数字をあえて雑に使う（「もう2時間経ってた笑」等）"""


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
    except Exception:
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


def pick_hashtag(body: str) -> str:
    """本文・記事タイトルの内容に合わせてHASHTAG_POOLから最適なハッシュタグを選ぶ。
    スコアが同点の場合はランダム選択。マッチなしは '#AI活用' を返す。"""
    scores = {}
    for item in HASHTAG_POOL:
        score = sum(1 for kw in item["keywords"] if kw in body)
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
                desc  = item.findtext("description", "").strip()[:150]
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
                desc  = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")[:150]
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
ターゲット：AI・副業に興味ある会社員・「わかる」「これ読みたい」と思わせる内容
{avoid}
【今日の記事】
タイトル：{title}
概要：{desc}

【良い例（記事を読んだ後の本音コメントのスタイル）】
---
これ読んでみたけど
自分の使い方まだまだだなって思った

プロンプトってこんな工夫できるのか
知らなかった…
---
---
タイトル見た時は「知ってる」と思ったけど
読んでみたら全然知らないことが書いてあった

油断してた笑
---
---
AIのこういう使い方
自分は思いつかなかった

仕事に使えそうで
ちょっとテンション上がった
---
---
読んだら「あ、これやってた」ってなった
ちゃんと言語化されると納得感がある

なんか整理された気がする
---
---
こういう記事読むたびに
AIの使い方ってまだ全然広がりそうだなって思う

自分が使ってるのはほんの一部か
---
---
最初タイトルで「またこの話か」と思ったけど
読んだら違う切り口で面白かった

食わず嫌いしてた
---
---
これ職場の人に共有したいやつ
でも「AI使ってるの？」ってなるのが面倒で

結局自分だけ知ってる状態になりがち笑
---
---
AIって結局使いこなせてる人と
そうじゃない人の差が広がってる気がしてる

こういう記事読んで少しでも埋めたい
---
---
え、これ知らなかった
しばらく前から使えた機能なのに

なんで今まで知らなかったんだろ
---
---
読んでみたら自分がなんとなくやってたことが
ちゃんと理由があることがわかった

なるほどな〜ってなる記事だった
---
---
これ試してみたくなった
今日の仕事終わりにやってみよ

こういう記事が一番助かる
---
---
AIの話って進化が早すぎて
追いかけるだけで精一杯になってくる

でも追いかけないと置いていかれそうで
---
---
こういう使い方あるのか
確かに言われてみれば当たり前なんだけど

なんで思いつかなかったんだろ
---
---
読んでてふと思ったけど
AIって使い方次第で全然別のツールになるよな

奥が深い
---
---
タイトルから想像してたのと
全然違う内容だった

良い意味で期待を外された記事
---

【ルール】
- 上の例のような「記事を読んだ後の本音・気づき」を書く
- 記事タイトルや内容を直接紹介・要約しない（感想を書く）
- 「です・ます」禁止
- 100文字以内でコンパクトに
- 絵文字は最大1個
- 綺麗に締めない・余白を残す
- URLは含めない（自動で付加される）

ツイート本文のみ出力。"""


def build_shigoto_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIに頼りながらなんとか生きてる普通の会社員がX（旧Twitter）に投稿する「仕事×AIのあるある・本音」を1件生成してください。
ターゲット：AIを使ってる・使い始めた会社員・「わかる〜」と思わせる内容
{avoid}
【良い例】
---
月曜の朝
今週のタスク整理をAIに出させてみたら

量が多すぎてやる気なくした
AIのせいにしよ笑
#AI活用
---
---
会議の議事録
いつも自分でまとめてたのをAIに任せてみたら

自分より読みやすくてちょっとへこんだ
…でも楽だからまあいいか
#AI活用
---
---
残業2時間してた作業
「試しにAIに投げてみるか」ってやってみたら

10分で終わった
さっきまでの2時間は何だったんだろ
#AI活用
---
---
上司への返信メール
感情的にならないようにAIに書いてもらったら

丁寧すぎて自分っぽくなかった
まあでも送った
#AI活用
---
---
月末の報告書
毎月詰まるのでAIに叩き台作らせてみたら

上司に「今月のまとめ良かった」って言われた
AIのことは言えなかった笑
#AI活用
---
---
明日締め切りの資料
何も手についてなかった

とりあえずAIに投げてみたら
なんかそれだけで落ち着いた
#AI活用
---
---
「これAIに頼んでいいのかな」
って迷ってる間に

隣の同僚はもう使って終わらせてた
迷ってる時間がいちばんもったいない
#AI活用
---
---
2時間悩んでた問題
試しにAIに聞いてみたら

30秒で答え出てきた
さっきの2時間…
#AI活用
---
---
会社でAIツールの使用が制限された

便利さを知ってしまった後だから
余計きつい

知らなければよかったまである
#AI活用
---
---
AIのおかげで今日は定時に帰れた
久しぶりすぎて何していいかわからなかった

自由な時間ってこんな感じだったっけ
#AI活用
---
---
入社1年目の子
AIの使い方が自分より全然上手くて

なんか複雑な気持ちになった
素直にすごいとは思う笑
#AI活用
---
---
AIで仕事が早くなった
その分仕事量が増えた

なんかちょっと違う気がするんだけど
気のせいかな
#AI活用
---
---
今日あった嫌なことをAIに話してみた

「それは大変でしたね」って返ってきた
なんか少し楽になった

AIでいいのかって気もするけど
#AI活用
---
---
プレゼン前日に気づいた
資料ほぼ作ってない

慌ててAIに構成から出させたら
意外と形になった

もう毎回こうしよかな笑
#AI活用
---
---
AIに質問したら
全然的外れな回答が来た

一人で笑ってしまった
こういう日もある
#AI活用
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「#AI活用」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_fukugyo_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIに頼りながら副業もしている会社員がX（旧Twitter）に投稿する「副業の現実・稼ぎ系」のつぶやきを1件生成してください。
ターゲット：副業に興味ある会社員・「自分もできそう」「わかる」と思わせる内容
{avoid}
【良い例】
---
副業を始めて3ヶ月
収益が初めて発生した日

金額は大したことないけど
自分で稼いだっていう感覚が全然違った
#副業
---
---
本業終わってから副業しようとしたけど
体力が全然残ってない

AIに作業の半分を任せてから
なんとか続けられてる
#副業
---
---
副業でnote始めてみた
最初の記事を書くのに3時間かかった

AIに構成だけ出してもらったら
次からは1時間で書けるようになった
#副業
---
---
クラウドソーシングで初めて案件取れた
金額は3000円だったけど

なんかもう本業やめられる気がしてた笑
現実はそんな甘くない
#副業
---
---
副業の月収が本業の日給を超えた日

「これいけるんじゃないか」
って思ったけど翌月また下がった

副業ってそういうものらしい
#副業
---
---
副業の確定申告
去年は何もわからなくてパニックだったのを

今年はAIに聞きながらやったら
なんとかなった

毎年これが怖い
#副業
---
---
副業始めてから
時間の使い方が変わった

ダラダラ見てたYouTubeの時間が
気づいたら副業の時間になってた
#副業
---
---
副業の提案文
毎回うまく書けなかったのを

AIに叩き台作らせてから
通過率が変わった気がする
#副業
---
---
副業で失敗した
納期に間に合わなくてクライアントに怒られた

AIで作業してたのに
見積もりが甘かっただけだった笑
#副業
---
---
副業の収入が安定してきた
でも本業より好きかどうかはまだわからない

お金のためにやってるのか
好きでやってるのか
#副業
---
---
副業を始めて良かったと思う瞬間
本業で嫌なことがあった日でも

「まあ副業あるし」
って思えること

それだけで全然違う
#副業
---
---
副業の作業をAIに手伝ってもらってる

自分でやる部分と任せる部分の
バランスが難しい

全部任せたらそれは自分の副業なのか笑
#副業
---
---
副業始めたきっかけは
本業の給料じゃ足りないから

でも今は
副業の方が楽しくなってきてる

どっちが本業かわからなくなってきた
#副業
---
---
副業仲間ができた
同じくAI使いながら稼いでる人たち

情報交換してたら
自分の使い方がまだまだだってわかった
#副業
---
---
副業をAIで効率化したら
余った時間でさらに別のことを始めた

これが正しいのかどうかは
よくわからない笑
#副業
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「#副業」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


def build_kyokan_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""会社員の「共感・本音・愚痴系」のつぶやきをX（旧Twitter）用に1件生成してください。
ターゲット：会社員全般・「それな」「わかる」と思わせる本音
{avoid}
【良い例】
---
月曜の朝
「今週もがんばるか」って気持ちになれない

とりあえず出社してる
それだけで十分だと思うことにした
---
---
また会議が3時間あった
決まったことは何もない

この時間で仕事できたのに
って毎回思う
---
---
残業して帰ったら
もう何もしたくなくて

ご飯食べてすぐ寝た
これが続いてる
---
---
頑張って結果出したのに
評価に全然反映されなかった

モチベどうやって保てばいいんだろ
正直わからない
---
---
転職しようか迷ってる
でも今の環境が悪いわけでもない

なんか現状維持がいちばん怖い気もする
動けない自分もいる
---
---
休日に仕事のこと考えてた
「あの対応合ってたかな」って

やめようと思っても止まらない
頭の中にいる上司
---
---
なんか今日やる気が出ない
理由は特にない

でも仕事は終わらない
こういう日が一番きつい
---
---
同期が先に昇進した
おめでとうとは言えたけど

心の中は複雑だった
素直じゃないな自分
---
---
AIに仕事を任せるのが増えてきた
便利なのはわかってる

でも自分の仕事って何なんだろ
ってたまに考える
---
---
深夜にひとりで作業してると
なんか孤独な気持ちになる

でも集中できるのは深夜なんだよな
矛盾してる
---
---
給料が上がらない
物価は上がってる

何かを変えなきゃいけないのはわかってる
でも何を変えればいいのかがわからない
---
---
仕事ができる人って
何が違うんだろうって観察してる

なんかAIの使い方が上手いだけな気がしてきた
そういう時代なのかも
---
---
「仕事好きですか？」って聞かれたら
正直答えられない

嫌いではないけど
好きかと言われると…
---
---
有給を取ろうとしたら
なんか申し訳なくなった

取る権利あるのに
この感覚どこから来てるんだろ
---
---
今の会社で5年経った
転職すると言い続けて5年

気づいたら30代になってた
時間が経つのが怖い
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

ハッシュタグは付けない。URLは含めない。ツイート本文のみ出力。"""


def build_question_prompt(history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""AIを使いながら副業もしている会社員がX（旧Twitter）に投稿する「問いかけ・共感を誘う質問系」のつぶやきを1件生成してください。
ターゲット：AI・副業・仕事に興味ある会社員・思わず反応したくなる問いかけ
{avoid}
【良い例】
---
仕事でAI使ってる人に聞きたいんだけど
どんなことに使ってる？

自分はメール返信と議事録が多いけど
他にある？
#AI活用
---
---
副業してる人って
月どのくらい稼いでる？

収益化できるまでどのくらいかかったか
気になってる
#AI活用
---
---
ChatGPTとClaudeって
みんな使い分けてる？

なんとなく使ってるけど
正直違いがよくわかってない笑
#AI活用
---
---
会社でAIツールって解禁されてる？

使える会社と使えない会社で
かなり差が出てきてる気がする
#AI活用
---
---
残業って月何時間くらいしてる？

「当たり前」だと思ってたけど
最近それが普通じゃない気がしてきた
---
---
転職って考えたことある？

「いつでも動ける準備」をしてる人と
してない人でかなり違う気がしてて
---
---
AIで一番「これは使える」
と思った使い方ってある？

みんながどう使ってるか
純粋に気になってる
#AI活用
---
---
副業って何から始めた？

始めたいけど何をすればいいか
わからない人けっこう多そう
#副業
---
---
月いくらAI関係に課金してる？

無料プランで十分派と
有料一択派に分かれる気がしてる
#AI活用
---
---
仕事のモチベって
どうやって保ってる？

上がる時と下がる時の差が激しすぎて
自分でよくわからなくなってきた
---
---
AI使う前と後で
一番変わったことって何？

仕事の仕方なのか考え方なのか
人それぞれな気がして
#AI活用
---
---
副業と本業どっちが好き？

副業の方が好きになってきてる人って
けっこういそう
#副業
---
---
定時に帰れてる？

「定時に帰る」ことを
達成感と感じてる自分がいる
---
---
AIを使いこなせてる自信ある？

みんなが「使ってる」は言うけど
「使いこなせてる」はまた別な気がしてる
#AI活用
---
---
1年後どうなりたいか
決まってる？

なんとなく生きてたら
気づいたら30代になってた笑
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

ハッシュタグは内容に合わせて「#AI活用」「#副業」のどちらか1つ、または付けない。URLは含めない。ツイート本文のみ出力。"""


def build_trend_prompt(trend_kw: str, history: list) -> str:
    avoid = _past_keywords_hint(history)
    return f"""「{trend_kw}」というトレンドと仕事・AIを絡めた会社員のつぶやきをX（旧Twitter）用に1件生成してください。
キャラ：AIに頼りながらなんとか生きてる普通の会社員
ターゲット：AIに興味ある会社員・「へえー」「わかる」と思わせる内容
{avoid}
【良い例】
---
「{trend_kw}」って最近よく聞くな〜

これもAIと組み合わせたら
どう変わるんだろってちょっと考えてしまった
#AI活用
---

{STYLE_GUIDE}

{ABSOLUTE_RULES}

末尾に「#AI活用」を1行で付ける。URLは含めない。ツイート本文のみ出力。"""


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

def invoke_bedrock(prompt: str) -> str:
    """Bedrockでツイートテキストを生成する。"""
    resp = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
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
    else:
        category = pick_category(used_categories)
    print(f"[Category] {category} (直近使用: {used_categories[-MAX_CATEGORY_HISTORY:]})")

    # ── 履歴読み込み ──────────────────────────────────
    history  = load_history(category)
    past_kws = [kw for e in history for kw in e.get("keywords", [])]
    print(f"[History] 過去キーワード数: {len(past_kws)}")

    # ── プロンプト構築 ────────────────────────────────
    builders = {
        "shigoto":  build_shigoto_prompt,
        "fukugyo":  build_fukugyo_prompt,
        "kyokan":   build_kyokan_prompt,
        "question": build_question_prompt,
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
