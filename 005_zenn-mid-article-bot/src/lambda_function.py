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
cfn = boto3.client("cloudformation", region_name="ap-northeast-1")

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
RECENT_TOPICS_LIMIT = 4

# ─── 中級者向けトピック定義（16記事分 ≒ 8ヶ月分） ────────────────────────────
AWS_TOPICS = [
    # ── 複合アーキテクチャ系 ─────────────────────────────────────────────────
    {
        "id": "serverless_ec",
        "name": "サーバーレスECバックエンド完全構成",
        "article_type": "architecture",
        "services": ["API Gateway", "Lambda", "DynamoDB", "SQS", "SNS"],
        "subtitle": "API Gateway + Lambda + DynamoDB + SQS + SNS で構築する本番級バックエンド",
        "keywords": "サーバーレス, API Gateway, Lambda, DynamoDB, SQS, SNS, 非同期処理, スロットリング, 冪等性",
        "primary_service": "apigateway",
        "secondary_service": "lambda",
        "emoji": "🛒",
    },
    {
        "id": "static_web_hosting",
        "name": "静的Webホスティング最適解",
        "article_type": "architecture",
        "services": ["S3", "CloudFront", "Route 53", "ACM", "WAF"],
        "subtitle": "S3 + CloudFront + Route 53 + ACM + WAF で構築するセキュアな静的サイト",
        "keywords": "静的サイト, CloudFront, S3, Route 53, ACM, WAF, HTTPS, カスタムドメイン, OAC, キャッシュ制御",
        "primary_service": "cloudfront",
        "secondary_service": "s3",
        "emoji": "🌐",
    },
    {
        "id": "container_platform",
        "name": "コンテナアプリ本番運用基盤",
        "article_type": "architecture",
        "services": ["ECS Fargate", "ALB", "ECR", "CloudWatch", "Secrets Manager"],
        "subtitle": "ECS Fargate + ALB + ECR + CloudWatch でコンテナを本番運用する",
        "keywords": "ECS Fargate, ALB, ECR, CloudWatch, Secrets Manager, タスク定義, サービス, ローリングデプロイ, ヘルスチェック",
        "primary_service": "ecs",
        "secondary_service": "ecr",
        "emoji": "🐳",
    },
    {
        "id": "event_driven_pipeline",
        "name": "イベント駆動データ処理パイプライン",
        "article_type": "architecture",
        "services": ["Kinesis Data Streams", "Lambda", "S3", "Athena", "Glue"],
        "subtitle": "Kinesis + Lambda + S3 + Athena でリアルタイムデータを収集・分析する",
        "keywords": "Kinesis, Lambda, S3, Athena, Glue, リアルタイム処理, データパイプライン, パーティション, Parquet, ETL",
        "primary_service": "kinesis",
        "secondary_service": "lambda",
        "emoji": "🌊",
    },
    {
        "id": "microservices_base",
        "name": "マイクロサービス観測性基盤",
        "article_type": "architecture",
        "services": ["API Gateway", "Lambda", "DynamoDB", "SQS", "X-Ray"],
        "subtitle": "API Gateway + Lambda + DynamoDB + SQS + X-Ray で分散トレーシングを実現する",
        "keywords": "マイクロサービス, X-Ray, 分散トレーシング, API Gateway, Lambda, DynamoDB, SQS, サービスマップ, レイテンシ分析",
        "primary_service": "apigateway",
        "secondary_service": "xray",
        "emoji": "🔬",
    },
    {
        "id": "multi_region_dr",
        "name": "マルチリージョンDR構成",
        "article_type": "architecture",
        "services": ["Route 53", "ALB", "EC2", "RDS", "S3 Cross-Region Replication"],
        "subtitle": "Route 53 + ALB + RDS Multi-AZ でRTO/RPOを最小化するDR設計",
        "keywords": "DR, RTO, RPO, Route 53, フェイルオーバー, RDS Multi-AZ, S3レプリケーション, ヘルスチェック, パイロットライト, ウォームスタンバイ",
        "primary_service": "route53",
        "secondary_service": "rds",
        "emoji": "🌍",
    },
    {
        "id": "realtime_notify",
        "name": "リアルタイム通知・アラートシステム",
        "article_type": "architecture",
        "services": ["SNS", "SQS", "Lambda", "SES", "EventBridge"],
        "subtitle": "SNS + SQS + Lambda + EventBridge でスケーラブルな通知基盤を構築する",
        "keywords": "SNS, SQS, Lambda, SES, EventBridge, Pub/Sub, デッドレターキュー, フィルタリングポリシー, メッセージルーティング, 冪等性",
        "primary_service": "sns",
        "secondary_service": "sqs",
        "emoji": "🔔",
    },
    {
        "id": "bedrock_rag",
        "name": "Bedrock RAG アーキテクチャ",
        "article_type": "architecture",
        "services": ["Amazon Bedrock", "S3", "OpenSearch Serverless", "Lambda", "API Gateway"],
        "subtitle": "Bedrock + S3 + OpenSearch Serverless + Lambda でRAGシステムを構築する",
        "keywords": "RAG, Bedrock, Knowledge Base, OpenSearch Serverless, ベクトル検索, エンベディング, LLM, チャンキング, ハイブリッド検索",
        "primary_service": "bedrock",
        "secondary_service": "opensearch",
        "emoji": "🤖",
    },
    # ── ユースケース別ソリューション ────────────────────────────────────────
    {
        "id": "cicd_pipeline",
        "name": "AWS CI/CDパイプライン構築",
        "article_type": "usecase",
        "services": ["CodePipeline", "CodeBuild", "CodeDeploy", "ECR", "ECS"],
        "subtitle": "CodePipeline + CodeBuild + CodeDeploy でコンテナアプリのCI/CDを自動化する",
        "keywords": "CI/CD, CodePipeline, CodeBuild, CodeDeploy, ECR, ECS, Blue/Greenデプロイ, ビルドスペック, パイプラインステージ, 自動テスト",
        "primary_service": "codepipeline",
        "secondary_service": "codebuild",
        "emoji": "🚀",
    },
    {
        "id": "ml_pipeline",
        "name": "機械学習パイプライン自動化",
        "article_type": "usecase",
        "services": ["SageMaker AI", "S3", "Lambda", "Step Functions", "EventBridge"],
        "subtitle": "SageMaker + Step Functions + Lambda で学習〜デプロイを自動化するMLパイプライン",
        "keywords": "SageMaker AI, Step Functions, Lambda, S3, MLOps, モデルレジストリ, バッチ推論, A/Bテスト, ドリフト検知, Pipeline",
        "primary_service": "sagemaker",
        "secondary_service": "step_functions",
        "emoji": "🧠",
    },
    {
        "id": "log_analytics",
        "name": "ログ集約・分析基盤の構築",
        "article_type": "usecase",
        "services": ["CloudTrail", "CloudWatch Logs", "Kinesis Firehose", "S3", "Athena"],
        "subtitle": "CloudTrail + Kinesis Firehose + Athena でAWS全体のログを集約・分析する",
        "keywords": "CloudTrail, CloudWatch Logs, Kinesis Firehose, S3, Athena, ログ集約, セキュリティ監査, SQLクエリ, コスト効率, データカタログ",
        "primary_service": "cloudtrail",
        "secondary_service": "athena",
        "emoji": "🔍",
    },
    {
        "id": "cost_optimization",
        "name": "AWSコスト最適化の実践戦略",
        "article_type": "usecase",
        "services": ["Cost Explorer", "AWS Budgets", "Savings Plans", "Lambda", "CloudWatch"],
        "subtitle": "Cost Explorer + Budgets + Savings Plans + 自動停止Lambdaでコストを30%削減する",
        "keywords": "コスト最適化, Cost Explorer, Budgets, Savings Plans, Reserved Instances, Spot, Lambda自動停止, タグ管理, Cost Allocation, Compute Optimizer",
        "primary_service": "cost_explorer",
        "secondary_service": "budgets",
        "emoji": "💰",
    },
    {
        "id": "security_hardening",
        "name": "AWSセキュリティ強化設計",
        "article_type": "usecase",
        "services": ["AWS WAF", "GuardDuty", "Security Hub", "CloudTrail", "Config"],
        "subtitle": "WAF + GuardDuty + Security Hub + Config で多層防御セキュリティを実現する",
        "keywords": "WAF, GuardDuty, Security Hub, CloudTrail, AWS Config, 多層防御, 脅威検知, コンプライアンス, セキュリティスコア, 自動修復",
        "primary_service": "waf",
        "secondary_service": "guardduty",
        "emoji": "🛡️",
    },
    {
        "id": "backup_dr",
        "name": "バックアップ・DR設計の実践",
        "article_type": "usecase",
        "services": ["AWS Backup", "S3", "RDS", "DynamoDB", "CloudFormation"],
        "subtitle": "AWS Backup + S3 Cross-Region + RDS スナップショットで障害に強い設計を実現する",
        "keywords": "AWS Backup, S3 Cross-Region Replication, RDS スナップショット, DynamoDB PITRバックアップ, RTO, RPO, CloudFormation, 復元テスト, バックアップポリシー",
        "primary_service": "backup",
        "secondary_service": "rds",
        "emoji": "💾",
    },
    {
        "id": "multi_account",
        "name": "マルチアカウント管理の実践",
        "article_type": "usecase",
        "services": ["AWS Organizations", "Control Tower", "Service Catalog", "IAM Identity Center", "CloudFormation StackSets"],
        "subtitle": "Organizations + Control Tower + IAM Identity Center でセキュアなマルチアカウント環境を構築する",
        "keywords": "AWS Organizations, Control Tower, Service Catalog, IAM Identity Center, SCP, ガードレール, ランディングゾーン, アカウントファクトリー, OU設計",
        "primary_service": "organizations",
        "secondary_service": "control_tower",
        "emoji": "🏢",
    },
    {
        "id": "data_lake",
        "name": "データレイク構築の実践",
        "article_type": "usecase",
        "services": ["S3", "AWS Glue", "Athena", "Lake Formation", "QuickSight"],
        "subtitle": "S3 + Glue + Athena + Lake Formation + QuickSight でデータレイクを構築してBIまで繋げる",
        "keywords": "データレイク, S3, Glue, Athena, Lake Formation, QuickSight, データカタログ, ETL, パーティショニング, データガバナンス, 列指向フォーマット",
        "primary_service": "glue",
        "secondary_service": "athena",
        "emoji": "🏞️",
    },
]

