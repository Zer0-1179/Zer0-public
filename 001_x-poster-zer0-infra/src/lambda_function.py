import os, json, boto3, urllib.request, xml.etree.ElementTree as ET, random, re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from requests_oauthlib import OAuth1
import requests

JST = timezone(timedelta(hours=9))
HISTORY_PARAM = "/xposter/posted-history"
MAX_USED_URLS       = 28
MAX_USED_TYPES      = 6
MAX_ARTICLE_AGE_DAYS = 14

RSS_FEEDS = [
    {"url": "https://aws.amazon.com/jp/new/feed/", "source": "aws_news", "label": "AWS公式ニュース"},
    {"url": "https://aws.amazon.com/jp/blogs/aws/feed/", "source": "aws_blog", "label": "AWSブログ"},
    {"url": "https://dev.classmethod.jp/feed/", "source": "classmethod", "label": "クラスメソッド"},
    {"url": "https://zenn.dev/topics/aws/feed", "source": "zenn", "label": "Zenn"},
    {"url": "https://qiita.com/tags/aws/feed.atom", "source": "qiita", "label": "Qiita"},
]

# 王道AWSサービスキーワード（マッチ数が多い記事を優先選択する）
MAINSTREAM_KEYWORDS = [
    "EC2", "S3", "Lambda", "RDS", "VPC", "IAM", "CloudWatch",
    "ECS", "EKS", "Fargate", "DynamoDB", "CloudFront", "API Gateway",
    "SQS", "SNS", "SES", "Bedrock", "CodePipeline", "CodeBuild",
    "Elastic Load Balancing", "ELB", "ALB", "NLB", "Auto Scaling",
    "Route 53", "CloudFormation", "Systems Manager", "SSM",
    "Secrets Manager", "KMS", "WAF", "Shield", "GuardDuty",
    "CloudTrail", "Config", "Trusted Advisor", "Cost Explorer",
    "Glue", "Athena", "Redshift", "EMR", "Kinesis", "MSK",
    "Step Functions", "EventBridge", "AppSync",
    "Amazon Bedrock", "Amazon Q", "Amazon Connect",
    "Amazon WorkSpaces", "Amazon Chime", "Amazon Lex",
    "Amazon Polly", "Amazon Rekognition", "Amazon Transcribe",
    "Amazon Translate", "Amazon Comprehend", "Amazon Kendra",
    "Amazon SageMaker", "Amazon Aurora", "Amazon ElastiCache",
    "Amazon MemoryDB", "Amazon OpenSearch", "Amazon Neptune",
    "Amazon Timestream", "Amazon QLDB", "Amazon Macie",
    "Amazon Inspector", "Amazon Detective", "Amazon Fraud Detector",
    "Amazon CodeGuru", "Amazon DevOps Guru", "Amazon Lookout",
    "Amazon Personalize", "Amazon Forecast", "Amazon Textract",
]

SLOTS = {
    "morning": {
        "sources": ["aws_news", "aws_blog", "zenn", "qiita"],
        "with_url": False,
        "types": ["news_reaction", "aws_tips", "aws_question"],
    },
    "evening": {
        "sources": ["aws_news", "aws_blog", "classmethod", "zenn", "qiita"],
        "with_url": True,
        "types": ["news_intro", "aws_failure", "news_comparison", "classmethod_reaction"],
    },
}

# @Zer0_Infra の口調再現用 Few-shot 例
FEW_SHOT_MORNING = """・「なんか今日はAmazonQの調子がよくない😢」
・「今更ながらclaude codeインストールした〜 自分ではできなかった領域も手が付けられるし、使い方もっと学んだらやりたい事が結構できそう!! これはもっと早くに使って覚えるべきだったな🕯」
・「リツアンSTCに転籍して1ヶ月。仕事自体は同じだけど、給料と働き方は前より楽に。SES特有の雑務がなくなったのも地味に大きい。このまま良い感じで続けたい。」
・「最近現行のスクリプトの読解と流用方法に時間使ってるなぁ🤔 少し勉強しますか〜」"""

