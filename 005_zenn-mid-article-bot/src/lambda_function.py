import json
import os
import random
import re
import time
import boto3
import datetime
from botocore.config import Config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
try:
    from diagram_generator import generate_diagrams
except ImportError:
    def generate_diagrams(topic, base_path):
        return []

# AWS clients
bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    # 自動リトライを無効化: read_timeoutはBedrock課金が発生した後に起こり得るため、
    # botocoreの自動リトライを許すとLambdaのTimeout(900s)超過やBedrockコスト二重発生に繋がる
    config=Config(read_timeout=880, connect_timeout=10, retries={"max_attempts": 0}),
)
ses = boto3.client("ses", region_name="ap-northeast-1")
s3  = boto3.client("s3",  region_name="ap-northeast-1")
ssm = boto3.client("ssm", region_name="ap-northeast-1")

# Lambda環境かどうかで出力先を切り替え
_IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Environment variables
SES_SENDER_EMAIL    = os.environ["SES_SENDER_EMAIL"]
SES_RECIPIENT_EMAIL = os.environ["SES_RECIPIENT_EMAIL"]
BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-sonnet-4-6")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    "/tmp/zenn_mid_articles" if _IS_LAMBDA
    else os.path.expanduser("~/Zer0/005_Zenn_Mid_Article_Bot/output"),
)
S3_BUCKET  = os.environ.get("S3_BUCKET", "zer0-dev-s3")
S3_PREFIX  = "zenn-mid-articles"

# SSM: 直近トピック履歴
SSM_PARAM_PATH      = "/mid-article-bot/recent-topics"
# 16トピック中、除外しすぎて即リセットにならない範囲で最大限除外する。
# 旧デフォルト4だと最短2ヶ月強で同一トピックが再登場し、記事タイトルが完全一致し得た
RECENT_TOPICS_LIMIT = int(os.environ.get("RECENT_TOPICS_LIMIT", "12"))

# SSM: トピックごとの累計生成回数（再登場時のタイトル重複防止用サフィックスに使用）
SSM_PARAM_OCCURRENCE = "/mid-article-bot/topic-occurrence"

# ─── Bedrock 呼び出しパラメータ（定数化） ────────────────────────────────────
BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"
ARTICLE_MAX_TOKENS        = 24000     # 記事本文生成用
# Claude Sonnet 4.6 概算単価（USD / 100万トークン）
SONNET_INPUT_COST_PER_MTOK  = 3.0
SONNET_OUTPUT_COST_PER_MTOK = 15.0
# Claude Haiku 4.5 概算単価（test_mode時に使用、USD / 100万トークン）
HAIKU_INPUT_COST_PER_MTOK  = 1.0
HAIKU_OUTPUT_COST_PER_MTOK = 5.0
# AWS公式ドキュメント取得
DOCS_FETCH_TIMEOUT_SEC = 15
DOCS_MAX_CHARS         = 6000