# ─── AWS公式ドキュメント URL マップ（primary_service キー） ───────────────────
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
    "waf":           "https://docs.aws.amazon.com/ja_jp/waf/latest/developerguide/what-is-aws-waf.html",
    "backup":        "https://docs.aws.amazon.com/ja_jp/aws-backup/latest/devguide/whatisbackup.html",
    "organizations": "https://docs.aws.amazon.com/ja_jp/organizations/latest/userguide/orgs_introduction.html",
    "xray":          "https://docs.aws.amazon.com/ja_jp/xray/latest/devguide/aws-xray.html",
    "rds":           "https://docs.aws.amazon.com/ja_jp/AmazonRDS/latest/UserGuide/Welcome.html",
    "glue":          "https://docs.aws.amazon.com/ja_jp/glue/latest/dg/what-is-glue.html",
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
    "security_hardening":{"emoji": "🛡️","topics": ["aws", "セキュリティ", "guardduty", "waf"]},
    "backup_dr":        {"emoji": "💾", "topics": ["aws", "backup", "dr", "可用性"]},
    "multi_account":    {"emoji": "🏢", "topics": ["aws", "organizations", "マルチアカウント", "ガバナンス"]},
    "data_lake":        {"emoji": "🏞️", "topics": ["aws", "datalake", "glue", "athena"]},
}