FEW_SHOT_EVENING = """・「今回のプロジェクトでわざわざ指定時間内はCloudWatchアラームが発砲しないようにLambdaで作った...現状東京リージョンで使えないみたいだから、今回の構成が無駄ではなかったけど今後はこれで楽に設定できるのは素晴らしい🌟」
・「最近現行のスクリプトの読解と流用方法に時間使ってるなぁ🤔 そして、powershellが全然わからん... 少し勉強しますか〜」
・「シェルのスクリプトの改行コードで問題がでた。ついでにPythonの改行コードについて調べたら、PythonはCRLFやLFが混在してても問題無いことを知った〜 Pythonはもっと勉強するべきだな〜」
・「wslってユーザごとにインストール必要なんだ🤔 EC2がwsl2に対応してればwslの共有もできるようだけど、wsl1しか対応してないからユーザ事にインストールしたわ〜 ほーんてかんじ」"""

# 末尾の締め方パターン（投稿ごとに1つ抽選してプロンプトに注入する）
ENDING_PATTERNS = {
    "question": """- 締め方：読者に反応を促す問いかけで終える
  例：「みんなどこに落ち着いてる？」「同じ経験ある人いる？」「どう対処してる？」
      「現場でもこんな感じ？」「もっといい方法あったら教えて」
  ※ 不自然になる場合は無理に入れなくてよい""",
    "empathy": """- 締め方：読者が「わかる」と思う一言で終える
  例：「地味にハマりポイントなんだよな」「こういうの誰も教えてくれないやつ」
      「知ってると知らないとで結構差が出る」「わかる人にはわかる」""",
    "plain": """- 締め方：感想や気づきをそのまま言って普通に終わる。まとめようとしない
  例：「もっと早く知りたかった」「これは覚えておきたい」「少し試してみたくなった」
      「思ったより簡単だった」「これ結構使えそう」""",
    "open": """- 締め方：きれいに締めない。言い切らずに余韻で終わってよい
  例：「まあ様子見かな」「どうなんだろな」「あとで調べる」「うーん」""",
}


def pick_ending_rule() -> str:
    """締め方パターンを重み付きで1つ選ぶ（問いかけ偏重を防ぐ）。"""
    key = random.choices(
        ["question", "empathy", "plain", "open"],
        weights=[25, 25, 35, 15],
    )[0]
    return ENDING_PATTERNS[key]


# AIっぽさを消すための共通ルール
HUMAN_RULE = """- 同じ言い回し・同じリズムを毎回使わない（「〜なんだろう🤔」「面白いな〜」の多用禁止）
- 文字数上限まで書こうとしない。短くても全然いい
- 英単語の前後に不要な半角スペースを入れない（「AWS の」ではなく「AWSの」）
- きれいに整いすぎた文にしない。多少雑な並びでいい"""

# 事実の正確性ルール（誤情報を投稿しないための共通ルール）
FACT_RULE = """- 事実の正確性が最優先。サービス仕様・対応リージョン・料金・制限値・機能の有無は、記事に書いてあることだけを使う
- 記事に書かれていない仕様・数値を推測で断定しない。自信がない事実には触れない（感想・疑問の形ならOK）"""

# classmethod_reaction の3パターン
CLASSMETHOD_PATTERNS = [
    "発見・得した系：「知らなかった、得した、これは使える」という気づきを自然に表現する",
    "どっち派・現場どうしてる系：「みんなの現場では？」「どっち使ってる？」という問いかけを自然に盛り込む",
    "共感・あるある系：「わかる〜」「自分もそう」という共感を誘う内容にする",
]