# ─── 中級者向けトピック定義（16記事分 ≒ 8ヶ月分） ────────────────────────────
# サービス数は1トピック3つまでに絞る（複数サービスを跨ぐ細かい統合バグの温床になりやすいため）
#
# "variants": トピック内のサービス組み合わせ変動枠。同一トピックが再登場しても記事内容が
# 完全に同じにならないよう、services / subtitle / keywords を上書きする差分辞書のリストを持つ。
# select_topic() が「基本形 + 各バリエーション」から random.choice で1つに確定するため、
# 呼び出し側（generate_article / diagram_generator / fetch_aws_docs）は従来どおり固定の
# services リストとして扱える。バリエーションのサービス名は _SERVICE_NAME_TO_DOCS_ID と
# diagram_generator の _SERVICE_ICON_KEYWORDS に必ず対応エントリを持つこと。
# _ZENN_META のタグに含まれるサービスはバリエーションでも必ず残すこと（タグの正確性維持）。
AWS_TOPICS = [
    # ── 複合アーキテクチャ系 ─────────────────────────────────────────────────
    {
        "id": "serverless_ec",
        "name": "サーバーレスECバックエンド完全構成",
        "article_type": "architecture",
        "services": ["API Gateway", "Lambda", "DynamoDB"],
        "subtitle": "API Gateway + Lambda + DynamoDB で構築する本番級バックエンド",
        "keywords": "サーバーレス, API Gateway, Lambda, DynamoDB, スロットリング, 冪等性",
        "primary_service": "apigateway",
        "primary_service_label": "API Gateway",
        "emoji": "🛒",
        "variants": [
            {
                "services": ["API Gateway", "Lambda", "Aurora Serverless v2"],
                "subtitle": "API Gateway + Lambda + Aurora Serverless v2 で構築するリレーショナルDBバックエンド",
                "keywords": "サーバーレス, API Gateway, Lambda, Aurora Serverless v2, RDS Proxy, コネクション管理, オートスケーリング",
            },
        ],
    },
    {
        "id": "static_web_hosting",
        "name": "静的Webホスティング最適解",
        "article_type": "architecture",
        "services": ["S3", "CloudFront", "ACM"],
        "subtitle": "S3 + CloudFront + ACM で構築するセキュアな静的サイト",
        "keywords": "静的サイト, CloudFront, S3, ACM, HTTPS, カスタムドメイン, OAC, キャッシュ制御",
        "primary_service": "cloudfront",
        "primary_service_label": "CloudFront",
        "emoji": "🌐",
        "variants": [
            {
                "services": ["S3", "CloudFront", "Route 53"],
                "subtitle": "S3 + CloudFront + Route 53 で構築するカスタムドメインの静的サイト",
                "keywords": "静的サイト, CloudFront, S3, Route 53, カスタムドメイン, エイリアスレコード, OAC, キャッシュ制御",
            },
        ],
    },
    {
        "id": "container_platform",
        "name": "コンテナアプリ本番運用基盤",
        "article_type": "architecture",
        "services": ["ECS Fargate", "ALB", "ECR"],
        "subtitle": "ECS Fargate + ALB + ECR でコンテナを本番運用する",
        "keywords": "ECS Fargate, ALB, ECR, タスク定義, サービス, ローリングデプロイ, ヘルスチェック",
        "primary_service": "ecs",
        "primary_service_label": "ECS Fargate",
        "emoji": "🐳",
    },
    {
        "id": "event_driven_pipeline",
        "name": "イベント駆動データ処理パイプライン",
        "article_type": "architecture",
        "services": ["Kinesis Data Streams", "Lambda", "S3"],
        "subtitle": "Kinesis + Lambda + S3 でリアルタイムデータを収集・保存する",
        "keywords": "Kinesis, Lambda, S3, リアルタイム処理, データパイプライン, シャード, バッチウィンドウ",
        "primary_service": "kinesis",
        "primary_service_label": "Kinesis Data Streams",
        "emoji": "🌊",
    },
    {
        "id": "microservices_base",
        "name": "マイクロサービス観測性基盤",
        "article_type": "architecture",
        "services": ["API Gateway", "Lambda", "X-Ray"],
        "subtitle": "API Gateway + Lambda + X-Ray で分散トレーシングを実現する",
        "keywords": "マイクロサービス, X-Ray, 分散トレーシング, API Gateway, Lambda, サービスマップ, レイテンシ分析",
        "primary_service": "xray",
        "primary_service_label": "X-Ray",
        "emoji": "🔬",
    },
    {
        "id": "multi_region_dr",
        "name": "マルチリージョンDR構成",
        "article_type": "architecture",
        "services": ["Route 53", "RDS", "S3 Cross-Region Replication"],
        "subtitle": "Route 53 + RDS Multi-AZ + S3レプリケーションでRTO/RPOを最小化するDR設計",
        "keywords": "DR, RTO, RPO, Route 53, フェイルオーバー, RDS Multi-AZ, S3レプリケーション, ヘルスチェック",
        "primary_service": "route53",
        "primary_service_label": "Route 53",
        "emoji": "🌍",
    },
    {
        "id": "realtime_notify",
        "name": "リアルタイム通知・アラートシステム",
        "article_type": "architecture",
        "services": ["SNS", "SQS", "Lambda"],
        "subtitle": "SNS + SQS + Lambda でスケーラブルな通知基盤を構築する",
        "keywords": "SNS, SQS, Lambda, Pub/Sub, デッドレターキュー, メッセージルーティング, 冪等性",
        "primary_service": "sns",
        "primary_service_label": "SNS",
        "emoji": "🔔",
    },
    {
        "id": "bedrock_rag",
        "name": "Bedrock RAG アーキテクチャ",
        "article_type": "architecture",
        "services": ["Amazon Bedrock", "S3", "OpenSearch Serverless"],
        "subtitle": "Bedrock + S3 + OpenSearch Serverless でRAGシステムを構築する",
        "keywords": "RAG, Bedrock, Knowledge Base, OpenSearch Serverless, ベクトル検索, エンベディング, チャンキング",
        "primary_service": "bedrock",
        "primary_service_label": "Amazon Bedrock",
        "emoji": "🤖",
    },
    {
        "id": "vpc_network",
        "name": "セキュアなVPCネットワーク基盤設計",
        "article_type": "architecture",
        "services": ["VPC", "NAT Gateway", "Internet Gateway"],
        "subtitle": "VPC + NAT Gateway + Internet Gateway で構築するセキュアなネットワーク基盤",
        "keywords": "VPC, サブネット設計, NAT Gateway, Internet Gateway, ルートテーブル, ネットワークACL, セキュリティグループ",
        "primary_service": "vpc",
        "primary_service_label": "VPC",
        "emoji": "🔌",
    },
    {
        "id": "async_orchestration",
        "name": "非同期ジョブオーケストレーション基盤",
        "article_type": "architecture",
        "services": ["EventBridge", "SQS", "Step Functions"],
        "subtitle": "EventBridge + Step Functions + SQS で疎結合な非同期処理基盤を構築する",
        "keywords": "EventBridge, Step Functions, SQS, 非同期処理, ジョブオーケストレーション, 疎結合, リトライ制御",
        "primary_service": "eventbridge",
        "primary_service_label": "EventBridge",
        "emoji": "⚙️",
    },
    {
        "id": "cicd_ec2_deploy",
        "name": "EC2 Blue/Greenデプロイパイプライン",
        "article_type": "architecture",
        "services": ["Auto Scaling", "CodeDeploy", "EC2"],
        "subtitle": "EC2 Auto Scaling + CodeDeploy で構築するBlue/Greenデプロイパイプライン",
        "keywords": "CodeDeploy, EC2, Auto Scaling, Blue/Greenデプロイ, ローリングアップデート, デプロイ自動化, ロールバック",
        "primary_service": "codedeploy",
        "primary_service_label": "CodeDeploy",
        "emoji": "🔁",
    },
    {
        "id": "user_auth_cognito",
        "name": "Cognitoによるユーザー認証基盤",
        "article_type": "architecture",
        "services": ["Amazon Cognito", "API Gateway", "IAM Role"],
        "subtitle": "Cognito + API Gateway + IAM Role で構築するユーザー認証・認可基盤",
        "keywords": "Cognito, ユーザープール, IDプール, API Gateway, 認証, 認可, フェデレーション",
        "primary_service": "cognito",
        "primary_service_label": "Amazon Cognito",
        "emoji": "🔑",
    },
    # ── ユースケース別ソリューション ────────────────────────────────────────
    {
        "id": "cicd_pipeline",
        "name": "AWS CI/CDパイプライン構築",
        "article_type": "usecase",
        "services": ["CodePipeline", "CodeBuild", "ECR"],
        "subtitle": "CodePipeline + CodeBuild + ECR でコンテナイメージのビルド〜配布を自動化する",
        "keywords": "CI/CD, CodePipeline, CodeBuild, ECR, ビルドスペック, パイプラインステージ, 自動テスト",
        "primary_service": "codepipeline",
        "primary_service_label": "CodePipeline",
        "emoji": "🚀",
        "variants": [
            {
                "services": ["CodePipeline", "CodeBuild", "CodeDeploy"],
                "subtitle": "CodePipeline + CodeBuild + CodeDeploy でビルド〜デプロイまでを自動化する",
                "keywords": "CI/CD, CodePipeline, CodeBuild, CodeDeploy, デプロイ自動化, ロールバック, パイプラインステージ",
            },
            {
                "services": ["CodePipeline", "CodeBuild", "S3"],
                "subtitle": "CodePipeline + CodeBuild + S3 で静的サイトのビルド〜配信を自動化する",
                "keywords": "CI/CD, CodePipeline, CodeBuild, S3, 静的サイト配信, アーティファクト管理, 自動テスト",
            },
        ],
    },
    {
        "id": "ml_pipeline",
        "name": "機械学習パイプライン自動化",
        "article_type": "usecase",
        "services": ["SageMaker AI", "S3", "Step Functions"],
        "subtitle": "SageMaker + Step Functions + S3 で学習〜デプロイを自動化するMLパイプライン",
        "keywords": "SageMaker AI, Step Functions, S3, MLOps, モデルレジストリ, バッチ推論, Pipeline",
        "primary_service": "sagemaker",
        "primary_service_label": "SageMaker AI",
        "emoji": "🧠",
    },
    {
        "id": "log_analytics",
        "name": "ログ集約・分析基盤の構築",
        "article_type": "usecase",
        "services": ["CloudTrail", "S3", "Athena"],
        "subtitle": "CloudTrail + S3 + Athena でAWS全体のログを集約・分析する",
        "keywords": "CloudTrail, S3, Athena, ログ集約, セキュリティ監査, SQLクエリ, パーティション射影",
        "primary_service": "cloudtrail",
        "primary_service_label": "CloudTrail",
        "emoji": "🔍",
        "variants": [
            {
                "services": ["CloudTrail", "AWS Glue", "Athena"],
                "subtitle": "CloudTrail + Glue Data Catalog + Athena でスキーマ管理されたログ分析基盤を構築する",
                "keywords": "CloudTrail, AWS Glue, Athena, Glue Data Catalog, クローラー, ログ分析, セキュリティ監査, スキーマ管理",
            },
            {
                "services": ["CloudTrail", "Amazon Data Firehose", "Athena"],
                "subtitle": "CloudTrail + Data Firehose + Athena でログをニアリアルタイムに集約・分析する",
                "keywords": "CloudTrail, Amazon Data Firehose, Athena, CloudWatch Logs サブスクリプションフィルター, ニアリアルタイム, ログ集約, 動的パーティショニング",
            },
        ],
    },
    {
        "id": "cost_optimization",
        "name": "AWSコスト最適化の実践戦略",
        "article_type": "usecase",
        "services": ["Cost Explorer", "AWS Budgets", "Lambda"],
        "subtitle": "Cost Explorer + Budgets + 自動停止Lambdaでコストを可視化・削減する",
        "keywords": "コスト最適化, Cost Explorer, Budgets, Lambda自動停止, タグ管理, Cost Allocation",
        "primary_service": "cost_explorer",
        "primary_service_label": "Cost Explorer",
        "emoji": "💰",
    },
    {
        "id": "security_hardening",
        "name": "AWSセキュリティ強化設計",
        "article_type": "usecase",
        "services": ["GuardDuty", "Security Hub", "CloudTrail"],
        "subtitle": "GuardDuty + Security Hub + CloudTrailで脅威検知と監査証跡を一元化する",
        "keywords": "GuardDuty, Security Hub, CloudTrail, 脅威検知, コンプライアンス, セキュリティスコア",
        "primary_service": "guardduty",
        "primary_service_label": "GuardDuty",
        "emoji": "🛡️",
    },
    {
        "id": "backup_dr",
        "name": "バックアップ・DR設計の実践",
        "article_type": "usecase",
        "services": ["AWS Backup", "RDS", "DynamoDB"],
        "subtitle": "AWS Backup + RDS + DynamoDB のバックアッププランで障害に強い設計を実現する",
        "keywords": "AWS Backup, RDS スナップショット, DynamoDB PITRバックアップ, RTO, RPO, 復元テスト, バックアップポリシー",
        "primary_service": "backup",
        "primary_service_label": "AWS Backup",
        "emoji": "💾",
        "variants": [
            {
                "services": ["AWS Backup", "RDS", "EC2"],
                "subtitle": "AWS Backup + RDS + EC2 のバックアッププランで障害に強い設計を実現する",
                "keywords": "AWS Backup, RDS スナップショット, EC2 AMIバックアップ, EBSスナップショット, RTO, RPO, 復元テスト",
            },
        ],
    },
    {
        "id": "multi_account",
        "name": "マルチアカウント管理の実践",
        "article_type": "usecase",
        "services": ["AWS Organizations", "Control Tower", "IAM Identity Center"],
        "subtitle": "Organizations + Control Tower + IAM Identity Center でセキュアなマルチアカウント環境を構築する",
        "keywords": "AWS Organizations, Control Tower, IAM Identity Center, SCP, ガードレール, ランディングゾーン, OU設計",
        "primary_service": "organizations",
        "primary_service_label": "AWS Organizations",
        "emoji": "🏢",
    },
    {
        "id": "data_lake",
        "name": "データレイク構築の実践",
        "article_type": "usecase",
        "services": ["S3", "AWS Glue", "Athena"],
        "subtitle": "S3 + Glue + Athena でデータレイクを構築しSQLで分析する",
        "keywords": "データレイク, S3, Glue, Athena, データカタログ, ETL, パーティショニング, 列指向フォーマット",
        "primary_service": "glue",
        "primary_service_label": "AWS Glue",
        "emoji": "🏞️",
    },
    {
        "id": "observability_monitoring",
        "name": "運用監視・アラート基盤の構築",
        "article_type": "usecase",
        "services": ["CloudWatch", "CloudWatch Alarm", "SNS"],
        "subtitle": "CloudWatch + CloudWatch Alarm + SNS で運用監視・アラート基盤を構築する",
        "keywords": "CloudWatch, メトリクス, アラーム, SNS, 運用監視, 可観測性, しきい値設計",
        "primary_service": "cloudwatch",
        "primary_service_label": "CloudWatch",
        "emoji": "📈",
        "variants": [
            {
                "services": ["CloudWatch", "EventBridge", "SNS"],
                "subtitle": "CloudWatch + EventBridge + SNS でアラームイベントを柔軟にルーティングする監視基盤",
                "keywords": "CloudWatch, EventBridge, SNS, アラーム状態変化イベント, イベントルール, 運用監視, 通知ルーティング",
            },
        ],
    },
    {
        "id": "edge_security",
        "name": "CloudFrontエッジセキュリティ強化",
        "article_type": "usecase",
        "services": ["CloudFront", "WAF", "Shield"],
        "subtitle": "CloudFront + WAF + Shield で構築するエッジセキュリティ基盤",
        "keywords": "CloudFront, WAF, Shield, DDoS対策, Webセキュリティ, レートリミット, ルールグループ",
        "primary_service": "waf",
        "primary_service_label": "WAF",
        "emoji": "🧱",
    },
    {
        "id": "secrets_rotation",
        "name": "認証情報ローテーション基盤の構築",
        "article_type": "usecase",
        "services": ["Secrets Manager", "EC2", "IAM Role"],
        "subtitle": "Secrets Manager + EC2 + IAM Role で認証情報の自動ローテーションを実現する",
        "keywords": "Secrets Manager, 認証情報ローテーション, IAM Role, EC2, シークレット管理, 最小権限",
        "primary_service": "secrets_manager",
        "primary_service_label": "Secrets Manager",
        "emoji": "🔐",
    },
    {
        "id": "data_governance",
        "name": "データレイクガバナンス基盤",
        "article_type": "usecase",
        "services": ["Lake Formation", "AWS Glue", "IAM"],
        "subtitle": "Lake Formation + Glue + IAM でデータレイクのアクセス制御を実現する",
        "keywords": "Lake Formation, データガバナンス, アクセス制御, Glue, IAM, データカタログ, 列レベル権限",
        "primary_service": "lake_formation",
        "primary_service_label": "Lake Formation",
        "emoji": "🗂️",
    },
]