ARTICLE_PROMPT_TEMPLATE = """
あなたはZennで多くの「いいね」を獲得している技術ライターです。
「読んでよかった」と思わせるアーキテクチャ解説記事を書いてください。
テンプレートを埋める作業ではなく、設計判断の背景まで伝える記事です。

## テーマ
{topic_name}：{topic_subtitle}

## 使用するAWSサービス（すべて記事中で扱うこと）
{services}

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

```yaml:cloudformation.yaml
Resources:
  MyFunction:
    Type: AWS::Lambda::Function
```

```bash:動作確認
aws cloudformation describe-stacks --stack-name my-stack
```

---

## 記事の見出し構成（この順序を基本とする）

アーキテクチャ解説記事として自然な流れを保つため、以下の順序を基本とする。
テーマの特性に応じてセクションの統合・分割・改題は自由。

### ## はじめに
- **冒頭の1〜2文で「誰が・どんな課題を持っているか」を具体的に描く**
  - 課題から入る例:「オーダー急増でAPIが落ちた経験はありませんか？{topic_name}を使うと〜」
  - ニーズから入る例:「{topic_name}が必要になるのは、〜というシナリオが多いです」
  - 「この記事では〜を解説します」という宣言は使わない
- この記事で「何が作れるようになるか・何を判断できるようになるか」を1〜2文で示す
- 対象読者と前提知識（箇条書き可）

### ## アーキテクチャ概要

**`{{DIAGRAM_1}}` マーカーの配置ルール（必ず守ること）**
- マーカーは `## アーキテクチャ概要` セクションの本文中にのみ置く。他のセクション・見出し直後には置かない。
- 直前（1文）: このアーキテクチャで何が実現できるかを一言で示す予告文を書く（毎回違う切り口で）
  - 良い例: 「{topic_name}の全体像を先に把握しておくと、以降の設計判断が理解しやすくなります。」
  - 良い例: 「以下の構成図に、{services}の接続関係と主なデータの流れをまとめました。」
  - 禁止: 「以下が全体構成図です。」のような内容のない定型文
- 直後（1〜2文）: 図から読み取れる最重要ポイントを具体的に補足する

構成:
1. この構成が解決する課題と解決策の概要を段落で書く
2. 予告文（1文）を書く
3. 単独行で `{{DIAGRAM_1}}` を挿入（前後に空行必須）
4. 図の補足説明（1〜2文）
5. 各サービスが担う役割を1〜2行で箇条書き
6. データ・リクエストの流れを番号付きで説明

### ## 各コンポーネントの選定理由
- なぜこのサービスの組み合わせを選んだか（代替案との比較をテーブルで）
- 各サービスが解決する課題を「課題 → 解決策 → 採用理由」の形で書く
- `:::message` で「設計のポイント」を強調する

### ## 構成手順
- **前提条件**: 必要なツール・権限（AWSアカウント、AWS CLI等）
- **ステップ1〜5以上**: CloudFormationスニペットを中心に手順を説明
  - コードは `yaml:cloudformation.yaml` 形式で記述する（SAMは使わない）
  - 各ステップのつまずきポイントを `:::message` で注記する
  - AWS CLIコマンドはファイル名付きコードブロックで記述し、**成功時のレスポンス例を必ず示す**
- **デプロイ・動作確認**: 実際に動かして確認する手順

### ## 設計上の考慮ポイント

**`{{DIAGRAM_2}}` マーカーの配置ルール（必ず守ること）**
- マーカーは `## 設計上の考慮ポイント` セクションの本文中にのみ置く。他のセクションには置かない。
- 直前（1文）: 図2が示している観点（コスト・セキュリティ・スケーラビリティのどれか）に言及する文を書く（毎回違う切り口で）
  - 良い例: 「以下の図は、{services}間のデータフローとコスト最適化ポイントを示しています。」
  - 良い例: 「{topic_name}における処理の詳細フローを図示します。各レイヤーでの変換・制御の流れを確認してください。」
  - 禁止: 「以下の図を参照してください。」のような内容のない定型文
- 直後（1〜2文）: 図に描かれた特定のフローや設計上の工夫を具体的に指摘し、以降の解説への橋渡しをする

構成:
1. このセクション全体の視点を1文で紹介
2. 予告文（1文）を書く
3. 単独行で `{{DIAGRAM_2}}` を挿入（前後に空行必須）
4. 図の補足説明と以降の解説への橋渡し（1〜2文）
5. コスト・セキュリティ・スケーラビリティの3観点を解説:
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

### ## まとめ
- **「次に何をすべきか・どう発展させるか」を中心に書く**（学んだことの箇条書き再掲は避ける）
- このアーキテクチャが本領を発揮するシナリオと、逆に向いていないシナリオ
- 発展として学ぶべき次のトピック（関連サービス・設計パターン）

### ## 参考
- AWS公式ドキュメントへの参照（URLは書かず「AWS公式ドキュメント: サービス名」形式）

---

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |

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

## CloudFormation・IAM・コード品質の必須ルール

### IAM ポリシー（間違えやすい点）
- `ec2:DescribeInstances` / `s3:ListBuckets` / `cloudwatch:GetMetricData` などリスト・Describe系アクションは**リソースレベル条件（`ec2:ResourceTag` 等）を非サポート**。これらは `Resource: '*'` のみで単独ステートメントに書く
- リソースタグ条件（`ec2:ResourceTag/Environment: dev` 等）は `StopInstances` / `PutObject` などリソースレベル権限に対応したアクションのみに付与する
- 同一ステートメントにリソース条件対応・非対応のアクションを混在させない（条件が正しく評価されない）

### Lambda Runtime
- Lambda の Runtime は現時点の最新安定版を使う: `python3.13`（Python）/ `nodejs22.x`（Node.js）
- `python3.12` や `nodejs20.x` 等の旧バージョンは使わない

### CloudFormation の正確性
- 記事内の CFn テンプレートは**実際にデプロイできる完全なリソース定義**を書く
- `!Ref` / `!GetAtt` の参照先が同じテンプレート内に存在することを確認する
- SNS → Lambda トリガーには `AWS::Lambda::Permission`（Principal: sns.amazonaws.com）が必須
- 80%通知と100%通知で**アクションが異なる場合は SNS トピックを別々に作成する**（同一トピックに Lambda 購読を紐付けると全閾値でLambdaが発動する）
- SNS メール購読（`Protocol: email`）はデプロイ後に**確認メールのクリックが必要**な旨を記事内で明記する

### AWS サービスの制約（よく見落とされる事実）
- **Compute Optimizer**: メモリ使用率の分析には **CloudWatch Agent の別途インストールが必要**。Agent なしでは CPU・ネットワーク・ディスクのみ分析対象になる
- **AWS Budgets のデータ反映**: コストデータが Budgets に反映されるまで**最大24時間**かかる場合がある。「リアルタイム検知」は不可
- **Cost Explorer API コスト**: `GetCostAndUsage` 等のAPI呼び出しは**1リクエストあたり$0.01**の費用が発生する（コンソール閲覧は無料）
- **Savings Plans キャンセル不可**: 購入後のキャンセルは不可。推奨額の80〜90%からスタートする旨を必ず記載する
- サービスの制約・注意点は「できること」と同等の重みで記載する
"""