def pick_mainstream_article(articles: list) -> dict:
    """王道サービスへの言及数でスコアリングし、最もスコアの高い記事を返す。
    zenn・qiita はスコア1未満の記事を除外する。除外後に候補が0件の場合は
    aws_news・aws_blog のみにフォールバックする。"""
    if not articles:
        raise RuntimeError("全RSSフィードから記事が取得できませんでした")
    def score(article):
        text = (article.get("title", "") + " " + article.get("desc", "")).upper()
        return sum(1 for kw in MAINSTREAM_KEYWORDS if kw.upper() in text)

    scored = [(score(a), a) for a in articles]

    # zenn・qiita はスコア1以上のみ候補にする
    filtered = [
        (s, a) for s, a in scored
        if a["source"] not in ("zenn", "qiita") or s >= 1
    ]

    # フォールバック：フィルタ後が空なら公式ソースのみに絞る
    if not filtered:
        filtered = [
            (s, a) for s, a in scored
            if a["source"] in ("aws_news", "aws_blog")
        ]
    # 最終フォールバック：全記事
    if not filtered:
        filtered = scored

    filtered.sort(key=lambda x: x[0], reverse=True)
    best_score, best_article = filtered[0]
    print(f"[Pick] score={best_score} / {best_article['title'][:60]}")
    return best_article


def load_history(ssm_client) -> dict:
    """SSMから投稿履歴を読み込む。パラメータが存在しない場合は空の履歴を返す。"""
    try:
        value = ssm_client.get_parameter(Name=HISTORY_PARAM)["Parameter"]["Value"]
        return json.loads(value)
    except ssm_client.exceptions.ParameterNotFound:
        print("[History] パラメータ未存在。空履歴で初期化します。")
        return {"used_urls": [], "used_types": [], "used_keywords": [], "last_updated": None}
    except Exception as e:
        print(f"[History] 読み込みエラー（空履歴で続行）: {e}")
        return {"used_urls": [], "used_types": [], "used_keywords": [], "last_updated": None}


def save_history(ssm_client, history: dict):
    """SSMに投稿履歴を保存する。"""
    history["last_updated"] = datetime.now(JST).isoformat()
    ssm_client.put_parameter(
        Name=HISTORY_PARAM,
        Value=json.dumps(history, ensure_ascii=False),
        Type="String",
        Overwrite=True,
    )
    print(f"[History] 保存完了: URL {len(history['used_urls'])}件, Type {len(history['used_types'])}件")


def pick_post_type(slot_types: list, used_types: list) -> str:
    """used_types（直近MAX_USED_TYPES件）に含まれていないタイプからランダム選択。
    全タイプが直近に含まれている場合は最も古く使われたタイプを選ぶ。"""
    recent = used_types[-MAX_USED_TYPES:]
    unused = [t for t in slot_types if t not in recent]
    if unused:
        return random.choice(unused)
    # 全タイプが直近に含まれている場合：recent は古い順なので先頭から探す
    for t in recent:
        if t in slot_types:
            return t
    return random.choice(slot_types)


def build_hashtags(main: dict, max_extra: int = 2) -> str:
    """記事内容からハッシュタグを生成する。
    #AWS は必ず含め、マッチしたサービス名から最大 max_extra 個をランダム追加する。"""
    text = (main.get("title", "") + " " + main.get("desc", "")).upper()
    matched = []
    seen = set()
    for kw in MAINSTREAM_KEYWORDS:
        if kw.upper() in text:
            tag = "#" + kw.replace(" ", "")
            # 同義サービスの正式名称は略称タグに寄せる
            tag = {"#ElasticLoadBalancing": "#ELB", "#SystemsManager": "#SSM"}.get(tag, tag)
            norm = tag.upper()
            # 「#Bedrock」と「#AmazonBedrock」のような包含関係の重複は最初の方（短い方）だけ残す
            if any(norm in s or s in norm for s in seen):
                continue
            matched.append(tag)
            seen.add(norm)
    extra = random.sample(matched, min(max_extra, len(matched)))
    return " ".join(["#AWS"] + extra)


