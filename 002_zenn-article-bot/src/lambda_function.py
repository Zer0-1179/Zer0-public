import json
import os
import random
import boto3
import datetime
from botocore.config import Config
try:
    from diagram_generator import generate_diagrams
except ImportError:
    def generate_diagrams(topic_id, base_path):
        return []

# AWS clients
bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=880, connect_timeout=10),
)
ses = boto3.client("ses", region_name="ap-northeast-1")
s3  = boto3.client("s3",  region_name="ap-northeast-1")
ssm = boto3.client("ssm", region_name="ap-northeast-1")

# Lambda環境かどうかで出力先を切り替え
_IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Environment variables
SES_SENDER_EMAIL    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT_EMAIL = os.environ["SES_RECIPIENT_EMAIL"]
BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    "/tmp/zenn_articles" if _IS_LAMBDA
    else os.path.expanduser("~/Zer0/002_Zenn_Auto_Article_Bot/output"),
)
S3_BUCKET  = "zer0-dev-s3"
S3_PREFIX  = "zenn-articles"

# SSM: 直近トピック履歴
SSM_PARAM_PATH      = "/note-article-bot/recent-topics"
RECENT_TOPICS_LIMIT = 5

AWS_TOPICS = [
    {
        "id": "ec2",
        "name": "Amazon EC2",
        "subtitle": "仮想サーバーを使いこなす完全ガイド",
        "keywords": "インスタンスタイプ, AMI, セキュリティグループ, キーペア, Elastic IP",
    },
    {
        "id": "s3",
        "name": "Amazon S3",
        "subtitle": "オブジェクトストレージ徹底活用ガイド",
        "keywords": "バケット, オブジェクト, ストレージクラス, バージョニング, 静的Webサイトホスティング",
    },
    {
        "id": "iam",
        "name": "AWS IAM",
        "subtitle": "セキュアなアクセス管理を実現する完全ガイド",
        "keywords": "ユーザー, グループ, ロール, ポリシー, MFA, 最小権限の原則",
    },
    {
        "id": "vpc",
        "name": "Amazon VPC",
        "subtitle": "仮想ネットワーク設計の完全ガイド",
        "keywords": "サブネット, ルートテーブル, インターネットゲートウェイ, NATゲートウェイ, セキュリティグループ",
    },
    {
        "id": "rds",
        "name": "Amazon RDS",
        "subtitle": "マネージドデータベースサービス完全ガイド",
        "keywords": "MySQL, PostgreSQL, Multi-AZ, リードレプリカ, 自動バックアップ, パラメータグループ",
    },
    {
        "id": "lambda",
        "name": "AWS Lambda",
        "subtitle": "サーバーレスアーキテクチャ入門ガイド",
        "keywords": "関数, トリガー, イベント, コールドスタート, レイヤー, 同時実行数",
    },
    {
        "id": "cloudwatch",
        "name": "Amazon CloudWatch",
        "subtitle": "監視・ログ管理の完全ガイド",
        "keywords": "メトリクス, アラーム, ログ, ダッシュボード, イベント, Insights",
    },
    {
        "id": "ecs",
        "name": "Amazon ECS",
        "subtitle": "コンテナオーケストレーション完全ガイド",
        "keywords": "タスク定義, クラスター, サービス, Fargate, ECR, ロードバランサー",
    },
    {
        "id": "dynamodb",
        "name": "Amazon DynamoDB",
        "subtitle": "NoSQLデータベース完全活用ガイド",
        "keywords": "テーブル, パーティションキー, ソートキー, GSI, LSI, オンデマンドキャパシティ",
    },
    {
        "id": "cloudfront",
        "name": "Amazon CloudFront",
        "subtitle": "CDNで高速・安全なコンテンツ配信ガイド",
        "keywords": "ディストリビューション, オリジン, エッジロケーション, キャッシュ, WAF連携",
    },
    {
        "id": "api_gateway",
        "name": "Amazon API Gateway",
        "subtitle": "REST/WebSocket APIを構築する完全ガイド",
        "keywords": "REST API, HTTP API, Lambda統合, 認証, スロットリング, ステージ",
    },
    {
        "id": "sqs",
        "name": "Amazon SQS",
        "subtitle": "メッセージキューで疎結合アーキテクチャを実現するガイド",
        "keywords": "標準キュー, FIFOキュー, デッドレターキュー, 可視性タイムアウト, ロングポーリング",
    },
    # ─── AI / ML 系 ───────────────────────────────────────────────────────────
    {
        "id": "bedrock",
        "name": "Amazon Bedrock",
        "subtitle": "生成AIをアプリに組み込む完全ガイド",
        "keywords": "基盤モデル, Claude, Titan, RAG, Knowledge Base, プロンプトエンジニアリング, Agents",
    },
    {
        "id": "sagemaker",
        "name": "Amazon SageMaker AI",
        "subtitle": "機械学習モデルの構築・学習・デプロイ完全ガイド",
        "keywords": "Studio, Training Job, Endpoint, Pipeline, Feature Store, Ground Truth, AutoML",
    },
    {
        "id": "rekognition",
        "name": "Amazon Rekognition",
        "subtitle": "画像・動画解析AIサービス活用ガイド",
        "keywords": "物体検出, 顔認識, テキスト検出, コンテンツモデレーション, カスタムラベル, 顔比較",
    },
    {
        "id": "textract",
        "name": "Amazon Textract",
        "subtitle": "文書・帳票の自動データ抽出完全ガイド",
        "keywords": "OCR, フォーム解析, テーブル抽出, 非同期処理, S3連携, ドキュメント解析",
    },
    # ─── その他主要サービス ────────────────────────────────────────────────────
    {
        "id": "step_functions",
        "name": "AWS Step Functions",
        "subtitle": "サーバーレスワークフロー自動化完全ガイド",
        "keywords": "ステートマシン, タスク, 並列処理, エラーハンドリング, Retry, Catch, Express Workflow",
    },
    {
        "id": "sns",
        "name": "Amazon SNS",
        "subtitle": "Pub/Subメッセージングで通知基盤を構築するガイド",
        "keywords": "トピック, サブスクリプション, プッシュ通知, メール, SQS連携, フィルタリングポリシー",
    },
    {
        "id": "elasticache",
        "name": "Amazon ElastiCache",
        "subtitle": "インメモリキャッシュでアプリを高速化するガイド",
        "keywords": "Redis, Memcached, クラスター, レプリケーション, セッション管理, キャッシュ戦略, TTL",
    },
    {
        "id": "route53",
        "name": "Amazon Route 53",
        "subtitle": "DNS・トラフィック管理で可用性を高める完全ガイド",
        "keywords": "ホストゾーン, Aレコード, エイリアス, フェイルオーバー, ヘルスチェック, レイテンシールーティング",
    },
    {
        "id": "kinesis",
        "name": "Amazon Kinesis",
        "subtitle": "リアルタイムデータストリーミング完全ガイド",
        "keywords": "Data Streams, Firehose, シャード, コンシューマー, S3連携, リアルタイム分析, Data Analytics",
    },
    {
        "id": "cloudtrail",
        "name": "AWS CloudTrail",
        "subtitle": "AWSアカウントの操作ログ管理・セキュリティ監査ガイド",
        "keywords": "証跡, イベント履歴, S3保存, EventBridge連携, セキュリティ監査, コンプライアンス, 不審な操作検知",
    },
]