# ─── AWS公式ドキュメント取得 ──────────────────────────────────────────────────

def fetch_aws_docs(service_id: str, max_chars: int = 6000) -> str:
    """AWS公式ドキュメントを取得してプレーンテキストを返す。失敗時は空文字列。"""
    import re
    import urllib.request

    url = DOCS_URL_MAP.get(service_id, "")
    if not url:
        print(f"[Docs] {service_id}: URL未定義のためスキップ")
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

def select_topic_with_bedrock(excluded_ids: list[str], model_id: str) -> dict:
    """Bedrock を使って重複を避けながらトピックを選択する"""
    available = [t for t in AWS_TOPICS if t["id"] not in excluded_ids]
    if not available:
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS

    topic_list = "\n".join([f"- {t['id']}: {t['name']} ({t['article_type']})" for t in available])

    prompt = f"""以下のAWSアーキテクチャ・ソリューション一覧から、今月の記事テーマを1つランダムに選んでください。
architectureとusecaseが交互になるように選ぶと良いですが、純粋にランダムでも構いません。

{topic_list}

選んだトピックのIDのみを返してください（例: serverless_ec）。説明は不要です。"""

    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result   = json.loads(response["body"].read())
    topic_id = result["content"][0]["text"].strip().lower()
    usage = result.get("usage", {})
    print(f"[Bedrock/topic] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}")

    for topic in available:
        if topic["id"] == topic_id:
            return topic

    return random.choice(available)


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict, today: str, model_id: str) -> tuple[str, bool]:
    """Bedrock を使って記事を生成する。(article_text, is_truncated) を返す"""
    docs_content = fetch_aws_docs(topic.get("primary_service", ""))
    docs_section = (
        "## AWS公式ドキュメント（根拠情報）\n"
        "以下はAWS公式ドキュメントから取得した情報です。技術的事実はこの内容を根拠として正確に記述し、矛盾しないようにしてください。\n"
        "ドキュメントに記載のない事実は、確実に知っている場合のみ記述し、不確かな場合は記述しないか「〜の場合があります」等の不確定表現を使ってください。\n\n"
        f"{docs_content}\n\n---\n"
        if docs_content else ""
    )
    services_str = "、".join(topic["services"])
    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        services=services_str,
        keywords=topic["keywords"],
        today=today,
        docs_section=docs_section,
    )

    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 24000,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    usage = result.get("usage", {})
    stop_reason = result.get("stop_reason", "unknown")
    is_truncated = stop_reason == "max_tokens"
    print(f"[Bedrock/article] in={usage.get('input_tokens',0)}, out={usage.get('output_tokens',0)}, stop={stop_reason}")
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
    "{topic_name} – 全体アーキテクチャ構成図",
    "{topic_name} – データフロー・詳細構成図",
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
        return article

    # フォールバック用: 見出し名で挿入位置を探す順序
    _FALLBACK_HEADINGS = ["アーキテクチャ概要", "設計上の考慮ポイント"]

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
            target_heading = _FALLBACK_HEADINGS[img_idx] if img_idx < len(_FALLBACK_HEADINGS) else None
            h2_positions = [i for i, line in enumerate(lines) if line.startswith("## ")]
            if not h2_positions:
                continue  # 見出しが1つもない場合は挿入をスキップ

            if target_heading:
                matched = [i for i, line in enumerate(lines)
                           if line.startswith("## ") and target_heading in line]
                insert_idx = matched[0] if matched else h2_positions[min(img_idx + 1, len(h2_positions) - 1)]
            else:
                insert_idx = h2_positions[min(img_idx + 1, len(h2_positions) - 1)]

            lines.insert(insert_idx + 1, placeholder)
            result = "\n".join(lines)

    return result