def is_japanese(text: str) -> bool:
    """テキストに日本語文字（ひらがな・カタカナ・漢字）が含まれるか判定する。"""
    return bool(re.search(r'[ぁ-んァ-ン一-龥]', text))


def extract_topic_keywords(title: str) -> list:
    """MAINSTREAM_KEYWORDSからタイトルにマッチするキーワードを抽出してUPPERで返す"""
    text = title.upper()
    return [kw.upper() for kw in MAINSTREAM_KEYWORDS if kw.upper() in text]


def is_topic_duplicate(article: dict, used_keywords: list) -> bool:
    """extract_topic_keywordsの結果とused_keywordsの直近40件を比較し、
    1つ以上被っていればTrueを返す"""
    keywords = extract_topic_keywords(article.get("title", ""))
    if not keywords:
        return False
    recent = used_keywords[-40:]
    overlap = sum(1 for kw in keywords if kw in recent)
    return overlap >= 1


SERVICE_COOLDOWN_DAYS = 3


def is_service_in_cooldown(article: dict, used_services: dict) -> bool:
    """記事の主要サービスが直近SERVICE_COOLDOWN_DAYS日以内に投稿済みであればTrueを返す"""
    keywords = extract_topic_keywords(article.get("title", ""))
    today = datetime.now(JST).date()
    for kw in keywords:
        last = used_services.get(kw)
        if last:
            last_date = datetime.fromisoformat(last).date()
            if (today - last_date).days < SERVICE_COOLDOWN_DAYS:
                return True
    return False


def is_too_old(article: dict) -> bool:
    """公開日がMAX_ARTICLE_AGE_DAYS日より古い場合Trueを返す。日付不明の場合はFalse"""
    pub_str = article.get("pub_date", "")
    if not pub_str:
        return False
    try:
        pub = parsedate_to_datetime(pub_str)
    except Exception:
        try:
            pub = datetime.fromisoformat(pub_str)
        except Exception:
            return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    return pub.astimezone(timezone.utc) < cutoff


def fetch_article_text(url: str, max_chars: int = 2500) -> str:
    """メイン記事ページの本文を取得しテキスト化する（事実確認用の抜粋）。失敗時は空文字。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        print(f"[Article] 本文取得: {len(text)}文字 → 抜粋{min(len(text), max_chars)}文字")
        return text[:max_chars]
    except Exception as e:
        print(f"[Article] 本文取得失敗（RSS概要のみで続行）: {e}")
        return ""


def verify_tweet(bedrock, body: str, title: str, article_excerpt: str, max_len: int) -> str:
    """生成ツイートの事実主張を記事本文と突き合わせて検証し、必要なら修正版を返す。"""
    prompt = f"""あなたはAWS技術記事の監修者。以下のX投稿草案に含まれる「事実の主張」だけを検証してください。

【根拠（記事タイトル）】{title}
【根拠（記事本文抜粋）】
{article_excerpt or "（本文取得失敗。タイトルのみが根拠）"}

【投稿草案】
{body}

【検証ルール】
- サービス仕様・対応リージョン・料金・制限値・機能の有無などの事実主張が、根拠と矛盾していないか確認する
- 根拠に書かれておらず、AWSの一般知識としても確実といえない事実主張は、削除するか感想・疑問の形に書き換える
- 個人の感想・体験談・問いかけ・口調・文体・絵文字・改行はそのまま維持する
- {max_len}文字以内を維持する