# ─── AWS公式ドキュメント URL マップ（サービスIDキー） ─────────────────────────
DOCS_URL_MAP: dict[str, str] = {
    "apigateway":    "https://docs.aws.amazon.com/ja_jp/apigateway/latest/developerguide/welcome.html",
    "cloudfront":    "https://docs.aws.amazon.com/ja_jp/AmazonCloudFront/latest/DeveloperGuide/Introduction.html",
    "ecs":           "https://docs.aws.amazon.com/ja_jp/AmazonECS/latest/developerguide/Welcome.html",
    "kinesis":       "https://docs.aws.amazon.com/ja_jp/streams/latest/dev/introduction.html",
    "route53":       "https://docs.aws.amazon.com/ja_jp/Route53/latest/DeveloperGuide/Welcome.html",
    "sns":           "https://docs.aws.amazon.com/ja_jp/sns/latest/dg/welcome.html",
    "bedrock":       "https://docs.aws.amazon.com/ja_jp/bedrock/latest/userguide/what-is-bedrock.html",
    "codepipeline":  "https://docs.aws.amazon.com/ja_jp/codepipeline/latest/userguide/welcome.html",
    "sagemaker":     "https://docs.aws.amazon.com/ja_jp/sagemaker/latest/dg/whatis.html",
    "cloudtrail":    "https://docs.aws.amazon.com/ja_jp/awscloudtrail/latest/userguide/cloudtrail-user-guide.html",
    "cost_explorer": "https://docs.aws.amazon.com/ja_jp/cost-management/latest/userguide/what-is-costmanagement.html",
    "guardduty":     "https://docs.aws.amazon.com/ja_jp/guardduty/latest/ug/what-is-guardduty.html",
    "backup":        "https://docs.aws.amazon.com/ja_jp/aws-backup/latest/devguide/whatisbackup.html",
    "organizations": "https://docs.aws.amazon.com/ja_jp/organizations/latest/userguide/orgs_introduction.html",
    "xray":          "https://docs.aws.amazon.com/ja_jp/xray/latest/devguide/aws-xray.html",
    "rds":           "https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/UserGuide/Welcome.html",
    "glue":          "https://docs.aws.amazon.com/ja_jp/glue/latest/dg/what-is-glue.html",
    # ── v2.9で追加: 各トピック3サービス全件の根拠ドキュメント取得用 ──
    "lambda":              "https://docs.aws.amazon.com/ja_jp/lambda/latest/dg/welcome.html",
    "dynamodb":            "https://docs.aws.amazon.com/ja_jp/amazondynamodb/latest/developerguide/Introduction.html",
    "s3":                  "https://docs.aws.amazon.com/ja_jp/AmazonS3/latest/userguide/Welcome.html",
    "s3_crr":              "https://docs.aws.amazon.com/ja_jp/AmazonS3/latest/userguide/replication.html",
    "acm":                 "https://docs.aws.amazon.com/ja_jp/acm/latest/userguide/acm-overview.html",
    "alb":                 "https://docs.aws.amazon.com/ja_jp/elasticloadbalancing/latest/application/introduction.html",
    "ecr":                 "https://docs.aws.amazon.com/ja_jp/AmazonECR/latest/userguide/what-is-ecr.html",
    "sqs":                 "https://docs.aws.amazon.com/ja_jp/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html",
    "opensearch_serverless": "https://docs.aws.amazon.com/ja_jp/opensearch-service/latest/developerguide/serverless.html",
    "codebuild":           "https://docs.aws.amazon.com/ja_jp/codebuild/latest/userguide/welcome.html",
    "step_functions":      "https://docs.aws.amazon.com/ja_jp/step-functions/latest/dg/welcome.html",
    "athena":              "https://docs.aws.amazon.com/ja_jp/athena/latest/ug/what-is.html",
    "budgets":             "https://docs.aws.amazon.com/ja_jp/cost-management/latest/userguide/budgets-managing-costs.html",
    "security_hub":        "https://docs.aws.amazon.com/ja_jp/securityhub/latest/userguide/what-is-securityhub.html",
    "control_tower":       "https://docs.aws.amazon.com/ja_jp/controltower/latest/userguide/what-is-control-tower.html",
    "iam_identity_center": "https://docs.aws.amazon.com/ja_jp/singlesignon/latest/userguide/what-is.html",
    # ── v3.3で追加: トピックプール拡充（新8トピック）用 ──
    "vpc":             "https://docs.aws.amazon.com/ja_jp/vpc/latest/userguide/what-is-amazon-vpc.html",
    "eventbridge":     "https://docs.aws.amazon.com/ja_jp/eventbridge/latest/userguide/eb-what-is.html",
    "autoscaling":     "https://docs.aws.amazon.com/ja_jp/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html",
    "codedeploy":      "https://docs.aws.amazon.com/ja_jp/codedeploy/latest/userguide/welcome.html",
    "ec2":             "https://docs.aws.amazon.com/ja_jp/AWSEC2/latest/UserGuide/concepts.html",
    "cognito":         "https://docs.aws.amazon.com/ja_jp/cognito/latest/developerguide/what-is-amazon-cognito.html",
    "iam":             "https://docs.aws.amazon.com/ja_jp/IAM/latest/UserGuide/introduction.html",
    "cloudwatch":      "https://docs.aws.amazon.com/ja_jp/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html",
    "waf":             "https://docs.aws.amazon.com/ja_jp/waf/latest/developerguide/what-is-aws-waf.html",
    # Shield Advancedは現在AWS WAF開発者ガイドに統合されているため同一URL（意図的な重複）
    "shield":          "https://docs.aws.amazon.com/ja_jp/waf/latest/developerguide/what-is-aws-waf.html",
    "secrets_manager": "https://docs.aws.amazon.com/ja_jp/secretsmanager/latest/userguide/intro.html",
    "lake_formation":  "https://docs.aws.amazon.com/ja_jp/lake-formation/latest/dg/what-is-lake-formation.html",
    # ── トピック内サービス変動枠（variants）用 ──
    "firehose":          "https://docs.aws.amazon.com/ja_jp/firehose/latest/dev/what-is-this-service.html",
    "aurora_serverless": "https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html",
}

# ─── トピックの services 表記文字列 → DOCS_URL_MAP キー ───────────────────────
# AWS_TOPICS の services リストに現れる文字列と厳密に一致させる（存在しない組み合わせは
# 取得スキップになるだけで安全）
_SERVICE_NAME_TO_DOCS_ID: dict[str, str] = {
    "API Gateway": "apigateway",
    "Lambda": "lambda",
    "DynamoDB": "dynamodb",
    "S3": "s3",
    "CloudFront": "cloudfront",
    "ACM": "acm",
    "ECS Fargate": "ecs",
    "ALB": "alb",
    "ECR": "ecr",
    "Kinesis Data Streams": "kinesis",
    "X-Ray": "xray",
    "Route 53": "route53",
    "RDS": "rds",
    "S3 Cross-Region Replication": "s3_crr",
    "SNS": "sns",
    "SQS": "sqs",
    "Amazon Bedrock": "bedrock",
    "OpenSearch Serverless": "opensearch_serverless",
    "CodePipeline": "codepipeline",
    "CodeBuild": "codebuild",
    "SageMaker AI": "sagemaker",
    "Step Functions": "step_functions",
    "CloudTrail": "cloudtrail",
    "Athena": "athena",
    "Cost Explorer": "cost_explorer",
    "AWS Budgets": "budgets",
    "GuardDuty": "guardduty",
    "Security Hub": "security_hub",
    "AWS Backup": "backup",
    "AWS Organizations": "organizations",
    "Control Tower": "control_tower",
    "IAM Identity Center": "iam_identity_center",
    "AWS Glue": "glue",
    # ── v3.3で追加: トピックプール拡充（新8トピック）用 ──
    "VPC": "vpc",
    "NAT Gateway": "vpc",
    "Internet Gateway": "vpc",
    "EventBridge": "eventbridge",
    "Auto Scaling": "autoscaling",
    "CodeDeploy": "codedeploy",
    "EC2": "ec2",
    "Amazon Cognito": "cognito",
    "IAM Role": "iam",
    "CloudWatch": "cloudwatch",
    "CloudWatch Alarm": "cloudwatch",
    "WAF": "waf",
    "Shield": "shield",
    "Secrets Manager": "secrets_manager",
    "Lake Formation": "lake_formation",
    "IAM": "iam",
    # ── トピック内サービス変動枠（variants）用 ──
    "Amazon Data Firehose": "firehose",
    "Aurora Serverless v2": "aurora_serverless",
}

