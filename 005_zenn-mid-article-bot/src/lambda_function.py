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
BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-sonnet-4-6")
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    "/tmp/zenn_mid_articles" if _IS_LAMBDA
    else os.path.expanduser("~/Zer0/005_Zenn_Mid_Article_Bot/output"),
)
S3_BUCKET  = "zer0-dev-s3"
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
あなたはZennの技術記事を執筆するプロのテクニカルライターです。
以下の条件に従って、AWSの中級者向けの高品質な技術記事を日本語で作成してください。

## テーマ
{topic_name}：{topic_subtitle}

## 使用するAWSサービス（すべて記事中で扱うこと）
{services}

## キーワード（記事中に自然に含めること）
{keywords}

## 記事の要件
- **文字数**: 4,000〜6,000文字（本文のみ、見出しを除く）
- **対象読者**: AWSの基本サービスを使ったことがある中級者（EC2/S3/IAMは理解済み。複数サービスの組み合わせを学びたい人）
- **トーン**: 実践的・技術的。「なぜそのサービスを選んだか」の設計理由を重視する
- **価値**: 読者が読み終えたら、CloudFormation/SAMのテンプレートを参考に自分の環境で試せるレベル

## Zenn Markdown記法の積極活用（必須）

### テーブル
サービス比較・料金・設定オプションには必ずMarkdownテーブルを使う。

### メッセージボックス
- 重要な設計判断ポイントは `:::message` で囲む（前後に空行必須）
- コスト注意・セキュリティ警告は `:::message alert` を使う

使用例:
:::message
ここに重要な設計ポイントを書く
:::

:::message alert
ここにコスト・セキュリティの注意事項を書く
:::

### アコーディオン
本番環境向けの応用設定・トラブルシューティングは `:::details タイトル` でまとめる（前後に空行必須）。

使用例:
:::details 本番環境向けの追加設定
補足内容
:::

### コードブロック
言語またはファイル名を必ず指定する。CloudFormation/SAMのコードは `yaml:template.yaml` 形式で書く。

使用例:
```yaml:template.yaml
Resources:
  MyFunction:
    Type: AWS::Serverless::Function
```

```bash:動作確認
aws cloudformation describe-stacks --stack-name my-stack
```

## 必須の見出し構成（この順序で書くこと）

### ## はじめに（200〜300文字）
- この構成が解決する課題・ビジネス上のニーズ
- この記事で学べることの概要
- 対象読者と前提知識

### ## アーキテクチャ概要（500〜700文字）

**【重要】`{{DIAGRAM_1}}` マーカーの配置ルール（必ず守ること）**
- マーカーは `## アーキテクチャ概要` セクションの本文中にのみ置くこと。記事の先頭・他のセクション・見出し直後には絶対に置かない。
- マーカーの直前（1文）：このアーキテクチャ全体で何が実現できるかを一言で示す予告文を書く。
  - 良い例：「{topic_name}の全体構成を図示します。{services}がどのように連携するかを確認してください。」
  - 良い例：「以下の構成図に、{services}の接続関係と主なデータの流れをまとめました。」
  - 悪い例（禁止）：「以下が全体構成図です。」のような内容のない定型文
- マーカーの直後（1〜2文）：図から読み取れる最重要ポイントを具体的に補足する。どのサービスがどこに配置され、どう連携するかを図に言及しながら説明すること。

構成：
1. 全体像を説明する段落（課題と解決策の概要）を書く
2. 予告文（1文）を書く
3. 単独行で `{{DIAGRAM_1}}` を挿入
4. 図の補足説明（1〜2文）を書く
5. 各サービスが担う役割を1〜2行で箇条書き
6. データ・リクエストの流れを番号付きで説明

### ## 各コンポーネントの選定理由（600〜900文字）
- なぜこのサービスの組み合わせを選んだか（代替案との比較をテーブルで）
- 各サービスが解決する課題を「課題→解決策→採用理由」の形で書く
- `:::message` で「設計のポイント」を強調する

### ## 構成手順（1,500〜2,500文字）
- **前提条件**: 必要なツール・権限（AWSアカウント、AWS CLI、SAM CLI等）
- **ステップ1〜5以上**: IaCコードを中心に手順を説明
  - 重要なCloudFormation/SAMスニペットを `yaml:template.yaml` コードブロックで示す
  - 各ステップのハマりどころを `:::message` で注記する
  - AWS CLIコマンドはファイル名付きコードブロックで記述し、成功時のレスポンス例を必ず示す
- **デプロイ・動作確認**: 実際に動かして確認する手順

### ## 設計上の考慮ポイント（700〜1,000文字）

**【重要】`{{DIAGRAM_2}}` マーカーの配置ルール（必ず守ること）**
- マーカーは `## 設計上の考慮ポイント` セクションの本文中にのみ置くこと。他のセクションには絶対に置かない。
- マーカーの直前（1文）：このセクションで解説するコスト・セキュリティ・スケーラビリティのうち、図2が最も直接的に示している観点に言及する文を書く。
  - 良い例：「以下の図は、{services}間のデータフローとコスト最適化ポイントを示しています。」
  - 良い例：「{topic_name}における処理の詳細フローを図示します。各レイヤーでの変換・制御の流れを確認してください。」
  - 悪い例（禁止）：「以下の図を参照してください。」のような内容のない定型文
- マーカーの直後（1〜2文）：図2に描かれた特定のフローや設計上の工夫を具体的に指摘し、以降のコスト・セキュリティ・スケーラビリティ解説への橋渡しをする。

