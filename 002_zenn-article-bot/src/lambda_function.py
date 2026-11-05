import json
import os
import random
import time
import boto3
import datetime
from botocore.config import Config
# 構成図PNGの自動生成は廃止（2026-09-08〜）。画像はGPTに記事の質確認と合わせて
# 生成・最適配置を依頼する手動ワークフローへ移行した。diagram_generator.py は
# 将来また使う可能性があるため削除せず残してあるが、本体からは呼び出さない。

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
    # 新機能記事モード（2026-11-05〜）で追加したインフラ系サービス
    "systems_manager":     {"emoji": "🛠️",  "topics": ["aws", "ssm", "運用", "インフラ"]},
    "aurora":              {"emoji": "🌅",  "topics": ["aws", "aurora", "データベース", "クラウド"]},
    "eks":                 {"emoji": "☸️",  "topics": ["aws", "eks", "kubernetes", "コンテナ"]},
    "fargate":             {"emoji": "🚢",  "topics": ["aws", "fargate", "コンテナ", "サーバーレス"]},
    "ecr":                 {"emoji": "📦",  "topics": ["aws", "ecr", "コンテナ", "docker"]},
    "elb":                 {"emoji": "⚖️",  "topics": ["aws", "elb", "ネットワーク", "インフラ"]},
    "auto_scaling":        {"emoji": "📈",  "topics": ["aws", "autoscaling", "ec2", "インフラ"]},
    "efs":                 {"emoji": "🗂️",  "topics": ["aws", "efs", "ストレージ", "インフラ"]},
    "fsx":                 {"emoji": "🗄️",  "topics": ["aws", "fsx", "ストレージ", "インフラ"]},
    "backup":              {"emoji": "💾",  "topics": ["aws", "backup", "バックアップ", "インフラ"]},
    "kms":                 {"emoji": "🔑",  "topics": ["aws", "kms", "暗号化", "セキュリティ"]},
    "secrets_manager":     {"emoji": "🤫",  "topics": ["aws", "secretsmanager", "セキュリティ", "インフラ"]},
    "acm":                 {"emoji": "📜",  "topics": ["aws", "acm", "ssl", "セキュリティ"]},
    "waf":                 {"emoji": "🛡️",  "topics": ["aws", "waf", "セキュリティ", "ネットワーク"]},
    "shield":              {"emoji": "🛡️",  "topics": ["aws", "shield", "セキュリティ", "ddos"]},
    "network_firewall":    {"emoji": "🧱",  "topics": ["aws", "networkfirewall", "セキュリティ", "ネットワーク"]},
    "guardduty":           {"emoji": "👮",  "topics": ["aws", "guardduty", "セキュリティ", "監視"]},
    "security_hub":        {"emoji": "🛡️",  "topics": ["aws", "securityhub", "セキュリティ", "監視"]},
    "config":              {"emoji": "📋",  "topics": ["aws", "awsconfig", "ガバナンス", "セキュリティ"]},
    "cloudformation":      {"emoji": "🏗️",  "topics": ["aws", "cloudformation", "iac", "インフラ"]},
    "organizations":       {"emoji": "🏢",  "topics": ["aws", "organizations", "ガバナンス", "マルチアカウント"]},
    "control_tower":       {"emoji": "🗼",  "topics": ["aws", "controltower", "ガバナンス", "マルチアカウント"]},
    "identity_center":     {"emoji": "🪪",  "topics": ["aws", "iam", "sso", "セキュリティ"]},
    "transit_gateway":     {"emoji": "🔀",  "topics": ["aws", "transitgateway", "ネットワーク", "vpc"]},
    "direct_connect":      {"emoji": "🔌",  "topics": ["aws", "directconnect", "ネットワーク", "インフラ"]},
    "vpn":                 {"emoji": "🔐",  "topics": ["aws", "vpn", "ネットワーク", "インフラ"]},
    "eventbridge":         {"emoji": "📡",  "topics": ["aws", "eventbridge", "サーバーレス", "イベント駆動"]},
    "cost_management":     {"emoji": "💰",  "topics": ["aws", "コスト最適化", "請求", "クラウド"]},
    "amazon_linux":        {"emoji": "🐧",  "topics": ["aws", "amazonlinux", "linux", "インフラ"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
「読んでよかった」と思わせる記事を書いてください。テンプレートを埋める作業ではなく、読者の課題を解決する記事です。

**最優先事項: 文字数は見出し・コードも含めた記事全体で3,500〜4,000文字程度（長くても4,500文字以内）。
見出し（##）は「はじめに」「ポイント」「まとめ」の3つだけにし、ハンズオン（操作手順）は書かない。
ただし中身は薄くしない。「ポイント」では各要点を具体例・数字・理由まで踏み込んで書き、読者が仕事で使える判断材料を渡すこと。
超えそうな場合は要点の数を減らして収める（1つ1つの説明を浅くして数を増やすのは避ける）。**

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
3〜4分で読める記事で、仕事で使うときの勘所と判断基準をつかみたい。

---

## 品質の原則

**書くこと**
- 冒頭で「誰の・どんな問題を・どう解決するか」を1段落以内に伝える
- 具体的な数字で語る（「高速です」ではなく「〜ms以下」）
- 1文1意。「〜し、〜であり、〜するため」は分割する
- 「〜できます」（「〜することができます」は使わない）
- 要点には「なぜそうするか」の理由を一言添える

**書かないこと・避けること**
- 「本記事では〜について解説します」（宣言型の導入）
- 「非常に重要です」「ぜひ試してみてください」（根拠のない煽り文句）
- 読者が知っていることの説明（「AWSはクラウドです」等の自明な前提）
- 前セクションをそのままなぞるだけのまとめ
- 根拠のない最上級表現（「最も優れた」「業界標準」）
- 文章で書けるのに箇条書きに逃げる（流れを作れる部分は文章で書く）
- 手順を示さずに「〜は簡単です」と言う

---

## Zenn Markdown記法（最小限にする）

- `:::message`（読者が見落としやすい重要ポイント）または `:::message alert`（コスト・セキュリティの具体的な注意）を**最大1つ**まで使ってよい。前後に必ず空行を入れる
- テーブル・`:::details`は使わない
- コードブロックは設定例やコマンド例として説明に必要な場合のみ、最大2つ・各15行以内で、言語名を指定する（手順の羅列にはしない）

---

## 記事の見出し構成（この3見出しのみ。他の見出しは追加しない）

### ## はじめに（3〜5文）
- **冒頭の1文で {topic_name} が「誰の・どんな問題を・どう解決するか」を伝える**
- 「この記事では〜を解説します」という宣言は使わない

### ## ポイント
- 今回の切り口に沿った要点3つを、それぞれ `### ` の小見出しを付けて書く（小見出しは3つまで）
- 各要点は「何か → なぜ大事か（理由・仕組み） → 具体例（数字・設定値・よくある構成）」の順で、1要点あたり900〜1,100文字程度で書く（設定例があれば短いコードブロックで示してよい）
- 3つのうち1つは、初心者がつまずきやすい点またはコスト・セキュリティの注意にする
- 操作手順・ハンズオン・前提条件・後片付けは書かない

### ## まとめ（2〜3文）
- **「次に何をすべきか」を書く**（学んだことの箇条書き再掲は避ける）

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
- 重要な用語は**太字**で強調する
- 料金に触れる場合は断定せず幅を持たせる（「〜円程度」「〜$以下」形式）
- 日付に触れる場合は本日の日付（{today}）を基準にする
- **文字数**: 記事全体で3,500〜4,000文字程度（長くても4,500文字以内）

---

## 技術的な正確性
- サービスの「できないこと・注意点」も「できること」と同等に扱う
- **NATゲートウェイ**: 「数百円/月」のような過小な金額を書かない（24時間稼働なら東京リージョンで月数千円規模）
- **ALB自体は台数を自動増減しない**。インスタンスの自動追加はAuto Scalingの役割であり、両者を混同しない
- **Lambda Runtime**に触れる場合は最新安定版（`python3.14` / `nodejs24.x`）を使う
"""


NEWS_ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
AWSの新機能の発表を、AWSを使い始めたばかりのエンジニア向けに分かりやすく紹介する記事を書いてください。

**最優先事項: 文字数は見出し・コードも含めた記事全体で3,500〜4,000文字程度（長くても4,500文字以内）。
見出し（##）は「はじめに」「ポイント」「まとめ」の3つだけにし、ハンズオン（操作手順）は書かない。**

**最重要: 新機能の内容は、下の「発表内容（根拠情報）」と「関連する公式ドキュメント」に書かれている事実だけを書くこと。**
公式ドキュメントが英語の場合は、内容を正確に日本語にして使う。記事を厚くするための材料は、推測ではなく公式ドキュメントから取ること。
根拠情報に書かれていない仕様・料金・対応リージョン・提供開始日・数値を推測で補わない。分からないことは書かないか「詳細は公式発表を確認してください」とする。
特に次の書き方は禁止する（根拠情報に明記されている場合を除く）:
- 「これまでは〜できなかった」「従来は〜が限定的だった」など、以前の状態についての主張
- プロトコル名・内部の仕組み・セキュリティ上の性質など、根拠情報にない技術的な詳細の付け足し
- 発表に出てくる技術用語（製品名・機能名）の意味を、確信がないまま言い換えること
サービスの基本的な説明（そのサービスが何をするものか）だけは、一般に確立した知識の範囲で補ってよい。
「どんな場面で役立つか」は、根拠情報から素直に読み取れる利用シーンに留める。

## 出力形式（必須）
出力の**1行目**を次の形式にしてください。

TITLE: ここに記事タイトルを書く

タイトルのルール:
- サービス名と新機能の中身が分かる具体的な表現にする（発表タイトルの丸写しは避ける）
- 30〜50文字程度
- 例: 「Amazon EKS Auto ModeがGateway APIに対応、Ingressとの違いと使いどころ」

その後、空行を1行挟んで記事本文（## はじめに から始まる）を書いてください。

---

## 発表内容（根拠情報）
- サービス: {service_name}
- 発表タイトル: {news_title}
- 発表日: {news_date}

{news_body}

{news_docs_section}
{docs_section}
## 読者像
プログラミング経験はあるが、AWSをほぼ使ったことがない初級エンジニア。
7〜8分で読める記事で、この新機能が自分に関係あるか、使うなら何をすればよいかを判断したい。

---

## 品質の原則

**書くこと**
- 冒頭で「誰の・どんな問題を・どう解決するか」を1段落以内に伝える
- 具体的な数字で語る（「高速です」ではなく「〜ms以下」）
- 1文1意。「〜し、〜であり、〜するため」は分割する
- 「〜できます」（「〜することができます」は使わない）
- 要点には「なぜそうするか」の理由を一言添える

**書かないこと・避けること**
- 「本記事では〜について解説します」（宣言型の導入）
- 「非常に重要です」「ぜひ試してみてください」（根拠のない煽り文句）
- 読者が知っていることの説明（「AWSはクラウドです」等の自明な前提）
- 前セクションをそのままなぞるだけのまとめ
- 根拠のない最上級表現（「最も優れた」「業界標準」）
- 文章で書けるのに箇条書きに逃げる（流れを作れる部分は文章で書く）
- 手順を示さずに「〜は簡単です」と言う

---

## Zenn Markdown記法（最小限にする）

- `:::message`（読者が見落としやすい重要ポイント）または `:::message alert`（コスト・セキュリティの具体的な注意）を**最大1つ**まで使ってよい。前後に必ず空行を入れる
- テーブル・`:::details`は使わない
- コードブロックは設定例やコマンド例として説明に必要な場合のみ、最大2つ・各15行以内で、言語名を指定する（手順の羅列にはしない）

---

## 記事の見出し構成（この3見出しのみ。他の見出しは追加しない）

### ## はじめに（3〜5文）
- **冒頭の1文で「何が発表されたか」と「誰にうれしいか」を伝える**
- サービス自体を知らない初級者にも分かるよう、{service_name} が何をするサービスかを1文で添える
- 「この記事では〜を解説します」という宣言は使わない

### ## ポイント
- 次の5つを、それぞれ `### ` の小見出しを付けて書く（小見出しは5つまで。順番もこのとおり）
  1. 背景（この機能が関係する仕組みの基本と、何を解決するための機能か。以前の課題は根拠情報に書かれている場合のみ）
  2. 何が変わったのか（新機能の中身。主な機能・対応範囲を具体的に）
  3. 使い方のイメージ（公式ドキュメントにある設定例・マニフェスト・コマンド例を1〜2個、短いコードブロックで示し、各行が何をしているかを説明する。根拠情報に例がない場合はコードを書かず、設定の流れを文章で説明する）
  4. どんな場面で役立つか（初級者がイメージしやすい利用シーンを2つ程度）
  5. 使う前に知っておきたいこと（前提条件・制約・料金・対象リージョン・考慮事項のうち、根拠情報に書かれているもの）
- 各要点は600〜800文字程度。理由と具体例まで書く
- 「使い方のイメージ」は理解のための例示に留め、手順を1から10まで並べるハンズオンにはしない。後片付けは書かない

### ## まとめ（2〜3文）
- **「次に何をすべきか」を書く**（自分の環境で関係しそうか確認する、公式発表を読む、等）
- 出典リンクはシステムが記事末尾に自動で付けるので、本文に出典URLを書かない

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
- 重要な用語は**太字**で強調する
- 料金に触れる場合は断定せず幅を持たせる（「〜円程度」「〜$以下」形式）
- 日付に触れる場合は本日の日付（{today}）を基準にする
- **文字数**: 記事全体で3,500〜4,000文字程度（長くても4,500文字以内）

---

## 技術的な正確性
- サービスの「できないこと・注意点」も「できること」と同等に扱う
- **NATゲートウェイ**: 「数百円/月」のような過小な金額を書かない（24時間稼働なら東京リージョンで月数千円規模）
- **ALB自体は台数を自動増減しない**。インスタンスの自動追加はAuto Scalingの役割であり、両者を混同しない
- **Lambda Runtime**に触れる場合は最新安定版（`python3.14` / `nodejs24.x`）を使う
"""


# ─── 新機能記事モード（2026-11-05〜、既定） ──────────────────────────────────────
# 定番28トピック×切り口4種の解説は似た内容の記事が続くようになったため、
# AWS公式「最新情報」（What's New 日本語版）RSSから新機能の発表を1件選んで紹介する記事に切り替えた。
# 対象は従来の28トピックのサービス＋インフラ系サービスの発表に限る。
# 候補が無い・RSSが取れない場合は従来の定番解説（evergreen）にフォールバックする。
NEWS_FEED_URL = os.environ.get("NEWS_FEED_URL", "https://aws.amazon.com/jp/new/feed/")
SSM_NEWS_URL_PARAM_PATH = "/zenn-article-bot/recent-news-urls"
RECENT_NEWS_URLS_LIMIT = 60
NEWS_BODY_MAX_CHARS = 4000
# 発表本文は1件1,000文字前後しかなく4,000文字の記事の根拠には足りないため、
# 発表本文にリンクされた公式ドキュメント（docs.aws.amazon.com、約97%の発表にある）も取得して根拠に加える
NEWS_DOCS_MAX_PAGES = 2
NEWS_DOCS_MAX_CHARS_PER_PAGE = 7000
# 直近のトピック（サービス）を避ける段階。候補が尽きたら緩める（全除外→直近5件のみ除外→除外なし）
NEWS_RECENT_TOPIC_TIERS = (20, 5, 0)

# RSSの<category>に入る製品タグ（general:products/xxx）→ (トピックID, 表示名)。
# 従来28トピックのサービスは既存IDに寄せ（SSMの重複除外・Zennメタ・公式ドキュメントURLを共用するため）、
# それ以外はインフラ分野のサービスだけを追加している。ここに無いサービスの発表は候補にしない。
NEWS_PRODUCT_MAP: dict[str, tuple[str, str]] = {
    # 従来28トピックのサービス
    "amazon-ec2": ("ec2", "Amazon EC2"),
    "amazon-s3": ("s3", "Amazon S3"),
    "aws-iam": ("iam", "AWS IAM"),
    "amazon-vpc": ("vpc", "Amazon VPC"),
    "amazon-rds": ("rds", "Amazon RDS"),
    "amazon-rds-for-mysql": ("rds", "Amazon RDS"),
    "amazon-rds-for-postgresql": ("rds", "Amazon RDS"),
    "amazon-rds-for-mariadb": ("rds", "Amazon RDS"),
    "amazon-rds-for-oracle": ("rds", "Amazon RDS"),
    "amazon-rds-for-sql-server": ("rds", "Amazon RDS"),
    "aws-lambda": ("lambda", "AWS Lambda"),
    "amazon-cloudwatch": ("cloudwatch", "Amazon CloudWatch"),
    "amazon-ecs": ("ecs", "Amazon ECS"),
    "amazon-dynamodb": ("dynamodb", "Amazon DynamoDB"),
    "amazon-cloudfront": ("cloudfront", "Amazon CloudFront"),
    "amazon-api-gateway": ("api_gateway", "Amazon API Gateway"),
    "amazon-sqs": ("sqs", "Amazon SQS"),
    "amazon-simple-queue-service": ("sqs", "Amazon SQS"),
    "amazon-bedrock": ("bedrock", "Amazon Bedrock"),
    "amazon-sagemaker": ("sagemaker", "Amazon SageMaker AI"),
    "amazon-rekognition": ("rekognition", "Amazon Rekognition"),
    "amazon-textract": ("textract", "Amazon Textract"),
    "aws-step-functions": ("step_functions", "AWS Step Functions"),
    "amazon-sns": ("sns", "Amazon SNS"),
    "amazon-simple-notification-service": ("sns", "Amazon SNS"),
    "amazon-elasticache": ("elasticache", "Amazon ElastiCache"),
    "amazon-route-53": ("route53", "Amazon Route 53"),
    "amazon-kinesis": ("kinesis", "Amazon Kinesis"),
    "amazon-kinesis-data-streams": ("kinesis", "Amazon Kinesis"),
    "amazon-data-firehose": ("kinesis", "Amazon Kinesis"),
    "aws-cloudtrail": ("cloudtrail", "AWS CloudTrail"),
    "amazon-elastic-block-store": ("ec2_ebs", "Amazon EBS"),
    "amazon-ebs": ("ec2_ebs", "Amazon EBS"),
    "aws-privatelink": ("vpc_endpoint", "AWS PrivateLink"),
    # インフラ分野の追加サービス
    "aws-systems-manager": ("systems_manager", "AWS Systems Manager"),
    "amazon-aurora": ("aurora", "Amazon Aurora"),
    "amazon-eks": ("eks", "Amazon EKS"),
    "aws-fargate": ("fargate", "AWS Fargate"),
    "amazon-ecr": ("ecr", "Amazon ECR"),
    "elastic-load-balancing": ("elb", "Elastic Load Balancing"),
    "amazon-ec2-auto-scaling": ("auto_scaling", "Amazon EC2 Auto Scaling"),
    "aws-auto-scaling": ("auto_scaling", "AWS Auto Scaling"),
    "amazon-efs": ("efs", "Amazon EFS"),
    "amazon-fsx": ("fsx", "Amazon FSx"),
    "amazon-fsx-for-windows-file-server": ("fsx", "Amazon FSx"),
    "amazon-fsx-netapp-ontap": ("fsx", "Amazon FSx"),
    "amazon-fsx-for-lustre": ("fsx", "Amazon FSx"),
    "aws-backup": ("backup", "AWS Backup"),
    "aws-kms": ("kms", "AWS KMS"),
    "aws-secrets-manager": ("secrets_manager", "AWS Secrets Manager"),
    "aws-certificate-manager": ("acm", "AWS Certificate Manager"),
    "aws-waf": ("waf", "AWS WAF"),
    "aws-shield": ("shield", "AWS Shield"),
    "aws-network-firewall": ("network_firewall", "AWS Network Firewall"),
    "amazon-guardduty": ("guardduty", "Amazon GuardDuty"),
    "aws-security-hub": ("security_hub", "AWS Security Hub"),
    "aws-config": ("config", "AWS Config"),
    "aws-cloudformation": ("cloudformation", "AWS CloudFormation"),
    "aws-organizations": ("organizations", "AWS Organizations"),
    "aws-control-tower": ("control_tower", "AWS Control Tower"),
    "aws-iam-identity-center": ("identity_center", "AWS IAM Identity Center"),
    "aws-transit-gateway": ("transit_gateway", "AWS Transit Gateway"),
    "aws-direct-connect": ("direct_connect", "AWS Direct Connect"),
    "aws-site-to-site-vpn": ("vpn", "AWS Site-to-Site VPN"),
    "amazon-eventbridge": ("eventbridge", "Amazon EventBridge"),
    "aws-cost-explorer": ("cost_management", "AWS Cost Explorer"),
    "aws-budgets": ("cost_management", "AWS Budgets"),
    "amazon-linux": ("amazon_linux", "Amazon Linux"),
}

# 候補から外すタイトル。他リージョン・GovCloud等への提供拡大は日本の初級者の記事ネタにならない
# （001 X投稿Botのフィルターと同じ考え方）
NEWS_NOISE_PATTERNS = [
    r"GovCloud", r"Sovereign Cloud", r"中国",
    r"(?<!クロス)(?<!マルチ)リージョン.*(利用可能|提供開始|使用可能|一般提供)",
    r"(?<!クロス)(?<!マルチ)リージョン(が|を)?(拡大|増加|追加)",
    r"(米国|欧州|アジアパシフィック|南米|カナダ|中東|アフリカ|メキシコ|イスラエル)[^(（]*[(（].*(利用可能|提供開始|使用可能|サポート|拡大|追加)",
    r"\d+\s*G(bps)?\s*の拡張",  # Direct Connect等の特定ロケーションの回線増強
    r"パートナー", r"Marketplace", r"AWS Transform",
    r"推奨パッチ", r"累積更新プログラム",  # DBエンジンの定例パッチ告知は記事ネタにならない
    r"EMR on EKS",  # 分析基盤（EMR）の話題でEKS自体の新機能ではない
]

# タイトル中のサービス名の表記ゆれ。ここに無いIDは表示名から「Amazon 」「AWS 」を除いた名前で探す。
# RSSの製品タグには関連サービスも並ぶため（例: 「SageMaker AIでSOCI…」にECRのタグ）、
# タグで当たったサービスのうち「タイトルに名前が出てくるもの」だけを主役として採用する。
NEWS_TITLE_ALIASES: dict[str, list[str]] = {
    "sagemaker": ["SageMaker"],
    "rds": ["RDS"],
    "ec2_ebs": ["EBS", "Elastic Block Store"],
    "vpc_endpoint": ["PrivateLink", "VPC エンドポイント", "VPCエンドポイント"],
    "kinesis": ["Kinesis", "Data Firehose"],
    "sqs": ["SQS", "Simple Queue Service"],
    "sns": ["SNS", "Simple Notification Service"],
    "auto_scaling": ["EC2 Auto Scaling", "Auto Scaling"],
    "elb": ["Elastic Load Balancing", "Load Balancer", "ロードバランサー", "ALB", "NLB"],
    "fsx": ["FSx"],
    "kms": ["Key Management Service", "KMS"],
    "acm": ["Certificate Manager", "ACM"],
    "config": ["AWS Config"],
    "identity_center": ["IAM アイデンティティセンター", "IAM Identity Center"],
    "cost_management": ["Cost Explorer", "Budgets"],
    "vpn": ["Site-to-Site VPN", "VPN"],
}


def _html_to_text(raw: str) -> str:
    import html as _html
    import re as _re
    raw = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=_re.S | _re.I)
    text = _html.unescape(_re.sub(r"<[^>]+>", " ", raw))
    return _re.sub(r"\s+", " ", text).strip()


def _news_service(categories: str, title: str) -> tuple[str, str] | None:
    """RSSの<category>（カンマ区切り）の製品タグで当たったサービスのうち、タイトルで一番前に名前が出るものを返す。
    同じ位置から始まる場合は長い名前を優先する（「EC2 Auto Scaling」をEC2ではなくAuto Scalingにする）"""
    import re as _re
    best = None  # (位置, -長さ, サービス)
    for cat in (categories or "").split(","):
        cat = _html_to_text(cat)
        if not cat.startswith("general:products/"):
            continue
        hit = NEWS_PRODUCT_MAP.get(cat[len("general:products/"):])
        if not hit:
            continue
        aliases = NEWS_TITLE_ALIASES.get(hit[0]) or [_re.sub(r"^(Amazon|AWS) ", "", hit[1])]
        for alias in aliases:
            # 英数字の途中で一致しない（「EBS」が「WEBSOCKET」に当たらない）よう境界つきで探す
            m = _re.search(r"(?<![A-Za-z0-9])" + _re.escape(alias) + r"(?![A-Za-z0-9])", title)
            if m:
                key = (m.start(), -len(alias), hit)
                if best is None or key < best:
                    best = key
    if not best:
        return None
    # タイトルの先頭に別のAWSサービスが出る発表（例: 「AWS DataSync の拡張モードで Amazon FSx …」）は、
    # 主役が対象外サービスなので採用しない（関連サービス側の記事として誤って書かせない）
    first = _re.search(r"(Amazon|AWS) ", title)
    if first and best[0] > first.end():
        return None
    return best[2]


def _parse_news_date(pub_date: str) -> str:
    """RSSのpubDate（RFC 822, GMT）をJSTの YYYY-MM-DD にする。失敗時は空文字"""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
    except Exception:
        return ""


def fetch_news_items() -> list[dict]:
    """AWS公式「最新情報」RSSを取得し、対象サービスの新機能発表だけを返す。
    RSSのdescriptionには発表本文がほぼ全文入っているため、それを記事の根拠に使う。"""
    import re as _re
    import urllib.request
    import xml.etree.ElementTree as ET

    req = urllib.request.Request(NEWS_FEED_URL, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        tree = ET.parse(resp)
    items = []
    all_items = tree.findall(".//item")
    for item in all_items:
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if any(_re.search(p, title) for p in NEWS_NOISE_PATTERNS):
            continue
        service = _news_service(item.findtext("category") or "", title)
        if not service:
            continue
        raw_desc = item.findtext("description") or ""
        body = _html_to_text(raw_desc)
        doc_urls = []
        for u in _re.findall(r'href="([^"]+)"', raw_desc):
            u = u.split("#")[0]
            if u.startswith("https://docs.aws.amazon.com/") and u not in doc_urls:
                doc_urls.append(u)
        items.append({
            "title": title, "url": link, "body": body[:NEWS_BODY_MAX_CHARS],
            "date": _parse_news_date(item.findtext("pubDate") or ""),
            "topic_id": service[0], "service_name": service[1],
            "doc_urls": doc_urls[:NEWS_DOCS_MAX_PAGES],
        })
    print(f"[News] RSS {len(all_items)}件中、対象サービスの発表 {len(items)}件")
    return items


def select_news(items: list[dict], recent_urls: list[str], recent_topics: list[str]) -> dict | None:
    """使用済みURLを除き、直近に扱ったサービスをなるべく避けてランダムに1件選ぶ。
    本文が短すぎる発表（根拠不足で推測が混ざりやすい）は外す。"""
    pool = [i for i in items if i["url"] not in recent_urls and len(i["body"]) >= 200]
    if not pool:
        return None
    for tier in NEWS_RECENT_TOPIC_TIERS:
        avoid = set(recent_topics[-tier:]) if tier else set()
        cands = [i for i in pool if i["topic_id"] not in avoid]
        if cands:
            return random.choice(cands)
    return None


def fetch_news_docs(doc_urls: list[str]) -> str:
    """発表本文にリンクされた公式ドキュメントを取得してテキストで返す。日本語版（/ja_jp/）を先に試し、
    取れなければ元のURL。新機能のページは日本語版が未翻訳で英語のことが多い。失敗したページは飛ばす"""
    import re as _re
    import urllib.request
    parts = []
    for url in doc_urls:
        cands = [url.replace("https://docs.aws.amazon.com/", "https://docs.aws.amazon.com/ja_jp/", 1), url]
        if "/ja_jp/" in url:
            cands = [url]
        for u in cands:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                m = _re.search(r"<main[^>]*>(.*?)</main>", raw, _re.S | _re.I)
                text = _html_to_text(m.group(1) if m else raw)
                if len(text) < 300:
                    continue
                parts.append(f"### {u}\n{text[:NEWS_DOCS_MAX_CHARS_PER_PAGE]}")
                print(f"[NewsDocs] {len(text)}文字取得 → {min(len(text), NEWS_DOCS_MAX_CHARS_PER_PAGE)}文字使用 ({u})")
                break
            except Exception as e:
                print(f"[NewsDocs] 取得エラー（スキップ）: {u}: {e}")
    return "\n\n".join(parts)


def news_to_topic(news: dict) -> dict:
    """選んだ発表を既存処理（ファイル名・Zennメタ・メール）で使うトピック形式に変換する"""
    return {
        "id": news["topic_id"],
        "name": news["service_name"],
        "subtitle": news["title"],
        "keywords": "",
    }


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

def generate_article(topic: dict, today: str, angle: str, news: dict | None = None) -> tuple[str, str, bool, dict]:
    """Bedrock を使って記事を生成する。(article_text, title, is_truncated, meta) を返す。
    news を渡すと新機能紹介記事（発表本文を根拠にする）、None なら従来の定番解説記事を生成する"""
    docs_content = fetch_aws_docs(topic["id"])
    docs_section = (
        "## AWS公式ドキュメント（根拠情報）\n"
        "以下はAWS公式ドキュメントから取得した情報です。技術的事実はこの内容を根拠として正確に記述し、矛盾しないようにしてください。\n"
        "ドキュメントに記載のない事実は、確実に知っている場合のみ記述し、不確かな場合は記述しないか「〜の場合があります」等の不確定表現を使ってください。\n\n"
        f"{docs_content}\n\n---\n"
        if docs_content else ""
    )
    diagram_section = ""
    if news:
        if docs_section:
            docs_section = docs_section.replace(
                "## AWS公式ドキュメント（根拠情報）",
                "## サービスの基本（AWS公式ドキュメント、サービス説明の補足用）",
            )
        news_docs = fetch_news_docs(news.get("doc_urls") or [])
        news_docs_section = (
            "## 関連する公式ドキュメント（根拠情報・詳細）\n"
            "発表本文にリンクされていたAWS公式ドキュメントです。新機能の詳細・設定例・制約はここから取ってください。\n\n"
            f"{news_docs}\n\n---\n"
            if news_docs else ""
        )
        prompt = NEWS_ARTICLE_PROMPT_TEMPLATE.format(
            news_docs_section=news_docs_section,
            service_name=topic["name"],
            news_title=news["title"],
            news_date=news.get("date") or "不明",
            news_body=news["body"],
            docs_section=docs_section,
            today=today,
        )
    else:
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

    # 新機能記事は出典（AWS公式の発表ページ）をコード側で必ず末尾に付ける（LLMにURLを書かせると誤記しうるため）
    if news:
        date_part = f"、{news['date']}" if news.get("date") else ""
        text = text.rstrip() + f"\n\n**出典**: [{news['title']}]({news['url']})（AWS 最新情報{date_part}）\n"

    meta = {
        "cost_usd": cost_usd,
        "stop_reason": stop_reason,
        "in_tokens": in_tok,
        "out_tokens": out_tok,
        "docs_chars": len(docs_content) + (len(news_docs) if news else 0),
        "angle": angle,
    }
    return text, title, is_truncated, meta


# ─── MD 生成 ───────────────────────────────────────────────────────────────

def _embed_image_placeholders(article: str, png_paths: list[str], topic_name: str) -> str:
    """画像はBot側で生成しない（2026-09-08〜、GPTに質確認と合わせて生成・最適配置を依頼する
    運用のため）。プロンプト側も{DIAGRAM_N}マーカーの出力は指示していないが、LLMが過去の
    学習データの影響で稀に出力するケースに備え、残存マーカーだけ除去する。
    """
    import re as _re
    cleaned, n = _re.subn(r'\n*\{\{?DIAGRAM_\d+\}\}?\n*', '\n\n', article)
    if n:
        print(f"[WARNING] 未使用のDIAGRAMマーカー{n}件を除去しました")
    return cleaned


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
    """記事を MD ファイルに保存する（画像はBot側で生成しない。png_pathsは常に空）。mdパスを返す"""
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
    "python3.13": "python3.14", "python3.12": "python3.14", "python3.11": "python3.14",
    "python3.10": "python3.14", "python3.9": "python3.14",
    "nodejs22.x": "nodejs24.x", "nodejs20.x": "nodejs24.x", "nodejs18.x": "nodejs24.x",
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

    # 2026-11-05〜 目安は4,000文字程度（ハンズオンなし）。500文字→2,000文字でもまだ薄いとのユーザー判断で4,000文字に戻した。
    # AWS CLIコマンドの必須チェックは廃止したまま。超過・不足とも止めずにメールで警告だけ出す
    if char_count < 2800:
        issues.append(f"文字数が目安(4,000文字程度)に対して少なすぎます: {char_count:,}文字")
    elif char_count > 5500:
        issues.append(f"文字数が目安(4,000文字程度)を大きく超えています: {char_count:,}文字")
    if "aws " in article_text and "--region" not in article_text:
        issues.append("AWS CLIコマンドに --region の明示が見当たりません")

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

    for old_runtime in ("python3.13", "python3.12", "python3.11", "python3.10", "python3.9", "nodejs22.x", "nodejs20.x", "nodejs18.x"):
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
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "未生成（GPTに作成・配置を依頼してください）"

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
    ) if png_paths else "<li>（未生成。GPTに作成・配置を依頼してください）</li>"

    s3_row = (
        f'<tr><td style="padding:5px;font-weight:bold;">S3保存先</td>'
        f'<td><code>{s3_url}</code></td></tr>'
        if s3_url else ""
    )
    download_row = (
        '<li>S3からローカルにダウンロード（下記コマンドをそのままコピペして実行）<br>'
        '<code style="display:inline-block;margin-top:4px;">'
        'bash 002_Zenn_Auto_Article_Bot/scripts/download_article.sh'
        '</code></li>'
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
1. 記事をダウンロード（下記コマンドをそのままコピペして実行）
bash 002_Zenn_Auto_Article_Bot/scripts/download_article.sh
2. GPTに記事内容を渡して質確認と画像の生成・最適な挿入箇所の提案を依頼し、画像を貼り込む
3. Zennエディタで新規記事を作成（または zenn-cli で管理）
4. MDファイルの内容を貼り付け
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
      <li>GPTに記事内容を渡して質確認と画像の生成・最適な挿入箇所の提案を依頼し、画像を貼り込む</li>
      <li>Zennエディタで新規記事を作成</li>
      <li>MDファイルの内容を貼り付け</li>
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

def get_recent_news_urls() -> list[str]:
    return _get_recent_ids(SSM_NEWS_URL_PARAM_PATH)


def save_news_url_to_ssm(url: str, dry_run: bool = False) -> None:
    _save_recent_id(SSM_NEWS_URL_PARAM_PATH, url, RECENT_NEWS_URLS_LIMIT, dry_run=dry_run)


def _pick_news(recent_topics: list[str]) -> dict | None:
    """新機能の発表を1件選ぶ。RSS取得失敗・候補なしは None（呼び出し側で定番解説にフォールバック）"""
    try:
        items = fetch_news_items()
    except Exception as e:
        print(f"[News] RSS取得エラー（定番解説にフォールバック）: {e}")
        return None
    news = select_news(items, get_recent_news_urls(), recent_topics)
    if news is None:
        print("[News] 未使用の対象発表がありません（定番解説にフォールバック）")
    return news


def run(dry_run: bool = False, mode: str = "news"):
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
    print(f"  直近のトピック（{len(recent_topics)}件）: {recent_topics}")
    news = _pick_news(recent_topics) if mode == "news" else None
    if news:
        topic = news_to_topic(news)
        angle = f"新機能紹介（{news.get('date') or '日付不明'}発表: {news['url']}）"
        save_topic_to_ssm(topic["id"], dry_run=dry_run)
        save_news_url_to_ssm(news["url"], dry_run=dry_run)
    else:
        if mode == "news":
            mode = "evergreen_fallback"
        topic = select_topic(excluded_ids=recent_topics)
        save_topic_to_ssm(topic["id"], dry_run=dry_run)
        recent_angles = get_recent_angles()
        angle = select_angle(excluded_angles=recent_angles)
        save_angle_to_ssm(angle, dry_run=dry_run)  # 除外判定は素の切り口文字列で行うため、注記を付ける前に保存する
        if mode == "evergreen_fallback":
            angle = f"【新機能の候補なしのため定番解説】{angle}"
    print(f"  モード: {mode} / トピック: {topic['name']} / {angle} [{time.time()-_t:.1f}s]")

    # Step 2: 出力先準備（画像はGPTに手動で依頼する運用のため、構成図PNGは生成しない）
    _t = time.time()
    output_dir = os.path.expanduser(OUTPUT_DIR)
    md_path, png_base = _prepare_article_paths(topic, timestamp, output_dir, dry_run=dry_run)
    png_paths: list[str] = []
    print(f"  出力先準備完了 [{time.time()-_t:.1f}s]")

    # Step 3: 記事生成
    _t = time.time()
    print("Step 3: 記事を生成中（4,000文字程度）...")
    article, title, is_truncated, gen_meta = generate_article(topic, today, angle, news=news)
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
        "mode": mode,
        "news_url": news["url"] if news else None,
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
    # 既定は新機能紹介（news）。{"mode": "evergreen"} で従来の定番解説を明示的に生成できる
    mode = (event or {}).get("mode") or os.environ.get("ARTICLE_MODE", "news")
    if mode not in ("news", "evergreen"):
        print(f"[WARNING] 不明なmode={mode!r}。newsで実行します")
        mode = "news"
    topic, char_count, md_path, png_paths, s3_url = run(dry_run=dry_run, mode=mode)
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