# ─── Zennフロントマター用メタ情報 ─────────────────────────────────────────────
_ZENN_META: dict[str, dict] = {
    "serverless_ec":    {"emoji": "🛒", "topics": ["aws", "architecture", "apigateway", "lambda"]},
    "static_web_hosting":{"emoji": "🌐","topics": ["aws", "architecture", "cloudfront", "s3"]},
    "container_platform":{"emoji": "🐳","topics": ["aws", "architecture", "ecs", "fargate"]},
    "event_driven_pipeline":{"emoji": "🌊","topics": ["aws", "architecture", "kinesis", "lambda"]},
    "microservices_base":{"emoji": "🔬","topics": ["aws", "architecture", "xray", "lambda"]},
    "multi_region_dr":  {"emoji": "🌍", "topics": ["aws", "architecture", "route53", "rds"]},
    "realtime_notify":  {"emoji": "🔔", "topics": ["aws", "architecture", "sns", "sqs"]},
    "bedrock_rag":      {"emoji": "🤖", "topics": ["aws", "bedrock", "rag", "生成ai"]},
    "cicd_pipeline":    {"emoji": "🚀", "topics": ["aws", "cicd", "codepipeline", "devops"]},
    "ml_pipeline":      {"emoji": "🧠", "topics": ["aws", "mlops", "sagemaker", "stepfunctions"]},
    "log_analytics":    {"emoji": "🔍", "topics": ["aws", "cloudtrail", "athena", "セキュリティ"]},
    "cost_optimization":{"emoji": "💰", "topics": ["aws", "コスト最適化", "finops", "クラウド"]},
    "security_hardening":{"emoji": "🛡️","topics": ["aws", "セキュリティ", "guardduty", "securityhub"]},
    "backup_dr":        {"emoji": "💾", "topics": ["aws", "backup", "dr", "可用性"]},
    "multi_account":    {"emoji": "🏢", "topics": ["aws", "organizations", "マルチアカウント", "ガバナンス"]},
    "data_lake":        {"emoji": "🏞️", "topics": ["aws", "datalake", "glue", "athena"]},
    "vpc_network":      {"emoji": "🔌", "topics": ["aws", "vpc", "network", "architecture"]},
    "async_orchestration": {"emoji": "⚙️", "topics": ["aws", "eventbridge", "stepfunctions", "architecture"]},
    "cicd_ec2_deploy":  {"emoji": "🔁", "topics": ["aws", "codedeploy", "ec2", "cicd"]},
    "user_auth_cognito":{"emoji": "🔑", "topics": ["aws", "cognito", "認証", "architecture"]},
    "observability_monitoring": {"emoji": "📈", "topics": ["aws", "cloudwatch", "監視", "sns"]},
    "edge_security":    {"emoji": "🧱", "topics": ["aws", "waf", "セキュリティ", "cloudfront"]},
    "secrets_rotation": {"emoji": "🔐", "topics": ["aws", "secretsmanager", "セキュリティ", "iam"]},
    "data_governance":  {"emoji": "🗂️", "topics": ["aws", "lakeformation", "glue", "データガバナンス"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
「読んでよかった」と思わせるアーキテクチャ解説記事を書いてください。
テンプレートを埋める作業ではなく、設計判断の背景まで伝える記事です。

## テーマ
{topic_name}：{topic_subtitle}

## 使用するAWSサービス（すべて記事中で扱うこと）
{services}

**構成図との整合性（必須）**: 構成図は上記サービスの並び・接続関係から機械的に生成される。
本文の「アーキテクチャ概要」「データ・リクエストの流れ」で説明する構成は、上記サービス一覧に
含まれる範囲・関係性と一致させること。上記に無いサービスへの分岐（例: 記載のないSQSへの
ファンアウト、記載のない並列処理）を本文で言及しない。

## キーワード（記事中に自然に含めること）
{keywords}

{docs_section}
## 読者像
AWSの基本サービス（EC2/S3/IAM）は使ったことがある中級者。
複数サービスを組み合わせた実践的な構成を、「なぜその設計か」まで理解したい。

---

## 品質の原則

**書くこと**
- 「なぜこのサービスを選んだか」「代替案と比べてどう違うか」を必ず示す
- 具体的な数字・コマンド・レスポンス例で語る（「スケールします」ではなく「同時実行数が〜まで」）
- 1文1意。長い複文は分割する
- 「〜できます」（「〜することができます」は使わない）
- 各ステップに「なぜそうするか」の理由を添える
- コードは実際に動くもの。省略や疑似コードは使わない
- **本文中で「〜を実現する」「〜を作成する」「〜を自動化する」と明言した機能は、対応するCLIコマンド・コード・設定を本文中に必ず含める**（タイトルや導入文の主張と実際のハンズオン手順が一致しているか、書き終えた後に自己チェックする）

**書かないこと・避けること**
- 「本記事では〜について解説します」（宣言型の導入）
- 「非常に重要です」「ぜひ試してみてください」（根拠のない煽り文句）
- 読者が知っていることの説明（「Lambdaとはサーバーレスの関数実行サービスです」等）
- 前セクションをそのままなぞるだけのまとめ
- 根拠のない最上級表現（「最もスケーラブルな」「業界標準」）
- 文章で書けるのに箇条書きに逃げる（流れを作れる部分は文章で書く）
- 手順を示さずに「〜は簡単です」と言う

---

## Zenn Markdown記法（効果的な場面でのみ使う）

**テーブル**: サービス比較・料金・オプション一覧など読者の判断を助ける場面
**:::message**: 設計上の重要な判断ポイントのみ（乱発しない）
**:::message alert**: コスト・セキュリティの具体的な注意（「注意してください」だけでなく何に注意するかを書く）
**:::details**: 読まなくてもメインが理解できる応用設定・トラブルシューティング
**コードブロック**: 言語またはファイル名を必ず指定する

使用例:
:::message
重要な設計判断ポイント（読者が見落としやすいこと）
:::

:::message alert
コスト・セキュリティの注意（具体的に書く）
:::

:::details 本番環境向けの追加設定
補足内容
:::

```bash:ステップ例
# ── ①IAMロールを作成する ──────────────────────
aws iam create-role --role-name my-app-role \\
  --assume-role-policy-document file://trust-policy.json
```

```bash:動作確認
aws iam get-role --role-name my-app-role --query 'Role.Arn' --output text
```

---

## 記事の見出し構成（この順序を基本とする）

アーキテクチャ解説記事として自然な流れを保つため、以下の順序を基本とする。
テーマの特性に応じてセクションの統合・分割・改題は自由。

### ## はじめに
{opening_style}
  - 指定された切り口はアプローチの指示であり、例文の転写ではなく自分の言葉で具体的に書く
  - 「この記事では〜を解説します」という宣言は使わない
- この記事で「何が作れるようになるか・何を判断できるようになるか」を1〜2文で示す
- **「この記事でわかること」を3行の箇条書きで示す**（スキマー向けの要点先出し。冒頭の課題描写のすぐ後、対象読者の前に置く）
  - 各行は具体的な成果物・判断軸で書く（例:「{topic_name}の構成要素と役割分担」「本番運用で見落としがちなコスト・セキュリティの落とし穴」）
  - 「〜がわかります」で統一し、抽象的な言い換えの羅列にしない
- 対象読者と前提知識（箇条書き可）

### ## アーキテクチャ概要

**`{{DIAGRAM_1}}` マーカーの配置ルール（必ず守ること）**
- マーカーは `## アーキテクチャ概要` セクションの本文中にのみ置く。他のセクション・見出し直後には置かない。
- 直前（1文）: {diagram_intro_style}
  - 決まり文句ではなく、このテーマの内容に即した自分の言葉で書く
  - 禁止: 「以下が全体構成図です。」のような内容のない定型文
- 直後（1〜2文）: 図から読み取れる最重要ポイントを具体的に補足する

構成:
1. この構成が解決する課題と解決策の概要を段落で書く
2. 予告文（1文）を書く
3. 単独行で `{{DIAGRAM_1}}` を挿入（前後に空行必須）
4. 図の補足説明（1〜2文）
5. 各サービスが担う役割を1〜2行で箇条書き
6. データ・リクエストの流れを番号付きで説明

{middle_sections}

### ## 設計上の考慮ポイント

構成:
1. このセクション全体の視点を1文で紹介
2. コスト・セキュリティ・スケーラビリティの3観点を解説:
   - **コスト最適化**: 各サービスの料金構造と削減テクニック
   - **セキュリティ**: IAMポリシー最小権限・暗号化・ネットワーク分離の具体的な設定
   - **スケーラビリティ**: 高負荷時の挙動とボトルネック対策

:::message alert
コストが予想外に膨らみやすいポイントと回避策を必ず明記する
:::

### ## 月額コスト目安
- 小規模・中規模・大規模の3パターンをテーブルで比較
- 各サービスのコスト内訳（リクエスト数・ストレージ・データ転送）
- コスト削減のための設定（無料枠・Savings Plans・Reserved等）
- 「最新情報はAWS公式の料金ページで確認してください」と注記する
- **計算根拠を必ず示す**: 単価×数量の計算式を本文またはテーブル内に明記し、合計欄は内訳の
  単純合計と一致させる（内訳と合計が食い違わないか書き終えた後に検算する）
- **日額と月額を混同しない**（日額の値をそのまま月額として書かない。月額換算は30日で計算する）
- 無料枠を差し引いた実質コストなのか、フル単価での試算なのかを明示する

### ## まとめ
- **「次に何をすべきか・どう発展させるか」を中心に書く**（学んだことの箇条書き再掲は避ける）
- このアーキテクチャが本領を発揮するシナリオと、逆に向いていないシナリオ
- 発展として学ぶべき次のトピック（関連サービス・設計パターン）

### ## 参考
- 「## 参考」の見出しだけを書き、本文（リンク一覧）は一切書かない
- 関連する全サービスの公式ドキュメントへのリンクはシステムが自動挿入する

---

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |
| Amazon Quick（BI機能はQuick Sight） | Amazon QuickSight | 2025年10月〜2026年 |

---

## 注意事項
- **記事の先頭にYAML frontmatter（--- で囲まれたブロック）を書かない**（frontmatterはシステムが自動付与する）
- 見出しは ## や ### を使ったMarkdown形式で書く（# は使わない）
- コードやコマンドはバッククォート3つで囲み、言語名またはファイル名を指定する
- 重要な用語は**太字**で強調する
- AWSコンソールの操作は具体的なメニュー名やボタン名を明記する
- 料金は2026年時点の情報を参考にし「最新情報はAWS公式サイトで確認してください」と注記する
- CLIコマンドの実行結果は**成功時のレスポンス例を必ずコードブロックで示す**（「結果が表示されます」は使わない）
- `:::message` や `:::details` は前後に必ず空行を入れること
- コードブロック内のサンプル日付は**本日の日付（{today}）** を基準にする（`2024`や`2023`等の過去の年は使わない）
- **文字数**: 6,000〜8,000文字程度（水増しより内容の充実を優先する）

---

## AWS CLI・IAM・コード品質の必須ルール

### IAM ポリシー（間違えやすい点）
- `ec2:DescribeInstances` / `s3:ListBuckets` / `cloudwatch:GetMetricData` などリスト・Describe系アクションは**リソースレベル条件（`ec2:ResourceTag` 等）を非サポート**。これらは `Resource: '*'` のみで単独ステートメントに書く
- リソースタグ条件（`ec2:ResourceTag/Environment: dev` 等）は `StopInstances` / `PutObject` などリソースレベル権限に対応したアクションのみに付与する
- 同一ステートメントにリソース条件対応・非対応のアクションを混在させない（条件が正しく評価されない）

### Lambda Runtime
- Lambda の Runtime は現時点の最新安定版を使う: `python3.14`（Python）/ `nodejs22.x`（Node.js）
- `python3.13` 以前や `nodejs20.x` 等の旧バージョンは使わない

### AWS CLI コマンドの正確性
- 記事内のAWS CLIコマンドは**実際に実行できるもの**を書く（オプション名・引数の誤記に注意）
- 変数は必ず `APP_NAME=` / `REGION=` / `ACCOUNT_ID=` で記事冒頭に定義し、以降の全コマンドで参照する
- リソースを作成したら ARN・URI を中間変数に保存し、後続コマンドで参照する
- SNS → Lambda のイベント連携には `aws lambda add-permission` によるリソースベースポリシーの追加が必須
- IAMポリシーはすべてファイル参照（`file://policy.json`）で記述する
- **JSONを受け取るオプション（`--attributes` / `--policy` / `--message-attributes` 等）に、
  シェルのコマンド置換やshorthand構文でJSONを直接埋め込まない**（例: `Key=$(cat file.json)`は
  実際にAWS側でパースエラーになる誤りパターン）。変数に読み込んでから渡すか `file://` 参照を使う
- 削除コマンドは必ずクリーンアップセクションにまとめる

### AWS サービスの制約（よく見落とされる事実）
- **Compute Optimizer**: メモリ使用率の分析には **CloudWatch Agent の別途インストールが必要**。Agent なしでは CPU・ネットワーク・ディスクのみ分析対象になる
- **AWS Budgets のデータ反映**: コストデータが Budgets に反映されるまで**最大24時間**かかる場合がある。「リアルタイム検知」は不可
- **Cost Explorer API コスト**: `GetCostAndUsage` 等のAPI呼び出しは**1リクエストあたり$0.01**の費用が発生する（コンソール閲覧は無料）
- **Savings Plans キャンセル不可**: 購入後のキャンセルは不可。推奨額の80〜90%からスタートする旨を必ず記載する
- サービスの制約・注意点は「できること」と同等の重みで記載する
"""

# ─── 書き出し・構成のバリエーション（コード側乱択） ───────────────────────────
# 以前はプロンプトに「課題から入る例」「ニーズから入る例」の例文を併記していたが、
# 生成記事7件中6件が同一パターン（失敗談引用型）の書き出しになる偏りが確認された。
# LLMに「ランダムに選んで」と指示しても偏る（トピック選択で実証済み）ため、
# コード側 random.choice で1つだけをプロンプトに埋め込む。逐語転写を誘発しないよう
# 完全な例文は載せず「このアプローチで書け」という指示に留める。

_OPENING_STYLES: list[str] = [
    "- **冒頭の1〜2文は「実際に起きがちな失敗・障害」から入る**（運用現場で起きる具体的なトラブルを1つ描き、その対処として本構成につなげる）",
    "- **冒頭の1〜2文は「具体的な数字」から入る**（レイテンシ・リクエスト数・コスト等の定量的な事実から、この構成が必要になる理由につなげる）",
    "- **冒頭の1〜2文は「読者への問いかけ」から入る**（読者が現場で迷いそうな設計判断を疑問形で示し、その答えとして本構成を提示する）",
    "- **冒頭の1〜2文は「素朴な構成の限界」から入る**（単純な構成では何が破綻するかを示し、本構成でどう変わるかのビフォーアフターにつなげる）",
    "- **冒頭の1〜2文は「この構成が必要になる典型シナリオ」から入る**（どんなチーム・システム規模・フェーズで必要になるかを具体的に描く）",
]

# 構成図直前の予告文も「良い例」の逐語転写が確認されたため、切り口の指示のみ乱択で与える
_DIAGRAM_INTRO_STYLES: list[str] = [
    "図を先に把握しておくと以降のどの設計判断が理解しやすくなるか、を示す予告文を書く",
    "図に何がまとまっているか（サービス間の接続関係・データの流れ）を予告する1文を書く",
    "図のどこに注目して読んでほしいか（要のサービス・境界など）を示す1文を書く",
]

# 「選定理由」と「構成手順」は記事として自然さを損なわない範囲で順序を入れ替えられるため、
# 2ブロックを乱択で並べ替えて {middle_sections} に埋め込む（見出し構成の紋切り型化を防ぐ）
_SECTION_COMPONENTS = """### ## 各コンポーネントの選定理由
- なぜこのサービスの組み合わせを選んだか（代替案との比較をテーブルで）
- 各サービスが解決する課題を「課題 → 解決策 → 採用理由」の形で書く
- `:::message` で「設計のポイント」を強調する"""

_SECTION_STEPS = """### ## 構成手順
- **前提条件**: 「AWSマネジメントコンソールにログイン済み（AWS CloudShellを使用）」＋必要なIAM権限のみでよい（ローカル環境へのインストール手順は書かない）
- **実行環境はAWS CloudShellに統一する**: AWS CLI・Python/pip・Node.js/npm・jq・zip/unzipはCloudShellにプリインストール済みのため、ローカルのセットアップ手順は不要
  - IAM権限は「CloudShellにログインしているIAMユーザー／ロールの権限がそのまま使われる」旨を`:::message`で必ず注記する
  - CloudShellは約20〜30分操作がないとセッションがタイムアウトする旨も注記する
- **作業ディレクトリと変数の設定（冒頭に必須）**: `bash:変数設定` ブロックで `APP_NAME` / `REGION` / `ACCOUNT_ID` を定義する
- **ステップ1〜5以上**: AWS CLIコマンドを中心に手順を説明する
  - 各ステップ冒頭に `# ── ①目的 ────` 形式のセクションコメントを付ける（番号は通し番号）
  - コードブロックは `bash:ステップ名` 形式で記述する
  - IAMポリシー等の長いJSONはすべてファイル参照（`file://policy.json`）で記述する
  - 変数展開が必要なJSONファイルは unquoted heredoc（`<< EOF`）を使用し、リテラルは quoted heredoc（`<< 'EOF'`）を明示的に使い分ける
  - リソース作成後に取得した ARN・URI は変数に保存して後続コマンドで参照する
  - 各ステップのつまずきポイントを `:::message` で注記する
  - AWS CLIコマンドは**成功時のレスポンス例を必ずコードブロックで示す**（「結果が表示されます」は使わない）
- **クリーンアップ（末尾に必須）**: 作成したリソースを逆順に削除するコマンドを列挙する。**クリーンアップより後に新規リソースを作成するコードを置かない**（読者が「片付け済み」と誤解したまま追加コードを実行し、リソースが残留する事故になるため）。片付け対象が複数ステップにまたがる場合は、最後のクリーンアップステップで一括削除する
- **動作確認**: 実際に動かして確認する手順"""


def build_article_prompt(topic: dict, today: str, docs_section: str) -> str:
    """記事生成プロンプトを組み立てる。書き出しスタイル・図の予告文の切り口・
    中盤セクション（選定理由/構成手順）の順序をコード側乱択で決定する。
    {{DIAGRAM_1}}マーカーの記法・配置ルールはここでは一切変更しない。
    """
    middle_order = random.choice([
        (_SECTION_COMPONENTS, _SECTION_STEPS),
        (_SECTION_STEPS, _SECTION_COMPONENTS),
    ])
    return ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        services="、".join(topic["services"]),
        keywords=topic["keywords"],
        today=today,
        docs_section=docs_section,
        primary_service_label=topic.get("primary_service_label", ""),
        opening_style=random.choice(_OPENING_STYLES),
        diagram_intro_style=random.choice(_DIAGRAM_INTRO_STYLES),
        middle_sections="\n\n".join(middle_order),
    )


# ─── AWS公式ドキュメント取得 ──────────────────────────────────────────────────

def fetch_aws_docs(service_id: str, max_chars: int = DOCS_MAX_CHARS) -> str:
    """AWS公式ドキュメントを取得してプレーンテキストを返す。失敗時は空文字列。"""
    import re
    import urllib.request

    url = DOCS_URL_MAP.get(service_id, "")
    if not url:
        print(f"[Docs] {service_id}: URL未定義のためスキップ")
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urllib.request.urlopen(req, timeout=DOCS_FETCH_TIMEOUT_SEC) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)

        main = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
        content = main.group(1) if main else html

        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        print(f"[Docs] {service_id}: {len(text)}文字取得 ({url})")
        return text[:max_chars]
    except Exception as e:
        print(f"[Docs] {service_id}: 取得エラー（スキップ）: {e}")
        return ""


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
        print(f"[WARNING] SSM読み込みエラー。トピック除外なしで続行します（同テーマが連続生成される可能性あり）: {e}")
        return []


def save_topic_to_ssm(topic_id: str, recent: list[str]):
    """選択したトピックを SSM に保存する（最新 RECENT_TOPICS_LIMIT 件を保持）。
    recentはStep 1で取得済みの除外リストをそのまま渡す（ここで再取得すると、
    一時的なSSM読み込みエラー時に履歴が丸ごと[topic_id]1件だけに縮退してしまうため）。
    """
    recent = list(recent)
    if topic_id in recent:
        recent.remove(topic_id)
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


def get_topic_occurrence(topic_id: str) -> int:
    """SSM からトピックの累計生成回数を取得する（0=初回）。
    RECENT_TOPICS_LIMIT引き上げでも全トピック消化後は再登場し得るため、
    再登場時に記事タイトルへ回次サフィックスを付与し完全一致を避ける。
    """
    try:
        response = ssm.get_parameter(Name=SSM_PARAM_OCCURRENCE)
        counts = json.loads(response["Parameter"]["Value"])
        return counts.get(topic_id, 0) if isinstance(counts, dict) else 0
    except ssm.exceptions.ParameterNotFound:
        return 0
    except Exception as e:
        print(f"[WARNING] SSM occurrence読み込みエラー（0として続行）: {e}")
        return 0


def increment_topic_occurrence(topic_id: str) -> None:
    """トピックの累計生成回数をSSMに保存する（get_topic_occurrenceと同じ辞書を更新）"""
    try:
        response = ssm.get_parameter(Name=SSM_PARAM_OCCURRENCE)
        counts = json.loads(response["Parameter"]["Value"])
        if not isinstance(counts, dict):
            counts = {}
    except ssm.exceptions.ParameterNotFound:
        counts = {}
    except Exception as e:
        print(f"[WARNING] SSM occurrence読み込みエラー（新規カウントとして続行）: {e}")
        counts = {}
    counts[topic_id] = counts.get(topic_id, 0) + 1
    try:
        ssm.put_parameter(
            Name=SSM_PARAM_OCCURRENCE,
            Value=json.dumps(counts),
            Type="String",
            Overwrite=True,
        )
    except Exception as e:
        print(f"SSM occurrence書き込みエラー（無視して続行）: {e}")


# ─── トピック選択 ─────────────────────────────────────────────────────────────

def _resolve_topic_variant(topic: dict) -> dict:
    """variants定義を持つトピックは「基本形＋各バリエーション」から1つを乱択して確定する。
    返す辞書はvariantsキーを持たない解決済みトピックで、呼び出し側は従来どおり
    固定のservices/subtitle/keywordsとして扱える。variantsが無いトピックはそのまま返す
    （コピーするのは、呼び出し側の変更がAWS_TOPICS本体を汚染しないようにするため）。
    """
    resolved = {k: v for k, v in topic.items() if k != "variants"}
    variants = topic.get("variants")
    if variants:
        # 空辞書 {} は「基本形のまま」を表す（基本形も等確率で選ばれ続けるようにする）
        resolved.update(random.choice([{}] + list(variants)))
    return resolved


def select_topic(excluded_ids: list[str]) -> dict:
    """重複を避けながらトピックを選択する。
    以前はBedrockに「ランダムに選んで」と依頼していたが、実績を集計すると
    特定トピック（log_analytics）に強く偏っており、LLMの「ランダム」は
    公平な乱択として機能していなかった。Bedrock呼び出し自体が不要なため、
    コスト・レイテンシ削減も兼ねてrandom.choiceに置き換える。
    """
    available = [t for t in AWS_TOPICS if t["id"] not in excluded_ids]
    if not available:
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS
    return _resolve_topic_variant(random.choice(available))


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

DOCS_MAX_CHARS_PER_SERVICE = 2500  # 3サービス分を取得するため1件あたりの上限を絞る


def generate_article(topic: dict, today: str, model_id: str) -> tuple[str, bool]:
    """Bedrock を使って記事を生成する。(article_text, is_truncated) を返す"""
    # v2.9: primary_service 1件だけでなく、トピックの3サービス全件から根拠情報を取得する
    # （従来はハルシネーション抑制策が主軸1サービスにしか効いていなかった）
    docs_parts = []
    seen_ids: set[str] = set()
    for svc in topic["services"]:
        doc_id = _SERVICE_NAME_TO_DOCS_ID.get(svc, "")
        if not doc_id or doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        content = fetch_aws_docs(doc_id, max_chars=DOCS_MAX_CHARS_PER_SERVICE)
        if content:
            docs_parts.append(f"### {svc}\n{content}")
    docs_content = "\n\n".join(docs_parts)
    docs_section = (
        "## AWS公式ドキュメント（根拠情報）\n"
        "以下は各AWSサービスの公式ドキュメントから取得した情報です。技術的事実はこの内容を根拠として正確に記述し、矛盾しないようにしてください。\n"
        "ドキュメントに記載のない事実は、確実に知っている場合のみ記述し、不確かな場合は記述しないか「〜の場合があります」等の不確定表現を使ってください。\n\n"
        f"{docs_content}\n\n---\n"
        if docs_content else ""
    )
    prompt = build_article_prompt(topic, today, docs_section)

    body_dict = {
        "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
        "max_tokens": ARTICLE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if "sonnet-5" in model_id:
        # Haikuはadaptive thinking非対応のため、Sonnet 5使用時のみ有効化する
        # 注意: BEDROCK_MODEL_IDをsonnet-5系ARNに切り替える場合はcfn-mid-article-generator.yaml
        # のBedrock IAMポリシー（bedrock:InvokeModel Resource）にsonnet-5のARNを追加すること。
        # 現状はsonnet-4-6/haiku-4-5のみ許可しておりAccessDeniedになる
        body_dict["thinking"] = {"type": "adaptive"}

    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body_dict),
    )

    result = json.loads(response["body"].read())
    # thinking有効時はcontent[0]がthinkingブロック（"text"キーなし）になり得るため、
    # type=="text" のブロックを明示的に探す（content[0]決め打ちはKeyErrorの原因になる）。
    # adaptive thinkingがmax_tokensで打ち切られるとtextブロック自体が存在しないことがあるため、
    # デフォルトNoneを指定してStopIteration（未捕捉のままlambda_handlerまで伝播しBedrockコスト
    # 二重発生の原因になる）を避け、空記事＋truncated扱いにフォールバックする
    text_block = next((b for b in result["content"] if b.get("type") == "text"), None)
    usage = result.get("usage", {})
    stop_reason = result.get("stop_reason", "unknown")
    is_truncated = stop_reason == "max_tokens" or text_block is None
    text = text_block["text"] if text_block is not None else ""
    if text_block is None:
        print("[WARNING] Bedrock応答にtextブロックがありません（thinking中に打ち切られた可能性）。空の記事として扱います。")
    in_tok  = usage.get('input_tokens', 0)
    out_tok = usage.get('output_tokens', 0)
    is_haiku = "haiku" in model_id
    input_cost_per_mtok  = HAIKU_INPUT_COST_PER_MTOK  if is_haiku else SONNET_INPUT_COST_PER_MTOK
    output_cost_per_mtok = HAIKU_OUTPUT_COST_PER_MTOK if is_haiku else SONNET_OUTPUT_COST_PER_MTOK
    cost_usd = (in_tok * input_cost_per_mtok + out_tok * output_cost_per_mtok) / 1_000_000  # 概算
    print(f"[Bedrock/article] in={in_tok}, out={out_tok}, stop={stop_reason}, cost≈${cost_usd:.4f}")
    if is_truncated:
        print("[WARNING] 記事がmax_tokensで打ち切られました。記事が不完全な可能性があります。")

    # Bedrock が記事冒頭に YAML frontmatter を付けることがあるため除去する
    if text.lstrip().startswith("---"):
        lines = text.lstrip().splitlines(keepends=True)
        end = 1
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                end = i + 1
                break
        text = "".join(lines[end:]).lstrip()

    return text, is_truncated


# ─── MD 生成（画像プレースホルダー付き） ─────────────────────────────────────

_DIAGRAM_CAPTIONS = [
    "{topic_name} – 構成図",
]


def _make_image_placeholder(png_path: str, topic_name: str, index: int) -> str:
    filename = os.path.basename(png_path)
    caption_tmpl = _DIAGRAM_CAPTIONS[index - 1] if index - 1 < len(_DIAGRAM_CAPTIONS) else "{topic_name} 構成図" + str(index)
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
    """{{DIAGRAM_N}} マーカーを画像プレースホルダーに置換する。
    マーカーが見つからない場合は見出し名ベースのフォールバック挿入を行う。
    """
    if not png_paths:
        # format() 後は単一波括弧 {DIAGRAM_N}、未展開時は二重波括弧 {{DIAGRAM_N}} の
        # どちらが残っていても除去できるようにパターンを両対応にする。
        cleaned, n = re.subn(r'\n*\{\{?DIAGRAM_\d+\}\}?\n*', '\n\n', article)
        if n:
            print(f"[WARNING] PNG未生成のためDIAGRAMマーカー{n}件を除去しました")
        return cleaned

    # フォールバック用: 見出し名で挿入位置を探す順序
    _FALLBACK_HEADINGS = ["アーキテクチャ概要"]

    result = article
    for img_idx, png_path in enumerate(png_paths):
        n = img_idx + 1
        # format() 後は単一波括弧が正常だが、LLMがプロンプト例文の二重波括弧を
        # そのまま出力することがあるため両方を置換対象にする
        marker = "{" + f"DIAGRAM_{n}" + "}"
        marker_double = "{" + marker + "}"
        placeholder = _make_image_placeholder(png_path, topic_name, n)

        if marker_double in result:
            result = result.replace(marker_double, placeholder, 1)
        elif marker in result:
            result = result.replace(marker, placeholder, 1)
        else:
            # フォールバック: 対応する見出し名の直後に挿入
            lines = result.split("\n")
            target_heading = _FALLBACK_HEADINGS[img_idx] if img_idx < len(_FALLBACK_HEADINGS) else None
            h2_positions = [i for i, line in enumerate(lines) if line.startswith("## ")]
            if not h2_positions:
                # 見出しが1つもない場合は末尾に追記（スキップせずプレースホルダーを保持）
                print(f"[WARNING] DIAGRAM_{n} のマーカー・見出しが見つからないため末尾に挿入します")
                result = result.rstrip() + "\n\n" + placeholder
                continue

            if target_heading:
                matched = [i for i, line in enumerate(lines)
                           if line.startswith("## ") and target_heading in line]
                insert_idx = matched[0] if matched else h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            else:
                insert_idx = h2_positions[min(img_idx + 1, len(h2_positions) - 1)]

            lines.insert(insert_idx + 1, placeholder)
            result = "\n".join(lines)

    # 図の一部が生成失敗した場合、残存する {DIAGRAM_N} マーカーを除去する
    # LLMがプロンプト例文の二重波括弧 {{DIAGRAM_N}} をそのまま出力するケースもあるため、
    # 単一・二重波括弧の両方を除去対象にする（_embed_image_placeholders冒頭と同じパターン）
    result, n_orphan = re.subn(r'\n*\{\{?DIAGRAM_\d+\}\}?\n*', '\n\n', result)
    if n_orphan:
        print(f"[WARNING] 図生成失敗により未置換のDIAGRAMマーカー{n_orphan}件を除去しました")

    return result


def _inject_reference_link(article: str, topic: dict) -> str:
    """topicのservices全件について、公式ドキュメントURLを '## 参考' セクションに挿入する。
    LLMにURLを書かせるとハルシネーションのリスクがあるため、DOCS_URL_MAPの
    確定済みURLをコード側で直接挿入する（LLM生成テキストとは独立した安全な追記）。
    services内に対応表・URLマップが無いサービスがあれば、そのサービスだけ静かにスキップする
    （記事全体を失敗させない）。
    """
    link_lines: list[str] = []
    seen_urls: set[str] = set()
    for svc in topic.get("services", []):
        doc_id = _SERVICE_NAME_TO_DOCS_ID.get(svc, "")
        url = DOCS_URL_MAP.get(doc_id, "") if doc_id else ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        link_lines.append(f"- [{svc} 公式ドキュメント]({url})")
    if not link_lines:
        return article
    link_block = "\n".join(link_lines)

    lines = article.split("\n")
    # 完全一致「## 参考」を優先。見出し改題（例:「## 参考アーキテクチャとの比較」）に
    # 誤ってマッチしないよう、部分一致は最後に見つかったもの（通常は記事末尾の参考節）を使う
    exact = [i for i, line in enumerate(lines) if line.strip() == "## 参考"]
    if exact:
        ref_idx = exact[0]
    else:
        partial = [i for i, line in enumerate(lines) if line.startswith("## ") and "参考" in line]
        ref_idx = partial[-1] if partial else None
    if ref_idx is None:
        return article.rstrip() + f"\n\n## 参考\n\n{link_block}\n"

    lines.insert(ref_idx + 1, f"\n{link_block}")
    return "\n".join(lines)


def _next_article_number(output_dir: str) -> str:
    """既存フォルダの最大番号+1を返す。"""
    import glob
    existing = glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9]_*"))
    nums = [int(os.path.basename(p)[:3]) for p in existing]
    return f"{(max(nums) if nums else 0) + 1:03d}"


def save_to_local(topic: dict, article: str, timestamp: str, occurrence: int = 1) -> tuple[str, list[str]]:
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

    # 構成図を生成（1枚）
    png_paths = generate_diagrams(topic, png_base)

    # primary_service の確定URLを '## 参考' セクションに挿入（LLM生成ではない安全なリンク）
    article = _inject_reference_link(article, topic)

    # {{DIAGRAM_1}} マーカーで記事中に挿入（マーカー不在時はフォールバック）
    article_with_images = _embed_image_placeholders(article, png_paths, topic["name"])

    # Zennフロントマター用メタ情報
    meta = _ZENN_META.get(topic["id"], {"emoji": "☁️", "topics": ["aws", "architecture"]})
    topics_json = json.dumps(meta["topics"], ensure_ascii=False)

    # 再登場（occurrence>=2）時は完全同一タイトルにならないよう回次サフィックスを付与する
    title_suffix = f"（{occurrence}周目）" if occurrence >= 2 else ""

    full_content = f"""---
title: "{topic['name']}：{topic['subtitle']}{title_suffix}"
emoji: "{meta['emoji']}"
type: "tech"
topics: {topics_json}
published: false
---

{article_with_images}

<!-- 生成情報: topic={topic['id']} / type={topic['article_type']} / services={",".join(topic['services'])} / generated_at={timestamp} / chars={len(article)} / images={len(png_paths)}枚 -->
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return md_path, png_paths


# ─── S3 アップロード ──────────────────────────────────────────────────────────

def upload_to_s3(md_path: str, png_paths: list[str], s3_folder: str, prefix: str = S3_PREFIX) -> str:
    """MD ファイルと PNG 画像を S3 にアップロードし、S3 フォルダパスを返す"""
    s3_base = f"{prefix}/{s3_folder}"

    md_key = f"{s3_base}/{os.path.basename(md_path)}"
    s3.upload_file(md_path, S3_BUCKET, md_key, ExtraArgs={"ContentType": "text/markdown"})
    print(f"S3アップロード: s3://{S3_BUCKET}/{md_key}")

    for png_path in png_paths:
        png_key = f"{s3_base}/images/{os.path.basename(png_path)}"
        s3.upload_file(png_path, S3_BUCKET, png_key, ExtraArgs={"ContentType": "image/png"})
        print(f"S3アップロード: s3://{S3_BUCKET}/{png_key}")

    return f"s3://{S3_BUCKET}/{s3_base}/"


# ─── AWS CLI コマンドチェック ────────────────────────────────────────────────

def validate_cli_in_article(article_text: str) -> list[str]:
    """記事内にAWS CLIベースの構築手順が含まれているかチェックする"""
    issues = []

    # bashコードブロック内に限定してCLIコマンドを検索（散文中のaws言及と区別）
    bash_blocks = "\n".join(re.findall(r'```bash[^\n]*\n(.*?)```', article_text, re.DOTALL))
    required_in_bash = {
        "aws ": "bashブロック内のAWS CLIコマンド",
    }
    for keyword, label in required_in_bash.items():
        if keyword not in bash_blocks:
            issues.append(f"{label}が見つかりません")

    # 変数定義は記事全体から確認（変数設定ブロックは```bash外に書かれることもある）
    required_in_text = {
        "APP_NAME=":   "変数設定（APP_NAME）",
        "REGION=":     "変数設定（REGION）",
        "ACCOUNT_ID=": "変数設定（ACCOUNT_ID）",
    }
    for keyword, label in required_in_text.items():
        if keyword not in article_text:
            issues.append(f"{label}が見つかりません")

    # クリーンアップ節は同義語も許容（監視系トピックはクリーンアップ不要な場合もあるため警告のみ）
    _CLEANUP_SYNONYMS = ("クリーンアップ", "後片付け", "リソース削除")
    if not any(kw in article_text for kw in _CLEANUP_SYNONYMS):
        issues.append("クリーンアップセクションがありません（不要なトピックの場合は無視してください）")

    print(f"[CLI検証] 必須要素チェック完了 / 問題{len(issues)}件")
    return issues


# ─── 記事品質チェック（検出のみ・書き換えは行わない） ────────────────────────
# v2.3→v2.4でAI自動修正機能（検出→書き換え）を撤回した教訓を踏まえ、
# ここでは機械的に検出してメールで警告するだけに留め、記事本文には一切手を加えない。

_REQUIRED_HEADING_KEYWORDS = ["アーキテクチャ", "選定理由", "構成手順", "コスト", "まとめ", "参考"]
_BANNED_PHRASES = ["することができます", "本記事では", "ぜひ試してみてください"]
_OUTDATED_RUNTIME_PATTERNS = ["python3.13", "python3.12", "python3.11", "nodejs20.x", "nodejs18.x"]


def validate_article_quality(article_text: str) -> list[str]:
    """プロンプトで要求している品質ルールのうち機械チェック可能なものを検出する。
    見出しはテーマに応じた改題を許容しているため厳密な文字列一致ではなくキーワード部分一致で判定する。
    """
    issues = []

    headings = [line for line in article_text.split("\n") if line.startswith("## ")]
    heading_text = " ".join(headings)
    for kw in _REQUIRED_HEADING_KEYWORDS:
        if kw not in heading_text:
            issues.append(f"見出しに「{kw}」を含むセクションが見当たりません")

    for phrase in _BANNED_PHRASES:
        if phrase in article_text:
            issues.append(f"禁止表現「{phrase}」が含まれています")

    if re.search(r"SageMaker(?! AI)", article_text):
        issues.append("旧称「SageMaker」（正式には「SageMaker AI」）表記の可能性があります")

    for pattern in _OUTDATED_RUNTIME_PATTERNS:
        if pattern in article_text:
            issues.append(f"旧Runtime表記「{pattern}」が含まれています")

    for year in ("2023年", "2024年"):
        if year in article_text:
            issues.append(f"過去の年表記「{year}」が含まれています（本日の日付基準か確認してください）")

    if len(article_text) < 3000:
        issues.append(f"文字数が{len(article_text):,}文字と少なすぎます（生成失敗の可能性）")

    print(f"[品質検証] 機械チェック完了 / 問題{len(issues)}件")
    return issues


def extract_article_outline(article_text: str) -> list[tuple[str, int]]:
    """見出し（##/###）ごとの文字数を集計する（通知メールでのレビュー支援用）"""
    lines = article_text.split("\n")
    sections: list[tuple[str, int]] = []
    current_heading = None
    current_len = 0
    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            if current_heading is not None:
                sections.append((current_heading, current_len))
            current_heading = line.lstrip("#").strip()
            current_len = 0
        elif current_heading is not None:
            current_len += len(line)
    if current_heading is not None:
        sections.append((current_heading, current_len))
    return sections


# トピック別のレビュー着眼点（過去に実バグが見つかった箇所を中心に厳選、網羅は狙わない）
_REVIEW_HINTS: dict[str, list[str]] = {
    "cost_optimization": [
        "Cost Explorer の GetCostAndUsage 等API呼び出しが$0.01/回と明記されているか",
        "Budgets のコスト反映が最大24時間かかる旨が書かれているか",
        "Savings Plans購入後のキャンセル不可・推奨額80〜90%スタートの記載があるか",
    ],
    "log_analytics": [
        "Athenaのパーティション（Partition Projection等）の説明が省略されていないか",
        "CloudTrailログのS3保存形式（gzip等）の記述が実態と合っているか",
    ],
    "security_hardening": [
        "GuardDuty・Security Hubのリージョン別有効化が必要な点に触れているか",
    ],
    "microservices_base": [
        "X-Rayのトレース有効化（Active Tracing設定）の手順が漏れていないか",
    ],
    "multi_region_dr": [
        "Route 53ヘルスチェックの評価間隔・フェイルオーバー条件が具体的に書かれているか",
    ],
    "bedrock_rag": [
        "Knowledge Base同期・チャンキング設定の説明が概念だけで終わっていないか",
    ],
}
_DEFAULT_REVIEW_HINT = "料金・バージョン表記が最新か、AWS公式ドキュメントで確認してください"


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, s3_url: str = "", is_truncated: bool = False,
    cfn_issues: list | None = None, test_mode: bool = False,
):
    """SES でメール通知を送信する（MD・PNG添付付き）"""
    import html as _html
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    preview_html = _html.escape(preview)
    services_str = " + ".join(topic["services"])
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    outline = extract_article_outline(article)
    outline_text = "\n".join(f"  - {h}（約{c:,}文字）" for h, c in outline) or "  （見出しが検出できませんでした）"
    outline_html = "".join(
        f'<li>{_html.escape(h)} <span style="color:#888;">（約{c:,}文字）</span></li>' for h, c in outline
    ) or "<li>（見出しが検出できませんでした）</li>"

    review_hints = _REVIEW_HINTS.get(topic["id"], [_DEFAULT_REVIEW_HINT])
    review_hints_text = "\n".join(f"  - {h}" for h in review_hints)
    review_hints_html = "".join(f'<li>{_html.escape(h)}</li>' for h in review_hints)

    subject_prefix = "【TEST】" if test_mode else ""
    subject = (
        f"{subject_prefix}【⚠️ 記事が途中で切れています】{topic['name']} - {timestamp}"
        if is_truncated else
        f"{subject_prefix}【Zenn中級記事生成完了】{topic['name']} - {timestamp}"
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
        '<li>S3からローカルにダウンロード（下記コマンドをそのままコピペして実行）<br>'
        '<code style="display:inline-block;margin-top:4px;">'
        'bash 005_Zenn_Mid_Article_Bot/scripts/download_article.sh'
        '</code></li>'
        if s3_url else ""
    )

    cfn_issues = cfn_issues or []
    truncation_warning_text = """
⚠️ 警告: 記事が途中で切れています
記事の生成がmax_tokensに達したため、末尾が不完全な可能性があります。
Zennに投稿する前に内容を必ず確認してください。
""" if is_truncated else ""

    cfn_warning_text = (
        "⚠️ AWS CLIチェックで問題が見つかりました:\n"
        + "\n".join(f"  - {i}" for i in cfn_issues) + "\n"
    ) if cfn_issues else ""

    body_text = f"""Zenn中級記事の自動生成が完了しました。
{truncation_warning_text}{cfn_warning_text}
■ 記事情報
- テーマ: {topic['name']}（{topic['article_type']}）
- 使用サービス: {services_str}
- 文字数: {char_count:,}文字
- 生成日時: {timestamp}
- 構成図PNG: {diagram_info}
- S3保存先: {s3_url}

■ 見出しアウトライン
{outline_text}

■ レビューチェックリスト（{topic['name']}）
{review_hints_text}

■ 記事プレビュー（先頭300文字）
{preview}...

■ 次のアクション
1. 記事をダウンロード（下記コマンドをそのままコピペして実行）
bash 005_Zenn_Mid_Article_Bot/scripts/download_article.sh
2. Zennエディタで新規記事を作成
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

    cfn_issues_html = (
        '<div style="background:#fde8e8;border:2px solid #e53e3e;padding:15px;border-radius:8px;margin:20px 0;">'
        '<h3 style="color:#c53030;margin-top:0;">⚠️ AWS CLIチェックで問題が見つかりました</h3>'
        '<ul style="color:#c53030;margin:0;">'
        + "".join(f'<li><code>{i}</code></li>' for i in cfn_issues)
        + '</ul></div>'
    ) if cfn_issues else (
        '<div style="background:#e8f5e9;border:1px solid #66bb6a;padding:10px 15px;border-radius:8px;margin:20px 0;">'
        '<p style="color:#2e7d32;margin:0;">✅ AWS CLIチェック — 問題なし</p>'
        '</div>'
    )

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#3EA8FF;">Zenn中級記事の自動生成が完了しました</h2>
  {truncation_warning_html}
  {cfn_issues_html}

  <div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>記事情報</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:5px;font-weight:bold;">テーマ</td>
          <td>{topic['name']}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">記事タイプ</td>
          <td>{"複合アーキテクチャ" if topic["article_type"] == "architecture" else "ユースケース別ソリューション"}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">使用サービス</td>
          <td>{services_str}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">文字数</td>
          <td>{char_count:,}文字</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">生成日時</td>
          <td>{timestamp}</td></tr>
      <tr><td style="padding:5px;font-weight:bold;">構成図PNG</td>
          <td><ul style="margin:0;padding-left:16px;">{png_list_html}</ul></td></tr>
      {s3_row}
    </table>
  </div>

  <div style="background:#f0f7ff;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>見出しアウトライン</h3>
    <ul style="margin:0;padding-left:16px;">{outline_html}</ul>
  </div>

  <div style="background:#f0f7ff;padding:15px;border-radius:8px;margin:20px 0;">
    <h3>レビューチェックリスト</h3>
    <ul style="margin:0;padding-left:16px;">{review_hints_html}</ul>
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
      <li>:::message ブロック内の指示に従ってPNGをアップロード・差し替え</li>
      <li><code>published: false</code> → <code>true</code> に変更して公開</li>
    </ol>
  </div>

  <p style="color:#999;font-size:12px;">このメールは自動送信されています。</p>
</body>
</html>
"""

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = SES_SENDER_EMAIL
    msg["To"] = SES_RECIPIENT_EMAIL

    msg_body = MIMEMultipart("alternative")
    msg_body.attach(MIMEText(body_text, "plain", "utf-8"))
    msg_body.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(msg_body)

    # MD・PNGを添付し、メールを開くだけでレビューを開始できるようにする。
    # 添付自体の失敗は本文送信を止める理由にならないため個別にtry/exceptで囲む
    try:
        with open(md_path, "rb") as f:
            md_part = MIMEApplication(f.read(), _subtype="markdown")
        md_part.add_header("Content-Disposition", "attachment", filename=os.path.basename(md_path))
        msg.attach(md_part)
    except Exception as e:
        print(f"MD添付エラー（無視して続行）: {e}")

    for png_path in png_paths:
        try:
            with open(png_path, "rb") as f:
                png_part = MIMEApplication(f.read(), _subtype="png")
            png_part.add_header("Content-Disposition", "attachment", filename=os.path.basename(png_path))
            msg.attach(png_part)
        except Exception as e:
            print(f"PNG添付エラー（無視して続行）: {e}")

    try:
        ses.send_raw_email(
            Source=SES_SENDER_EMAIL,
            Destinations=[SES_RECIPIENT_EMAIL],
            RawMessage={"Data": msg.as_string()},
        )
        print(f"メール送信完了（添付付き）: {subject}")
    except Exception as e:
        # 添付付き送信が失敗しても記事自体はS3に保存済みのため、通知だけは
        # 添付なしの通常メールにフォールバックして必ず届ける
        print(f"添付付きメール送信失敗。添付なしでフォールバック送信します: {e}")
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
        print(f"メール送信完了（添付なしフォールバック）: {subject}")


# ─── Lambda ハンドラ ──────────────────────────────────────────────────────────

HAIKU_MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"

def lambda_handler(event, context):
    _total_start = time.time()
    dry_run = bool((event or {}).get("dry_run", False))
    model_id = HAIKU_MODEL_ID if event.get("test_mode") else BEDROCK_MODEL_ID
    if event.get("test_mode"):
        print(f"[TEST MODE] モデルをHaikuに切り替えました: {model_id}")

    now       = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    today     = now.strftime("%Y-%m-%d")
    if dry_run:
        print(f"[{timestamp}] [DRY_RUN] Zenn中級記事自動生成を開始します（S3保存・メール送信・SSM書き込みをスキップ）")
    else:
        print(f"[{timestamp}] Zenn中級記事自動生成を開始します")

    # Step 1: 直近トピック取得
    _t = time.time()
    print("Step 1: 直近トピックをSSMから取得中...")
    excluded_ids = get_recent_topics()
    print(f"  除外トピック: {excluded_ids} [{time.time()-_t:.1f}s]")

    # Step 2: トピック選択
    _t = time.time()
    print("Step 2: トピックを選択中...")
    topic = select_topic(excluded_ids)
    print(f"  選択されたトピック: {topic['name']} ({topic['id']}) [{time.time()-_t:.1f}s]")
    print(f"  記事タイプ: {topic['article_type']}")
    print(f"  使用サービス: {', '.join(topic['services'])}")
    # このトピックの累計生成回次（タイトル重複防止サフィックス用。実際の保存はStep 6で行う）
    occurrence = get_topic_occurrence(topic["id"]) + 1
    print(f"  このトピックの生成回次: {occurrence}回目")

    # Step 3: 記事生成
    _t = time.time()
    print("Step 3: 記事を生成中（6,000〜8,000文字）...")
    article, is_truncated = generate_article(topic, today, model_id)
    print(f"  記事生成完了: {len(article):,}文字 [{time.time()-_t:.1f}s]")

    # Step 4: ローカル保存 + 構成図生成
    _t = time.time()
    print("Step 4: ローカルに保存中（記事MD + 構成図PNG）...")
    md_path, png_paths = save_to_local(topic, article, timestamp, occurrence)
    print(f"  MD保存完了: {md_path}")
    print(f"  PNG生成完了: {len(png_paths)}枚 [{time.time()-_t:.1f}s]")

    # Step 5: S3 アップロード（Lambda環境のみ）
    # ここで例外を伝播させるとLambdaの再試行で記事生成（Bedrockコスト）から
    # 丸ごとやり直しになるため、失敗しても後続のSSM保存・メール通知は続行する
    # test_modeはprefixを分け、本番の成果物と混ざらないようにする
    s3_url = ""
    if dry_run:
        print("Step 5: [DRY_RUN] S3アップロードをスキップ")
        s3_url = "(dry_run: S3アップロードなし)"
    elif _IS_LAMBDA:
        _t = time.time()
        print("Step 5: S3にアップロード中...")
        try:
            folder_prefix = "zenn-mid-articles-test" if event.get("test_mode") else "zenn-mid-articles"
            s3_folder = f"{timestamp}_{topic['id']}"
            s3_url = upload_to_s3(md_path, png_paths, s3_folder, prefix=folder_prefix)
            print(f"  S3アップロード完了: {s3_url} [{time.time()-_t:.1f}s]")
        except Exception as e:
            print(f"  S3アップロード失敗（無視して続行、記事はローカル/tmpにのみ存在）: {e}")

    # Step 6: SSM 更新
    # test_mode・dry_runでは本番のトピックローテーション状態（除外リスト・周回数）を汚染しないよう
    # 一切書き込まない（過去にtest実行の連打で本番の重複除外が実質機能しなくなっていた）
    if dry_run:
        print("Step 6: [DRY_RUN] SSM更新をスキップ")
    elif event.get("test_mode"):
        print("Step 6: SSM更新をスキップ（test_modeのため本番ローテーション状態は変更しません）")
    else:
        print("Step 6: SSMにトピックを保存中...")
        save_topic_to_ssm(topic["id"], excluded_ids)
        increment_topic_occurrence(topic["id"])

    # Step 7: 記事品質チェック（AWS CLI要素＋機械的な品質ルール、検出のみ）
    _t = time.time()
    print("Step 7: 記事の品質をチェック中...")
    try:
        cfn_issues = validate_cli_in_article(article) + validate_article_quality(article)
        if cfn_issues:
            print(f"  ⚠️ 検証問題: {len(cfn_issues)}件 [{time.time()-_t:.1f}s]")
        else:
            print(f"  ✓ 検証問題なし [{time.time()-_t:.1f}s]")
    except Exception as e:
        print(f"  品質チェックスキップ（無視して続行）: {e}")
        cfn_issues = []

    # Step 8: メール通知
    _t = time.time()
    if dry_run:
        print("Step 8: [DRY_RUN] メール送信をスキップ")
    else:
        print("Step 8: メール通知を送信中...")
        try:
            send_email_notification(
                topic, article, md_path, png_paths, timestamp, s3_url, is_truncated, cfn_issues,
                test_mode=bool(event.get("test_mode")),
            )
            print(f"  メール送信完了 [{time.time()-_t:.1f}s]")
        except Exception as e:
            print(f"  メール送信失敗（無視して続行）: {e}")

    print(f"[{timestamp}] 処理完了 (合計: {time.time()-_total_start:.1f}s)")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "中級記事生成が完了しました" if not dry_run else "中級記事生成が完了しました（dry_run）",
            "topic": topic["name"],
            "topic_id": topic["id"],
            "article_type": topic["article_type"],
            "services": topic["services"],
            "character_count": len(article),
            "png_count": len(png_paths),
            "s3_url": s3_url,
            "timestamp": timestamp,
            "dry_run": dry_run,
        }, ensure_ascii=False),
    }


# ─── ローカル実行エントリーポイント ──────────────────────────────────────────

if __name__ == "__main__":
    # ローカル動作確認はデフォルトでtest_mode（Haiku使用・本番SSM/S3を汚染しない）。
    # 本番同様のSonnet実行を試したい場合のみ環境変数で明示的に無効化する。
    _local_test_mode = os.environ.get("LOCAL_TEST_MODE", "1") != "0"
    result = lambda_handler({"test_mode": _local_test_mode}, None)
    print("\n=== 実行結果 ===")
    print(json.dumps(json.loads(result["body"]), ensure_ascii=False, indent=2))