構成：
1. このセクション全体の視点（コスト・セキュリティ・スケーラビリティ）を1文で紹介
2. 予告文（1文）を書く
3. 単独行で `{{DIAGRAM_2}}` を挿入
4. 図の補足説明と以降の解説への橋渡し（1〜2文）
5. コスト・セキュリティ・スケーラビリティの3観点を解説

コスト・セキュリティ・スケーラビリティの3つの観点でそれぞれ解説する：
- **コスト最適化**: 各サービスの料金構造と削減テクニック
- **セキュリティ**: IAMポリシー最小権限・暗号化・ネットワーク分離の具体的な設定
- **スケーラビリティ**: 高負荷時の挙動とボトルネック対策

:::message alert
コストが予想外に膨らみやすいポイントと回避策を必ず明記する
:::

### ## 月額コスト目安（300〜500文字）
- 小規模・中規模・大規模の3パターンをテーブルで比較
- 各サービスのコスト内訳（リクエスト数・ストレージ・データ転送）
- コスト削減のための設定（無料枠・Savings Plans・Reserved等）
- 「最新情報はAWS公式の料金ページで確認してください」と注記する

### ## まとめ（300〜400文字）
- 今回構築したアーキテクチャの要点をテーブルで整理
- このアーキテクチャの適用シナリオ
- 発展として学ぶべき次のトピック（関連サービス・パターン）

### ## 参考リンク
- AWS公式ドキュメントへの参照（URLは書かず「AWS公式ドキュメント: サービス名」形式）
- Udemyコースの紹介：「このアーキテクチャをさらに深く学ぶには、Udemyの「**AWS：ゼロから実践するAmazon Web Services。手を動かしながらインフラの基礎を習得**」コースがおすすめです。」

## AWSサービス名の最新化（必須）

記事内では**必ず現在の正式名称**を使うこと。

### 主な改名・リブランド済みサービス（2025年時点）

| 現在の正式名称 | 旧称 | 改名時期 |
| --- | --- | --- |
| Amazon SageMaker AI | Amazon SageMaker | 2024年11月 |
| Amazon Q Business | Amazon Kendra Intelligent Ranking（一部機能） | 2024年 |

## 注意事項
- **記事の先頭にYAML frontmatter（--- で囲まれたブロック）を書かない**（frontmatterはシステムが自動付与する）
- 見出しは ## や ### を使ったMarkdown形式で書く（# は使わない）
- コードやコマンドはバッククォート3つで囲み、言語名またはファイル名を指定する
- 重要な用語は**太字**で強調する
- AWSコンソールの操作は具体的なメニュー名やボタン名を明記する
- 料金は2026年時点の情報を参考にし、「最新情報はAWS公式サイトで確認してください」と注記する
- curlコマンドやCLI実行結果は、**成功時のレスポンス例を必ずコードブロックで示す**
- `:::message` や `:::details` は前後に必ず空行を入れること
- コードブロック内のサンプル日付・タイムスタンプは **本日の日付（{today}）** を基準にすること。`2024`や`2023`など過去の年は絶対に使わない
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
        print("全トピックが除外済みのためリセットします")
        available = AWS_TOPICS

    topic_list = "\n".join([f"- {t['id']}: {t['name']} ({t['article_type']})" for t in available])

    prompt = f"""以下のAWSアーキテクチャ・ソリューション一覧から、今月の記事テーマを1つランダムに選んでください。
architectureとusecaseが交互になるように選ぶと良いですが、純粋にランダムでも構いません。

{topic_list}

選んだトピックのIDのみを返してください（例: serverless_ec）。説明は不要です。"""

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
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

    for topic in available:
        if topic["id"] == topic_id:
            return topic

    return random.choice(available)


# ─── 記事生成 ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict, today: str) -> str:
    """Bedrock を使って記事を生成する"""
    services_str = "、".join(topic["services"])
    prompt = ARTICLE_PROMPT_TEMPLATE.format(
        topic_name=topic["name"],
        topic_subtitle=topic["subtitle"],
        services=services_str,
        keywords=topic["keywords"],
        today=today,
    )

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 7000,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    # Bedrock が記事冒頭に YAML frontmatter を付けることがあるため除去する
    if text.lstrip().startswith("---"):
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


# ─── SES メール通知 ───────────────────────────────────────────────────────────

def send_email_notification(
    topic: dict, article: str, md_path: str, png_paths: list[str],
    timestamp: str, s3_url: str = "",
):
    """SES でメール通知を送信する"""
    char_count = len(article)
    preview    = article[:300].replace("\n", " ")
    services_str = " + ".join(topic["services"])
    diagram_info = ", ".join(os.path.basename(p) for p in png_paths) if png_paths else "生成なし"

    subject = f"【Zenn中級記事生成完了】{topic['name']} - {timestamp}"

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

    body_text = f"""Zenn中級記事の自動生成が完了しました。

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

    body_html = f"""
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#3EA8FF;">Zenn中級記事の自動生成が完了しました</h2>

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
    global BEDROCK_MODEL_ID
    if event.get("test_mode"):
        BEDROCK_MODEL_ID = HAIKU_MODEL_ID
        print(f"[TEST MODE] モデルをHaikuに切り替えました: {HAIKU_MODEL_ID}")

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
    topic = select_topic_with_bedrock(excluded_ids)
    print(f"  選択されたトピック: {topic['name']} ({topic['id']})")
    print(f"  記事タイプ: {topic['article_type']}")
    print(f"  使用サービス: {', '.join(topic['services'])}")

    # Step 3: 記事生成
    print("Step 3: 記事を生成中（4,000〜6,000文字）...")
    article = generate_article(topic, today)
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

    # Step 7: メール通知
    print("Step 7: メール通知を送信中...")
    try:
        send_email_notification(topic, article, md_path, png_paths, timestamp, s3_url)
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