【出力形式】
JSONのみを出力する。説明・見出し・修正理由は一切書かない。
- 問題なし → {{"tweet": "<草案を一字も変えずそのまま>"}}
- 修正あり → {{"tweet": "<修正後の本文>"}}"""
    resp = bedrock.invoke_model(
        modelId="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 400,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": '{"tweet":'},  # プリフィルでJSON出力を強制
            ]})
    )
    raw = '{"tweet":' + json.loads(resp["body"].read())["content"][0]["text"]
    try:
        checked = json.JSONDecoder().raw_decode(raw)[0]["tweet"].strip()
    except Exception as e:
        print(f"[Verify] 出力パース失敗（草案をそのまま使用）: {e}")
        return body
    if checked != body:
        print(f"[Verify] 事実確認で修正あり:\n{checked}")
    else:
        print("[Verify] 事実確認OK（修正なし）")
    return checked


def build_prompt(post_type: str, main: dict, news_text: str, article_excerpt: str = "") -> str:
    title = main["title"]
    if not article_excerpt:
        article_excerpt = "（本文取得失敗。記事タイトルとRSS概要のみを根拠とし、それ以外の事実は書かない）"

    # 投稿ごとに目安文字数と締め方を抽選する（毎回同じ長さ・同じ締めになるのを防ぐ）
    if post_type in ("news_reaction", "aws_tips", "aws_question"):
        length_rule = f"- {random.choice([50, 70, 90])}文字前後を目安に（最大100文字）"
    else:
        length_rule = f"- {random.choice([70, 100, 140])}文字前後を目安に（最大160文字）"
    ending_rule = pick_ending_rule()

    if post_type == "news_reaction":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似してAWSニュースへの一言コメントを書いてください。

【実際の投稿例】
{FEW_SHOT_MORNING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【メイン記事の本文抜粋（事実はこの範囲内のことだけ書く）】
{article_excerpt}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- ニュースを読んで感じた一言・気づきをそのまま書く
- 情報を整理して伝えようとしない
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "aws_tips":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調でAWS実務Tipsを1つ書いてください。

【実際の投稿例】
{FEW_SHOT_MORNING}

【参考にするニュース（雰囲気を合わせる用）】
{news_text}

【ルール】
- 実際に現場で役立つAWS Tips（コスト削減・セキュリティ・運用効率など）を1つ
- 「知らなかった、得した」と思わせる内容が理想
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "aws_question":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調でAWSエンジニアのあるある・共感ネタを書いてください。

【実際の投稿例】
{FEW_SHOT_MORNING}

【参考にするニュース（話題のヒントにする）】
{news_text}

【ルール】
- AWSエンジニアなら「わかる〜」と思う体験談・あるあるを1つ
- または「みんなどうしてる？」と問いかける質問形式でもOK
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "news_intro":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似してAWSニュースへのコメントを書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【メイン記事の本文抜粋（事実はこの範囲内のことだけ書く）】
{article_excerpt}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 感想や気づきをそのまま書く感じで
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個、多くても2個
- URLは含めない（別途付加する）
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "aws_failure":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調で、AWSニュースに関連した「ハマりポイント・失敗談・よくある落とし穴」を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【メイン記事の本文抜粋（事実はこの範囲内のことだけ書く）】
{article_excerpt}

【ルール】
- このニュースに関連したサービスで自分がハマった・ヒヤッとした経験談や落とし穴を1つ
- 「気をつけて」「これで詰まった」「やらかした」系の内容が理想
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "news_comparison":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調で、AWSニュースをもとに「比較・意見・どっち派？」系の投稿を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【メイン記事の本文抜粋（事実はこの範囲内のことだけ書く）】
{article_excerpt}

【ルール】
- このニュースに関連して「AとBどっちが好き？」「自分はこっち派」「こっちの方が実用的では？」系の意見や問いかけ
- 読んだ人が思わず反応したくなる内容が理想
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    elif post_type == "classmethod_reaction":
        pattern = random.choice(CLASSMETHOD_PATTERNS)
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似して、クラスメソッドの技術記事への反応を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日の記事】
タイトル：{title}
参考：{news_text}

【メイン記事の本文抜粋（事実はこの範囲内のことだけ書く）】
{article_excerpt}

【今回の投稿パターン】
{pattern}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
{length_rule}
{HUMAN_RULE}
{FACT_RULE}
{ending_rule}
- ツイート本文のみ出力"""

    return ""


