import json
import os
import random
import time
import boto3
import datetime
from botocore.config import Config
try:
    from diagram_generator import generate_diagrams_with_titles
except ImportError:
    def generate_diagrams_with_titles(topic_id, base_path):
        return [], []

# AWS clients
bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(
        read_timeout=880, connect_timeout=10,
        retries={"max_attempts": 4, "mode": "adaptive"},
    ),
)
ses = boto3.client("ses", region_name="ap-northeast-1")
s3  = boto3.client("s3",  region_name="ap-northeast-1")
ssm = boto3.client("ssm", region_name="ap-northeast-1")

# Lambda環境かどうかで出力先を切り替え
_IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Environment variables
SES_SENDER_EMAIL    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT_EMAIL = os.environ["SES_RECIPIENT_EMAIL"]
BEDROCK_ARTICLE_MODEL_ID = os.environ.get("BEDROCK_ARTICLE_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    "/tmp/zenn_articles" if _IS_LAMBDA
    else os.path.expanduser("~/Zer0/002_Zenn_Auto_Article_Bot/output"),
)
S3_BUCKET  = os.environ.get("S3_BUCKET", "zer0-dev-s3")
S3_PREFIX  = "zenn-articles"

# SSM: 直近トピック履歴
# 注意: AWS_TOPICS の総数（28件）と同値にすると、全トピック消化後に除外リストが
# 常に「全トピック」を含んだまま固定化し、以後 select_topic_with_bedrock の
# 「全除外時リセット」分岐が毎回発火して重複除外が恒久的に無効化されるバグがあった
# （2026-07-03 第2巡レビューで修正）。総数より必ず小さい値にすること。
SSM_PARAM_PATH      = "/zenn-article-bot/recent-topics"
RECENT_TOPICS_LIMIT = int(os.environ.get("RECENT_TOPICS_LIMIT", "20"))

# 記事の「切り口」バリエーション（2026-07-05追加）。28トピックは月2本ペースで
# 約14ヶ月で一巡するため、2周目以降も同じ記事にならないよう切り口を変えて多様性を出す。
_DEFAULT_ANGLES = [
    "コスト最適化の観点（無料枠・課金項目・節約のコツを中心に）",
    "セキュリティ設定の観点（権限・暗号化・アクセス制御を中心に）",
    "他サービスとの連携パターンの観点（組み合わせて使う実践例を中心に）",
    "初心者がつまずきやすいポイント集の観点（設定ミス・エラー対処を中心に）",
]
SSM_ANGLE_PARAM_PATH = "/zenn-article-bot/recent-angles"
# _DEFAULT_ANGLES の総数(4件)と同値にすると、トピック除外と同じ「全消化後の
# 恒久ロック」バグ（2026-07-03発見）が再発するため、必ず総数より小さい値にすること
RECENT_ANGLES_LIMIT = int(os.environ.get("RECENT_ANGLES_LIMIT", "3"))

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
    # ─── サービス特化トピック ────────────────────────────────────────────────────
    {
        "id": "ec2_ssm",
        "name": "Amazon EC2 × AWS Systems Manager",
        "subtitle": "Session Managerでキーペアもbastionも不要な安全接続ガイド",
        "keywords": "Session Manager, SSM Agent, IAMロール, ポートフォワーディング, 踏み台不要, VPCエンドポイント, 接続ログ",
    },
    {
        "id": "ec2_ebs",
        "name": "Amazon EC2 × Amazon EBS",
        "subtitle": "ボリューム種類の使い分けと複数アタッチで性能を最大化するガイド",
        "keywords": "gp3, io2, st1, sc1, スループット, IOPS, 複数ボリュームアタッチ, スナップショット, 暗号化",
    },
    {
        "id": "lambda_layers",
        "name": "AWS Lambda Layers",
        "subtitle": "外部ライブラリ・共有コードをLayerで効率管理するガイド",
        "keywords": "Layer, 依存関係, zip, Python, Node.js, バージョン管理, 共有ライブラリ, デプロイパッケージ削減",
    },
    {
        "id": "s3_lifecycle",
        "name": "Amazon S3 ライフサイクルポリシー",
        "subtitle": "ストレージクラス自動移行でコストを最適化するガイド",
        "keywords": "ライフサイクルルール, Standard-IA, Glacier, Intelligent-Tiering, 自動削除, コスト削減, バージョニング",
    },
    {
        "id": "vpc_endpoint",
        "name": "Amazon VPC エンドポイント",
        "subtitle": "インターネットを通らずAWSサービスへプライベート接続するガイド",
        "keywords": "ゲートウェイ型, インターフェイス型, PrivateLink, S3エンドポイント, DynamoDB, セキュリティ, 通信コスト削減",
    },
    {
        "id": "cloudwatch_insights",
        "name": "Amazon CloudWatch Logs Insights",
        "subtitle": "クエリ言語でログを高速検索・集計・可視化するガイド",
        "keywords": "クエリ構文, fields, filter, stats, sort, limit, エラー分析, レイテンシ集計, ダッシュボード連携",
    },
]

