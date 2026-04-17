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

# 共感・問いかけフック（全タイプ共通ルール）
EMPATHY_RULE = """- 末尾の締め方は以下のどれか1パターンをその内容に合わせて自然に選ぶ（毎回問いかけにしない）
  【パターンA：問いかけ】読者に反応を促す一言
    例：「みんなどこに落ち着いてる？」「同じ経験ある人いる？」「みんなはどっち派？」
        「これ知ってた？」「現場でもこんな感じ？」「同じとこで詰まった人いる？」
        「もっといい方法あったら教えて」「みんなの環境ではどう？」「自分だけじゃないよね？」
        「これ試した人いる？」「どう対処してる？」「知らなかったの自分だけ？」「どう思う？」
  【パターンB：共感・あるある】読者が「わかる」と思う一言で締める
    例：「こういうの地味に助かるよね」「ある？こういうの」「わかりすぎる」
        「これあるあるすぎる」「地味にハマりポイントなんだよな」「なんかわかる」
        「こういうの誰も教えてくれないやつ」「現場あるあるすぎて笑える」
        「これ気づいたとき少し得した気分になる」「地味だけど大事なやつ」
        「知ってると知らないとで結構差が出る」「こういう細かいとこ好き」「わかる人にはわかる」
  【パターンC：気づき・伝える】自分の感想や発見をそのまま伝えて自然に終わる
    例：「これ知っておくだけで全然違う」「意外と知らない人多そう」「もっと早く知りたかった」
        「なんか勉強になった」「これは素直にいいと思った」「じわじわ便利さがわかってくるやつ」
        「こういうアップデート地味にうれしい」「思ったより簡単だった」
        「ちゃんと理解してなかったことに気づいた」「これは覚えておきたい」
        「知らなかった、得した」「これ結構使えそう」「少し試してみたくなった」
  ※ 不自然になる場合は無理に入れなくてよい・パターンCで普通に終わってもよい"""

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
            if tag not in seen:
                matched.append(tag)
                seen.add(tag)
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


def build_prompt(post_type: str, main: dict, news_text: str) -> str:
    title = main["title"]

    if post_type == "news_reaction":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似してAWSニュースへの一言コメントを書いてください。

【実際の投稿例】
{FEW_SHOT_MORNING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- ニュースを読んで感じた一言・気づきをそのまま書く
- 情報を整理して伝えようとしない
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない
- 100文字以内でコンパクトに
{EMPATHY_RULE}
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
- 100文字以内でコンパクトに
{EMPATHY_RULE}
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
- 100文字以内でコンパクトに
{EMPATHY_RULE}
- ツイート本文のみ出力"""

    elif post_type == "news_intro":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似してAWSニュースへのコメントを書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 感想や気づきをそのまま書く感じで
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個、多くても2個
- URLは含めない（別途付加する）
- 160文字以内
{EMPATHY_RULE}
- ツイート本文のみ出力"""

    elif post_type == "aws_failure":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調で、AWSニュースに関連した「ハマりポイント・失敗談・よくある落とし穴」を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【ルール】
- このニュースに関連したサービスで自分がハマった・ヒヤッとした経験談や落とし穴を1つ
- 「気をつけて」「これで詰まった」「やらかした」系の内容が理想
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
- 160文字以内
{EMPATHY_RULE}
- ツイート本文のみ出力"""

    elif post_type == "news_comparison":
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調で、AWSニュースをもとに「比較・意見・どっち派？」系の投稿を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日のAWSニュース】
メイン：{title}
参考：{news_text}

【ルール】
- このニュースに関連して「AとBどっちが好き？」「自分はこっち派」「こっちの方が実用的では？」系の意見や問いかけ
- 読んだ人が思わず反応したくなる内容が理想
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
- 160文字以内
{EMPATHY_RULE}
- ツイート本文のみ出力"""

    elif post_type == "classmethod_reaction":
        pattern = random.choice(CLASSMETHOD_PATTERNS)
        return f"""以下はAWSインフラエンジニア（@Zer0_Infra）の実際のXの投稿例です。この人の口調・温度感を完全に真似して、クラスメソッドの技術記事への反応を書いてください。

【実際の投稿例】
{FEW_SHOT_EVENING}

【今日の記事】
タイトル：{title}
参考：{news_text}

【今回の投稿パターン】
{pattern}

【ルール】
- 上の投稿例の人が書いたような自然な口調で
- 「です・ます」は使わない（常体・口語）
- 大げさな表現・まとめっぽい締めは不要
- 絵文字は0〜1個
- URLは含めない（別途付加する）
- 160文字以内
{EMPATHY_RULE}
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
            for item in tree.findall(".//item")[:5]:
                title    = item.findtext("title", "").strip()
                link     = item.findtext("link", "").strip()
                desc     = item.findtext("description", "").strip()[:150]
                pub_date = item.findtext("pubDate", "").strip()
                if title and link:
                    articles.append({"source": feed["source"], "label": feed["label"], "title": title, "url": link, "desc": desc, "pub_date": pub_date})
        except Exception as e:
            print(f"[RSS] {feed['label']} error: {e}")
    return articles


def lambda_handler(event, context):
    now      = datetime.now(JST)
    slot_key = os.environ.get("FORCE_SLOT") or ("morning" if now.hour < 15 else "evening")
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

    prompt = build_prompt(post_type, main, news_text)
    suffix = (f"\n{main['url']}\n{hashtags}" if with_url else f"\n{hashtags}")

    bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-1")
    resp = bedrock.invoke_model(
        modelId="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]})
    )
    body = json.loads(resp["body"].read())["content"][0]["text"].strip()
    max_body = 280 - len(suffix) - 1
    if len(body) > max_body:
        body = body[:max_body - 1] + "…"
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