def _next_article_number(output_dir: str) -> str:
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

    # 構成図を生成（2枚）
    png_paths = generate_diagrams(topic["id"], png_base)

    # 図1・図2ともに {{DIAGRAM_N}} マーカーで記事中に挿入（マーカー不在時はフォールバック）
    article_with_images = _embed_image_placeholders(article, png_paths, topic["name"])

    # Zennフロントマター用メタ情報
    meta = _ZENN_META.get(topic["id"], {"emoji": "☁️", "topics": ["aws", "architecture"]})
    topics_json = json.dumps(meta["topics"], ensure_ascii=False)

    full_content = f"""---
title: "{topic['name']}：{topic['subtitle']}"
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


# ─── CFn テンプレート検証 ────────────────────────────────────────────────────

def validate_cfn_in_article(article_text: str) -> list[str]:
    """記事内の完全なCFnテンプレートをcloudformation:ValidateTemplateでチェックする"""
    import re
    import yaml as _yaml

    # !Ref / !Sub / !GetAtt 等のCFnタグをsafe_loadで扱えるようにするローダー
    class _CfnLoader(_yaml.SafeLoader):
        pass
    _CfnLoader.add_multi_constructor(
        '!',
        lambda loader, tag, node: (
            loader.construct_scalar(node) if isinstance(node, _yaml.ScalarNode)
            else loader.construct_sequence(node, deep=True) if isinstance(node, _yaml.SequenceNode)
            else loader.construct_mapping(node, deep=True)
        ),
    )

    issues = []
    pattern = r'```(?:yaml|YAML)(?::[^\n]*)?\n(.*?)```'
    blocks = re.findall(pattern, article_text, re.DOTALL)

    complete = []
    for i, block in enumerate(blocks, 1):
        if 'Resources:' not in block:
            continue
        try:
            parsed = _yaml.load(block, Loader=_CfnLoader)
            if isinstance(parsed, dict) and 'Resources' in parsed:
                complete.append((i, block))
        except _yaml.YAMLError as e:
            issues.append(f"ブロック{i}: YAML構文エラー — {str(e)[:200]}")

    if not complete and not issues:
        return []

    for i, block in complete:
        try:
            cfn.validate_template(TemplateBody=block)
        except Exception as e:
            msg = getattr(e, 'response', {}).get('Error', {}).get('Message', str(e))
            issues.append(f"ブロック{i}: {str(msg)[:300]}")

    print(f"[CFn検証] 完全テンプレート{len(complete)}件検証 / 問題{len(issues)}件")
    return issues


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, s3_url: str = "", is_truncated: bool = False,
    cfn_issues: list | None = None,
):
    """SES でメール通知を送信する"""
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    services_str = " + ".join(topic["services"])
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    subject = (
        f"【⚠️ 記事が途中で切れています】{topic['name']} - {timestamp}"
        if is_truncated else
        f"【Zenn中級記事生成完了】{topic['name']} - {timestamp}"
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
        '<code>bash ~/Zer0/005_Zenn_Mid_Article_Bot/download_article.sh</code></li>'
        if s3_url else ""
    )

    cfn_issues = cfn_issues or []
    truncation_warning_text = """