# ─── AWS公式ドキュメント URL マップ ───────────────────────────────────────────
DOCS_URL_MAP: dict[str, str] = {
    "ec2":            "https://docs.aws.amazon.com/ja_jp/AWSEC2/latest/UserGuide/concepts.html",
    "s3":             "https://docs.aws.amazon.com/ja_jp/AmazonS3/latest/userguide/Welcome.html",
    "iam":            "https://docs.aws.amazon.com/ja_jp/IAM/latest/UserGuide/introduction.html",
    "vpc":            "https://docs.aws.amazon.com/ja_jp/vpc/latest/userguide/what-is-amazon-vpc.html",
    "rds":            "https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/UserGuide/Welcome.html",
    "lambda":         "https://docs.aws.amazon.com/ja_jp/lambda/latest/dg/welcome.html",
    "cloudwatch":     "https://docs.aws.amazon.com/ja_jp/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html",
    "ecs":            "https://docs.aws.amazon.com/ja_jp/AmazonECS/latest/developerguide/Welcome.html",
    "dynamodb":       "https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/Introduction.html",
    "cloudfront":     "https://docs.aws.amazon.com/ja_jp/AmazonCloudFront/latest/DeveloperGuide/Introduction.html",
    "api_gateway":    "https://docs.aws.amazon.com/ja_jp/apigateway/latest/developerguide/welcome.html",
    "sqs":            "https://docs.aws.amazon.com/ja_jp/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html",
    "bedrock":        "https://docs.aws.amazon.com/ja_jp/bedrock/latest/userguide/what-is-bedrock.html",
    "sagemaker":      "https://docs.aws.amazon.com/ja_jp/sagemaker/latest/dg/whatis.html",
    "rekognition":    "https://docs.aws.amazon.com/ja_jp/rekognition/latest/dg/what-is.html",
    "textract":       "https://docs.aws.amazon.com/ja_jp/textract/latest/dg/what-is.html",
    "step_functions": "https://docs.aws.amazon.com/ja_jp/step-functions/latest/dg/welcome.html",
    "sns":            "https://docs.aws.amazon.com/ja_jp/sns/latest/dg/welcome.html",
    "elasticache":    "https://docs.aws.amazon.com/ja_jp/AmazonElastiCache/latest/dg/WhatIs.html",
    "route53":        "https://docs.aws.amazon.com/ja_jp/Route53/latest/DeveloperGuide/Welcome.html",
    "kinesis":        "https://docs.aws.amazon.com/ja_jp/streams/latest/dev/introduction.html",
    "cloudtrail":     "https://docs.aws.amazon.com/ja_jp/awscloudtrail/latest/userguide/cloudtrail-user-guide.html",
    "ec2_ssm":        "https://docs.aws.amazon.com/ja_jp/systems-manager/latest/userguide/session-manager.html",
    "ec2_ebs":        "https://docs.aws.amazon.com/ja_jp/AWSEC2/latest/UserGuide/AmazonEBS.html",
    "lambda_layers":  "https://docs.aws.amazon.com/ja_jp/lambda/latest/dg/chapter-layers.html",
    "s3_lifecycle":   "https://docs.aws.amazon.com/ja_jp/AmazonS3/latest/userguide/object-lifecycle-mgmt.html",
    "vpc_endpoint":   "https://docs.aws.amazon.com/ja_jp/vpc/latest/privatelink/what-is-privatelink.html",
    "cloudwatch_insights": "https://docs.aws.amazon.com/ja_jp/AmazonCloudWatch/latest/logs/AnalyzingLogData.html",
}

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
    "cloudtrail":          {"emoji": "🔍",  "topics": ["aws", "cloudtrail", "セキュリティ", "監査"]},
    "ec2_ssm":             {"emoji": "🔑",  "topics": ["aws", "ec2", "ssm", "セキュリティ"]},
    "ec2_ebs":             {"emoji": "💽",  "topics": ["aws", "ec2", "ebs", "ストレージ"]},
    "lambda_layers":       {"emoji": "🧩",  "topics": ["aws", "lambda", "サーバーレス", "python"]},
    "s3_lifecycle":        {"emoji": "♻️",  "topics": ["aws", "s3", "コスト最適化", "クラウド"]},
    "vpc_endpoint":        {"emoji": "🔒",  "topics": ["aws", "vpc", "privatelink", "ネットワーク"]},
    "cloudwatch_insights": {"emoji": "🔎",  "topics": ["aws", "cloudwatch", "ログ分析", "監視"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
「読んでよかった」と思わせる記事を書いてください。テンプレートを埋める作業ではなく、読者の課題を解決する記事です。

## 出力形式（必須）
出力の**1行目**を次の形式にしてください。

TITLE: ここに記事タイトルを書く

タイトルのルール:
- 読者が「自分ごと」に感じる具体的な表現（「〜したい人向け」「〜で詰まったら」等）
- サービス名をそのままコピーしない（「AWS Lambdaとは」のような汎用タイトルは避ける）
- 30〜50文字程度
- 例: 「AWS Lambdaのコールドスタートを1秒以下に抑える3つの方法」

その後、空行を1行挟んで記事本文（## はじめに から始まる）を書いてください。

---

## テーマ
{topic_name}：{topic_subtitle}

## 今回の切り口
{angle}
この切り口を軸に記事を構成してください（同じサービスでも切り口を変えることで内容の重複を避けます）。

## キーワード（記事中に自然に含めること）
{keywords}

{docs_section}
{diagram_section}
## 読者像
プログラミング経験はあるが、AWSをほぼ使ったことがない初級エンジニア。
「概念を知りたい」より「実際に動かして仕事で使いたい」が動機。

---

## 品質の原則

**書くこと**
- 冒頭で「誰の・どんな問題を・どう解決するか」を1段落以内に伝える
- 具体的な数字・コマンド・レスポンス例で語る（「高速です」ではなく「〜ms以下」）
- 1文1意。「〜し、〜であり、〜するため」は分割する
- 「〜できます」（「〜することができます」は使わない）
- 各ステップに「なぜそうするか」の理由を添える

**書かないこと・避けること**
- 「本記事では〜について解説します」（宣言型の導入）
- 「非常に重要です」「ぜひ試してみてください」（根拠のない煽り文句）
- 読者が知っていることの説明（「AWSはクラウドです」等の自明な前提）
- 前セクションをそのままなぞるだけのまとめ
- 根拠のない最上級表現（「最も優れた」「業界標準」）
- 文章で書けるのに箇条書きに逃げる（流れを作れる部分は文章で書く）
- 手順を示さずに「〜は簡単です」と言う

---

## Zenn Markdown記法（効果的な場面でのみ使う）

**テーブル**: 比較・一覧が読者の判断を助ける場面で使う
**:::message**: 読者が見落としやすい重要ポイントのみ（乱発しない）
**:::message alert**: コスト・セキュリティの具体的な注意（「注意してください」だけでなく何に注意するかを書く）
**:::details**: 読まなくてもメインが理解できる応用・補足
**コードブロック**: 言語またはファイル名を必ず指定

使用例:
:::message
重要なポイント（読者が見落としやすいこと）
:::

:::message alert
コスト・セキュリティの注意（具体的に書く）
:::

:::details 応用：本番環境向けの設定
補足内容
:::

```bash:動作確認
aws s3 ls
```

```json:レスポンス例
{{"status": "ok"}}
```

---

## 記事の見出し構成

「はじめに」と「まとめ」は必ず含める。
中間セクションはサービスの特性・読者の理解フローに合わせて自由に構成する（毎回同じ構成にしなくてよい）。

### ## はじめに
- **冒頭の1文で {topic_name} が「誰の・どんな問題を・どう解決するか」を伝える**
  - 課題から入る例: 「〜に困ったことはありませんか？{topic_name}を使うと〜」
  - 本質から入る例: 「{topic_name}は〜するためのサービスです。これがあると〜が不要になります」
  - 「この記事では〜を解説します」という宣言は使わない
- この記事を読むと「何ができるようになるか」を1〜2文で示す
- 書き終えたら以下のマーカーを**単独行**で挿入（前後に空行必須）:

{{DIAGRAM_1}}

  直前に図を見る動機づけになる1〜2文を書く（毎回違う切り口で。例文のコピー不可）:
  - 「{topic_name}の全体像を先に掴んでおくと、以降の説明がすっと入ってきます。」
  - 「実際の現場でどう使われているか、構成図から先に見ておきましょう。」

### 中間セクション（以下から選んで自由に構成する）

| 要素 | 内容 |
|------|------|
| サービス概要 | 役割・特徴・ユースケース 2〜3例。`:::message` で一言まとめ |
| 料金体系 | Free Tier・主要課金項目。`:::message alert` で見落としやすいコスト |
| ハンズオン | AWSコンソール操作手順（下記参照） |
| アーキテクチャ / 連携パターン | 実務でよく使う構成例・他サービスとの組み合わせ |
| ベストプラクティス / 落とし穴 | 実務で詰まるポイント・よくある設定ミス |
| 他サービスとの使い分け | 「〇〇との違い」「どちらを選ぶか」の判断基準 |

**ハンズオンを含める場合**、セクション冒頭（手順前）に以下を挿入（前後に空行必須）:

{{DIAGRAM_2}}

  直前に図を見る動機づけになる1〜2文を書く（毎回違う切り口で）

ハンズオンに必ず含めること:
- **前提条件**（必要なもの。箇条書き）
- **操作手順**（番号付き。各ステップに「なぜそうするか」とつまずきやすいポイント）
- **動作確認**（コマンドまたはブラウザ操作 ＋ **成功時のレスポンス例をコードブロックで必ず示す**）
- **後片付け**（料金が発生しないようリソースを削除する手順）

### ## まとめ
- **「次に何をすべきか」を中心に書く**（学んだことの箇条書き再掲は避ける）
- {topic_name}を使うべき場面・使わなくてよい場面の整理
- 次のステップとして効果的な関連サービスの提案

---

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |

## OS・AMIの鮮度（必須）

EC2のAMIにディストリビューション名を出す場合、**サポート終了（EOL）済みのバージョンを新規構築の例に使わない**こと。

| 対象 | 状態 | 記事での扱い |
| --- | --- | --- |
| Amazon Linux 2 | 2026年6月30日でEOL済み | 新規構築の例には使わない。使うなら**Amazon Linux 2023**（AMIフィルタ例: `al2023-ami-*-x86_64`）を使う |

---

## 注意事項
- **記事の先頭にYAML frontmatter（--- で囲まれたブロック）を書かない**（frontmatterはシステムが自動付与する）
- 見出しは ## や ### を使ったMarkdown形式で書く（# は使わない）
- コードやコマンドはバッククォート3つで囲み、言語名またはファイル名を指定する
- 重要な用語は**太字**で強調する
- AWSコンソールの操作は具体的なメニュー名やボタン名を明記する
- 料金は2026年時点の情報を参考にし「最新情報はAWS公式サイトで確認してください」と注記する
- curlコマンドやブラウザ確認では**成功時のレスポンス例を必ずコードブロックで示す**（「結果が表示されます」のような曖昧な表現は使わない）
- `:::message` や `:::details` は前後に必ず空行を入れること
- コードブロック内のサンプル日付は**本日の日付（{today}）** を基準にする（`2024`や`2023`等の過去の年は使わない。連番が必要な場合は翌日・数時間後など`{today}`前後の日付を使う）
- **文字数**: 4,000〜8,000文字程度が目安（水増しは避けつつ、完全なコード例・正確な内容を優先する。目安を大きく下回る場合のみ注意する）

---

## コード品質の必須ルール

### IAM ポリシー
- IAM ポリシーは最小権限で書く。`Resource: '*'` を使う場合はその理由を文中で説明する
- `Describe*` / `List*` 系アクションはリソース条件を非サポートのため `Resource: '*'` のみで記述し、変更系アクション（`Put*` / `Delete*` / `Stop*` 等）と同一ステートメントに混在させない

### Lambda Runtime
- Lambda の Runtime は現時点の最新安定版を使う: `python3.14`（Python）/ `nodejs22.x`（Node.js）
- 旧バージョン（`python3.13` 以前 / `nodejs20.x` 等）は使わない

### AWS CLI の正確性
- 記事内のコードは省略・疑似コードなしで、**実際に動く完全な記述**にする
- CLIコマンドは `--region ap-northeast-1` を明示する
- コマンドで使い回す値（バケット名・ロール名等）は冒頭の変数定義ブロックにまとめる（例: `BUCKET_NAME=my-app-bucket`）
- SNS メール購読はデプロイ後に**確認メールのクリックが必要**な旨を記事内で必ず明記する
- **オプション名を記憶だけで作らない**。特に以下は誤りが多いので注意する:
  - 真偽値オプションは `--flag` / `--no-flag` の形式（`--flag true` のように値を渡す形式ではない。例: RDSの`--publicly-accessible` / `--no-publicly-accessible`）
  - セキュリティグループを参照元に指定する場合は `--source-group`（`--source-security-group-id` のような存在しないオプション名を作らない）
  - 自信のないオプション名は、確実に存在するシンプルな代替手段（例: `--cidr` でIP範囲指定）に置き換える
- **リソース間の依存関係・作成順序の制約に注意する**（例: RDSのDBサブネットグループは最低2つのAZにまたがるサブネットが必要。セキュリティグループを相互参照させた場合、削除時は参照されている側を先に消さないとエラーになる）
- 「後片付け」セクションは、記事内で作成した**全リソースの削除コマンドを省略せず**書く（「〜も忘れずに削除してください」のような文章だけで済ませない）。削除順序は依存関係の逆順（作成と逆順、かつ相互参照があるものはそれも考慮）にする

### AWS サービスの制約
- サービスの「できないこと・注意点」を「できること」と同等の重みで記載する
- 料金は断定的に書かず幅を持たせる（「〜円程度」「〜$以下」形式）
- **NATゲートウェイ**: 「数百円/月」のような過小な金額を書かない。時間課金＋データ処理量課金の両方がかかり、24時間稼働なら東京リージョンで**月数千円規模（目安$45前後＋データ処理料）**になる
- **ALB（Application Load Balancer）自体は台数を自動増減しない**。トラフィック増加時のインスタンス自動追加は**Auto Scaling**の役割であり、ALBは分散のみを担う。両者を混同して「ALBが自動でインスタンスを追加する」と書かない
"""


# ─── AWS公式ドキュメント取得 ──────────────────────────────────────────────────

def fetch_aws_docs(topic_id: str, max_chars: int = 6000) -> str:
    """AWS公式ドキュメントを取得してプレーンテキストを返す。失敗時は空文字列。"""
    import re
    import urllib.request

    url = DOCS_URL_MAP.get(topic_id, "")
    if not url:
        print(f"[Docs] {topic_id}: URL未定義のためスキップ")
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)

        main = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
        content = main.group(1) if main else html

        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        print(f"[Docs] {topic_id}: {len(text)}文字取得 ({url})")
        return text[:max_chars]
    except Exception as e:
        print(f"[Docs] {topic_id}: 取得エラー（スキップ）: {e}")
        return ""


# ─── SSM: トピック・切り口の重複除外 ──────────────────────────────────────────

def _get_recent_ids(ssm_path: str) -> list[str]:
    """SSM から直近のID履歴リストを取得する（トピック・切り口共通）"""
    try:
        response = ssm.get_parameter(Name=ssm_path)
        ids = json.loads(response["Parameter"]["Value"])
        return ids if isinstance(ids, list) else []
    except ssm.exceptions.ParameterNotFound:
        return []
    except Exception as e:
        print(f"[WARNING] SSM読み込みエラー（{ssm_path}）。除外なしで続行します（同内容が連続生成される可能性あり）: {e}")
        return []


def _save_recent_id(ssm_path: str, item_id: str, limit: int, dry_run: bool = False) -> None:
    """選択したIDをSSMに保存する（最新limit件を保持、トピック・切り口共通）"""
    if dry_run:
        print(f"[DRY_RUN] SSM書き込みスキップ: {ssm_path}")
        return
    recent = _get_recent_ids(ssm_path)
    if item_id in recent:
        recent.remove(item_id)
    recent.append(item_id)
    recent = recent[-limit:]
    try:
        ssm.put_parameter(
            Name=ssm_path,
            Value=json.dumps(recent),
            Type="String",
            Overwrite=True,
        )
        print(f"SSM保存完了（{ssm_path}）: {recent}")
    except Exception as e:
        print(f"SSM書き込みエラー（{ssm_path}、無視して続行）: {e}")


def get_recent_topics() -> list[str]:
    return _get_recent_ids(SSM_PARAM_PATH)


def save_topic_to_ssm(topic_id: str, dry_run: bool = False) -> None:
    _save_recent_id(SSM_PARAM_PATH, topic_id, RECENT_TOPICS_LIMIT, dry_run=dry_run)


def get_recent_angles() -> list[str]:
    return _get_recent_ids(SSM_ANGLE_PARAM_PATH)


def save_angle_to_ssm(angle: str, dry_run: bool = False) -> None:
    _save_recent_id(SSM_ANGLE_PARAM_PATH, angle, RECENT_ANGLES_LIMIT, dry_run=dry_run)


def _extract_bedrock_text(result: dict) -> str | None:
    """Bedrock invoke_model のレスポンスから安全にテキストを取り出す。
    ガードレール発動・異常終了等で content が空配列になることがあり、
    result["content"][0]["text"] を直接書くと IndexError で未処理クラッシュする。"""
    content = result.get("content") or []
    if not content:
        return None
    text = content[0].get("text")
    return text if isinstance(text, str) else None


# ─── トピック・切り口の選択 ────────────────────────────────────────────────────

def select_topic(excluded_ids: list[str]) -> dict:
    """重複を避けながらランダムにトピックを選択する。
    以前はBedrockに選ばせていたが、LLMのランダム選択は先頭・有名サービスに
    偏りやすいうえフォールバックも常にrandom.choiceだったため実質的な効果がなく、
    Bedrock呼び出し1回分のコスト・レイテンシ・障害点だけが残っていた
    （2026-07-05ブラッシュアップでrandom.choiceに統一）。"""
    available = [t for t in AWS_TOPICS if t["id"] not in excluded_ids]
    if not available:
        # 全トピックが除外済みの場合（通常は発生しない）はリセット
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS
    return random.choice(available)


def select_angle(excluded_angles: list[str]) -> str:
    """直近使用した切り口を避けながらランダムに選択する"""
    available = [a for a in _DEFAULT_ANGLES if a not in excluded_angles]
    if not available:
        available = _DEFAULT_ANGLES
    return random.choice(available)


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict, today: str, angle: str, diagram_titles: list[str]) -> tuple[str, str, bool, dict]:
    """Bedrock を使って記事を生成する。(article_text, title, is_truncated, meta) を返す"""
    docs_content = fetch_aws_docs(topic["id"])
    docs_section = (
        "## AWS公式ドキュメント（根拠情報）\n"
        "以下はAWS公式ドキュメントから取得した情報です。技術的事実はこの内容を根拠として正確に記述し、矛盾しないようにしてください。\n"
        "ドキュメントに記載のない事実は、確実に知っている場合のみ記述し、不確かな場合は記述しないか「〜の場合があります」等の不確定表現を使ってください。\n\n"
        f"{docs_content}\n\n---\n"
        if docs_content else ""
    )
    diagram_section = ""
    if diagram_titles:
        diagram_lines = "\n".join(f"- 図{i}: {t}" for i, t in enumerate(diagram_titles, start=1))
        diagram_section = (
            "## 構成図（本文と整合させること）\n"
            "記事中には以下の構成図が挿入されます。図の直前の説明文・ハンズオン手順の内容はこの構成と一致させてください。\n"
            f"{diagram_lines}\n\n---\n"
        )
    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        keywords=topic["keywords"],
        today=today,
        docs_section=docs_section,
        diagram_section=diagram_section,
        angle=angle,
    )

    response = bedrock.invoke_model(
        modelId=BEDROCK_ARTICLE_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = _extract_bedrock_text(result)
    if text is None:
        raise RuntimeError(
            f"Bedrock記事生成の応答からcontentが取得できませんでした（stop_reason={result.get('stop_reason')}）"
        )
    usage = result.get("usage", {})
    stop_reason = result.get("stop_reason", "unknown")
    is_truncated = stop_reason == "max_tokens"
    in_tok  = usage.get('input_tokens', 0)
    out_tok = usage.get('output_tokens', 0)
    cost_usd = (in_tok * 0.80 + out_tok * 4.0) / 1_000_000  # Haiku pricing (概算)
    print(f"[Bedrock/article] model={BEDROCK_ARTICLE_MODEL_ID} in={in_tok}, out={out_tok}, stop={stop_reason}, cost≈${cost_usd:.4f}")
    if is_truncated:
        print("[WARNING] 記事がmax_tokensで打ち切られました。記事が不完全な可能性があります。")

    # 1行目の TITLE: を抽出してから本文を分離する
    title = f"{topic['name']}：{topic['subtitle']}"  # デフォルト（抽出失敗時のフォールバック）
    text_stripped = text.lstrip()
    if text_stripped.startswith("TITLE:"):
        first_line, _, rest = text_stripped.partition("\n")
        extracted = first_line[len("TITLE:"):].strip()
        if extracted:
            title = extracted
            print(f"[Title] 抽出成功: {title}")
        text = rest.lstrip()
    else:
        print(f"[Title] TITLE: 行が見つからず。フォールバックタイトルを使用: {title}")

    # Bedrock が記事冒頭に YAML frontmatter を付けることがあるため除去する
    if text.lstrip().startswith("---"):
        lines = text.lstrip().splitlines(keepends=True)
        end = 1
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                end = i + 1
                break
        text = "".join(lines[end:]).lstrip()

    meta = {
        "cost_usd": cost_usd,
        "stop_reason": stop_reason,
        "in_tokens": in_tok,
        "out_tokens": out_tok,
        "docs_chars": len(docs_content),
        "angle": angle,
    }
    return text, title, is_truncated, meta


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
        import re as _re
        # マーカーは format() 後に単一波括弧 {DIAGRAM_N} となる。
        # 二重波括弧 {{...}} とのどちらが残っても除去できるようにする。
        cleaned, n = _re.subn(r'\n*\{\{?DIAGRAM_\d+\}\}?\n*', '\n\n', article)
        if n:
            print(f"[WARNING] PNG未生成のためDIAGRAMマーカー{n}件を除去しました")
        return cleaned

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
            if not h2_positions:
                # 見出しが1つも無い場合は末尾に追記（IndexError 回避）
                print(f"[WARNING] DIAGRAM_{n} のマーカー・見出しが見つからないため末尾に挿入します")
                result = result.rstrip() + "\n\n" + placeholder
                continue
            if target:
                matched = [i for i, line in enumerate(lines)
                           if line.startswith("## ") and target in line]
                insert_idx = matched[0] if matched else \
                    h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            else:
                insert_idx = h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            lines.insert(insert_idx + 1, placeholder)
            result = "\n".join(lines)

    # 図の一部が生成失敗した場合、残存する {DIAGRAM_N} マーカーを除去する
    import re as _re
    result, n_orphan = _re.subn(r'\n*\{DIAGRAM_\d+\}\n*', '\n\n', result)
    if n_orphan:
        print(f"[WARNING] 図生成失敗により未置換のDIAGRAMマーカー{n_orphan}件を除去しました")

    return result


SSM_COUNTER_PATH = "/zenn-article-bot/article-counter"

def _next_article_number(output_dir: str, dry_run: bool = False) -> str:
    """SSMカウンターから次の記事番号を取得してインクリメントする（例: '016'）"""
    try:
        resp = ssm.get_parameter(Name=SSM_COUNTER_PATH)
        current = int(resp["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        current = 0
    except (ValueError, TypeError) as e:
        print(f"[WARNING] 記事番号カウンターの値が不正です。0から再開します: {e}")
        current = 0
    next_num = current + 1
    if dry_run:
        print(f"[DRY_RUN] 記事番号カウンター書き込みスキップ（プレビュー番号: {next_num:03d}）")
    else:
        try:
            ssm.put_parameter(Name=SSM_COUNTER_PATH, Value=str(next_num), Type="String", Overwrite=True)
        except Exception as e:
            print(f"[WARNING] 記事番号カウンターの保存に失敗（番号は採番済みとして続行）: {e}")
    return f"{next_num:03d}"


def _prepare_article_paths(topic: dict, timestamp: str, output_dir: str, dry_run: bool = False) -> tuple[str, str]:
    """記事の出力先ディレクトリを準備する。(mdパス, 構成図ベースパス) を返す"""
    os.makedirs(output_dir, exist_ok=True)

    base_name   = f"{timestamp}_{topic['id']}"
    num         = _next_article_number(output_dir, dry_run=dry_run)
    article_dir = os.path.join(output_dir, f"{num}_{base_name}")
    images_dir  = os.path.join(article_dir, "images")
    os.makedirs(article_dir, exist_ok=True)
    os.makedirs(images_dir,  exist_ok=True)

    md_path  = os.path.join(article_dir, f"{base_name}.md")
    png_base = os.path.join(images_dir,  f"{base_name}_diagram")
    return md_path, png_base


def save_to_local(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, title: str,
) -> str:
    """記事を MD ファイルに保存する（構成図は生成済みの png_paths を使用）。mdパスを返す"""
    # 図1・図2ともに {DIAGRAM_N} マーカーで記事中に挿入（マーカー不在時はフォールバック）
    article_with_images = _embed_image_placeholders(article, png_paths, topic["name"])

    # Zennフロントマター用メタ情報
    meta = _ZENN_META.get(topic["id"], {"emoji": "☁️", "topics": ["aws", "クラウド"]})
    topics_json = json.dumps(meta["topics"], ensure_ascii=False)
    frontmatter_title = title if title else f"{topic['name']}：{topic['subtitle']}"

    full_content = f"""---
title: "{frontmatter_title}"
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

    return md_path


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


# ─── 記事の軽微な自動修正（Bedrock再呼び出し不要・コストゼロ） ──────────────────

_OLD_RUNTIME_MAP = {
    "python3.12": "python3.13", "python3.11": "python3.13",
    "python3.10": "python3.13", "python3.9": "python3.13",
    "nodejs20.x": "nodejs22.x", "nodejs18.x": "nodejs22.x",
}


def _auto_fix_article(article_text: str) -> tuple[str, list[str]]:
    """Bedrockを再呼び出しせず、文字列置換だけで安全に直せる軽微な問題だけを自動修正する。
    文字数不足・:::message対応漏れ・図の欠落など内容そのものに関わる問題は対象外（要手動確認）。
    (修正後テキスト, 適用した修正の説明リスト) を返す。"""
    text = article_text
    fixes = []

    # 1. 古いLambdaランタイム表記を最新に置換
    for old, new in _OLD_RUNTIME_MAP.items():
        if old in text:
            text = text.replace(old, new)
            fixes.append(f"古いランタイム表記 `{old}` → `{new}` に置換")

    # 2. コードブロック外のh1見出し（# xxx）を h2（## xxx）に格上げ
    lines = text.splitlines(keepends=True)
    in_code = False
    h1_fixed = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not in_code and stripped.startswith("# ") and not stripped.startswith("## "):
            lines[i] = "#" + line
            h1_fixed += 1
    if h1_fixed:
        text = "".join(lines)
        fixes.append(f"h1見出し{h1_fixed}件を##に格上げ")

    # 3. 言語/ファイル名指定のないコードブロック開始行に text を補完
    lines = text.splitlines(keepends=True)
    in_code = False
    bare_fixed = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped.startswith("```"):
            if not in_code and stripped == "```":
                lines[i] = line.replace("```", "```text", 1)
                bare_fixed += 1
            in_code = not in_code
    if bare_fixed:
        text = "".join(lines)
        fixes.append(f"言語/ファイル名指定のないコードブロック{bare_fixed}件に`text`を補完")

    # 4. 記事中に --region が一つもない場合、単一行で完結するAWS CLIコマンドにのみ補完
    #    （行末が\の複数行コマンドは、他行に--regionがある可能性があり誤修正のリスクがあるため対象外）
    if "aws " in text and "--region" not in text:
        lines = text.splitlines(keepends=True)
        region_fixed = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("aws ") and not stripped.endswith("\\"):
                ending = "\n" if line.endswith("\n") else ""
                lines[i] = line.rstrip("\n") + " --region ap-northeast-1" + ending
                region_fixed += 1
        if region_fixed:
            text = "".join(lines)
            fixes.append(f"--region未指定のAWS CLIコマンド{region_fixed}件に `--region ap-northeast-1` を補完")

    return text, fixes


# ─── 記事品質チェック ─────────────────────────────────────────────────────────

def validate_article(article_text: str, char_count: int) -> list[str]:
    """記事の品質を機械的にチェックする（文字数・Markdown記法・CLIコマンドの体裁など）"""
    import re as _re
    issues = []
    lines = article_text.splitlines()

    if "aws " not in article_text:
        issues.append("AWS CLIコマンドが見つかりません")
    elif "--region" not in article_text:
        issues.append("AWS CLIコマンドに --region の明示が見当たりません")

    # 目標は4,000〜8,000文字程度だが、内容充実を優先する方針上、実測は8,000〜9,500文字台になることもある
    # （2026-07-05確認）。上限超過は許容し、極端に短い場合（＝内容不足・生成異常の兆候）のみ検出する
    if char_count < 3000:
        issues.append(f"文字数が目安(4,000〜8,000文字程度)に対して少なすぎます: {char_count:,}文字")

    open_count  = sum(1 for l in lines if l.strip().startswith(":::") and l.strip() != ":::")
    close_count = sum(1 for l in lines if l.strip() == ":::")
    if open_count != close_count:
        issues.append(f":::message / :::details の開始・終了が対応していません（開始{open_count}件 / 終了{close_count}件）")

    in_code = False
    bad_code_blocks = 0
    h1_found = False
    for l in lines:
        if l.startswith("```"):
            if not in_code and l.strip() == "```":
                bad_code_blocks += 1
            in_code = not in_code
            continue
        # h1見出しチェックはMarkdown本文のみ対象（コードブロック内のシェルコメント "# ..." を誤検出しないため）
        if not in_code and _re.match(r'^# [^#]', l):
            h1_found = True
    if bad_code_blocks:
        issues.append(f"言語/ファイル名指定のないコードブロックが{bad_code_blocks}件あります")
    if h1_found:
        issues.append("h1見出し（# ）が混入しています（見出しは##以下を使うルール）")

    for old_runtime in ("python3.12", "python3.11", "python3.10", "python3.9", "nodejs20.x", "nodejs18.x"):
        if old_runtime in article_text:
            issues.append(f"古いLambdaランタイム記載が見つかりました: {old_runtime}")

    if "## はじめに" not in article_text:
        issues.append("## はじめに セクションが見つかりません")
    if "## まとめ" not in article_text:
        issues.append("## まとめ セクションが見つかりません")

    print(f"[記事検証] 必須要素チェック完了 / 問題{len(issues)}件")
    return issues


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, title: str = "", s3_url: str = "", is_truncated: bool = False,
    issues: list | None = None, angle: str = "", gen_meta: dict | None = None,
    applied_fixes: list | None = None,
):
    """SES でメール通知を送信する"""
    import html as _html
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    preview_html = _html.escape(preview)
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    gen_meta = gen_meta or {}
    headings = [l[3:].strip() for l in article.splitlines() if l.startswith("## ")]
    headings_text = "\n".join(f"  - {h}" for h in headings) if headings else "  (見出しなし)"
    headings_html = "".join(f"<li>{_html.escape(h)}</li>" for h in headings) if headings else "<li>(見出しなし)</li>"
    docs_fetched = gen_meta.get("docs_chars", 0) > 0
    docs_info = f"取得成功（{gen_meta['docs_chars']:,}文字）" if docs_fetched else "取得なし"
    cost_usd = gen_meta.get("cost_usd")
    cost_info = f"${cost_usd:.4f}" if cost_usd is not None else "不明"
    stop_reason = gen_meta.get("stop_reason", "unknown")

    subject = (
        f"【⚠️ 記事が途中で切れています】{topic['name']} - {timestamp}"
        if is_truncated else
        f"【Zenn記事生成完了】{topic['name']}の記事が生成されました - {timestamp}"
    )

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
        '<code>bash ~/Zer0/002_Zenn_Auto_Article_Bot/scripts/download_article.sh</code></li>'
        if s3_url else ""
    )

    issues = issues or []
    applied_fixes = applied_fixes or []
    fixes_text = ("\n".join(f"  - {f}" for f in applied_fixes)) if applied_fixes else "  (なし)"
    fixes_html = "".join(f"<li>{_html.escape(f)}</li>" for f in applied_fixes) if applied_fixes else "<li>(なし)</li>"

    truncation_warning_text = """
⚠️ 警告: 記事が途中で切れています
記事の生成がmax_tokensに達したため、末尾が不完全な可能性があります。
Zennに投稿する前に内容を必ず確認してください。
""" if is_truncated else ""

    issues_warning_text = (
        "⚠️ 記事品質チェックで問題が見つかりました:\n"
        + "\n".join(f"  - {i}" for i in issues) + "\n"
    ) if issues else ""

    body_text = f"""Zenn技術記事の自動生成が完了しました。
{truncation_warning_text}{issues_warning_text}
■ 記事情報
- タイトル: {title}
- テーマ: {topic['name']}（{topic['subtitle']}）
- 切り口: {angle}
- 文字数: {char_count:,}文字
- 生成日時: {timestamp}
- 構成図PNG: {diagram_info}
- S3保存先: {s3_url}
- AWS公式ドキュメント: {docs_info}
- Bedrockコスト概算: {cost_info}（stop_reason={stop_reason}）

■ 見出し一覧
{headings_text}

■ 自動修正（Bedrock再呼び出しなし）
{fixes_text}

■ 記事プレビュー（先頭300文字）
{preview}...

■ 次のアクション
1. bash ~/Zer0/002_Zenn_Auto_Article_Bot/scripts/download_article.sh
2. Zennエディタで新規記事を作成（または zenn-cli で管理）
3. MDファイルの内容を貼り付け
4. :::message ブロック内の指示に従ってPNGをアップロード・差し替え
5. published: false → true に変更して公開

このメールは自動送信されています。
"""

    truncation_warning_html = """
  <div style="background:#fff3cd;border:2px solid #f0ad4e;padding:15px;border-radius:8px;margin:20px 0;">
    <h3 style="color:#856404;margin-top:0;">⚠️ 記事が途中で切れています</h3>
    <p style="color:#856404;margin:0;">
      記事の生成が <code>max_tokens</code> に達したため、末尾が不完全な可能性があります。<br>
      Zennに投稿する前に内容を必ず確認してください。
    </p>
  </div>
""" if is_truncated else ""

    issues_html = (
        '<div style="background:#fde8e8;border:2px solid #e53e3e;padding:15px;border-radius:8px;margin:20px 0;">'
        '<h3 style="color:#c53030;margin-top:0;">⚠️ 記事品質チェックで問題が見つかりました</h3>'
        '<ul style="color:#c53030;margin:0;">'
        + "".join(f'<li><code>{i}</code></li>' for i in issues)
        + '</ul></div>'
    ) if issues else (
        '<div style="background:#e8f5e9;border:1px solid #66bb6a;padding:10px 15px;border-radius:8px;margin:20px 0;">'
        '<p style="color:#2e7d32;margin:0;">✅ 記事品質チェック — 問題なし</p>'
        '</div>'
    )

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#3EA8FF;">Zenn技術記事の自動生成が完了しました</h2>
  {truncation_warning_html}
  {issues_html}

  <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事情報</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:5px;font-weight:bold;">タイトル</td>
          <td>{_html.escape(title)}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">テーマ</td>
          <td>{topic['name']}（{topic['subtitle']}）</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">切り口</td>
          <td>{_html.escape(angle)}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">文字数</td>
          <td>{char_count:,}文字</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">生成日時</td>
          <td>{timestamp}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">構成図PNG</td>
          <td><ul style="margin:0;padding-left:16px;">{png_list_html}</ul></td></tr>
      <tr><td style="padding:5px;font-weight:bold;">AWS公式ドキュメント</td>
          <td>{docs_info}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">Bedrockコスト概算</td>
          <td>{cost_info}（stop_reason={stop_reason}）</td></tr>
      {s3_row}
    </table>
  </div>

  <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>見出し一覧</h3>
    <ul style="margin:0;padding-left:16px;">{headings_html}</ul>
  </div>

  <div style="background:#eef6fc;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>自動修正（Bedrock再呼び出しなし）</h3>
    <ul style="margin:0;padding-left:16px;">{fixes_html}</ul>
  </div>

  <div style="background:#fff8e1;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事プレビュー</h3>
    <p style="color:#555;">{preview_html}...</p>
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