def get_ssm(name):
    ssm = boto3.client("ssm")
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def fetch_rss(sources):
    articles = []
    for feed in RSS_FEEDS:
        if feed["source"] not in sources:
            continue
        try:
            req = urllib.request.Request(feed["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                tree = ET.parse(r)
            # RSS 2.0形式
            for item in tree.findall(".//item")[:5]:
                title    = item.findtext("title", "").strip()
                link     = item.findtext("link", "").strip()
                desc     = item.findtext("description", "").strip()[:150]
                pub_date = item.findtext("pubDate", "").strip()
                if title and link:
                    articles.append({"source": feed["source"], "label": feed["label"], "title": title, "url": link, "desc": desc, "pub_date": pub_date})
            # Atom形式（Qiita等）
            for entry in tree.findall(".//{http://www.w3.org/2005/Atom}entry")[:5]:
                title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link  = ""
                for lk in entry.findall("{http://www.w3.org/2005/Atom}link"):
                    if lk.get("rel") in (None, "alternate"):
                        link = lk.get("href", "")
                        break
                desc     = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")[:150]
                pub_date = (entry.findtext("{http://www.w3.org/2005/Atom}updated") or "").strip()
                if title and link:
                    articles.append({"source": feed["source"], "label": feed["label"], "title": title, "url": link, "desc": desc, "pub_date": pub_date})
        except Exception as e:
            print(f"[RSS] {feed['label']} error: {e}")
    return articles


def lambda_handler(event, context):
    now      = datetime.now(JST)
    slot_key = os.environ.get("FORCE_SLOT") or "evening"
    if slot_key not in SLOTS:
        print(f"[Warning] 無効なFORCE_SLOT値: '{slot_key}' → evening にフォールバック")
        slot_key = "evening"
    slot     = SLOTS[slot_key]
    with_url = slot["with_url"]

    prefix = os.environ.get("SSM_PREFIX", "/xposter")
    ssm    = boto3.client("ssm")

    # SSMから投稿履歴を読み込む
    history = load_history(ssm)

    # 投稿タイプをSSM履歴ベースで選択
    post_type = pick_post_type(slot["types"], history.get("used_types", []))
    print(f"[Start] {now.strftime('%Y-%m-%d %H:%M JST')} / {slot_key} / {post_type} / URL={'あり' if with_url else 'なし'}")

    api_key    = get_ssm(f"{prefix}/x-api-key")
    api_secret = get_ssm(f"{prefix}/x-api-secret")
    acc_token  = get_ssm(f"{prefix}/x-access-token")
    acc_secret = get_ssm(f"{prefix}/x-access-secret")

    used_urls     = history.get("used_urls", [])
    used_keywords = history.get("used_keywords", [])
    used_services = history.get("used_services", {})

    # classmethod_reaction は classmethod ソース固定・日本語優先
    if post_type == "classmethod_reaction":
        articles = fetch_rss(["classmethod"])
        articles = [a for a in articles if not is_too_old(a)]
        print(f"[RSS] {len(articles)}件取得（{MAX_ARTICLE_AGE_DAYS}日以内）")
        unused = [a for a in articles if a["url"] not in used_urls
                  and not is_topic_duplicate(a, used_keywords)
                  and not is_service_in_cooldown(a, used_services)]
        if not unused:
            unused = [a for a in articles if a["url"] not in used_urls
                      and not is_service_in_cooldown(a, used_services)]
        if not unused:
            unused = [a for a in articles if a["url"] not in used_urls]
        print(f"[Filter] pool={len(unused)}件")
        pool   = unused if unused else articles
        jp     = [a for a in pool if is_japanese(a["title"])]
        main   = pick_mainstream_article(jp if jp else pool)
    else:
        articles = fetch_rss(slot["sources"])
        articles = [a for a in articles if not is_too_old(a)]
        print(f"[RSS] {len(articles)}件取得（{MAX_ARTICLE_AGE_DAYS}日以内）")
        unused = [a for a in articles if a["url"] not in used_urls
                  and not is_topic_duplicate(a, used_keywords)
                  and not is_service_in_cooldown(a, used_services)]
        if not unused:
            unused = [a for a in articles if a["url"] not in used_urls
                      and not is_service_in_cooldown(a, used_services)]
        if not unused:
            unused = [a for a in articles if a["url"] not in used_urls]
        print(f"[Filter] pool={len(unused)}件")
        pool   = unused if unused else articles
        jp     = [a for a in pool if is_japanese(a["title"])]
        if jp:
            pool = jp
        main   = pick_mainstream_article(pool)

    other_pool = [a for a in pool if a["url"] != main["url"]]
    news_text = "\n".join(f"[{a['label']}] {a['title']}" for a in ([main] + other_pool)[:3])

    # ハッシュタグを記事内容から動的生成
    hashtags = build_hashtags(main)

    # メイン記事の本文を取得（生成のグラウンディング＋事実検証の根拠に使う）
    article_text = fetch_article_text(main["url"])

    prompt = build_prompt(post_type, main, news_text, article_text)
    suffix = (f"\n{main['url']}\n{hashtags}" if with_url else f"\n{hashtags}")

    bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-1")
    resp = bedrock.invoke_model(
        modelId="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]})
    )
    body = json.loads(resp["body"].read())["content"][0]["text"].strip()

    # 投稿前に事実主張を記事本文と突き合わせて検証する
    max_len = 100 if slot_key == "morning" else 160
    body = verify_tweet(bedrock, body, main["title"], article_text, max_len)

    max_body = 280 - len(suffix) - 1
    if len(body) > max_body:
        # 文の途中でぶった切れないよう、直近の文末記号まで戻って切る
        cut = body[:max_body]
        idx = max(cut.rfind(s) for s in "。！？!?…〜笑")
        body = cut[:idx + 1] if idx >= max_body // 2 else cut[:max_body - 1] + "…"
    tweet = f"{body}{suffix}"
    print(f"[Tweet]\n{tweet}\n[文字数] {len(tweet)}")

    if os.environ.get("DRY_RUN", "false").lower() == "true":
        print("[DRY RUN] スキップ（SSM履歴は更新しません）")
        return {"statusCode": 200, "post_type": post_type, "tweet": tweet}

    auth = OAuth1(api_key, api_secret, acc_token, acc_secret)
    r = requests.post("https://api.twitter.com/2/tweets", auth=auth, json={"text": tweet}, timeout=30)
    print(f"[X] Status: {r.status_code}, Response: {r.text}")
    r.raise_for_status()
    tweet_id = r.json().get("data", {}).get("id")
    print(f"[Success] https://x.com/i/web/status/{tweet_id}")

    # 投稿成功後にSSM履歴を更新
    updated_urls = used_urls + [main["url"]]
    history["used_urls"]  = updated_urls[-MAX_USED_URLS:]
    updated_types = history.get("used_types", []) + [post_type]
    history["used_types"] = updated_types[-MAX_USED_TYPES:]
    new_keywords = extract_topic_keywords(main["title"])
    history["used_keywords"] = (history.get("used_keywords", []) + new_keywords)[-40:]
    # サービス別クールダウン履歴を更新
    today_str = datetime.now(JST).date().isoformat()
    for kw in new_keywords:
        used_services[kw] = today_str
    cutoff = (datetime.now(JST).date() - timedelta(days=30)).isoformat()
    history["used_services"] = {k: v for k, v in used_services.items() if v > cutoff}
    save_history(ssm, history)

    return {"statusCode": 200, "post_type": post_type, "tweet_id": tweet_id}