⚠️ 警告: 記事が途中で切れています
記事の生成がmax_tokensに達したため、末尾が不完全な可能性があります。
Zennに投稿する前に内容を必ず確認してください。
""" if is_truncated else ""

    cfn_warning_text = (
        "⚠️ CFnテンプレート検証で問題が見つかりました:\n"
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

■ 記事プレビュー（先頭300文字）
{preview}...

■ 次のアクション
1. bash ~/Zer0/005_Zenn_Mid_Article_Bot/download_article.sh
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
        '<h3 style="color:#c53030;margin-top:0;">⚠️ CFnテンプレート検証で問題が見つかりました</h3>'
        '<ul style="color:#c53030;margin:0;">'
        + "".join(f'<li><code>{i}</code></li>' for i in cfn_issues)
        + '</ul></div>'
    ) if cfn_issues else (
        '<div style="background:#e8f5e9;border:1px solid #66bb6a;padding:10px 15px;border-radius:8px;margin:20px 0;">'
        '<p style="color:#2e7d32;margin:0;">✅ CFnテンプレート検証 — 問題なし</p>'
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
      <li>:::message ブロック内の指示に従ってPNGをアップロード・差し替え</li>
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
    print(f"メール送信完了: {subject}")


# ─── Lambda ハンドラ ──────────────────────────────────────────────────────────

HAIKU_MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"

def lambda_handler(event, context):
    model_id = HAIKU_MODEL_ID if event.get("test_mode") else BEDROCK_MODEL_ID
    if event.get("test_mode"):
        print(f"[TEST MODE] モデルをHaikuに切り替えました: {model_id}")

    now       = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    today     = now.strftime("%Y-%m-%d")
    print(f"[{timestamp}] Zenn中級記事自動生成を開始します")

    # Step 1: 直近トピック取得
    print("Step 1: 直近トピックをSSMから取得中...")
    excluded_ids = get_recent_topics()
    print(f"  除外トピック: {excluded_ids}")

    # Step 2: トピック選択
    print("Step 2: Bedrockでトピックを選択中...")
    topic = select_topic_with_bedrock(excluded_ids, model_id)
    print(f"  選択されたトピック: {topic['name']} ({topic['id']})")
    print(f"  記事タイプ: {topic['article_type']}")
    print(f"  使用サービス: {', '.join(topic['services'])}")

    # Step 3: 記事生成
    print("Step 3: 記事を生成中（6,000〜8,000文字）...")
    article, is_truncated = generate_article(topic, today, model_id)
    print(f"  記事生成完了: {len(article):,}文字")

    # Step 4: ローカル保存 + 構成図生成
    print("Step 4: ローカルに保存中（記事MD + 構成図PNG）...")
    md_path, png_paths = save_to_local(topic, article, timestamp)
    print(f"  MD保存完了: {md_path}")
    print(f"  PNG生成完了: {len(png_paths)}枚")

    # Step 5: S3 アップロード（Lambda環境のみ）
    s3_url = ""
    if _IS_LAMBDA:
        print("Step 5: S3にアップロード中...")
        s3_folder = f"{timestamp}_{topic['id']}"
        s3_url = upload_to_s3(md_path, png_paths, s3_folder)
        print(f"  S3アップロード完了: {s3_url}")

    # Step 6: SSM 更新
    print("Step 6: SSMにトピックを保存中...")
    save_topic_to_ssm(topic["id"])

    # Step 7: CFnテンプレート検証
    print("Step 7: CFnテンプレートを検証中...")
    try:
        cfn_issues = validate_cfn_in_article(article)
        if cfn_issues:
            print(f"  ⚠️ CFn問題検出: {len(cfn_issues)}件")
        else:
            print("  ✓ CFn検証問題なし")
    except Exception as e:
        print(f"  CFn検証スキップ（無視して続行）: {e}")
        cfn_issues = []

    # Step 8: メール通知
    print("Step 8: メール通知を送信中...")
    try:
        send_email_notification(topic, article, md_path, png_paths, timestamp, s3_url, is_truncated, cfn_issues)
    except Exception as e:
        print(f"  メール送信失敗（無視して続行）: {e}")

    print(f"[{timestamp}] 処理が正常に完了しました")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "中級記事生成が完了しました",
            "topic": topic["name"],
            "topic_id": topic["id"],
            "article_type": topic["article_type"],
            "services": topic["services"],
            "character_count": len(article),
            "png_count": len(png_paths),
            "s3_url": s3_url,
            "timestamp": timestamp,
        }, ensure_ascii=False),
    }


# ─── ローカル実行エントリーポイント ──────────────────────────────────────────

if __name__ == "__main__":
    result = lambda_handler({}, None)
    print("\n=== 実行結果 ===")
    print(json.dumps(json.loads(result["body"]), ensure_ascii=False, indent=2))