def run(dry_run: bool = False):
    _total_start = time.time()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    today     = now.strftime("%Y-%m-%d")

    if dry_run:
        print(f"[{timestamp}] [DRY_RUN] Zenn技術記事自動生成を開始します（S3保存・メール送信・SSM書き込みをスキップ）")
    else:
        print(f"[{timestamp}] Zenn技術記事自動生成を開始します")

    # Step 1: トピック・切り口の選択
    _t = time.time()
    print("Step 1: トピック・切り口を選択中...")
    recent_topics = get_recent_topics()
    print(f"  除外トピック（直近{len(recent_topics)}件）: {recent_topics}")
    topic = select_topic(excluded_ids=recent_topics)
    save_topic_to_ssm(topic["id"], dry_run=dry_run)

    recent_angles = get_recent_angles()
    angle = select_angle(excluded_angles=recent_angles)
    save_angle_to_ssm(angle, dry_run=dry_run)
    print(f"  選択されたトピック: {topic['name']} / 切り口: {angle} [{time.time()-_t:.1f}s]")

    # Step 2: 出力先準備 + 構成図生成（記事プロンプトに図の内容を伝えるため記事生成より先に行う）
    _t = time.time()
    print("Step 2: 構成図を生成中...")
    output_dir = os.path.expanduser(OUTPUT_DIR)
    md_path, png_base = _prepare_article_paths(topic, timestamp, output_dir, dry_run=dry_run)
    png_paths, diagram_titles = generate_diagrams_with_titles(topic["id"], png_base)
    print(f"  PNG生成完了: {len(png_paths)}枚 [{time.time()-_t:.1f}s]" if png_paths else f"  PNG生成: スキップ [{time.time()-_t:.1f}s]")

    # Step 3: 記事生成
    _t = time.time()
    print("Step 3: 記事を生成中（4,000〜8,000文字程度）...")
    article, title, is_truncated, gen_meta = generate_article(topic, today, angle, diagram_titles)
    char_count = len(article)
    print(f"  記事生成完了: {char_count:,}文字 title={title!r} [{time.time()-_t:.1f}s]")

    # 軽微な問題を自動修正（Bedrock再呼び出しなし・コストゼロ）
    article, applied_fixes = _auto_fix_article(article)
    char_count = len(article)
    if applied_fixes:
        print(f"  自動修正 {len(applied_fixes)}件: {applied_fixes}")

    # Step 4: ローカル保存（MD + 画像プレースホルダー埋め込み）
    _t = time.time()
    print("Step 4: ファイル保存中...")
    save_to_local(topic, article, md_path, png_paths, timestamp, title)
    print(f"  MD保存完了: {md_path} [{time.time()-_t:.1f}s]")

    # Step 5: S3 アップロード
    _t = time.time()
    if dry_run:
        print("Step 5: [DRY_RUN] S3アップロードをスキップ")
        s3_url = "(dry_run: S3アップロードなし)"
    else:
        print("Step 5: S3にアップロード中...")
        s3_folder = f"{timestamp}_{topic['id']}"
        s3_url    = upload_to_s3(md_path, png_paths, s3_folder)
        print(f"  S3アップロード完了: {s3_url} [{time.time()-_t:.1f}s]")

    # Step 6: 記事品質チェック
    _t = time.time()
    print("Step 6: 記事品質をチェック中...")
    try:
        issues = validate_article(article, char_count)
        if len(png_paths) < 2:
            issues.append(f"構成図が{len(png_paths)}枚しか生成されていません（想定: 2枚）")
        if issues:
            print(f"  ⚠️ 品質チェック問題: {len(issues)}件 [{time.time()-_t:.1f}s]")
        else:
            print(f"  ✓ 品質チェック問題なし [{time.time()-_t:.1f}s]")
    except Exception as e:
        print(f"  品質チェックスキップ（無視して続行）: {e}")
        issues = []

    # Step 7: SES メール通知
    _t = time.time()
    if dry_run:
        print("Step 7: [DRY_RUN] メール送信をスキップ")
        print(f"  [DRY_RUN] タイトル: {title}")
        print(f"  [DRY_RUN] 自動修正: {applied_fixes if applied_fixes else 'なし'}")
        print(f"  [DRY_RUN] 品質チェック結果: {issues if issues else '問題なし'}")
    else:
        print("Step 7: メール通知を送信中...")
        send_email_notification(
            topic, article, md_path, png_paths, timestamp, title,
            s3_url, is_truncated, issues, angle, gen_meta, applied_fixes,
        )
        print(f"  メール送信完了 [{time.time()-_t:.1f}s]")

    # 構造化サマリーログ（CloudWatch Logs Insights での集計用）
    print(json.dumps({
        "metric": "zenn_article_generated",
        "topic": topic["id"],
        "angle": angle,
        "chars": char_count,
        "cost_usd": gen_meta.get("cost_usd"),
        "truncated": is_truncated,
        "docs_fetched": gen_meta.get("docs_chars", 0) > 0,
        "images": len(png_paths),
        "auto_fixed": len(applied_fixes),
        "quality_issues": len(issues),
        "duration_s": round(time.time() - _total_start, 1),
        "dry_run": dry_run,
    }, ensure_ascii=False))

    print(f"[{timestamp}] 処理完了 (合計: {time.time()-_total_start:.1f}s)")
    return topic, char_count, md_path, png_paths, s3_url


def lambda_handler(event, context):
    dry_run = bool((event or {}).get("dry_run", False))
    topic, char_count, md_path, png_paths, s3_url = run(dry_run=dry_run)
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "記事生成が完了しました" if not dry_run else "記事生成が完了しました（dry_run）",
                "topic":   topic["name"],
                "character_count": char_count,
                "images_generated": len(png_paths),
                "s3_url": s3_url,
                "dry_run": dry_run,
            },
            ensure_ascii=False,
        ),
    }


if __name__ == "__main__":
    run()