# ─── Zennフロントマター用メタ情報 ─────────────────────────────────────────────
_ZENN_META: dict[str, dict] = {
    "ec2":           {"emoji": "🖥️",  "topics": ["aws", "ec2", "インフラ", "クラウド"]},
    "s3":            {"emoji": "🪣",  "topics": ["aws", "s3", "ストレージ", "クラウド"]},
    "iam":           {"emoji": "🔐",  "topics": ["aws", "iam", "セキュリティ", "クラウド"]},
    "vpc":           {"emoji": "🌐",  "topics": ["aws", "vpc", "ネットワーク", "クラウド"]},
    "rds":           {"emoji": "🗄️",  "topics": ["aws", "rds", "データベース", "クラウド"]},
    "lambda":        {"emoji": "⚡",  "topics": ["aws", "lambda", "サーバーレス", "クラウド"]},
    "cloudwatch":    {"emoji": "📊",  "topics": ["aws", "cloudwatch", "監視", "クラウド"]},
    "ecs":           {"emoji": "📦",  "topics": ["aws", "ecs", "コンテナ", "docker"]},
    "dynamodb":      {"emoji": "💾",  "topics": ["aws", "dynamodb", "nosql", "データベース"]},
    "cloudfront":    {"emoji": "🚀",  "topics": ["aws", "cloudfront", "cdn", "クラウド"]},
    "api_gateway":   {"emoji": "🔌",  "topics": ["aws", "apigateway", "api", "サーバーレス"]},
    "sqs":           {"emoji": "📬",  "topics": ["aws", "sqs", "メッセージキュー", "クラウド"]},
    "bedrock":       {"emoji": "🤖",  "topics": ["aws", "bedrock", "生成ai", "llm"]},
    "sagemaker":     {"emoji": "🧠",  "topics": ["aws", "sagemakerAI", "機械学習", "ai"]},
    "rekognition":   {"emoji": "👁️",  "topics": ["aws", "rekognition", "画像認識", "ai"]},
    "textract":      {"emoji": "📄",  "topics": ["aws", "textract", "ocr", "ai"]},
    "step_functions":{"emoji": "🔄",  "topics": ["aws", "stepfunctions", "ワークフロー", "サーバーレス"]},
    "sns":           {"emoji": "📢",  "topics": ["aws", "sns", "通知", "クラウド"]},
    "elasticache":   {"emoji": "⚡",  "topics": ["aws", "elasticache", "redis", "キャッシュ"]},
    "route53":       {"emoji": "🌍",  "topics": ["aws", "route53", "dns", "ネットワーク"]},
    "kinesis":       {"emoji": "🌊",  "topics": ["aws", "kinesis", "ストリーミング", "データ"]},
    "cloudtrail":    {"emoji": "🔍",  "topics": ["aws", "cloudtrail", "セキュリティ", "監査"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennの技術記事を執筆するプロのテクニカルライターです。
以下の条件に従って、AWS初心者向けの高品質な技術記事を日本語で作成してください。

## テーマ
{topic_name}：{topic_subtitle}

## キーワード（記事中に自然に含めること）
{keywords}

## 記事の要件
- **文字数**: 3,000〜5,000文字（本文のみ、見出しを除く）
- **対象読者**: AWS初心者（プログラミング経験はあるが、AWSをほぼ使ったことがない人）
- **トーン**: 親しみやすく、わかりやすい言葉で、専門用語は必ず説明する
- **価値**: 読者が読み終えたら実際にAWSコンソールで試せるレベルの実践的な内容

## Zenn Markdown記法の積極活用（必須）

### テーブル
料金比較・設定オプション・機能比較には必ずMarkdownテーブルを使う。

### メッセージボックス
- 重要なポイントは `:::message` で囲む（前後に空行必須）
- コスト注意・セキュリティ警告は `:::message alert` を使う

使用例:
:::message
ここに重要なポイントを書く
:::

:::message alert
ここにコスト・セキュリティの注意事項を書く
:::

### アコーディオン
補足情報・応用設定は `:::details タイトル` でまとめる（前後に空行必須）。

使用例:
:::details 応用：本番環境向けの設定
補足内容
:::

### コードブロック
言語またはファイル名を必ず指定する。

使用例:
```bash:動作確認
aws s3 ls
```

```json:レスポンス例
{{"status": "ok"}}
```

## 必須の見出し構成（この順序で書くこと）

### ## はじめに（200〜300文字）
- なぜこのサービスを学ぶべきかの動機づけ
- この記事で学べることの概要
- 書き終えたら、以下のマーカーを**単独行**で挿入すること（前後に空行必須）:

{{DIAGRAM_1}}

  マーカーの直前に、読者が「そーなんだ！」と思えるような**1〜2文**を書くこと。
  以下の例を参考に、毎回違う切り口で書くこと（例文をそのままコピーしない）:
  - 「{topic_name}、実はこんな構成で使われていることが多いんです。全体像を先に見ておくと、後の説明がグッとわかりやすくなります。」
  - 「AWSの現場でよく見かける{topic_name}の構成がこちら。シンプルに見えて、なかなか考えられた設計です。」
  - 「まずは完成図を眺めてみてください。『あ、思ったよりシンプルだな』と感じたらラッキーです。」
  - 「{topic_name}を使うとき、他のAWSサービスとどう組み合わせるか迷いませんか？よく使われるパターンを先に共有します。」
  - 「図を見るだけでも、{topic_name}がどんな役割を担っているかイメージできるはずです。」

### ## {topic_name}とは？（500〜800文字）
- サービスの役割と特徴をわかりやすく説明
- 具体的なユースケース（2〜3例）をテーブルで整理
- 他のAWSサービスとの連携イメージ
- `:::message` で「一言まとめ」を入れる

### ## 料金体系を理解しよう（400〜600文字）
- 無料利用枠（Free Tier）の詳細を**テーブルで整理**
- 主要な料金プランをテーブルで比較
- 月額コストの目安（具体的な数字）
- `:::message alert` で「コスト注意ポイント」を明記

### ## ハンズオン：実際に使ってみよう（1,500〜2,500文字）
- セクション冒頭に、読者が手を動かす前に全体像を掴める**1〜2文**を書いた後、以下のマーカーを**単独行**で挿入すること（前後に空行必須）:

{{DIAGRAM_2}}

  以下の例を参考に、毎回違う切り口で書くこと（例文をそのままコピーしない）:
  - 「さっそく手を動かしていきましょう。今回作るのはこちらの構成です。迷ったときはこの図に戻ってきてください。」
  - 「構築前に完成図を確認しておきましょう。ステップが多く見えても、図で見ると意外とシンプルです。」
  - 「百聞は一見にしかず。まず完成形を見てから進めた方が、各ステップの『なぜ』が理解しやすくなります。」
  - 「ここからが本番です。以下の構成を10〜15分で作り上げます。」
  - 「作業を始める前に、今回のゴールをしっかり頭に入れておきましょう。」

- **前提条件**: 必要なもの（AWSアカウント等）を箇条書き
- **ステップ1〜5以上**: AWSコンソールの操作手順を番号付きで詳しく説明
  - 各ステップにつまずきやすいポイントへの注意書き
  - コマンドはファイル名付きコードブロックで記述
- **動作確認**: 以下を必ず含める
  - 確認コマンドまたはブラウザ操作
  - 成功時のレスポンス例を `:::` 付きコードブロックで示す
  - `:::message` でつまずきやすいポイントをまとめる
- **後片付け**: 料金が発生しないようにリソースを削除する手順

:::details 応用：本番環境で使うときのポイント
本番環境でよく使われる追加設定や推奨オプションをここに書く
:::

### ## まとめ（300〜400文字）
- 今回学んだことの振り返りをテーブルで整理
- 次のステップ（関連サービスの学習提案）
- 実務でよく使うシナリオの紹介

### ## さらに深く学びたい方へ
以下の文章を含めること：

「{topic_name}の基礎を学んだ次のステップとして、Udemyの「**AWS：ゼロから実践するAmazon Web Services。手を動かしながらインフラの基礎を習得**」コースがおすすめです。このコースでは{topic_name}を含むAWSの主要サービスを、実際にハンズオン形式で学ぶことができます。セール時には1,500円〜2,000円程度で購入できるので、ぜひチェックしてみてください！」

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。
サービスが改名・リブランドされている場合は、**「○○とは？」セクションの冒頭**に以下の形式で旧称を明記すること：

:::message
💡 **名称変更のお知らせ**
このサービスはかつて「**旧サービス名**」と呼ばれていましたが、202X年XX月に「**新サービス名**」へ改名されました。
ドキュメントや古い記事では旧名称が使われている場合があります。
:::

### 主な改名・リブランド済みサービス（2025年時点）

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |
| Amazon Bedrock | （新サービスのため旧称なし） | 2023年リリース |
| AWS Inferentia / Trainium | （新ハードウェアのため旧称なし） | — |

上記以外のサービスを執筆する場合も、過去に改名・統合・廃止された関連サービスがあれば同様に言及すること。
改名がない場合はこのブロックは不要。

## 注意事項
- **記事の先頭にYAML frontmatter（--- で囲まれたブロック）を書かない**（frontmatterはシステムが自動付与する）
- 見出しは ## や ### を使ったMarkdown形式で書く（# は使わない）
- コードやコマンドはバッククォート3つで囲み、言語名またはファイル名を指定する
- 重要な用語は**太字**で強調する
- AWSコンソールの操作は具体的なメニュー名やボタン名を明記する
- 料金は2026年時点の情報を参考にし、「最新情報はAWS公式サイトで確認してください」と注記する
- curlコマンドやブラウザ確認を記載する場合は、**成功時のレスポンス例を必ずコードブロックで示す**（「結果が表示されます」のような曖昧な表現は使わない）
- `:::message` や `:::details` は前後に必ず空行を入れること
- テーブルは料金・比較・まとめなど積極的に使う
- コードブロック内のサンプル日付・タイムスタンプは **本日の日付（{today}）** を基準にすること（例: `{today}T10:30:00Z`）。`2024`や`2023`など過去の年は絶対に使わない。連番が必要な場合は翌日や数時間後など`{today}`前後の日付を使う
"""


# ─── SSM: トピック重複除外 ────────────────────────────────────────────────────

def get_recent_topics() -> list[str]:
    """SSM から直近のトピックIDリストを取得する（最大 RECENT_TOPICS_LIMIT 件）"""
    try:
        response = ssm.get_parameter(Name=SSM_PARAM_PATH)
        ids = json.loads(response["Parameter"]["Value"])
        return ids if isinstance(ids, list) else []
    except ssm.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"SSM読み込みエラー（除外なしで続行）: {e}")
        return []


def save_topic_to_ssm(topic_id: str):
    """選択したトピックを SSM に保存する（最新 RECENT_TOPICS_LIMIT 件を保持）"""
    recent = get_recent_topics()
    recent.append(topic_id)
    recent = recent[-RECENT_TOPICS_LIMIT:]
    try:
        ssm.put_parameter(
            Name=SSM_PARAM_PATH,
            Value=json.dumps(recent),
            Type="String",
            Overwrite=True,
        )
        print(f"SSM保存完了: {recent}")
    except Exception as e:
        print(f"SSM書き込みエラー（無視して続行）: {e}")


# ─── トピック選択 ─────────────────────────────────────────────────────────────

def select_topic_with_bedrock(excluded_ids: list[str]) -> dict:
    """Bedrock を使って重複を避けながらトピックを選択する"""
    available = [t for t in AWS_TOPICS if t["id"] not in excluded_ids]
    if not available:
        # 全トピックが除外済みの場合（通常は発生しない）はリセット
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS

    topic_list = "\n".join([f"- {t['id']}: {t['name']}" for t in available])

    prompt = f"""以下のAWSサービス一覧から、今週の記事テーマを1つランダムに選んでください。
選択する際は、純粋にランダムに選んでください。

{topic_list}

選んだサービスのIDのみを返してください（例: ec2）。説明は不要です。"""

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result   = json.loads(response["body"].read())
    topic_id = result["content"][0]["text"].strip().lower()
    usage = result.get("usage", {})
    print(f"[Bedrock/topic] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")

    # Bedrock の返答が除外リストにない available トピックと一致するか確認
    for topic in available:
        if topic["id"] == topic_id:
            return topic

    # 一致しない場合は available からランダム選択
    return random.choice(available)


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict, today: str) -> str:
    """Bedrock を使って記事を生成する"""
    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        keywords=topic["keywords"],
        today=today,
    )

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5500,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    usage = result.get("usage", {})
    print(f"[Bedrock/article] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")

    # Bedrock が記事冒頭に YAML frontmatter を付けることがあるため除去する
    if text.lstrip().startswith("---"):
        # 2つ目の "---" までをスキップ
        lines = text.lstrip().splitlines(keepends=True)
        end = 1
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                end = i + 1
                break
        text = "".join(lines[end:]).lstrip()

    return text


# ─── MD 生成（画像プレースホルダー付き） ─────────────────────────────────────

_DIAGRAM_CAPTIONS = [
    "{topic_name} – よく使われる全体構成図",
    "{topic_name} – ハンズオンで構築する構成図",
]


def _make_image_placeholder(png_path: str, topic_name: str, index: int) -> str:
    filename = os.path.basename(png_path)
    caption_tmpl = _DIAGRAM_CAPTIONS[index - 1] if index - 1 < len(_DIAGRAM_CAPTIONS) \
        else "{topic_name} 構成図" + str(index)
    caption = caption_tmpl.format(topic_name=topic_name)
    return (
        f"\n"
        f":::message\n"
        f"📷 **【Zenn投稿時】** `{filename}` をZennエディタでアップロードし、下の画像パスをZenn CDN URLに置き換えてください。\n"
        f":::\n\n"
        f"![{caption}](./images/{filename})\n"
        f"*{caption}*\n"
    )


def _embed_image_placeholders(article: str, png_paths: list[str], topic_name: str) -> str:
    """{DIAGRAM_N} マーカーを画像プレースホルダーに置換する。
    マーカーが見つからない場合はフォールバック挿入（はじめに直後 / ハンズオン直後）。
    """
    if not png_paths:
        return article

    _FALLBACK_HEADINGS = ["はじめに", "ハンズオン"]

    result = article
    for img_idx, png_path in enumerate(png_paths):
        n = img_idx + 1
        marker = "{" + f"DIAGRAM_{n}" + "}"
        placeholder = _make_image_placeholder(png_path, topic_name, n)

        if marker in result:
            result = result.replace(marker, placeholder, 1)
        else:
            # フォールバック: 対応する見出し名の直後に挿入
            lines = result.split("\n")
            target = _FALLBACK_HEADINGS[img_idx] if img_idx < len(_FALLBACK_HEADINGS) else None
            h2_positions = [i for i, line in enumerate(lines) if line.startswith("## ")]
            if target:
                matched = [i for i, line in enumerate(lines)
                           if line.startswith("## ") and target in line]
                insert_idx = matched[0] if matched else \
                    h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            else:
                insert_idx = h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            lines.insert(insert_idx + 1, placeholder)
            result = "\n".join(lines)

    return result


def _next_article_number(output_dir: str) -> str:
    """output/ 内の既存記事フォルダ数をカウントして次の連番を返す（例: '006'）"""
    import glob
    existing = glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9]_*"))
    return f"{len(existing) + 1:03d}"


def save_to_local(topic: dict, article: str, timestamp: str) -> tuple[str, list[str]]:
    """記事を MD ファイルに保存し、構成図 PNG も生成する。(mdパス, pngパスリスト) を返す"""
    output_dir = os.path.expanduser(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    base_name   = f"{timestamp}_{topic['id']}"
    num         = _next_article_number(output_dir)
    article_dir = os.path.join(output_dir, f"{num}_{base_name}")
    images_dir  = os.path.join(article_dir, "images")
    os.makedirs(article_dir, exist_ok=True)
    os.makedirs(images_dir,  exist_ok=True)

    md_path  = os.path.join(article_dir, f"{base_name}.md")
    png_base = os.path.join(images_dir,  f"{base_name}_diagram")

    # 構成図を生成（最大2枚）
    png_paths = generate_diagrams(topic["id"], png_base)

    # 図1・図2ともに {DIAGRAM_N} マーカーで記事中に挿入（マーカー不在時はフォールバック）
    article_with_images = _embed_image_placeholders(article, png_paths, topic["name"])

    # Zennフロントマター用メタ情報
    meta = _ZENN_META.get(topic["id"], {"emoji": "☁️", "topics": ["aws", "クラウド"]})
    topics_json = json.dumps(meta["topics"], ensure_ascii=False)

    full_content = f"""---
title: "{topic['name']}：{topic['subtitle']}"
emoji: "{meta['emoji']}"
type: "tech"
topics: {topics_json}
published: false
---

{article_with_images}

<!-- 生成情報: topic={topic['id']} / generated_at={timestamp} / chars={len(article)} / images={len(png_paths)}枚 -->
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return md_path, png_paths


# ─── S3 アップロード ──────────────────────────────────────────────────────────

def upload_to_s3(md_path: str, png_paths: list[str], s3_folder: str) -> str:
    """MD ファイルと PNG 画像を S3 にアップロードし、S3 フォルダパスを返す"""
    s3_base = f"{S3_PREFIX}/{s3_folder}"

    md_key = f"{s3_base}/{os.path.basename(md_path)}"
    s3.upload_file(md_path, S3_BUCKET, md_key, ExtraArgs={"ContentType": "text/markdown"})
    print(f"S3アップロード: s3://{S3_BUCKET}/{md_key}")

    for png_path in png_paths:
        png_key = f"{s3_base}/images/{os.path.basename(png_path)}"
        s3.upload_file(png_path, S3_BUCKET, png_key, ExtraArgs={"ContentType": "image/png"})
        print(f"S3アップロード: s3://{S3_BUCKET}/{png_key}")

    return f"s3://{S3_BUCKET}/{s3_base}/"


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, s3_url: str = "",
):
    """SES でメール通知を送信する"""
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    subject = f"【Zenn記事生成完了】{topic['name']}の記事が生成されました - {timestamp}"

    png_list_html = "".join(
        f'<li><code>{os.path.basename(p)}</code></li>' for p in png_paths
    ) if png_paths else "<li>（生成なし）</li>"

    s3_row = (
        f'<tr><td style="padding:5px;font-weight:bold;">S3保存先</td>'
        f'<td><code>{s3_url}</code></td></tr>'
        if s3_url else ""
    )
    download_row = (
        '<li>S3からローカルにダウンロード: '
        '<code>bash ~/Zer0/002_Zenn_Auto_Article_Bot/download_article.sh</code></li>'
        if s3_url else ""
    )

    body_text = f"""Zenn技術記事の自動生成が完了しました。

■ 記事情報
- テーマ: {topic['name']}（{topic['subtitle']}）
- 文字数: {char_count:,}文字
- 生成日時: {timestamp}
- 構成図PNG: {diagram_info}
- S3保存先: {s3_url}

■ 記事プレビュー（先頭300文字）
{preview}...

■ 次のアクション
1. bash ~/Zer0/002_Zenn_Auto_Article_Bot/download_article.sh
2. Zennエディタで新規記事を作成（または zenn-cli で管理）
3. MDファイルの内容を貼り付け
4. :::message ブロック内の指示に従ってPNGをアップロード・差し替え
5. published: false → true に変更して公開

このメールは自動送信されています。
"""

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#3EA8FF;">Zenn技術記事の自動生成が完了しました</h2>

  <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事情報</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:5px;font-weight:bold;">テーマ</td>
          <td>{topic['name']}（{topic['subtitle']}）</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">文字数</td>
          <td>{char_count:,}文字</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">生成日時</td>
          <td>{timestamp}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">構成図PNG</td>
          <td><ul style="margin:0;padding-left:16px;">{png_list_html}</ul></td></tr>
      {s3_row}
    </table>
  </div>

  <div style="background:#fff8e1;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事プレビュー</h3>
    <p style="color:#555;">{preview}...</p>
  </div>

  <div style="background:#e8f5e9;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>次のアクション</h3>
    <ol>
      {download_row}
      <li>Zennエディタで新規記事を作成</li>
      <li>MDファイルの内容を貼り付け</li>
      <li><code>:::message</code> ブロックの指示に従ってPNGをアップロード・差し替え</li>
      <li><code>published: false</code> → <code>true</code> に変更して公開</li>
    </ol>
  </div>

  <p style="color:#999;font-size:12px;">このメールは自動送信されています。</p>
</body>
</html>
"""

    ses.send_email(
        Source=SES_SENDER_EMAIL,
        Destination={"ToAddresses": [SES_RECIPIENT_EMAIL]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": body_text, "Charset": "UTF-8"},
                "Html": {"Data": body_html, "Charset": "UTF-8"},
            },
        },
    )


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def run():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    today     = now.strftime("%Y-%m-%d")   # コードサンプル日付用 (例: 2026-04-12)

    print(f"[{timestamp}] Zenn技術記事自動生成を開始します")

    # Step 1: 直近トピック取得 → Bedrock でトピック選択 → SSM に保存
    print("Step 1: Bedrockでトピックを選択中...")
    recent_topics = get_recent_topics()
    print(f"  除外トピック（直近{len(recent_topics)}件）: {recent_topics}")
    topic = select_topic_with_bedrock(excluded_ids=recent_topics)
    print(f"  選択されたトピック: {topic['name']}")
    save_topic_to_ssm(topic["id"])

    # Step 2: 記事生成
    print("Step 2: 記事を生成中（3,000〜5,000文字）...")
    article    = generate_article(topic, today)
    char_count = len(article)
    print(f"  記事生成完了: {char_count:,}文字")

    # Step 3: ローカル保存（MD + PNG）
    print("Step 3: ファイル保存中（記事MD + 構成図PNG）...")
    md_path, png_paths = save_to_local(topic, article, timestamp)
    print(f"  MD保存完了: {md_path}")
    print(f"  PNG生成完了: {len(png_paths)}枚 {png_paths}" if png_paths else "  PNG生成: スキップ")

    # Step 4: S3 アップロード
    print("Step 4: S3にアップロード中...")
    s3_folder = f"{timestamp}_{topic['id']}"
    s3_url    = upload_to_s3(md_path, png_paths, s3_folder)
    print(f"  S3アップロード完了: {s3_url}")

    # Step 5: SES メール通知
    print("Step 5: メール通知を送信中...")
    send_email_notification(topic, article, md_path, png_paths, timestamp, s3_url)
    print("  メール送信完了")

    print(f"[{timestamp}] 処理が正常に完了しました")
    return topic, char_count, md_path, png_paths, s3_url


def lambda_handler(event, context):
    topic, char_count, md_path, png_paths, s3_url = run()
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "記事生成が完了しました",
                "topic":   topic["name"],
                "character_count": char_count,
                "images_generated": len(png_paths),
                "s3_url": s3_url,
            },
            ensure_ascii=False,
        ),
    }


if __name__ == "__main__":
    run()
